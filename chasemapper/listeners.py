#!/usr/bin/env python
#
#   Project Horus - Browser-Based Chase Mapper
# 	Listeners
#
#   Copyright (C) 2018  Mark Jessop <vk5qi@rfhead.net>
#   Released under GNU GPL v3 or later
#
# 	These classes have been pulled in from the horuslib library, to avoid
# 	requiring horuslib (hopefully soon-to-be retired) as a dependency.

import socket, json, sys, traceback
from threading import Thread
from dateutil.parser import parse
from datetime import datetime, timedelta

MAX_JSON_LEN = 32768


def fix_datetime(datetime_str, local_dt_str=None):
    """
    Given a HH:MM:SS string from an telemetry sentence, produce a complete timestamp, using the current system time as a guide for the date.
    """

    if local_dt_str is None:
        _now = datetime.utcnow()
    else:
        _now = parse(local_dt_str)

    # Are we in the rollover window?
    if _now.hour == 23 or _now.hour == 0:
        _outside_window = False
    else:
        _outside_window = True

    # Append on a timezone indicator if the time doesn't have one.
    if datetime_str.endswith("Z") or datetime_str.endswith("+00:00"):
        pass
    else:
        datetime_str += "Z"

    # Parsing just a HH:MM:SS will return a datetime object with the year, month and day replaced by values in the 'default'
    # argument.
    _telem_dt = parse(datetime_str, default=_now)

    if _outside_window:
        # We are outside the day-rollover window, and can safely use the current zulu date.
        return _telem_dt
    else:
        # We are within the window, and need to adjust the day backwards or forwards based on the sonde time.
        if _telem_dt.hour == 23 and _now.hour == 0:
            # Assume system clock running slightly fast, and subtract a day from the telemetry date.
            _telem_dt = _telem_dt - timedelta(days=1)

        elif _telem_dt.hour == 00 and _now.hour == 23:
            # System clock running slow. Add a day.
            _telem_dt = _telem_dt + timedelta(days=1)

        return _telem_dt


class UDPListener(object):
    """ UDP Broadcast Packet Listener 
    Listens for Horuslib UDP broadcast packets, and passes them onto a callback function
    """

    def __init__(
        self,
        callback=None,
        summary_callback=None,
        gps_callback=None,
        bearing_callback=None,
        port=55672,
    ):

        self.udp_port = port
        self.callback = callback
        self.summary_callback = summary_callback
        self.gps_callback = gps_callback
        self.bearing_callback = bearing_callback

        self.listener_thread = None
        self.s = None
        self.udp_listener_running = False

    def handle_udp_packet(self, packet):
        """ Process a received UDP packet """
        try:
            packet_dict = json.loads(packet)

            if self.callback is not None:
                self.callback(packet_dict)

            if packet_dict["type"] == "PAYLOAD_SUMMARY":
                if self.summary_callback is not None:
                    self.summary_callback(packet_dict)

            if packet_dict["type"] == "PAYLOAD_TELEMETRY":
                if "time_string" in packet_dict.keys():
                    packet_dict["time"] = packet_dict["time_string"]
                if self.summary_callback is not None:
                    self.summary_callback(packet_dict)

            if packet_dict["type"] == "GPS":
                if self.gps_callback is not None:
                    self.gps_callback(packet_dict)

            if packet_dict["type"] == "BEARING":
                if self.bearing_callback is not None:
                    self.bearing_callback(packet_dict)

            if packet_dict["type"] == "MODEM_STATS":
                if self.summary_callback is not None:
                    self.summary_callback(packet_dict)

        except Exception as e:
            print("Could not parse packet: %s" % str(e))
            traceback.print_exc()

    def udp_rx_thread(self):
        """ Listen for Broadcast UDP packets """

        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.settimeout(1)
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except:
            pass
        self.s.bind(("", self.udp_port))
        print("Started UDP Listener Thread.")
        self.udp_listener_running = True

        while self.udp_listener_running:
            try:
                m = self.s.recvfrom(MAX_JSON_LEN)
            except socket.timeout:
                m = None
            except:
                traceback.print_exc()

            if m != None:
                self.handle_udp_packet(m[0])

        print("Closing UDP Listener")
        self.s.close()

    def start(self):
        if self.listener_thread is None:
            self.listener_thread = Thread(target=self.udp_rx_thread)
            self.listener_thread.start()

    def close(self):
        self.udp_listener_running = False
        self.listener_thread.join()


