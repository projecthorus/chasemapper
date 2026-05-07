"""
Backend proxy for Maryland parcel queries (point + radius).

Validates inputs, paginates the MD geodata API, and returns a GeoJSON
FeatureCollection. Hard-caps radius at 1.0 mile for public-facing safety.
"""

import logging
import math

import requests


PARCEL_URL = (
    "https://geodata.md.gov/imap/rest/services/PlanningCadastre/"
    "MD_ParcelBoundaries/MapServer/0/query"
)
REQUEST_TIMEOUT = 30
PAGE_SIZE = 1000
RADIUS_MAX_MI = 1.0
RADIUS_MIN_MI = 0.05

MD_BBOX = {"lat_min": 37.88, "lat_max": 39.73, "lon_min": -79.49, "lon_max": -75.05}

_METERS_PER_MILE = 1609.344


def _empty_fc(error=None):
    fc = {"type": "FeatureCollection", "features": []}
    if error:
        fc["error"] = error
    return fc


def _bbox_meters(lat, lon, radius_meters):
    """Crude lat/lon delta around a point. Good enough for <=1 mile envelopes."""
    deg_lat = radius_meters / 111_320.0
    deg_lon = radius_meters / (111_320.0 * max(math.cos(math.radians(lat)), 0.01))
    return {
        "lat_min": lat - deg_lat,
        "lat_max": lat + deg_lat,
        "lon_min": lon - deg_lon,
        "lon_max": lon + deg_lon,
    }


def get_parcels_near(lat, lon, radius_miles, max_pages=5):
    """Fetch MD parcels within radius_miles of (lat, lon).

    Returns a GeoJSON FeatureCollection. Sets ``_truncated = True`` if pagination
    cap was hit. Returns an empty FeatureCollection with ``error`` set on
    validation or fetch failure.
    """
    try:
        lat = float(lat)
        lon = float(lon)
        radius_miles = float(radius_miles)
    except (TypeError, ValueError):
        return _empty_fc("lat/lon/radius must be numeric")

    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return _empty_fc("lat/lon out of range")
    if not (RADIUS_MIN_MI <= radius_miles <= RADIUS_MAX_MI):
        return _empty_fc(
            "radius must be between {} and {} miles".format(RADIUS_MIN_MI, RADIUS_MAX_MI)
        )

    if not (
        MD_BBOX["lat_min"] <= lat <= MD_BBOX["lat_max"]
        and MD_BBOX["lon_min"] <= lon <= MD_BBOX["lon_max"]
    ):
        return _empty_fc("Landing point is outside MD coverage.")

    radius_meters = radius_miles * _METERS_PER_MILE
    bbox = _bbox_meters(lat, lon, radius_meters)
    geometry = "{},{},{},{}".format(
        bbox["lon_min"], bbox["lat_min"], bbox["lon_max"], bbox["lat_max"]
    )

    features = []
    truncated = False
    for page in range(max_pages):
        params = {
            "where": "1=1",
            "geometry": geometry,
            "geometryType": "esriGeometryEnvelope",
            "spatialRel": "esriSpatialRelIntersects",
            "inSR": "4326",
            "outSR": "4326",
            "outFields": "OWNNAME1,PREMISEADD,ACCTID",
            "returnGeometry": "true",
            "f": "geojson",
            "resultRecordCount": PAGE_SIZE,
            "resultOffset": page * PAGE_SIZE,
        }
        try:
            r = requests.get(PARCEL_URL, params=params, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            logging.warning("Parcel proxy: fetch failed (page %d): %s", page, e)
            return _empty_fc("upstream parcel API error")

        page_feats = data.get("features", []) or []
        features.extend(page_feats)

        exceeded = bool(data.get("exceededTransferLimit") or data.get("properties", {}).get("exceededTransferLimit"))
        if len(page_feats) < PAGE_SIZE and not exceeded:
            break
        if page == max_pages - 1 and (len(page_feats) == PAGE_SIZE or exceeded):
            truncated = True

    fc = {"type": "FeatureCollection", "features": features}
    if truncated:
        fc["_truncated"] = True
    return fc
