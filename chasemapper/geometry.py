#!/usr/bin/env python
#
#   Project Horus - Flight Data to Geometry
#
#   Copyright (C) 2018  Mark Jessop <vk5qi@rfhead.net>
#   Released under GNU GPL v3 or later
#
import traceback
import logging
import numpy as np
from .atmosphere import *
from .earthmaths import position_info


class GenericTrack(object):
    """
    A Generic 'track' object, which stores track positions for a payload or chase car.
    Telemetry is added using the add_telemetry method, which takes a dictionary with time/lat/lon/alt keys (at minimum).
    This object performs a running average of the ascent/descent rate, and calculates the predicted landing rate if the payload
    is in descent.
    The track history can be exported to a LineString using the to_line_string method.
    """

    def __init__(
        self, ascent_averaging=6, landing_rate=5.0, heading_gate_threshold=0.0, turn_rate_threshold=4.0
    ):
        """ Create a GenericTrack Object. """

        # Averaging rate.
        self.ASCENT_AVERAGING = ascent_averaging
        # Payload state.
        self.landing_rate = landing_rate
        # Heading gate threshold (only gate headings if moving faster than this value in m/s)
        self.heading_gate_threshold = heading_gate_threshold
        # Turn rate threshold - only gate headings if turning *slower* than this value in degrees/sec
        self.turn_rate_threshold = turn_rate_threshold

        self.ascent_rate = 0.0
        self.heading = 0.0
        self.turn_rate = 100.0
        self.heading_valid = False
        self.speed = 0.0
        self.is_descending = False

        self.supplied_heading = False
        self.heading_status = None


        self.prev_heading = 0.0
        self.prev_time = 0.0

        # Internal store of track history data.
        # Data is stored as a list-of-lists, with elements of [datetime, lat, lon, alt, comment]
        self.track_history = []

    def add_telemetry(self, data_dict):
        """ 
        Accept telemetry data as a dictionary with fields 
        datetime, lat, lon, alt, comment
        """

        try:
            _datetime = data_dict["time"]
            _lat = data_dict["lat"]
            _lon = data_dict["lon"]
            _alt = data_dict["alt"]
            if "comment" in data_dict.keys():
                _comment = data_dict["comment"]
            else:
                _comment = ""

            self.track_history.append([_datetime, _lat, _lon, _alt, _comment])

            # If we have been supplied a 'true' heading with the position, override the state to use that.
            # In this case we are assuming that the heading is being provided by some form of magnetic compass,
            # and is valid even when the car is stationary.
            if "heading" in data_dict:
                # Rotate heading data if we have enough data
                if len(self.track_history) >=2:
                    self.prev_time = self.track_history[-2][0]
                    self.prev_heading = self.heading

                self.heading = data_dict["heading"]
                self.supplied_heading = True

            if "heading_status" in data_dict:
                self.heading_status = data_dict["heading_status"]

            self.update_states()

            return self.get_latest_state()
        except:
            logging.error("Error reading input data: %s" % traceback.format_exc())

    def get_latest_state(self):
        """ Get the latest position of the payload """

        if len(self.track_history) == 0:
            return None
        else:
            _latest_position = self.track_history[-1]
            _state = {
                "time": _latest_position[0],
                "lat": _latest_position[1],
                "lon": _latest_position[2],
                "alt": _latest_position[3],
                "ascent_rate": self.ascent_rate,
                "is_descending": self.is_descending,
                "landing_rate": self.landing_rate,
                "heading": self.heading,
                "heading_valid": self.heading_valid,
                "heading_status": self.heading_status,
                "turn_rate": self.turn_rate,
                "speed": self.speed,
            }
            return _state

    def calculate_ascent_rate(self):
        """ Calculate the ascent/descent rate of the payload based on the available data """
        if len(self.track_history) <= 1:
            return 0.0
        elif len(self.track_history) == 2:
            # Basic ascent rate case - only 2 samples.
            _time_delta = (
                self.track_history[-1][0] - self.track_history[-2][0]
            ).total_seconds()
            _altitude_delta = self.track_history[-1][3] - self.track_history[-2][3]

            if _time_delta == 0:
                logging.warning(
                    "Zero time-step encountered in ascent rate calculation - are multiple receivers reporting telemetry simultaneously?"
                )
                return 0.0
            else:
                return _altitude_delta / _time_delta

        else:
            _num_samples = min(len(self.track_history), self.ASCENT_AVERAGING)
            _asc_rates = []

            for _i in range(-1 * (_num_samples - 1), 0):
                _time_delta = (
                    self.track_history[_i][0] - self.track_history[_i - 1][0]
                ).total_seconds()
                _altitude_delta = (
                    self.track_history[_i][3] - self.track_history[_i - 1][3]
                )
                try:
                    _asc_rates.append(_altitude_delta / _time_delta)
                except ZeroDivisionError:
                    logging.warning(
                        "Zero time-step encountered in ascent rate calculation - are multiple receivers reporting telemetry simultaneously?"
                    )
                    continue
            
            # _mean2_time_delta = (
            #         self.track_history[-1][0] - self.track_history[-1*_num_samples][0]
            #     ).total_seconds()
            
            # _mean2_altitude_delta = (
            #         self.track_history[-1][3] - self.track_history[-1*_num_samples][3]
            #     )
            
            # _asc_rate2 = _mean2_altitude_delta / _mean2_time_delta

            #print(f"asc_rates: {_asc_rates}, Mean: {np.mean(_asc_rates)}")
            return np.mean(_asc_rates)

    def calculate_heading(self):
        """ Calculate the heading of the payload """
        if len(self.track_history) <= 1:
            return 0.0
        else:
            _pos_1 = self.track_history[-2]
            _pos_2 = self.track_history[-1]
            
            # Save previous heading.
            self.prev_heading = self.heading
            self.prev_time = _pos_1[0]

            # Calculate new heading
            try:
                _pos_info = position_info(
                    (_pos_1[1], _pos_1[2], _pos_1[3]), (_pos_2[1], _pos_2[2], _pos_2[3])
                )
            except ValueError:
                logging.debug("Math Domain Error in heading calculation - Identical Sequential Positions")
                return self.heading

            self.heading = _pos_info["bearing"]

            return self.heading


    def calculate_speed(self):
        """ Calculate Payload Speed in metres per second """
        if len(self.track_history) <= 1:
            return 0.0
        else:
            _time_delta = (
                self.track_history[-1][0] - self.track_history[-2][0]
            ).total_seconds()
            _pos_1 = self.track_history[-2]
            _pos_2 = self.track_history[-1]


            try:
                _pos_info = position_info(
                    (_pos_1[1], _pos_1[2], _pos_1[3]), (_pos_2[1], _pos_2[2], _pos_2[3])
                )
            except ValueError:
                logging.debug("Math Domain Error in speed calculation - Identical Sequential Positions")
                return 0.0

            try:
                _speed = _pos_info["great_circle_distance"] / _time_delta
            except ZeroDivisionError:
                logging.warning(
                    "Zero time-step encountered in speed calculation - are multiple receivers reporting telemetry simultaneously?"
                )
                return 0.0

            return _speed


    def calculate_turn_rate(self):
        """ Calculate heading rate based on previous heading and current heading """
        if len(self.track_history) > 2:
            # Grab current time
            _current_time = self.track_history[-1][0]

            _time_delta = (_current_time - self.prev_time).total_seconds()

            _heading_delta = (self.heading - self.prev_heading) % 360.0
            if _heading_delta >= 180.0:
                _heading_delta -= 360.0
            
            self.turn_rate = abs(_heading_delta)/_time_delta

            return self.turn_rate


    def update_states(self):
        """ Update internal states based on the current data """
        self.ascent_rate = self.calculate_ascent_rate()
        self.speed = self.calculate_speed()

        # If we haven't been supplied a heading, calculate one
        if not self.supplied_heading:
            self.heading = self.calculate_heading()

        # Calculate the turn rate
        self.calculate_turn_rate()

        if self.supplied_heading:
            # Heading supplied - only threshold on turn rate.
            if self.turn_rate < self.turn_rate_threshold:
                self.heading_valid = True
            else:
                self.heading_valid = False

        else:
            # Heading calculated - threshold on speed and turn rate.
            if (self.speed > self.heading_gate_threshold) and (self.turn_rate < self.turn_rate_threshold):
                self.heading_valid = True
            else:
                self.heading_valid = False

        self.is_descending = self.ascent_rate < 0.0

        if self.is_descending:
            _current_alt = self.track_history[-1][3]
            self.landing_rate = seaLevelDescentRate(self.ascent_rate, _current_alt)

    def to_polyline(self):
        """ Generate and return a Leaflet PolyLine compatible array """
        # Copy array into a numpy representation for easier slicing.
        if len(self.track_history) == 0:
            return []
        elif len(self.track_history) == 1:
            # LineStrings need at least 2 points. If we only have a single point,
            # fudge it by duplicating the single point.
            _track_data_np = np.array([self.track_history[0], self.track_history[0]])
        else:
            _track_data_np = np.array(self.track_history)
        # Produce new array
        _track_points = np.column_stack(
            (_track_data_np[:, 1], _track_data_np[:, 2], _track_data_np[:, 3])
        )

        return _track_points.tolist()

    def length(self):
        return len(self.track_history)
