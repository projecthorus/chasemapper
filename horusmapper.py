#!/usr/bin/env python2.7
#
#   Project Horus - Browser-Based Chase Mapper
#
#   Copyright (C) 2018  Mark Jessop <vk5qi@rfhead.net>
#   Released under GNU GPL v3 or later
#
import sys

# Version check.
if sys.version_info < (3, 6):
    print("CRITICAL - chasemapper requires Python 3.6 or newer!")
    sys.exit(1)

import json
import logging
import flask
from flask_socketio import SocketIO
import os.path
import pytz
import time
import traceback
from threading import Thread
from datetime import datetime, timedelta
from dateutil.parser import parse

from chasemapper import __version__ as CHASEMAPPER_VERSION
from chasemapper.config import *
from chasemapper.earthmaths import *
from chasemapper.geometry import *
from chasemapper.gps import SerialGPS
from chasemapper.gpsd import GPSDAdaptor
from chasemapper.atmosphere import time_to_landing
from chasemapper.listeners import OziListener, UDPListener, fix_datetime
from chasemapper.predictor import predictor_spawn_download, model_download_running
from chasemapper.habitat import (
    HabitatChaseUploader,
    initListenerCallsign,
    uploadListenerPosition,
)
from chasemapper.sondehub import SondehubChaseUploader
from chasemapper.logger import ChaseLogger
from chasemapper.logread import read_last_balloon_telemetry
from chasemapper.bearings import Bearings
from chasemapper.tawhiri import get_tawhiri_prediction


# Define Flask Application, and allow automatic reloading of templates for dev work
app = flask.Flask(__name__)
app.config["SECRET_KEY"] = "secret!"
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.jinja_env.auto_reload = True

# SocketIO instance
socketio = SocketIO(app)


# Chase Logger Instance (Initialised in main)
chase_logger = None

# Global stores of data.

# These settings are shared between server and all clients, and are updated dynamically.
chasemapper_config = {}

# Pointers to objects containing data listeners.
# These should all present a .close() function which will be called on
# listener profile change, or program exit.
data_listeners = []

# These settings are not editable by the client!
pred_settings = {}

# Offline map settings, again, not editable by the client.
map_settings = {"tile_server_enabled": False}

# Payload data Stores
current_payloads = {}  #  Archive data which will be passed to the web client
current_payload_tracks = (
    {}
)  # Store of payload Track objects which are used to calculate instantaneous parameters.

# Chase car position
car_track = GenericTrack()

# Bearing store
bearing_store = None
bearing_mode = False # Flag to indicate if we are receiving bearings

# Habitat/Sondehub Chase-Car uploader object
online_uploader = None

# Copy out any extra fields from incoming telemetry that we want to pass on to the GUI.
# At the moment we're really only using the burst timer field.
EXTRA_FIELDS = ["bt", "temp", "humidity", "sats", "snr"]


#
#   Flask Routes
#


@app.route("/")
def flask_index():
    """ Render main index page """
    return flask.render_template("index.html")

@app.route("/bearing")
def flask_bearing_entry():
    """ Render bearing entry page """
    return flask.render_template("bearing_entry.html")

@app.route("/oclock")
def flask_oclock():
    """ Render bearing o'clock page """
    return flask.render_template("oclock.html")

@app.route("/get_telemetry_archive")
def flask_get_telemetry_archive():
    return json.dumps(current_payloads)


@app.route("/get_config")
def flask_get_config():
    return json.dumps(chasemapper_config)


@app.route("/get_bearings")
def flask_get_bearings():
    return json.dumps(bearing_store.bearings)


# Some features of the web interface require comparisons with server time,
# so provide a route to grab it.
@app.route("/server_time")
def flask_get_server_time():
    return json.dumps(time.time())


@app.route("/tiles/<path:filename>")
def flask_server_tiles(filename):
    """ Serve up a file from the tile server location """
    global map_settings
    if map_settings["tile_server_enabled"]:
        return flask.send_from_directory(map_settings["tile_server_path"], filename)
    else:
        flask.abort(404)


def flask_emit_event(event_name="none", data={}):
    """ Emit a socketio event to any clients. """
    socketio.emit(event_name, data, namespace="/chasemapper")


