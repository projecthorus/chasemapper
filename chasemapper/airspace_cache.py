"""
Server-side cache for FAA airspace + TFR overlays.

Fetches Class B/C/D/E, Special Use Airspace, and TFRs from FAA endpoints,
filters to a regional bounding box (MD/PA/DE/VA/WV), persists to disk, and
serves cached GeoJSON to the chasemapper frontend. Background threads refresh
the cache (12h for airspace, 15min for TFRs).
"""

import json
import logging
import os
import threading
import time

import requests


REGION_BBOX = {"lat_min": 36.5, "lat_max": 42.5, "lon_min": -83.7, "lon_max": -74.6}
AIRSPACE_REFRESH_SEC = 12 * 60 * 60
TFR_REFRESH_SEC = 15 * 60
CACHE_DIR = os.path.join("cache", "airspace")
REQUEST_TIMEOUT = 30

STALE_THRESHOLD_SEC = {
    "class_b": 24 * 60 * 60,
    "class_c": 24 * 60 * 60,
    "class_d": 24 * 60 * 60,
    "class_e": 24 * 60 * 60,
    "sua": 24 * 60 * 60,
    "tfr": 60 * 60,
}

_CLASS_AIRSPACE_URL = (
    "https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/arcgis/rest/services/"
    "Class_Airspace/FeatureServer/0/query"
)
_SUA_URL = (
    "https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/arcgis/rest/services/"
    "Special_Use_Airspace/FeatureServer/0/query"
)
_TFR_URL = "https://tfr.faa.gov/tfrapi/exportTfrList"

LAYERS = ("class_b", "class_c", "class_d", "class_e", "sua", "tfr")

_CLASS_LOCAL_TYPE = {
    "class_b": "CLASS_B",
    "class_c": "CLASS_C",
    "class_d": "CLASS_D",
    "class_e": "CLASS_E",
}

_started = False
_start_lock = threading.Lock()


def _ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _layer_paths(layer):
    base = os.path.join(CACHE_DIR, layer)
    return base + ".geojson", base + ".meta.json"


def _atomic_write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def _write_layer(layer, geojson, fetched_at):
    geo_path, meta_path = _layer_paths(layer)
    _atomic_write_json(geo_path, geojson)
    _atomic_write_json(
        meta_path,
        {
            "fetched_at": fetched_at,
            "feature_count": len(geojson.get("features", [])),
        },
    )


def _read_layer(layer):
    geo_path, meta_path = _layer_paths(layer)
    if not os.path.exists(geo_path):
        return None, None
    try:
        with open(geo_path) as f:
            geo = json.load(f)
        meta = None
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)
        return geo, meta
    except Exception as e:
        logging.warning("Airspace cache: failed to read %s: %s", layer, e)
        return None, None


def _bbox_geometry_param():
    b = REGION_BBOX
    return "{},{},{},{}".format(b["lon_min"], b["lat_min"], b["lon_max"], b["lat_max"])


