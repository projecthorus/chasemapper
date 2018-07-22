#!/usr/bin/env python2.7
#
#   Project Horus - Browser-Based Chase Mapper
#
#   Copyright (C) 2018  Mark Jessop <vk5qi@rfhead.net>
#   Released under GNU GPL v3 or later
#
import json
import logging
import flask
from flask_socketio import SocketIO
import sys
import time
import traceback
from threading import Thread
from datetime import datetime, timedelta
from dateutil.parser import parse
from horuslib import *
from horuslib.geometry import *
from horuslib.atmosphere import time_to_landing
from horuslib.listener import OziListener, UDPListener
from horuslib.earthmaths import *
from chasemapper.config import *
from chasemapper.predictor import predictor_spawn_download, model_download_running


# Define Flask Application, and allow automatic reloading of templates for dev work
app = flask.Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True

# SocketIO instance
socketio = SocketIO(app)



# Global stores of data.

# These settings are shared between server and all clients, and are updated dynamically.
chasemapper_config = {}

# These settings are not editable by the client!
pred_settings = {}

# Payload data Stores
current_payloads = {} #  Archive data which will be passed to the web client
current_payload_tracks = {} # Store of payload Track objects which are used to calculate instantaneous parameters.

# Chase car position
car_track = GenericTrack()


#
#   Flask Routes
#

@app.route("/")
def flask_index():
    """ Render main index page """
    return flask.render_template('index.html')


@app.route("/get_telemetry_archive")
def flask_get_telemetry_archive():
    return json.dumps(current_payloads)


@app.route("/get_config")
def flask_get_config():
    return json.dumps(chasemapper_config)


def flask_emit_event(event_name="none", data={}):
    """ Emit a socketio event to any clients. """
    socketio.emit(event_name, data, namespace='/chasemapper') 


@socketio.on('client_settings_update', namespace='/chasemapper')
def client_settings_update(data):
    global chasemapper_config

    _predictor_change = "none"
    if (chasemapper_config['pred_enabled'] == False) and (data['pred_enabled'] == True):
        _predictor_change = "restart"
    elif (chasemapper_config['pred_enabled'] == True) and (data['pred_enabled'] == False):
        _predictor_change = "stop"

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


    # Push settings back out to all clients.
    flask_emit_event('server_settings_update', chasemapper_config)



def handle_new_payload_position(data):

    _lat = data['lat']
    _lon = data['lon']
    _alt = data['alt']
    _time_dt = data['time_dt']
    _callsign = data['callsign']
    
    _short_time = _time_dt.strftime("%H:%M:%S")

    if _callsign not in current_payloads:
        # New callsign! Create entries in data stores.
        current_payload_tracks[_callsign] = GenericTrack()

        current_payloads[_callsign] = {
            'telem': {'callsign': _callsign, 'position':[_lat, _lon, _alt], 'vel_v':0.0, 'speed':0.0, 'short_time':_short_time, 'time_to_landing':"", 'server_time':time.time()},
            'path': [],
            'pred_path': [],
            'pred_landing': [],
            'burst': [],
            'abort_path': [],
            'abort_landing': []
        }

    # Add new data into the payload's track, and get the latest ascent rate.
    current_payload_tracks[_callsign].add_telemetry({'time': _time_dt, 'lat':_lat, 'lon': _lon, 'alt':_alt, 'comment':_callsign})
    _state = current_payload_tracks[_callsign].get_latest_state()
    if _state != None:
        _vel_v = _state['ascent_rate']
        _speed = _state['speed']
        # If this payload is in descent, calculate the time to landing.

        if _vel_v < 0.0:
            # Try and get the altitude of the chase car - we use this as the expected 'ground' level.
            _car_state = car_track.get_latest_state()
            if _car_state != None:
                _ground_asl = _car_state['alt']
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
                _ttl = "%02d:%02d" % (_min,_sec)
        else:
            _ttl = ""

    else:
        _vel_v = 0.0
        _ttl = ""

    # Now update the main telemetry store.
    current_payloads[_callsign]['telem'] = {
        'callsign': _callsign, 
        'position':[_lat, _lon, _alt], 
        'vel_v':_vel_v,
        'speed':_speed,
        'short_time':_short_time,
        'time_to_landing': _ttl,
        'server_time':time.time()}

    current_payloads[_callsign]['path'].append([_lat, _lon, _alt])

    # Update the web client.
    flask_emit_event('telemetry_event', current_payloads[_callsign]['telem'])


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
        for i in range(int(chasemapper_config['pred_update_rate'])):
            time.sleep(1)
            if predictor_thread_running == False:
                break

    logging.info("Closed predictor loop.")