@socketio.on("client_settings_update", namespace="/chasemapper")
def client_settings_update(data):
    global chasemapper_config, online_uploader

    _predictor_change = "none"
    if (chasemapper_config["pred_enabled"] == False) and (data["pred_enabled"] == True):
        _predictor_change = "restart"
    elif (chasemapper_config["pred_enabled"] == True) and (
        data["pred_enabled"] == False
    ):
        _predictor_change = "stop"

    _habitat_change = "none"
    if (chasemapper_config["habitat_upload_enabled"] == False) and (
        data["habitat_upload_enabled"] == True
    ):
        _habitat_change = "start"
    elif (chasemapper_config["habitat_upload_enabled"] == True) and (
        data["habitat_upload_enabled"] == False
    ):
        _habitat_change = "stop"

    # Overwrite local config data with data from the client.
    chasemapper_config = data

    if _predictor_change == "restart":
        # Wait until any current predictions have finished.
        while predictor_semaphore:
            time.sleep(0.1)
        # Attempt to start the predictor.
        initPredictor()
    elif _predictor_change == "stop":
        # Wait until any current predictions have finished.
        while predictor_semaphore:
            time.sleep(0.1)

        predictor = None

    # Start or Stop the Habitat Chase-Car Uploader.
    if _habitat_change == "start":
        if online_uploader == None:
            _tracker = chasemapper_config["profiles"][
                chasemapper_config["selected_profile"]
            ]["online_tracker"]
            if _tracker == "habitat":
                logging.error(
                    "Habitat uploader now deprecated due to Habitat retirement, not starting uploader."
                )
            elif _tracker == "sondehub":
                online_uploader = SondehubChaseUploader(
                    update_rate=chasemapper_config["habitat_update_rate"],
                    callsign=chasemapper_config["habitat_call"],
                )
            elif _tracker == "sondehubamateur":
                online_uploader = SondehubChaseUploader(
                    update_rate=chasemapper_config["habitat_update_rate"],
                    callsign=chasemapper_config["habitat_call"],
                    amateur=True
                )
            else:
                logging.error(
                    "Unknown Online Tracker %s, not starting uploader." % _tracker
                )

    elif _habitat_change == "stop":
        online_uploader.close()
        online_uploader = None

    # Update the habitat uploader with a new update rate, if one has changed.
    if online_uploader != None:
        online_uploader.set_update_rate(chasemapper_config["habitat_update_rate"])
        online_uploader.set_callsign(chasemapper_config["habitat_call"])

    # Push settings back out to all clients.
    flask_emit_event("server_settings_update", chasemapper_config)


def handle_new_payload_position(data, log_position=True):

    _lat = data["lat"]
    _lon = data["lon"]
    _alt = data["alt"]
    _time_dt = data["time_dt"]
    _callsign = data["callsign"]

    _short_time = _time_dt.strftime("%H:%M:%S")

    if _callsign not in current_payloads:
        # New callsign! Create entries in data stores.
        current_payload_tracks[_callsign] = GenericTrack(ascent_averaging=chasemapper_config["ascent_rate_averaging"])

        current_payloads[_callsign] = {
            "telem": {
                "callsign": _callsign,
                "position": [_lat, _lon, _alt],
                "max_alt": 0.0,
                "vel_v": 0.0,
                "speed": 0.0,
                "short_time": _short_time,
                "time_to_landing": "",
                "server_time": time.time(),
            },
            "path": [],
            "pred_path": [],
            "pred_landing": [],
            "burst": [],
            "abort_path": [],
            "abort_landing": [],
            "max_alt": 0.0,
            "snr": -255.0,
        }

    # Add new data into the payload's track, and get the latest ascent rate.
    current_payload_tracks[_callsign].add_telemetry(
        {"time": _time_dt, "lat": _lat, "lon": _lon, "alt": _alt, "comment": _callsign}
    )
    _state = current_payload_tracks[_callsign].get_latest_state()
    if _state != None:
        _vel_v = _state["ascent_rate"]
        _speed = _state["speed"]
        # If this payload is in descent, calculate the time to landing.
        # Use < -1.0, to avoid jitter when the payload is on the ground.
        if _vel_v < -1.0:
            # Try and get the altitude of the chase car - we use this as the expected 'ground' level.
            _car_state = car_track.get_latest_state()
            if _car_state != None:
                _ground_asl = _car_state["alt"]
            else:
                _ground_asl = 0.0

            # Calculate
            _ttl = time_to_landing(_alt, _vel_v, ground_asl=_ground_asl)
            if _ttl is None:
                _ttl = ""
            elif _ttl == 0:
                _ttl = "LANDED"
            else:
                _min = _ttl // 60
                _sec = _ttl % 60
                _ttl = "%02d:%02d" % (_min, _sec)
        else:
            _ttl = ""

    else:
        _vel_v = 0.0
        _ttl = ""

    # Now update the main telemetry store.
    current_payloads[_callsign]["telem"] = {
        "callsign": _callsign,
        "position": [_lat, _lon, _alt],
        "vel_v": _vel_v,
        "speed": _speed,
        "short_time": _short_time,
        "time_to_landing": _ttl,
        "server_time": time.time(),
    }

    current_payloads[_callsign]["path"].append([_lat, _lon, _alt])

    # Copy out any extra fields we may want to pass onto the GUI.
    for _field in EXTRA_FIELDS:
        if _field in data:
            current_payloads[_callsign]["telem"][_field] = data[_field]

    # Check if the current payload altitude is higher than our previous maximum altitude.
    if _alt > current_payloads[_callsign]["max_alt"]:
        current_payloads[_callsign]["max_alt"] = _alt

    # Add the payload maximum altitude into the telemetry snapshot dictionary.
    current_payloads[_callsign]["telem"]["max_alt"] = current_payloads[_callsign][
        "max_alt"
    ]

    # Update the web client.
    flask_emit_event("telemetry_event", current_payloads[_callsign]["telem"])

    # Add the position into the logger
    if chase_logger and log_position:
        chase_logger.add_balloon_telemetry(data)
    else:
        logging.debug("Point not logged.")


def handle_modem_stats(data):
    """ Basic handling of modem statistics data. If it matches a known payload, send the info to the client. """

    if data["source"] in current_payloads:
        flask_emit_event(
            "modem_stats_event", {"callsign": data["source"], "snr": data["snr"]}
        )