def _fetch_class_airspace(layer):
    local_type = _CLASS_LOCAL_TYPE[layer]
    params = {
        "where": "LOCAL_TYPE='{}'".format(local_type),
        "geometry": _bbox_geometry_param(),
        "geometryType": "esriGeometryEnvelope",
        "spatialRel": "esriSpatialRelIntersects",
        "inSR": "4326",
        "outSR": "4326",
        "outFields": "*",
        "returnGeometry": "true",
        "f": "geojson",
        "resultRecordCount": 2000,
    }
    r = requests.get(_CLASS_AIRSPACE_URL, params=params, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _fetch_sua():
    params = {
        "where": "1=1",
        "geometry": _bbox_geometry_param(),
        "geometryType": "esriGeometryEnvelope",
        "spatialRel": "esriSpatialRelIntersects",
        "inSR": "4326",
        "outSR": "4326",
        "outFields": "*",
        "returnGeometry": "true",
        "f": "geojson",
        "resultRecordCount": 2000,
    }
    r = requests.get(_SUA_URL, params=params, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _bbox_contains(lat, lon):
    b = REGION_BBOX
    return b["lat_min"] <= lat <= b["lat_max"] and b["lon_min"] <= lon <= b["lon_max"]


def _coords_in_region(geom):
    """Walk a GeoJSON geometry and return True if any coord lands in the bbox."""
    if not geom:
        return False
    coords = geom.get("coordinates")
    if coords is None:
        return False

    def walk(c):
        if isinstance(c, (list, tuple)) and c and isinstance(c[0], (int, float)):
            lon, lat = c[0], c[1]
            return _bbox_contains(lat, lon)
        if isinstance(c, (list, tuple)):
            return any(walk(x) for x in c)
        return False

    return walk(coords)


def _fetch_tfrs():
    """TFR endpoint schema is loose. Be defensive: log and return empty FC on issues."""
    try:
        r = requests.get(_TFR_URL, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        raw = r.json()
    except Exception as e:
        logging.warning("Airspace cache: TFR fetch/parse failed: %s", e)
        return {"type": "FeatureCollection", "features": []}

    items = raw if isinstance(raw, list) else raw.get("tfrList") or raw.get("data") or []
    features = []
    for item in items:
        try:
            geom = item.get("shape") or item.get("geometry") or item.get("geom")
            if isinstance(geom, str):
                try:
                    geom = json.loads(geom)
                except Exception:
                    geom = None
            if not geom:
                continue
            if not _coords_in_region(geom):
                continue
            props = {k: v for k, v in item.items() if k not in ("shape", "geometry", "geom")}
            features.append({"type": "Feature", "geometry": geom, "properties": props})
        except Exception as e:
            logging.debug("Airspace cache: skipping malformed TFR item: %s", e)
            continue

    return {"type": "FeatureCollection", "features": features}


def _refresh_layer(layer):
    fetched_at = time.time()
    if layer in _CLASS_LOCAL_TYPE:
        geo = _fetch_class_airspace(layer)
    elif layer == "sua":
        geo = _fetch_sua()
    elif layer == "tfr":
        geo = _fetch_tfrs()
    else:
        raise ValueError("unknown layer: " + layer)

    if not isinstance(geo, dict) or geo.get("type") != "FeatureCollection":
        raise ValueError("unexpected response shape for " + layer)

    _write_layer(layer, geo, fetched_at)
    logging.info(
        "Airspace cache: refreshed %s (%d features)",
        layer,
        len(geo.get("features", [])),
    )


def _try_refresh(layer):
    try:
        _refresh_layer(layer)
        return True
    except Exception as e:
        logging.warning("Airspace cache: refresh failed for %s: %s (keeping stale cache)", layer, e)
        return False


def _refresh_loop(layer, interval_sec):
    while True:
        time.sleep(interval_sec)
        _try_refresh(layer)


def get_layer_geojson(layer):
    """Returns (geojson_dict, meta_dict). Either may be None if not cached."""
    if layer not in LAYERS:
        return None, None
    return _read_layer(layer)


def get_status():
    now = time.time()
    out = {}
    for layer in LAYERS:
        geo, meta = _read_layer(layer)
        cached = geo is not None
        fetched_at = meta.get("fetched_at") if meta else None
        feature_count = meta.get("feature_count") if meta else 0
        age_seconds = (now - fetched_at) if fetched_at else None
        stale = (
            age_seconds is not None
            and age_seconds > STALE_THRESHOLD_SEC.get(layer, 24 * 60 * 60)
        )
        out[layer] = {
            "cached": cached,
            "fetched_at": fetched_at,
            "age_seconds": age_seconds,
            "feature_count": feature_count,
            "stale": stale,
        }
    return out


def start_background_refresh():
    """Idempotent. Synchronously hydrates any missing caches, then starts background threads."""
    global _started
    with _start_lock:
        if _started:
            return
        _started = True

    _ensure_cache_dir()

    for layer in LAYERS:
        geo, _ = _read_layer(layer)
        if geo is None:
            logging.info("Airspace cache: no cache for %s, fetching synchronously", layer)
            _try_refresh(layer)
        else:
            logging.info("Airspace cache: loading %s from cache", layer)

    for layer in _CLASS_LOCAL_TYPE:
        threading.Thread(
            target=_refresh_loop, args=(layer, AIRSPACE_REFRESH_SEC), daemon=True
        ).start()
    threading.Thread(
        target=_refresh_loop, args=("sua", AIRSPACE_REFRESH_SEC), daemon=True
    ).start()
    threading.Thread(
        target=_refresh_loop, args=("tfr", TFR_REFRESH_SEC), daemon=True
    ).start()
