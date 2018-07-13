#!/usr/bin/env python2.7
#
#   Project Horus - Browser-Based Chase Mapper
#
#   Copyright (C) 2018  Mark Jessop <vk5qi@rfhead.net>
#   Released under GNU GPL v3 or later
#
import json
import flask
from flask_socketio import SocketIO
import time
from datetime import datetime
from dateutil.parser import parse
from horuslib import *
from horuslib.geometry import *
from horuslib.listener import OziListener, UDPListener
from horuslib.earthmaths import *


# Define Flask Application, and allow automatic reloading of templates for dev work
app = flask.Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True

# SocketIO instance
socketio = SocketIO(app)



# Global stores of data.

chasemapper_config = {
    # Start location for the map (until either a chase car position, or balloon position is available.)
    'default_lat': -34.9,
    'default_lon': 138.6,

    # Predictor settings
    'pred_enabled': True,  # Enable running and display of predicted flight paths.
    # Default prediction settings (actual values will be used once the flight is underway)
    'pred_asc_rate': 5.0,
    'pred_desc_rate': 6.0,
    'pred_burst': 28000,
    'show_abort': True # Show a prediction of an 'abort' paths (i.e. if the balloon bursts *now*)
    }

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



def udp_listener_summary_callback(data):
    ''' Handle a Payload Summary Message from UDPListener '''
    global current_payloads, current_payload_tracks
    # Extract the fields we need.
    print("SUMMARY:" + str(data))
    _lat = data['latitude']
    _lon = data['longitude']
    _alt = data['altitude']
    _callsign = "Payload" #  data['callsign'] # Quick hack to limit to a single balloon

    # Process the 'short time' value if we have been provided it.
    if 'time' in data.keys():
        _full_time = datetime.utcnow().strftime("%Y-%m-%dT") + data['time'] + "Z"
        _time_dt = parse(_full_time)
    else:
        # Otherwise use the current UTC time.
        _time_dt = datetime.utcnow()

    if _callsign not in current_payloads:
        # New callsign! Create entries in data stores.
        current_payload_tracks[_callsign] = GenericTrack()

        current_payloads[_callsign] = {
            'telem': {'callsign': _callsign, 'position':[_lat, _lon, _alt], 'vel_v':0.0},
            'path': [],
            'pred_path': [],
            'pred_landing': [],
            'abort_path': [],
            'abort_landing': []
        }

    # Add new data into the payload's track, and get the latest ascent rate.
    current_payload_tracks[_callsign].add_telemetry({'time': _time_dt, 'lat':_lat, 'lon': _lon, 'alt':_alt, 'comment':_callsign})
    _state = current_payload_tracks[_callsign].get_latest_state()
    if _state != None:
        _vel_v = _state['ascent_rate']
    else:
        _vel_v = 0.0

    # Now update the main telemetry store.
    current_payloads[_callsign]['telem'] = {'callsign': _callsign, 'position':[_lat, _lon, _alt], 'vel_v':_vel_v}
    current_payloads[_callsign]['path'].append([_lat, _lon, _alt])

    # Update the web client.
    flask_emit_event('telemetry_event', current_payloads[_callsign]['telem'])



def udp_listener_car_callback(data):
    ''' Handle car position data '''
    global car_track
    print("CAR:" + str(data))
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



if __name__ == "__main__":
    import argparse


    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    parser.add_argument("-p","--port",default=5001,help="Port to run Web Server on.")
    group.add_argument("--ozimux", action="store_true", default=False, help="Take payload input via OziMux (listen on port 8942).")
    group.add_argument("--summary", action="store_true", default=True, help="Take payload input data via Payload Summary Broadcasts.")
    parser.add_argument("--clamp", action="store_false", default=True, help="Clamp all tracks to ground.")
    parser.add_argument("--nolabels", action="store_true", default=False, help="Inhibit labels on placemarks.")
    parser.add_argument("--predict", action="store_true", help="Enable Flight Path Predictions.")
    parser.add_argument("--predict_binary", type=str, default="./pred", help="Location of the CUSF predictor binary. Defaut = ./pred")
    parser.add_argument("--burst_alt", type=float, default=30000.0, help="Expected Burst Altitude (m). Default = 30000")
    parser.add_argument("--descent_rate", type=float, default=5.0, help="Expected Descent Rate (m/s, positive value). Default = 5.0")
    parser.add_argument("--abort", action="store_true", default=False, help="Enable 'Abort' Predictions.")
    parser.add_argument("--predict_rate", type=int, default=15, help="Run predictions every X seconds. Default = 15 seconds.")
    args = parser.parse_args()

    # Start up UDP Broadcast Listener (which we use for car positions even if not for the payload)
    if args.summary:
        print("Using Payload Summary Messages.")
        _broadcast_listener = UDPListener(summary_callback=udp_listener_summary_callback,
                                            gps_callback=udp_listener_car_callback)
    else:
        _broadcast_listener = UDPListener(summary_callback=None,
                                            gps_callback=udp_listener_car_callback)

    _broadcast_listener.start()

    # Run the Flask app, which will block until CTRL-C'd.
    socketio.run(app, host='0.0.0.0', port=args.port)

    # Attempt to close the listener.
    _broadcast_listener.close()