#
#   Predictor Code
#
predictor = None
predictor_semaphore = False

predictor_thread_running = True
predictor_thread = None


def predictorThread():
    """ Run the predictor on a regular interval """
    global predictor_thread_running, chasemapper_config
    logging.info("Predictor loop started.")

    while predictor_thread_running:
        run_prediction()
        for i in range(int(chasemapper_config["pred_update_rate"])):
            time.sleep(1)
            if predictor_thread_running == False:
                break

    logging.info("Closed predictor loop.")


def run_prediction():
    """ Run a Flight Path prediction """
    global chasemapper_config, current_payloads, current_payload_tracks, predictor, predictor_semaphore

    if chasemapper_config["pred_enabled"] == False:
        return

    if (chasemapper_config["offline_predictions"] == True) and (predictor == None):
        return

    # Set the semaphore so we don't accidentally kill the predictor object while it's running.
    predictor_semaphore = True
    _payload_list = list(current_payload_tracks.keys())
    for _payload in _payload_list:

        # Check the age of the data.
        # No point re-running the predictor if the data is older than 30 seconds.
        _pos_age = current_payloads[_payload]["telem"]["server_time"]
        if (time.time() - _pos_age) > 30.0:
            logging.debug("Skipping prediction for %s due to old data." % _payload)
            continue

        _current_pos = current_payload_tracks[_payload].get_latest_state()
        _current_pos_list = [
            0,
            _current_pos["lat"],
            _current_pos["lon"],
            _current_pos["alt"],
        ]
        if current_payload_tracks[_payload].length() <= 1:
            logging.info(
                "Only %i point in this payload's track, skipping prediction.",
                current_payload_tracks[_payload].length(),
            )
            continue

        _pred_ok = False
        _abort_pred_ok = False

        if _current_pos["is_descending"]:
            _desc_rate = _current_pos["landing_rate"]
        else:
            _desc_rate = chasemapper_config["pred_desc_rate"]

        if _current_pos["alt"] > chasemapper_config["pred_burst"]:
            _burst_alt = _current_pos["alt"] + 100
        else:
            _burst_alt = chasemapper_config["pred_burst"]

        if predictor == "Tawhiri":
            logging.info("Requesting Prediction from Tawhiri for %s." % _payload)
            # Tawhiri requires that the burst altitude always be higher than the starting altitude.
            if _current_pos["is_descending"]:
                _burst_alt = _current_pos["alt"] + 1

            # Tawhiri requires that the ascent rate be > 0 for standard profiles.
            if _current_pos["ascent_rate"] < 0.1:
                _current_pos["ascent_rate"] = 0.1

            _tawhiri = get_tawhiri_prediction(
                launch_datetime=_current_pos["time"],
                launch_latitude=_current_pos["lat"],
                launch_longitude=_current_pos["lon"],
                launch_altitude=_current_pos["alt"],
                burst_altitude=_burst_alt,
                ascent_rate=_current_pos["ascent_rate"],
                descent_rate=_desc_rate,
            )

            if _tawhiri:
                _pred_path = _tawhiri["path"]
                _dataset = _tawhiri["dataset"] + " (Online)"
                # Inform the client of the dataset age
                flask_emit_event("predictor_model_update", {"model": _dataset})

            else:
                _pred_path = []

        else:
            logging.info("Running Offline Predictor for %s." % _payload)
            _pred_path = predictor.predict(
                launch_lat=_current_pos["lat"],
                launch_lon=_current_pos["lon"],
                launch_alt=_current_pos["alt"],
                ascent_rate=_current_pos["ascent_rate"],
                descent_rate=_desc_rate,
                burst_alt=_burst_alt,
                launch_time=_current_pos["time"],
                descent_mode=_current_pos["is_descending"],
            )

        if len(_pred_path) > 1:
            # Valid Prediction!
            _pred_path.insert(0, _current_pos_list)
            # Convert from predictor output format to a polyline.
            _pred_output = []
            for _point in _pred_path:
                _pred_output.append([_point[1], _point[2], _point[3]])

            current_payloads[_payload]["pred_path"] = _pred_output
            current_payloads[_payload]["pred_landing"] = _pred_output[-1]

            if _current_pos["is_descending"]:
                current_payloads[_payload]["burst"] = []
            else:
                # Determine the burst position.
                _cur_alt = 0.0
                _cur_idx = 0
                for i in range(len(_pred_output)):
                    if _pred_output[i][2] > _cur_alt:
                        _cur_alt = _pred_output[i][2]
                        _cur_idx = i

                current_payloads[_payload]["burst"] = _pred_output[_cur_idx]

            _pred_ok = True
            logging.info("Prediction Updated, %d data points." % len(_pred_path))
        else:
            current_payloads[_payload]["pred_path"] = []
            current_payloads[_payload]["pred_landing"] = []
            current_payloads[_payload]["burst"] = []
            logging.error("Prediction Failed, possible invalid or missing dataset.")
            flask_emit_event("predictor_model_update", {"model": "Dataset invalid."})

        # Abort predictions
        if (
            chasemapper_config["show_abort"]
            and (_current_pos["alt"] < chasemapper_config["pred_burst"])
            and (_current_pos["is_descending"] == False)
        ):

            if predictor == "Tawhiri":
                logging.info(
                    "Requesting Abort Prediction from Tawhiri for %s." % _payload
                )

                # Tawhiri requires that the ascent rate be > 0 for standard profiles.
                if _current_pos["ascent_rate"] < 0.1:
                    _current_pos["ascent_rate"] = 0.1

                _tawhiri = get_tawhiri_prediction(
                    launch_datetime=_current_pos["time"],
                    launch_latitude=_current_pos["lat"],
                    launch_longitude=_current_pos["lon"],
                    launch_altitude=_current_pos["alt"],
                    burst_altitude=_current_pos["alt"] + 200,
                    ascent_rate=_current_pos["ascent_rate"],
                    descent_rate=_desc_rate,
                )

                if _tawhiri:
                    _abort_pred_path = _tawhiri["path"]

                else:
                    _abort_pred_path = []

            else:
                logging.info("Running Offline Abort Predictor for: %s." % _payload)

                _abort_pred_path = predictor.predict(
                    launch_lat=_current_pos["lat"],
                    launch_lon=_current_pos["lon"],
                    launch_alt=_current_pos["alt"],
                    ascent_rate=_current_pos["ascent_rate"],
                    descent_rate=_desc_rate,
                    burst_alt=_current_pos["alt"] + 200,
                    launch_time=_current_pos["time"],
                    descent_mode=_current_pos["is_descending"],
                )

            if len(_pred_path) > 1:
                # Valid Prediction!
                _abort_pred_path.insert(0, _current_pos_list)
                # Convert from predictor output format to a polyline.
                _abort_pred_output = []
                for _point in _abort_pred_path:
                    _abort_pred_output.append([_point[1], _point[2], _point[3]])

                current_payloads[_payload]["abort_path"] = _abort_pred_output
                current_payloads[_payload]["abort_landing"] = _abort_pred_output[-1]

                _abort_pred_ok = True
                logging.info(
                    "Abort Prediction Updated, %d data points." % len(_pred_path)
                )
            else:
                current_payloads[_payload]["abort_path"] = []
                current_payloads[_payload]["abort_landing"] = []
                logging.error("Prediction Failed, possible invalid or missing dataset.")
                flask_emit_event("predictor_model_update", {"model": "Dataset invalid."})
        else:
            # Zero the abort path and landing
            current_payloads[_payload]["abort_path"] = []
            current_payloads[_payload]["abort_landing"] = []

        # Send the web client the updated prediction data.
        if _pred_ok or _abort_pred_ok:
            _client_data = {
                "callsign": _payload,
                "pred_path": current_payloads[_payload]["pred_path"],
                "pred_landing": current_payloads[_payload]["pred_landing"],
                "burst": current_payloads[_payload]["burst"],
                "abort_path": current_payloads[_payload]["abort_path"],
                "abort_landing": current_payloads[_payload]["abort_landing"],
            }
            flask_emit_event("predictor_update", _client_data)

            # Add the prediction run to the logger.
            if chase_logger:
                chase_logger.add_balloon_prediction(_client_data)

    # Clear the predictor-running semaphore
    predictor_semaphore = False


