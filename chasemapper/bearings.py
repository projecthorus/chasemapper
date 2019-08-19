#!/usr/bin/env python
#
#   Project Horus - Bearing Handler
#
#   Copyright (C) 2019  Mark Jessop <vk5qi@rfhead.net>
#   Released under GNU GPL v3 or later
#
#   
#   TODO:
#       [ ] Store a rolling buffer of car positions, to enable fusing of 'old' bearings with previous car positions.
#

import logging
import time

from threading import Lock


class Bearings(object):


    def __init__(self,
        socketio_instance = None,
        max_bearings = 300,
        max_bearing_age = 30*60
        ):


        # Reference to the socketio instance which will be used to pass data onto web clients
        self.sio = socketio_instance
        self.max_bearings = max_bearings
        self.max_age = max_bearing_age


        # Bearing store
        # Bearings are stored as a dict, with the key being the timestamp (time.time())
        # when the bearing arrived in the system.
        # Each record contains:
        # {
        #   'timestamp': time.time(), # A copy of the arrival timestamp
        #   'src_timestamp': time.time(), # Optional timestamp provided by the source
        #   'lat': 0.0, # Bearing start latitude
        #   'lon': 0.0, # Bearing start longitude
        #   'speed': 0.0, # Car speed at time of bearing arrival
        #   'heading': 0.0, # Car heading at time of bearing arrival
        #   'heading_valid': False, # Indicates if the car heading is considered valid (i.e. was captured while moving)
        #   'raw_bearing': 0.0, # Raw bearing value
        #   'true_bearing': 0.0, # Bearing converted to degrees true
        #   'confidence': 0.0, # Arbitrary confidence value - TBD what ranges this will take.
        # }
        self.bearings = {}

        self.bearing_lock = Lock()


        # Internal record of the chase car position, which is updated with incoming GPS data.
        # If incoming bearings do not contain lat/lon information, we fuse them with this position,
        # as long as it is valid.
        self.current_car_position = {
            'timestamp': None, # System timestamp from time.time()
            'datetime': None, # Datetime object from data source.
            'lat': 0.0,
            'lon': 0.0,
            'alt': 0.0,
            'heading': 0.0,
            'speed': 0.0,
            'heading_valid': False,
            'position_valid': False
        }


    def update_car_position(self, position):
        """ Accept a new car position, in the form of a dictionary produced by a GenericTrack object
            (refer geometry.py). This is of the form:

            _state = {
                'time'  : _latest_position[0],  # Datetime object, with timezone info
                'lat'   : _latest_position[1],
                'lon'   : _latest_position[2],
                'alt'   : _latest_position[3],
                'ascent_rate': self.ascent_rate, # Not used here
                'is_descending': self.is_descending, # Not used here
                'landing_rate': self.landing_rate, # Not used here
                'heading': self.heading, # Movement heading in degrees true
                'heading_valid': self.heading_valid, # Indicates if heading was calculated when the car was moving
                'speed': self.speed # Speed in m/s
            }

        """

        # Attempt to build up new chase car position dict
        try:
            _car_pos = {
                'timestamp': time.time(),
                'datetime': position['time'],
                'lat': position['lat'],
                'lon': position['lon'],
                'alt': position['alt'],
                'heading': self.current_car_position['heading'],
                'heading_valid': position['heading_valid'],
                'speed': position['speed'],
                'position_valid': True # Should we be taking this from upstream somewhere?
            }

            # Only gate through the heading if it is valid.
            if position['heading_valid']:
                _car_pos['heading'] = position['heading']

            # Mark position as invalid if we have zero lat/lon values
            if (_car_pos['lat'] == 0.0) and (_car_pos['lon'] == 0.0):
                _car_pos['position_valid'] = False

            # Replace car position state with new data
            self.current_car_position = _car_pos

        except Exception as e:
            logging.error("Bearing Handler - Invalid car position: %s" % str(e))


    def add_bearing(self, bearing):
        """ Add a bearing into the store, fusing incoming data with the latest car position as required.

        bearing must be a dictionary with the following keys:

        # Absolute bearings - lat/lon and true bearing provided
        {'type': 'BEARING', 'bearing_type': 'absolute', 'latitude': latitude, 'longitude': longitude, 'bearing': bearing}

        # Relative bearings - only relative bearing is provided.
        {'type': 'BEARING', 'bearing_type': 'relative', 'bearing': bearing}

        The following optional fields can be provided:
            'source': An identifier for the source of the bearings, i.e. 'kerberossdr', 'yagi-1'
            'timestamp': A timestamp of the bearing provided by the source.
            'confidence': A confidence value for the bearing, from 0 to [MAX VALUE ??]

        """

        # Should never be passed a non-bearing dict, but check anyway,
        if bearing['type'] != 'BEARING':
            return



        _arrival_time = time.time()

        # Get a copy of the current car position, in case it is updated
        _current_car_pos = self.current_car_position.copy()


        if 'timestamp' in bearing:
            _src_timestamp = bearing['timestamp']
        else:
            _src_timestamp = _arrival_time

        if 'confidence' in bearing:
            _confidence = bearing['confidence']
        else:
            _confidence = 100.0

        if 'power' in bearing:
            _power = bearing['power']
        else:
            _power = -1

        if 'source' in bearing:
            _source = bearing['source']
        else:
            _source = 'unknown'

        try:
            if bearing['bearing_type'] == 'relative':
                # Relative bearing - we need to fuse this with the current car position.

                # Temporary hack for KerberosSDR bearings, which are reflected across N/S
                if _source == 'kerberos-sdr':
                    bearing['bearing'] = 360.0 - bearing['bearing']
                    bearing['raw_doa'] = bearing['raw_doa'][::-1]


                _new_bearing = {
                    'timestamp':    _arrival_time,
                    'src_timestamp': _src_timestamp,
                    'lat':  _current_car_pos['lat'],
                    'lon': _current_car_pos['lon'],
                    'speed': _current_car_pos['speed'],
                    'heading': _current_car_pos['heading'],
                    'heading_valid': _current_car_pos['heading_valid'],
                    'raw_bearing': bearing['bearing'],
                    'true_bearing': (bearing['bearing'] + _current_car_pos['heading']) % 360.0,
                    'confidence': _confidence,
                    'power': _power,
                    'source': _source
                }


            elif bearing['bearing_type'] == 'absolute':
                # Absolute bearing - use the provided data as-is

                _new_bearing = {
                    'timestamp': _arrival_time,
                    'src_timestamp': _src_timestamp,
                    'lat': bearing['latitude'],
                    'lon': bearing['longitude'],
                    'speed': 0.0,
                    'heading': 0.0,
                    'heading_valid': True,
                    'raw_bearing': bearing['bearing'],
                    'true_bearing': bearing['bearing'],
                    'confidence': _confidence,
                    'power': _power,
                    'source': _source
                }


            else:
                return

        except Exception as e:
            logging.error("Bearing Handler - Invalid input bearing: %s" % str(e))
            return

        # We now have our bearing - now we need to store it
        self.bearing_lock.acquire()

        self.bearings["%.4f" % _arrival_time] = _new_bearing

        # Now we need to do a clean-up of our bearing list.
        # At this point, we should always have at least 2 bearings in our store
        if len(self.bearings) == 1:
            self.bearing_lock.release()
            return

        # Keep a list of what we remove, so we can pass it on to the web clients.
        _removal_list = []

        # Grab the list of bearing entries, and sort them by time
        _bearing_list = self.bearings.keys()
        _bearing_list.sort()

        # First remove any excess entries - we only get one bearing at a time, so we can do this simply:
        if len(_bearing_list) > self.max_bearings:
            self.bearings.pop(_bearing_list[0])
            _removal_list.append(_bearing_list[0])
            _bearing_list = _bearing_list[1:]

        # Now we need to remove *old* bearings.
        _min_time = time.time() - self.max_age

        _curr_time = float(_bearing_list[0])

        while _curr_time < _min_time:
            # Current entry is older than our limit, remove it.
            self.bearings.pop(_bearing_list[0])
            _removal_list.append(_bearing_list[0])
            _bearing_list = _bearing_list[1:]

            # Advance to the next entry in the list.
            _curr_time = float(_bearing_list[0])

        self.bearing_lock.release()

        # Add in any raw DOA data we may have been given.
        if 'raw_bearing_angles' in bearing:
            _new_bearing['raw_bearing_angles'] = bearing['raw_bearing_angles']
            _new_bearing['raw_doa'] = bearing['raw_doa']


        # Now we need to update the web clients on what has changed.
        _client_update = {
        'add': _new_bearing,
        'remove': _removal_list,
        'server_timestamp': time.time()
        }

        self.sio.emit('bearing_change', _client_update, namespace='/chasemapper') 


    def flush(self):
        """ Clear the bearing store """
        self.bearing_lock.acquire()
        self.bearings = {}
        self.bearing_lock.release()








