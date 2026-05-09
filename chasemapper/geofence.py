"""
Per-profile geofence storage and KML parsing.

A geofence is a polygon (lat/lon ring) plus min/max altitude and a
remain-inside / remain-outside flag. Geofences are uploaded as KML
files exported by the HAB Bounder cut-down device, parsed here into a
small JSON-friendly dict, persisted to a sidecar JSON file next to the
chasemapper config, and attached to each profile in chasemapper_config
so the frontend renders them on the Leaflet map.

KML shape we expect (HAB Bounder export):

    <Placemark>
      <name>Geofence</name>
      <description>
        Remain inside
        Min Alt: -500 meters
        Max Alt: 50000 meters
      </description>
      <Polygon>
        <outerBoundaryIs><LinearRing>
          <coordinates>
            lon,lat,alt
            ...
          </coordinates>
        </LinearRing></outerBoundaryIs>
      </Polygon>
    </Placemark>

The exporter may also include a <gx:Track> with the flight path; we
ignore everything that isn't the geofence Placemark.
"""

import json
import logging
import os
import re
import threading
import xml.etree.ElementTree as ET


KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}

# Cap on how big a single uploaded KML may be. Geofence-only KML is
# tiny; this limit really only protects us from someone uploading a
# multi-MB Flight.KML by mistake (the geofence is still parsed fine
# from those — but no point loading 50 MB of track points to discard).
MAX_KML_BYTES = 5 * 1024 * 1024

_save_lock = threading.Lock()


class GeofenceParseError(Exception):
    """Raised when a KML upload cannot be parsed into a geofence."""


# ---- KML parsing -------------------------------------------------------


def _findall_ns(elem, tag):
    """Find children regardless of whether the doc declares the KML
    namespace. Bounder's KML does declare it, but be lenient."""
    return elem.findall("kml:" + tag, KML_NS) + elem.findall(tag)


def _find_ns(elem, path_with_kml_prefix, fallback_path):
    """Try a namespaced path first, fall back to non-namespaced."""
    found = elem.find(path_with_kml_prefix, KML_NS)
    if found is not None:
        return found
    return elem.find(fallback_path)


def parse_kml_geofence(kml_bytes):
    """Parse a HAB Bounder KML and return the geofence dict.

    Returned shape (matches what the frontend expects):

        {
            "polygon": [[lat, lon], [lat, lon], ...],  # open ring
            "min_alt": float,                          # meters
            "max_alt": float,                          # meters
            "remain":  "inside" | "outside",
        }

    Raises GeofenceParseError on any malformed input.
    """
    if not kml_bytes:
        raise GeofenceParseError("Empty upload.")

    try:
        root = ET.fromstring(kml_bytes)
    except ET.ParseError as e:
        raise GeofenceParseError("Invalid XML: %s" % e)

    # Find every Placemark, then pick one that contains a Polygon. If
    # there are several, prefer the one named "Geofence" (case
    # insensitive) — that's what the Bounder exports.
    placemarks = root.findall(".//kml:Placemark", KML_NS)
    if not placemarks:
        placemarks = root.findall(".//Placemark")

    chosen = None
    for pm in placemarks:
        polygon_el = _find_ns(pm, ".//kml:Polygon", ".//Polygon")
        if polygon_el is None:
            continue
        name_el = _find_ns(pm, "kml:name", "name")
        name = (name_el.text or "").strip().lower() if name_el is not None else ""
        if "geofence" in name:
            chosen = pm
            break
        if chosen is None:
            chosen = pm  # remember first, keep looking for a "Geofence"

    if chosen is None:
        raise GeofenceParseError("No <Polygon> Placemark found in KML.")

    coords_el = _find_ns(
        chosen,
        ".//kml:outerBoundaryIs/kml:LinearRing/kml:coordinates",
        ".//outerBoundaryIs/LinearRing/coordinates",
    )
    if coords_el is None or not (coords_el.text or "").strip():
        raise GeofenceParseError("Polygon has no <coordinates>.")

    polygon = []
    for tok in coords_el.text.split():
        # Each token is "lon,lat[,alt]". KML is lon-first; Leaflet
        # wants lat-first. Drop altitude (we carry min/max separately).
        parts = tok.split(",")
        if len(parts) < 2:
            continue
        try:
            lon = float(parts[0])
            lat = float(parts[1])
        except ValueError:
            continue
        if not (-180.0 <= lon <= 180.0) or not (-90.0 <= lat <= 90.0):
            raise GeofenceParseError(
                "Coordinate out of range: lon=%s lat=%s" % (lon, lat)
            )
        polygon.append([lat, lon])

    # Bounder export sometimes repeats the closing waypoint; collapse
    # back-to-back duplicates and the trailing close (Leaflet draws the
    # ring closed regardless).
    while len(polygon) > 3 and polygon[-1] == polygon[-2]:
        polygon.pop()
    if len(polygon) > 3 and polygon[0] == polygon[-1]:
        polygon.pop()

    if len(polygon) < 3:
        raise GeofenceParseError(
            "Polygon needs at least 3 distinct vertices (got %d)." % len(polygon)
        )

    # Description carries Remain inside/outside + Min/Max altitude.
    desc_el = _find_ns(chosen, "kml:description", "description")
    desc = (desc_el.text or "") if desc_el is not None else ""

    remain = "inside"
    m = re.search(r"Remain\s+(inside|outside)", desc, re.I)
    if m:
        remain = m.group(1).lower()

    def _parse_alt(label_re, default):
        m = re.search(label_re + r"\s*:\s*(-?\d+(?:\.\d+)?)", desc, re.I)
        return float(m.group(1)) if m else default

    # Defaults match the HAB Bounder spec when the Altitude line is
    # omitted from the config: -1000 m to 50000 m.
    min_alt = _parse_alt(r"Min\s+Alt", -1000.0)
    max_alt = _parse_alt(r"Max\s+Alt", 50000.0)

    return {
        "polygon": polygon,
        "min_alt": min_alt,
        "max_alt": max_alt,
        "remain": remain,
    }


# ---- Persistence -------------------------------------------------------


def load_store(path):
    """Load the geofences sidecar. Returns {} on missing/invalid."""
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        logging.warning("Could not read geofence store %s: %s" % (path, e))
        return {}
    if not isinstance(data, dict):
        logging.warning("Geofence store %s is not a JSON object, ignoring." % path)
        return {}
    return data


def save_store(path, store):
    """Atomically write the geofences sidecar."""
    if not path:
        return
    with _save_lock:
        tmp = path + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(store, f, indent=2)
            os.replace(tmp, path)
        except OSError as e:
            logging.error("Could not save geofence store %s: %s" % (path, e))


def attach_to_profiles(chasemapper_config, store):
    """Stamp each profile dict with its geofence (or None) so it ships
    out via /get_config and server_settings_update."""
    for name, profile in chasemapper_config.get("profiles", {}).items():
        profile["geofence"] = store.get(name)