def initPredictor():
    global predictor, predictor_thread, chasemapper_config, pred_settings

    if chasemapper_config["offline_predictions"]:
        # Attempt to initialize an Offline Predictor instance
        try:
            from cusfpredict.predict import Predictor
            from cusfpredict.utils import gfs_model_age, available_gfs

            # Check if we have any GFS data
            _model_age = gfs_model_age(pred_settings["gfs_path"])
            if _model_age == "Unknown":
                logging.error("No GFS data in directory.")
                chasemapper_config["pred_model"] = "No GFS Data."
                flask_emit_event("predictor_model_update", {"model": "No GFS data."})
                chasemapper_config["offline_predictions"] = False
            else:
                # Check model contains data to at least 4 hours into the future.
                (_model_start, _model_end) = available_gfs(pred_settings["gfs_path"])
                _model_now = datetime.utcnow() + timedelta(0, 60 * 60 * 4)
                if (_model_now < _model_start) or (_model_now > _model_end):
                    # No suitable GFS data!
                    logging.error("GFS Data in directory does not cover now!")
                    chasemapper_config["pred_model"] = "Old GFS Data."
                    flask_emit_event(
                        "predictor_model_update", {"model": "Old GFS data."}
                    )
                    chasemapper_config["offline_predictions"] = False

                else:
                    chasemapper_config["pred_model"] = _model_age + " (Offline)"
                    flask_emit_event(
                        "predictor_model_update", {"model": _model_age + " (Offline)"}
                    )
                    predictor = Predictor(
                        bin_path=pred_settings["pred_binary"],
                        gfs_path=pred_settings["gfs_path"],
                    )

                    # Start up the predictor thread if it is not running.
                    if predictor_thread == None:
                        predictor_thread = Thread(target=predictorThread)
                        predictor_thread.start()

                    # Set the predictor to enabled, and update the clients.
                    chasemapper_config["offline_predictions"] = True

        except Exception as e:
            traceback.print_exc()
            logging.error("Loading predictor failed: " + str(e))
            flask_emit_event("predictor_model_update", {"model": "Failed - Check Log."})
            chasemapper_config["pred_model"] = "Failed - Check Log."
            print("Loading Predictor failed.")
            predictor = None

    else:
        # No initialization required for the online predictor
        predictor = "Tawhiri"
        flask_emit_event("predictor_model_update", {"model": "Tawhiri"})

        # Start up the predictor thread if it is not running.
        if predictor_thread == None:
            predictor_thread = Thread(target=predictorThread)
            predictor_thread.start()

    flask_emit_event("server_settings_update", chasemapper_config)