class OziListener(object):
    """
    Listen on a supplied UDP port for OziPlotter-compatible telemetry data.

    Incoming sentences are of the form:
    TELEMETRY.HH:MM:SS,latitude,longitude,altitude\n
    WAYPOINT,waypoint_name,latitude,longitude,comment\n
    """

    allowed_sentences = ["TELEMETRY", "WAYPOINT"]

    def __init__(
        self, hostname="", port=8942, telemetry_callback=None, waypoint_callback=None
    ):

        self.input_host = hostname
        self.input_port = port
        self.telemetry_callback = telemetry_callback
        self.waypoint_callback = waypoint_callback

        self.start()

    def start(self):
        """ Start the UDP Listener Thread. """
        self.udp_listener_running = True

        self.t = Thread(target=self.udp_rx_thread)
        self.t.start()

    def udp_rx_thread(self):
        """
        Listen for incoming UDP packets, and pass them off to another function to be processed.
        """

        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.settimeout(1)
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except:
            pass
        self.s.bind((self.input_host, self.input_port))

        while self.udp_listener_running:
            try:
                m = self.s.recvfrom(1024)
            except socket.timeout:
                m = None
            except:
                traceback.print_exc()

            if m != None:
                try:
                    self.handle_packet(m[0])
                except:
                    traceback.print_exc()
                    print("ERROR: Couldn't handle packet correctly.")
                    pass

        print("INFO: Closing UDP Listener Thread")
        self.s.close()

    def close(self):
        """
        Close the UDP listener thread.
        """
        self.udp_listener_running = False
        try:
            self.t.join()
        except:
            pass

    def handle_telemetry_packet(self, packet):
        """ Split a telemetry packet into time/lat/lon/alt, and pass it onto a callback """

        _fields = packet.split(",")
        _short_time = _fields[1]
        _lat = float(_fields[2])
        _lon = float(_fields[3])
        _alt = float(_fields[4])

        # Timestamp Handling
        # The 'short' timestamp (HH:MM:SS) is always assumed to be in UTC time.
        # To build up a complete datetime object, we use the system's current UTC time, and replace the HH:MM:SS part.
        _full_time = datetime.utcnow().strftime("%Y-%m-%dT") + _short_time + "Z"
        _time_dt = parse(_full_time)

        _time_dt = fix_datetime(_short_time)

        _output = {
            "time": _time_dt,
            "lat": _lat,
            "lon": _lon,
            "alt": _alt,
            "comment": "Telemetry Data",
        }

        self.telemetry_callback(_output)

    def handle_waypoint_packet(self, packet):
        """ Split a 'Waypoint' packet into fields, and pass onto a callback """

        _fields = packet.split(",")
        _waypoint_name = _fields[1]
        _lat = float(_fields[2])
        _lon = float(_fields[3])
        _comment = _fields[4]

        _time_dt = datetime.utcnow()

        _output = {
            "time": _time_dt,
            "name": _waypoint_name,
            "lat": _lat,
            "lon": _lon,
            "comment": _comment,
        }

        self.waypoint_callback(_output)

    def handle_packet(self, packet):
        """
        Check an incoming packet matches a valid type, and then forward it on.
        """

        # Extract header (first field)
        packet_type = packet.split(",")[0]

        if packet_type not in self.allowed_sentences:
            print("ERROR: Got unknown packet: %s" % packet)
            return

        try:
            # Now send on the packet if we are allowed to.
            if packet_type == "TELEMETRY" and (self.telemetry_callback != None):
                self.handle_telemetry_packet(packet)

            # Generally we always want to pass on waypoint data.
            if packet_type == "WAYPOINT" and (self.waypoint_callback != None):
                self.handle_waypoint_packet(packet)

        except:
            print("ERROR: Error when handling packet.")
            traceback.print_exc()