def run_prediction():
    ''' Run a Flight Path prediction '''
    global chasemapper_config, current_payloads, current_payload_tracks, predictor

    if (predictor == None) or (chasemapper_config['pred_enabled'] == False):
        return

    # Set the semaphore so we don't accidentally kill the predictor object while it's running.
    predictor_semaphore = True
    for _payload in current_payload_tracks:

        # Check the age of the data.
        # No point re-running the predictor if the data is older than 30 seconds.
        _pos_age = current_payloads[_payload]['telem']['server_time']
        if (time.time()-_pos_age) > 30.0:
            logging.debug("Skipping prediction for %s due to old data." % _payload)
            continue

        _current_pos = current_payload_tracks[_payload].get_latest_state()
        _current_pos_list = [0,_current_pos['lat'], _current_pos['lon'], _current_pos['alt']]

        _pred_ok = False
        _abort_pred_ok = False

        if _current_pos['is_descending']:
            _desc_rate = _current_pos['landing_rate']
        else:
            _desc_rate = chasemapper_config['pred_desc_rate']

        if _current_pos['alt'] > chasemapper_config['pred_burst']:
            _burst_alt = _current_pos['alt'] + 100
        else:
            _burst_alt = chasemapper_config['pred_burst']

        logging.info("Running Predictor for: %s." % _payload)
        _pred_path = predictor.predict(
                launch_lat=_current_pos['lat'],
                launch_lon=_current_pos['lon'],
                launch_alt=_current_pos['alt'],
                ascent_rate=_current_pos['ascent_rate'],
                descent_rate=_desc_rate,
                burst_alt=_burst_alt,
                launch_time=_current_pos['time'],
                descent_mode=_current_pos['is_descending'])

        if len(_pred_path) > 1:
            # Valid Prediction!
            _pred_path.insert(0,_current_pos_list)
            # Convert from predictor output format to a polyline.
            _pred_output = []
            for _point in _pred_path:
                _pred_output.append([_point[1], _point[2], _point[3]])

            current_payloads[_payload]['pred_path'] = _pred_output
            current_payloads[_payload]['pred_landing'] = _pred_output[-1]

            if _current_pos['is_descending']:
                current_payloads[_payload]['burst'] = []
            else:
                # Determine the burst position.
                _cur_alt = 0.0
                _cur_idx = 0
                for i in range(len(_pred_output)):
                    if _pred_output[i][2]>_cur_alt:
                        _cur_alt = _pred_output[i][2]
                        _cur_idx = i

                current_payloads[_payload]['burst'] = _pred_output[_cur_idx]

            _pred_ok = True
            logging.info("Prediction Updated, %d data points." % len(_pred_path))
        else:
            current_payloads[_payload]['pred_path'] = []
            current_payloads[_payload]['pred_landing'] = []
            current_payloads[_payload]['burst'] = []
            logging.error("Prediction Failed.")

        # Abort predictions
        if chasemapper_config['show_abort'] and (_current_pos['alt'] < chasemapper_config['pred_burst']) and (_current_pos['is_descending'] == False):
            logging.info("Running Abort Predictor for: %s." % _payload)

            _abort_pred_path = predictor.predict(
                    launch_lat=_current_pos['lat'],
                    launch_lon=_current_pos['lon'],
                    launch_alt=_current_pos['alt'],
                    ascent_rate=_current_pos['ascent_rate'],
                    descent_rate=_desc_rate,
                    burst_alt=_current_pos['alt']+200,
                    launch_time=_current_pos['time'],
                    descent_mode=_current_pos['is_descending'])

            if len(_pred_path) > 1:
                # Valid Prediction!
                _abort_pred_path.insert(0,_current_pos_list)
                # Convert from predictor output format to a polyline.
                _abort_pred_output = []
                for _point in _abort_pred_path:
                    _abort_pred_output.append([_point[1], _point[2], _point[3]])

                current_payloads[_payload]['abort_path'] = _abort_pred_output
                current_payloads[_payload]['abort_landing'] = _abort_pred_output[-1]

                _abort_pred_ok = True
                logging.info("Abort Prediction Updated, %d data points." % len(_pred_path))
            else:
                logging.error("Prediction Failed.")
                current_payloads[_payload]['abort_path'] = []
                current_payloads[_payload]['abort_landing'] = []
        else:
            # Zero the abort path and landing
            current_payloads[_payload]['abort_path'] = []
            current_payloads[_payload]['abort_landing'] = []

        predictor_semaphore = False

        # Send the web client the updated prediction data.
        if _pred_ok or _abort_pred_ok:
            _client_data = {
                'callsign': _payload,
                'pred_path': current_payloads[_payload]['pred_path'],
                'pred_landing': current_payloads[_payload]['pred_landing'],
                'burst': current_payloads[_payload]['burst'],
                'abort_path': current_payloads[_payload]['abort_path'],
                'abort_landing': current_payloads[_payload]['abort_landing']
            }
            flask_emit_event('predictor_update', _client_data)