def model_download_finished(result):
    """ Callback for when the model download is finished """
    global chasemapper_config
    if result == "OK":
        # Downloader reported OK, restart the predictor.
        chasemapper_config["offline_predictions"] = True
        initPredictor()
    else:
        # Downloader reported an error, pass on to the client.
        flask_emit_event("predictor_model_update", {"model": result})


@socketio.on("download_model", namespace="/chasemapper")
def download_new_model(data):
    """ Trigger a download of a new weather model """
    global pred_settings, model_download_running
    # Don't action anything if there is a model download already running

    logging.info("Web Client Initiated request for new predictor data.")

    if pred_settings["pred_model_download"] == "none":
        logging.info("No GFS model download command specified.")
        flask_emit_event("predictor_model_update", {"model": "No model download cmd."})
        return
    else:
        _model_cmd = pred_settings["pred_model_download"]
        flask_emit_event("predictor_model_update", {"model": "Downloading Model."})

        _status = predictor_spawn_download(_model_cmd, model_download_finished)
        flask_emit_event("predictor_model_update", {"model": _status})


@app.route("/download_model")
def download_new_model_2():
    """ Trigger a download of a new weather model via a GET request """
    global pred_settings, model_download_running

    logging.info("Web Client Initiated request for new predictor data via /download_model.")

    if pred_settings["pred_model_download"] == "none":
        logging.info("No GFS model download command specified.")
        return "No model download cmd."
    else:
        _model_cmd = pred_settings["pred_model_download"]
        _status = predictor_spawn_download(_model_cmd, model_download_finished)
        return _status


# Data Clearing Functions
@socketio.on("payload_data_clear", namespace="/chasemapper")
def clear_payload_data(data):
    """ Clear the payload data store """
    global predictor_semaphore, current_payloads, current_payload_tracks
    logging.warning("Client requested all payload data be cleared.")
    # Wait until any current predictions have finished running.
    while predictor_semaphore:
        time.sleep(0.1)

    current_payloads = {}
    current_payload_tracks = {}


@socketio.on("car_data_clear", namespace="/chasemapper")
def clear_car_data(data):
    """ Clear out the car position track """
    global car_track
    logging.warning("Client requested all chase car data be cleared.")
    car_track = GenericTrack()


@socketio.on("bearing_store_clear", namespace="/chasemapper")
def clear_bearing_data(data):
    """ Clear all bearing data """
    global bearing_store
    logging.warning("Client requested bearing data be cleared.")
    bearing_store.flush()
    flask_emit_event("server_bearings_cleared", {"foo":"bar"})


@socketio.on("mark_recovered", namespace="/chasemapper")
def mark_payload_recovered(data):
    """ Mark a payload as recovered, by uploading a station position """
    global online_uploader

    print(data)

    _serial = data["payload_call"]
    _callsign = data["my_call"]
    _lat = data["last_pos"][0]
    _lon = data["last_pos"][1]
    _alt = data["last_pos"][2]
    _msg = data["message"]
    _recovered = data["recovered"]

    if online_uploader != None:
        online_uploader.mark_payload_recovered(
            serial = _serial,
            callsign = _callsign,
            lat = _lat, 
            lon = _lon, 
            alt = _alt, 
            message = _msg, 
            recovered=_recovered
            )
    else:
        logging.error("No Online Tracker enabled, could not mark payload as recovered.")


# Incoming telemetry handlers


def ozi_listener_callback(data):
    """ Handle a OziMux input message """
    # OziMux message contains:
    # {'lat': -34.87915, 'comment': 'Telemetry Data', 'alt': 26493.0, 'lon': 139.11883, 'time': datetime.datetime(2018, 7, 16, 10, 55, 49, tzinfo=tzutc())}
    output = {}
    output["lat"] = float(data["lat"])
    output["lon"] = float(data["lon"])
    output["alt"] = float(data["alt"])
    output["callsign"] = "Payload"
    output["time_dt"] = data["time"]

    logging.info(
        "OziMux Data: %.5f, %.5f, %.1f" % (data["lat"], data["lon"], data["alt"])
    )

    try:
        handle_new_payload_position(output)
    except Exception as e:
        logging.error("Error Handling Payload Position - %s" % str(e))


