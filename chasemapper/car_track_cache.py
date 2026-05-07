"""
Per-day chase-car track buffer.

Holds the day's chase-car positions in memory and on disk so the trail
survives page refreshes (and daemon restarts within the same UTC day).
At UTC day rollover the buffer and the on-disk cache are wiped.

Design notes:
- Trimmed by both age (24h sliding) and a hard max length to bound memory.
- Disk writes are throttled (every WRITE_INTERVAL_SEC) to avoid hammering
  the SD card on a typical chase-cam Pi setup.
- Atomic write (tmp + replace) so a crash mid-write can't corrupt cache.
"""

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone

CACHE_DIR = os.path.join("cache", "car_track")
CACHE_FILE = os.path.join(CACHE_DIR, "car_track.json")
MAX_POINTS = 20000
MAX_AGE_SEC = 24 * 60 * 60
WRITE_INTERVAL_SEC = 10

_lock = threading.Lock()
_points = []          # list of [epoch, lat, lon, alt, heading]
_day_key = None       # YYYY-MM-DD UTC of current buffer
_last_write = 0.0
_started = False


def _today_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _ensure_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _atomic_write(path, payload):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f)
    os.replace(tmp, path)


def _wipe_disk():
    try:
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
    except Exception as e:
        logging.warning("car_track_cache: wipe failed: %s", e)


def _flush_locked():
    """Caller must hold _lock."""
    global _last_write
    try:
        _ensure_dir()
        _atomic_write(CACHE_FILE, {"day": _day_key, "points": _points})
        _last_write = time.time()
    except Exception as e:
        logging.warning("car_track_cache: flush failed: %s", e)


def _trim_locked():
    """Drop points older than MAX_AGE_SEC and cap MAX_POINTS. Caller holds _lock."""
    cutoff = time.time() - MAX_AGE_SEC
    # Lists in time order; trim from the head.
    idx = 0
    for p in _points:
        if p[0] >= cutoff:
            break
        idx += 1
    if idx:
        del _points[:idx]
    if len(_points) > MAX_POINTS:
        del _points[: len(_points) - MAX_POINTS]


def _load_from_disk():
    """Load existing buffer if and only if it's from today's UTC date."""
    global _points, _day_key
    if not os.path.exists(CACHE_FILE):
        _day_key = _today_utc()
        return
    try:
        with open(CACHE_FILE) as f:
            data = json.load(f)
        if data.get("day") == _today_utc():
            _points = list(data.get("points", []))
            _day_key = data["day"]
            _trim_locked()
            logging.info(
                "car_track_cache: loaded %d points from today's cache", len(_points)
            )
        else:
            logging.info("car_track_cache: discarding stale cache (day rollover)")
            _points = []
            _day_key = _today_utc()
            _wipe_disk()
    except Exception as e:
        logging.warning("car_track_cache: load failed (%s); starting fresh", e)
        _points = []
        _day_key = _today_utc()


def add_point(lat, lon, alt=0.0, heading=0.0):
    """Append a chase-car position. Throttled disk writes; day-rolls if needed."""
    global _day_key, _last_write
    with _lock:
        today = _today_utc()
        if _day_key != today:
            logging.info("car_track_cache: UTC day rollover, clearing buffer")
            _points.clear()
            _day_key = today
            _wipe_disk()

        try:
            lat = float(lat)
            lon = float(lon)
            alt = float(alt) if alt is not None else 0.0
            heading = float(heading) if heading is not None else 0.0
        except (TypeError, ValueError):
            return

        _points.append([time.time(), lat, lon, alt, heading])
        _trim_locked()

        if (time.time() - _last_write) >= WRITE_INTERVAL_SEC:
            _flush_locked()


def get_points():
    """Return a copy of the day's track as a list of [t, lat, lon, alt, heading]."""
    with _lock:
        return list(_points)


def clear():
    with _lock:
        _points.clear()
        _wipe_disk()


def _rollover_loop():
    """Once a minute, check for UTC day rollover; if so, wipe."""
    global _day_key
    while True:
        time.sleep(60)
        try:
            today = _today_utc()
            with _lock:
                if _day_key != today:
                    logging.info("car_track_cache: scheduled rollover wipe")
                    _points.clear()
                    _day_key = today
                    _wipe_disk()
        except Exception as e:
            logging.warning("car_track_cache: rollover loop error: %s", e)


def start():
    """Idempotent. Loads today's cache and starts the rollover thread."""
    global _started
    with _lock:
        if _started:
            return
        _started = True
    _ensure_dir()
    with _lock:
        _load_from_disk()
    threading.Thread(target=_rollover_loop, daemon=True).start()