def initPredictor():
    global predictor, predictor_thread, chasemapper_config, pred_settings
    try:
        from cusfpredict.predict import Predictor
        from cusfpredict.utils import gfs_model_age, available_gfs
        
        # Check if we have any GFS data
        _model_age = gfs_model_age(pred_settings['gfs_path'])
        if _model_age == "Unknown":
            logging.error("No GFS data in directory.")
            chasemapper_config['pred_model'] = "No GFS Data."
            flask_emit_event('predictor_model_update',{'model':"No GFS data."})
            chasemapper_config['pred_enabled'] = False
        else:
            # Check model contains data to at least 4 hours into the future.
            (_model_start, _model_end) = available_gfs(pred_settings['gfs_path'])
            _model_now = datetime.utcnow() + timedelta(0,60*60*4)
            if (_model_now < _model_start) or (_model_now > _model_end):
                # No suitable GFS data!
                logging.error("GFS Data in directory does not cover now!")
                chasemapper_config['pred_model'] = "Old GFS Data."
                flask_emit_event('predictor_model_update',{'model':"Old GFS data."})
                chasemapper_config['pred_enabled'] = False

            else:
                chasemapper_config['pred_model'] = _model_age
                flask_emit_event('predictor_model_update',{'model':_model_age})
                predictor = Predictor(bin_path=pred_settings['pred_binary'], gfs_path=pred_settings['gfs_path'])

                # Start up the predictor thread if it is not running.
                if predictor_thread == None:
                    predictor_thread = Thread(target=predictorThread)
                    predictor_thread.start()

                # Set the predictor to enabled, and update the clients.
                chasemapper_config['pred_enabled'] = True
        
        flask_emit_event('server_settings_update', chasemapper_config)

    except Exception as e:
        traceback.print_exc()
        logging.error("Loading predictor failed: " + str(e))
        flask_emit_event('predictor_model_update',{'model':"Failed - Check Log."})
        chasemapper_config['pred_model'] = "Failed - Check Log."
        print("Loading Predictor failed.")
        predictor = None


def model_download_finished(result):
    """ Callback for when the model download is finished """
    if result == "OK":
        # Downloader reported OK, restart the predictor.
        initPredictor()
    else:
        # Downloader reported an error, pass on to the client.
        flask_emit_event('predictor_model_update',{'model':result})


@socketio.on('download_model', namespace='/chasemapper')
def download_new_model(data):
    """ Trigger a download of a new weather model """
    global pred_settings, model_download_running
    # Don't action anything if there is a model download already running

    logging.info("Web Client Initiated request for new predictor data.")

    if pred_settings['pred_model_download'] == "none":
        logging.info("No GFS model download command specified.")
        flask_emit_event('predictor_model_update',{'model':"No model download cmd."})
        return
    else:
        _model_cmd = pred_settings['pred_model_download']
        flask_emit_event('predictor_model_update',{'model':"Downloading Model."})

        _status = predictor_spawn_download(_model_cmd, model_download_finished)
        flask_emit_event('predictor_model_update',{'model':_status})



# Data Clearing Functions
@socketio.on('payload_data_clear', namespace='/chasemapper')
def clear_payload_data(data):
    """ Clear the payload data store """
    global predictor_semaphore, current_payloads
    logging.warning("Client requested all payload data be cleared.")
    # Wait until any current predictions have finished running.
    while predictor_semaphore:
        time.sleep(0.1)

    current_payloads = {}
    current_payload_tracks = {}


@socketio.on('car_data_clear', namespace='/chasemapper')
def clear_car_data(data):
    """ Clear out the car position track """
    global car_track
    logging.warning("Client requested all chase car data be cleared.")
    car_track = GenericTrack()


# Incoming telemetry handlers

def ozi_listener_callback(data):
    """ Handle a OziMux input message """
    # OziMux message contains:
    # {'lat': -34.87915, 'comment': 'Telemetry Data', 'alt': 26493.0, 'lon': 139.11883, 'time': datetime.datetime(2018, 7, 16, 10, 55, 49, tzinfo=tzutc())}
    logging.info("OziMux Data:" + str(data))
    output = {}
    output['lat'] = data['lat']
    output['lon'] = data['lon']
    output['alt'] = data['alt']
    output['callsign'] = "Payload"
    output['time_dt'] = data['time']

    handle_new_payload_position(output)