def udp_listener_summary_callback(data):
    """ Handle a Payload Summary Message from UDPListener """

    # Modem stats messages are also passed in via this callback.
    # handle them separately.
    if data["type"] == "MODEM_STATS":
        handle_modem_stats(data)
        return

    # Otherwise, we have a PAYLOAD_SUMMARY message.

    # Extract the fields we need.
    # Convert to something generic we can pass onwards.
    output = {}
    output["lat"] = float(data["latitude"])
    output["lon"] = float(data["longitude"])
    output["alt"] = float(data["altitude"])
    output["callsign"] = data["callsign"]

    if "time" in data.keys():
        _time = data["time"]
    else:
        _time = "??:??:??"

    logging.info(
        "Horus UDP Data: %s, %s, %.5f, %.5f, %.1f"
        % (output["callsign"], _time, output["lat"], output["lon"], output["alt"])
    )

    # Process the 'short time' value if we have been provided it.
    if "time" in data.keys():
        output["time_dt"] = fix_datetime(data["time"])
        # _full_time = datetime.utcnow().strftime("%Y-%m-%dT") + data['time'] + "Z"
        # output['time_dt'] = parse(_full_time)
    else:
        # Otherwise use the current UTC time.

        output["time_dt"] = pytz.utc.localize(datetime.utcnow())

    # Copy out any extra fields that we want to pass on to the GUI.
    for _field in EXTRA_FIELDS:
        if _field in data:
            output[_field] = data[_field]

    try:
        handle_new_payload_position(output)
    except Exception as e:
        logging.error("Error Handling Payload Position - %s" % str(e))


def udp_listener_car_callback(data):
    """ Handle car position data """
    # TODO: Make a generic car position function, and have this function pass data into it
    # so we can add support for other chase car position inputs.
    global car_track, online_uploader, bearing_store
    _lat = float(data["latitude"])
    _lon = float(data["longitude"])

    # Handle when GPSD and/or other GPS data sources return a n/a for altitude.
    try:
        _alt = float(data["altitude"])
    except:
        _alt = 0.0

    _comment = "CAR"
    _time_dt = pytz.utc.localize(datetime.utcnow())

    logging.debug("Car Position: %.5f, %.5f" % (_lat, _lon))

    _car_position_update = {
        "time": _time_dt,
        "lat": _lat,
        "lon": _lon,
        "alt": _alt,
        "comment": _comment,
    }
    # Add in true heading data if we have been supplied it (e.g. from a uBlox NEO-M8U device)
    if "heading" in data:
        _car_position_update["heading"] = data["heading"]

    if "heading_status" in data:
        _car_position_update["heading_status"] = data["heading_status"]
    

    car_track.add_telemetry(_car_position_update)

    _state = car_track.get_latest_state()
    _heading = _state["heading"]
    _heading_status = _state["heading_status"]
    _heading_valid = _state["heading_valid"]
    _speed = _state["speed"]


    _car_telem = {
            "callsign": "CAR",
            "position": [_lat, _lon, _alt],
            "vel_v": 0.0,
            "heading": _heading,
            "heading_valid": _heading_valid,
            "heading_status": _heading_status,
            "speed": _speed,
    }

    if 'replay_time' in data:
        # We are getting data from a log file replay, make sure to pass this on
        _replay_time = parse(data['replay_time'])
        _replay_time_str = _replay_time.strftime("%Y-%m-%d %H:%M:%SZ")
        _car_telem['replay_time'] = _replay_time_str

    # Add in some additional status fields if we have them.
    if 'numSV' in data:
        _car_telem['numSV'] = data['numSV']

    # Push the new car position to the web client
    flask_emit_event(
        "telemetry_event",
        _car_telem
    )

    # Update the Online Position Uploader, if one exists.
    if online_uploader != None:
        online_uploader.update_position(data)

    # Update the bearing store with the current car state (position & bearing)
    if bearing_store != None:
        bearing_store.update_car_position(_state)

    # Add the car position to the logger, but only if we are moving (>10kph = ~3m/s)
    # .. or if are receving bearing data, in which case we want to store high resolution position data.
    if ( (_speed > 3.0) or bearing_mode) and chase_logger:
        _car_position_update["speed"] = _speed
        _car_position_update["heading"] = _heading
        chase_logger.add_car_position(_car_position_update)


def udp_listener_bearing_callback(data):
    global bearing_store, bearing_mode, chase_logger

    if bearing_store != None:
        bearing_store.add_bearing(data)
        bearing_mode = True
        if chase_logger:
            chase_logger.add_bearing(data)



@socketio.on("add_manual_bearing", namespace="/chasemapper")
def add_manual_bearing(data):
    # Add a user-supplied bearing from the web interface
    udp_listener_bearing_callback(data)


# Data Age Monitoring Thread
data_monitor_thread_running = True


def check_data_age():
    """ Regularly check the age of the payload data, and clear if latest position is older than X minutes."""
    global current_payloads, chasemapper_config, predictor_semaphore

    while data_monitor_thread_running:
        _now = time.time()
        _callsigns = list(current_payloads.keys())

        for _call in _callsigns:
            try:
                _latest_time = current_payloads[_call]["telem"]["server_time"]
                if (_now - _latest_time) > (
                    chasemapper_config["payload_max_age"] * 60.0
                ):
                    # Data is older than our maximum age!
                    # Make sure we do not have a predictor cycle running.
                    while predictor_semaphore:
                        time.sleep(0.1)

                    # Remove this payload from our global data stores.
                    current_payloads.pop(_call)
                    current_payload_tracks.pop(_call)

                    logging.info(
                        "Payload %s telemetry older than maximum age - removed from data store."
                        % _call
                    )
            except Exception as e:
                logging.error("Error checking payload data age - %s" % str(e))

        time.sleep(2)


def start_listeners(profile):
    """ Stop any currently running listeners, and startup a set of data listeners based on the supplied profile 
    
    Args:
        profile (dict): A dictionary containing:
            'name' (str): Profile name
            'telemetry_source_type' (str): Data source type (ozimux or horus_udp)
            'telemetry_source_port' (int): Data source port
            'car_source_type' (str): Car Position source type (none, horus_udp, gpsd, or station)
            'car_source_port' (int): Car Position source port
            'online_tracker' (str): Which online tracker to upload chase-car info to ('sondehub' or 'sondehubamateur')
    """
    global data_listeners, current_profile, online_uploader, chasemapper_config

    current_profile = profile

    # Stop any existing listeners.
    for _thread in data_listeners:
        try:
            _thread.close()
        except Exception as e:
            logging.error("Error closing thread - %s" % str(e))

    # Shut-down any online uploaders
    if online_uploader != None:
        online_uploader.close()
        online_uploader = None

    # Reset the listeners array.
    data_listeners = []

    # Start up a new online uploader immediately if uploading is already enabled.
    if chasemapper_config["habitat_upload_enabled"] == True:
        if profile["online_tracker"] == "habitat":
            logging.error(
                "Habitat uploader now deprecated due to Habitat retirement, not starting uploader."
            )
        elif profile["online_tracker"] == "sondehub":
            online_uploader = SondehubChaseUploader(
                update_rate=chasemapper_config["habitat_update_rate"],
                callsign=chasemapper_config["habitat_call"],
            )
        elif profile["online_tracker"] == "sondehubamateur":
            online_uploader = SondehubChaseUploader(
                update_rate=chasemapper_config["habitat_update_rate"],
                callsign=chasemapper_config["habitat_call"],
                amateur=True
            )
        else:
            logging.error(
                "Unknown Online Tracker %s, not starting uploader"
                % (profile["online_tracker"])
            )

    # Start up a OziMux listener, if we are using one.
    if profile["telemetry_source_type"] == "ozimux":
        logging.info(
            "Using OziMux data source on UDP Port %d" % profile["telemetry_source_port"]
        )
        _ozi_listener = OziListener(
            telemetry_callback=ozi_listener_callback,
            port=profile["telemetry_source_port"],
        )
        data_listeners.append(_ozi_listener)

    # Start up UDP Broadcast Listener (which we use for car positions even if not for the payload)

    # Case 1 - Both telemetry and car position sources are set to horus_udp, and have the same port set. Only start a single UDP listener
    if (
        (profile["telemetry_source_type"] == "horus_udp")
        and (profile["car_source_type"] == "horus_udp")
        and (profile["car_source_port"] == profile["telemetry_source_port"])
    ):
        # In this case, we start a single Horus UDP listener.
        logging.info(
            "Starting single Horus UDP listener on port %d"
            % profile["telemetry_source_port"]
        )
        _telem_horus_udp_listener = UDPListener(
            summary_callback=udp_listener_summary_callback,
            gps_callback=udp_listener_car_callback,
            bearing_callback=udp_listener_bearing_callback,
            port=profile["telemetry_source_port"],
        )
        _telem_horus_udp_listener.start()
        data_listeners.append(_telem_horus_udp_listener)

    else:
        if profile["telemetry_source_type"] == "horus_udp":
            # Telemetry via Horus UDP - Start up a listener
            logging.info(
                "Starting Telemetry Horus UDP listener on port %d"
                % profile["telemetry_source_port"]
            )
            _telem_horus_udp_listener = UDPListener(
                summary_callback=udp_listener_summary_callback,
                gps_callback=None,
                bearing_callback=udp_listener_bearing_callback,
                port=profile["telemetry_source_port"],
            )
            _telem_horus_udp_listener.start()
            data_listeners.append(_telem_horus_udp_listener)

        if profile["car_source_type"] == "horus_udp":
            # Car Position via Horus UDP - Start up a listener
            logging.info(
                "Starting Car Position Horus UDP listener on port %d"
                % profile["car_source_port"]
            )
            _car_horus_udp_listener = UDPListener(
                summary_callback=None,
                gps_callback=udp_listener_car_callback,
                bearing_callback=udp_listener_bearing_callback,
                port=profile["car_source_port"],
            )
            _car_horus_udp_listener.start()
            data_listeners.append(_car_horus_udp_listener)

        elif profile["car_source_type"] == "gpsd":
            # GPSD Car Position Source
            logging.info("Starting GPSD Car Position Listener.")
            _gpsd_gps = GPSDAdaptor(
                hostname=chasemapper_config["car_gpsd_host"],
                port=chasemapper_config["car_gpsd_port"],
                callback=udp_listener_car_callback,
            )
            data_listeners.append(_gpsd_gps)

        elif profile["car_source_type"] == "serial":
            # Serial GPS Source.
            logging.info("Starting Serial GPS Listener.")
            _serial_gps = SerialGPS(
                serial_port=chasemapper_config["car_serial_port"],
                serial_baud=chasemapper_config["car_serial_baud"],
                callback=udp_listener_car_callback,
            )
            data_listeners.append(_serial_gps)

        elif profile["car_source_type"] == "station":
            logging.info("Using Stationary receiver position.")

        else:
            # No Car position.
            logging.info("No car position data source.")


@socketio.on("profile_change", namespace="/chasemapper")
def profile_change(data):
    """ Client has requested a profile change """
    global chasemapper_config
    logging.info("Client requested change to profile: %s" % data)

    # Change the profile, and restart the listeners.
    chasemapper_config["selected_profile"] = data
    start_listeners(
        chasemapper_config["profiles"][chasemapper_config["selected_profile"]]
    )

    # Update all clients with the new profile selection
    flask_emit_event("server_settings_update", chasemapper_config)