def udp_listener_summary_callback(data):
    ''' Handle a Payload Summary Message from UDPListener '''
    global current_payloads, current_payload_tracks
    # Extract the fields we need.
    logging.info("Payload Summary Data: " + str(data))

    # Convert to something generic we can pass onwards.
    output = {}
    output['lat'] = data['latitude']
    output['lon'] = data['longitude']
    output['alt'] = data['altitude']
    output['callsign'] = "Payload" #  data['callsign'] # Quick hack to limit to a single balloon

    # Process the 'short time' value if we have been provided it.
    if 'time' in data.keys():
        _full_time = datetime.utcnow().strftime("%Y-%m-%dT") + data['time'] + "Z"
        output['time_dt'] = parse(_full_time)
    else:
        # Otherwise use the current UTC time.
        output['time_dt'] = datetime.utcnow()

    handle_new_payload_position(output)


def udp_listener_car_callback(data):
    ''' Handle car position data '''
    global car_track
    logging.debug("Car Position:" + str(data))
    _lat = data['latitude']
    _lon = data['longitude']
    _alt = data['altitude']
    _comment = "CAR"
    _time_dt = datetime.utcnow()

    _car_position_update = {
        'time'  :   _time_dt,
        'lat'   :   _lat,
        'lon'   :   _lon,
        'alt'   :   _alt,
        'comment':  _comment
    }

    car_track.add_telemetry(_car_position_update)

    _state = car_track.get_latest_state()
    _heading = _state['heading']

    # Push the new car position to the web client
    flask_emit_event('telemetry_event', {'callsign': 'CAR', 'position':[_lat,_lon,_alt], 'vel_v':0.0, 'heading': _heading})


# Add other listeners here...


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", type=str, default="horusmapper.cfg", help="Configuration file.")
    parser.add_argument("-v", "--verbose", action="store_true", default=False, help="Verbose output.")
    args = parser.parse_args()

    # Configure logging
    if args.verbose:
        _log_level = logging.DEBUG
    else:
        _log_level = logging.INFO

    logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', stream=sys.stdout, level=_log_level)
    # Make flask & socketio only output errors, not every damn GET request.
    logging.getLogger("requests").setLevel(logging.CRITICAL)
    logging.getLogger("urllib3").setLevel(logging.CRITICAL)
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    logging.getLogger('socketio').setLevel(logging.ERROR)
    logging.getLogger('engineio').setLevel(logging.ERROR)

    # Attempt to read in config file.
    chasemapper_config = read_config(args.config)
    # Die if we cannot read a valid config file.
    if chasemapper_config == None:
        logging.critical("Could not read any configuration data. Exiting")
        sys.exit(1)

    # Copy out the predictor settings to another dictionary.
    pred_settings = {
        'pred_binary': chasemapper_config['pred_binary'],
        'gfs_path': chasemapper_config['pred_gfs_directory'],
        'pred_model_download': chasemapper_config['pred_model_download']
    }

    running_threads = []

    # Start up the primary data source
    if chasemapper_config['data_source'] == "ozimux":
        logging.info("Using OziMux data source.")
        _ozi_listener = OziListener(telemetry_callback=ozi_listener_callback, port=chasemapper_config['ozimux_port'])
        running_threads.append(_ozi_listener)

    # Start up UDP Broadcast Listener (which we use for car positions even if not for the payload)
    if (chasemapper_config['data_source'] == "horus_udp") or (chasemapper_config['car_gps_source'] == "horus_udp"):
        _horus_udp_port = chasemapper_config['horus_udp_port']
        if chasemapper_config['data_source'] == "horus_udp":
            _summary_callback = udp_listener_summary_callback
        else:
            _summary_callback = None

        if chasemapper_config['car_gps_source'] == "horus_udp":
            logging.info("Listening for Chase Car position via Horus UDP.")
            _gps_callback = udp_listener_car_callback
        else:
            _gps_callback = None

        logging.info("Starting Horus UDP Listener")
        _horus_udp_listener = UDPListener(summary_callback=_summary_callback,
                                            gps_callback=_gps_callback)
        _horus_udp_listener.start()
        running_threads.append(_horus_udp_listener)


    if chasemapper_config['pred_enabled']:
        initPredictor()

    # Run the Flask app, which will block until CTRL-C'd.
    socketio.run(app, host=chasemapper_config['flask_host'], port=chasemapper_config['flask_port'])

    # Attempt to close the listeners.
    predictor_thread_running = False
    for _thread in running_threads:
        try:
            _thread.close()
        except Exception as e:
            logging.error("Error closing thread.")