@socketio.on("device_position", namespace="/chasemapper")
def device_position_update(data):
    """ Accept a device position update from a client and process it as if it was a chase car position """
    try:
        udp_listener_car_callback(data)
    except:
        pass


class WebHandler(logging.Handler):
    """ Logging Handler for sending log messages via Socket.IO to a Web Client """

    def emit(self, record):
        """ Emit a log message via SocketIO """
        # Deal with log records with no content.
        if record.msg:
            if "socket.io" not in record.msg:
                # Convert log record into a dictionary
                log_data = {
                    "level": record.levelname,
                    "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "msg": record.msg,
                }
                # Emit to all socket.io clients
                socketio.emit("log_event", log_data, namespace="/chasemapper")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default="horusmapper.cfg",
        help="Configuration file.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", default=False, help="Verbose output."
    )
    parser.add_argument(
        "-l",
        "--log",
        type=str,
        default=None,
        help="Custom log file name. (Default: ./log_files/<timestamp>.log",
    )
    parser.add_argument(
        "--nolog", action="store_true", default=False, help="Inhibit all logging."
    )
    args = parser.parse_args()

    # Configure logging
    if args.verbose:
        _log_level = logging.DEBUG
    else:
        _log_level = logging.INFO

    logging.basicConfig(
        format="%(asctime)s %(levelname)s:%(message)s",
        stream=sys.stdout,
        level=_log_level,
    )
    # Make flask & socketio only output errors, not every damn GET request.
    logging.getLogger("requests").setLevel(logging.CRITICAL)
    logging.getLogger("urllib3").setLevel(logging.CRITICAL)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    logging.getLogger("socketio").setLevel(logging.ERROR)
    logging.getLogger("engineio").setLevel(logging.ERROR)

    web_handler = WebHandler()
    logging.getLogger().addHandler(web_handler)

    # Start the Chase Logger (if logging not inhibited.)
    if not args.nolog:
        chase_logger = ChaseLogger(filename=args.log)
    else:
        logging.info("Chase Logging has been inhibited, not starting logger.")

    # Attempt to read in config file.
    chasemapper_config = read_config(args.config)
    # Die if we cannot read a valid config file.
    if chasemapper_config == None:
        logging.critical("Could not read configuration data. Exiting")
        sys.exit(1)

    # Add in Chasemapper version information.
    chasemapper_config["version"] = CHASEMAPPER_VERSION

    # Copy out the predictor settings to another dictionary.
    pred_settings = {
        "pred_binary": chasemapper_config["pred_binary"],
        "gfs_path": chasemapper_config["pred_gfs_directory"],
        "pred_model_download": chasemapper_config["pred_model_download"],
    }

    # Copy out Offline Map Settings
    map_settings = {
        "tile_server_enabled": chasemapper_config["tile_server_enabled"],
        "tile_server_path": chasemapper_config["tile_server_path"],
    }

    # Initialise Bearing store
    bearing_store = Bearings(
        socketio_instance=socketio,
        max_bearings=chasemapper_config["max_bearings"],
        max_bearing_age=chasemapper_config["max_bearing_age"],
    )

    # Set speed gate for car position object
    car_track.heading_gate_threshold = chasemapper_config["car_speed_gate"]
    car_track.turn_rate_threshold = chasemapper_config["turn_rate_threshold"]

    # Start listeners using the default profile selection.
    start_listeners(
        chasemapper_config["profiles"][chasemapper_config["selected_profile"]]
    )

    # Start up the predictor, if enabled.
    if chasemapper_config["pred_enabled"]:
        initPredictor()

    # Read in last known position, if enabled

    if chasemapper_config["reload_last_position"]:
        logging.info("Read in last position requested")
        try:
            handle_new_payload_position(read_last_balloon_telemetry(), False)
        except Exception as e:
            logging.warning("Unable to read in last position")
    else:
        logging.debug("Read in last position not requested")

    # Start up the data age monitor thread.
    _data_age_monitor = Thread(target=check_data_age)
    _data_age_monitor.start()

    # Run the Flask app, which will block until CTRL-C'd.
    logging.info(
        "Starting Chasemapper Server on: http://%s:%d/"
        % (chasemapper_config["flask_host"], chasemapper_config["flask_port"])
    )
    try:
        socketio.run(
            app,
            host=chasemapper_config["flask_host"],
            port=chasemapper_config["flask_port"],
            allow_unsafe_werkzeug=True
        )
    except TypeError as e:
        print(e)
        logging.debug("Not using allow_unsafe_werkzeug argument.")
        socketio.run(
            app,
            host=chasemapper_config["flask_host"],
            port=chasemapper_config["flask_port"]
        ) 

    # Close the predictor and data age monitor threads.
    predictor_thread_running = False
    data_monitor_thread_running = False

    # Close the chase logger
    if chase_logger:
        chase_logger.close()

    if online_uploader != None:
        online_uploader.close()

    # Attempt to close the running listeners.
    for _thread in data_listeners:
        try:
            _thread.close()
        except Exception as e:
            logging.error("Error closing thread - %s" % str(e))
