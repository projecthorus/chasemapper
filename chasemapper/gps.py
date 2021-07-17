#!/usr/bin/env python
#
#   Project Horus - Browser-Based Chase Mapper
#   GPS Communication Classes
#
#   Copyright (C) 2018  Mark Jessop <vk5qi@rfhead.net>
#   Released under GNU GPL v3 or later
#
import logging
import re
import time
import traceback
from datetime import datetime
from threading import Thread


class SerialGPS(object):
    """
    Read NMEA strings from a serial-connected GPS receiver
    """

    def __init__(
        self,
        serial_port="/dev/ttyUSB0",
        serial_baud=9600,
        timeout=5,
        callback=None,
        uberdebug=False,
        unittest=False,
    ):
        """
        Initialise a SerialGPS object.

        This class assumes the serial-connected GPS outputs GPRMC or GNRMC and GPGGA or GNGGA NMEA strings
        using 8N1 RS232 framing. It also assumes the GPGGA or GNGGA string is send after GPRMC or GNRMC. If this
        is not the case, position data may be up to 1 second out.

        Args:
            serial_port (str): Serial port (i.e. '/dev/ttyUSB0', or 'COM1') to receive data from.
            serial_baud (int): Baud rate.
            timeout (int): Serial port readline timeout (Seconds)
            callback (function): function to pass valid GPS positions to.
                GPS data is passed as a dictionary with fields matching the Horus UDP GPS message:
                packet = {
                    'type' : 'GPS',
                    'latitude': lat,
                    'longitude': lon,
                    'altitude': alt,
                    'speed': speed*3.6, # Convert speed to kph.
                    'valid': position_valid
                }
        """

        self.serial_port = serial_port
        self.serial_baud = serial_baud
        self.timeout = timeout
        self.callback = callback
        self.uberdebug = uberdebug

        # Indication of what the last expected string is.
        self.last_string = "GGA"

        # Current GPS state, in a format which matches the Horus UDP
        # 'Chase Car Position' message.
        # Note that these packets do not contain a timestamp.
        self.gps_state = {
            "type": "GPS",
            "latitude": 0.0,
            "longitude": 0.0,
            "altitude": 0.0,
            "speed": 0.0,
            "fix_status": 0,
            "heading": None,
            "valid": False,
        }

        self.serial_thread_running = False
        self.serial_thread = None
        self.ser = None

        if not unittest:
            self.start()

    def start(self):
        """ Start the GPS thread """
        if self.serial_thread != None:
            return
        else:
            self.serial_thread_running = True
            self.serial_thread = Thread(target=self.gps_thread)
            self.serial_thread.start()

    def close(self):
        """ Stop the GPS thread. """
        self.serial_thread_running = False
        # Wait for the thread to close.
        if self.serial_thread != None:
            self.serial_thread.join()

    def gps_thread(self):
        """ 
        Attempt to connect to a serial port and read lines of text from it.
        Pass all lines on to the NMEA parser function.
        """

        try:
            import serial
        except ImportError:
            logging.critical("Could not import pyserial library!")
            return

        while self.serial_thread_running:
            # Attempt to connect to the serial port.
            while self.ser == None and self.serial_thread_running:
                try:
                    self.ser = serial.Serial(
                        port=self.serial_port,
                        baudrate=self.serial_baud,
                        timeout=self.timeout,
                    )
                    logging.info(
                        "SerialGPS - Connected to serial port %s" % self.serial_port
                    )
                except Exception as e:
                    # Continue re-trying until we can connect to the serial port.
                    # This should let the user connect the gps *after* this object if instantiated if required.
                    logging.error("SerialGPS - Serial Port Error: %s" % e)
                    logging.error(
                        "SerialGPS - Sleeping 10s before attempting re-connect."
                    )
                    time.sleep(10)
                    self.ser = None
                    continue

            # Read a line of (hopefully) NMEA from the serial port.
            try:
                data = self.ser.readline()
            except:
                # If we hit a serial read error, attempt to reconnect.
                logging.error(
                    "SerialGPS - Error reading from serial device! Attempting to reconnect."
                )
                self.ser = None
                continue

            # Attempt to parse data.
            try:
                self.parse_nmea(data.decode("ascii"))
            except ValueError:
                logging.debug(
                    "SerialGPS - ValueError when attempting to parse data. GPS may not have lock"
                )
            except:
                traceback.print_exc()
                pass

        # Clean up before exiting thread.
        try:
            self.ser.close()
        except:
            pass
        logging.info("SerialGPS - Closing Thread.")

    def dm_to_sd(self, dm):
        """
        Converts a geographic coordiante given in "degres/minutes" dddmm.mmmm
        format (ie, "12319.943281" = 123 degrees, 19.953281 minutes) to a signed
        decimal (python float) format.
        Courtesy of https://github.com/Knio/pynmea2/
        """
        # '12319.943281'
        if not dm or dm == "0":
            return 0.0

        d, m = re.match(r"^(\d+)(\d\d\.\d+)$", dm).groups()
        return float(d) + float(m) / 60

    def parse_nmea(self, data):
        """
        Attempt to parse a line of NMEA data.
        If we have received a GPGGA or GNGGA string containing a position valid flag,
        send the data on to the callback function.
        """
        if self.uberdebug:
            print(data.strip())

        if ("$GPRMC" in data) or ("$GNRMC" in data):
            logging.debug("SerialGPS - Got GPRMC or GNRMC.")
            gprmc = data.split(",")
            gprmc_lat = self.dm_to_sd(gprmc[3])
            gprmc_latns = gprmc[4]
            gprmc_lon = self.dm_to_sd(gprmc[5])
            gprmc_lonew = gprmc[6]
            gprmc_speed = float(gprmc[7])

            if gprmc_latns == "S":
                self.gps_state["latitude"] = gprmc_lat * -1.0
            else:
                self.gps_state["latitude"] = gprmc_lat

            if gprmc_lonew == "W":
                self.gps_state["longitude"] = gprmc_lon * -1.0
            else:
                self.gps_state["longitude"] = gprmc_lon

            self.gps_state["speed"] = gprmc_speed * 0.51444 * 3.6

        elif ("$GPGGA" in data) or ("$GNGGA" in data):
            logging.debug("SerialGPS - Got GPGGA or GNGGA.")
            gpgga = data.split(",")
            gpgga_lat = self.dm_to_sd(gpgga[2])
            gpgga_latns = gpgga[3]
            gpgga_lon = self.dm_to_sd(gpgga[4])
            gpgga_lonew = gpgga[5]
            gpgga_fixstatus = int(gpgga[6])
            self.gps_state["fix_status"] = gpgga_fixstatus
            self.gps_state["altitude"] = float(gpgga[9])

            if gpgga_latns == "S":
                self.gps_state["latitude"] = gpgga_lat * -1.0
            else:
                self.gps_state["latitude"] = gpgga_lat

            if gpgga_lonew == "W":
                self.gps_state["longitude"] = gpgga_lon * -1.0
            else:
                self.gps_state["longitude"] = gpgga_lon

            if gpgga_fixstatus == 0:
                self.gps_state["valid"] = False
            else:
                self.gps_state["valid"] = True
            
            if self.last_string == "GGA":
                self.send_to_callback()
        
        elif ("$GPTHS" in data) or ("$GNTHS" in data):
            # Very basic handling of the uBlox NEO-M8U-provided True heading data.
            # This data *appears* to be the output of the fused solution, once the system
            # has self-calibrated. 
            # The GNTHS message can be enabled on the USB port by sending: $PUBX,40,THS,0,0,0,1,0,0*55\r\n
            # to the GPS.
            logging.debug("SerialGPS - Got Heading Info (GNTHS).")
            gnths = data.split(",")
            try:
                if len(gnths[1]) > 0:
                    # Data is present in the heading field, try and parse it.
                    gnths_heading = float(gnths[1])
                    # Get the heading validity field.
                    gnths_valid = gnths[2]

                    if gnths_valid != "V":
                        # Treat anything other than 'V' as a valid heading
                        self.gps_state["heading"] = gnths_heading
                    else:
                        self.gps_state["heading"] = None
                else:
                    # Blank field, which means data is not valid.
                    self.gps_state["heading"] = None


                # Assume that if we are receiving GNTHS strings, that they are the last in the batch.
                # Stop sending data when we get a GGA string.
                self.last_string = "THS"

                # Send to callback if we have lock.
                if self.gps_state["fix_status"] != 0:
                    self.send_to_callback()

            except:
                # Failed to parse field, which probably means an invalid heading.
                logging.debug(f"Failed to parse GNTHS: {data}")
                # Invalidate the heading data, and revert to emitting messages on GGA strings.
                self.gps_state["heading"] = None
                self.last_string = "GGA"
                
        else:
            # Discard all other lines
            pass

    def send_to_callback(self):
        """
        Send the current GPS data snapshot onto the callback function,
        if one exists.
        """
        # Generate a copy of the gps state
        _state = self.gps_state.copy()

        if _state["heading"] is None:
            _state.pop("heading")

        # Attempt to pass it onto the callback function.
        if self.callback != None:
            try:
                self.callback(_state)
            except Exception as e:
                traceback.print_exc()
                logging.error(
                    "SerialGPS - Error Passing data to callback - %s" % str(e)
                )


class GPSDGPS(object):
    """ Read GPS data from a GPSD server """

    def __init__(self, hostname="127.0.0.1", port=2947, callback=None):
        """ Init """
        pass


if __name__ == "__main__":
    #
    #   GPS Parser Test Script
    #   Call with either:
    #   $ python -m chasemapper.gps /dev/ttyUSB0
    #   or
    #   $ python -m chasemapper.gps /path/to/nmea_log.txt
    #
    import sys, time

    logging.basicConfig(
        format="%(asctime)s %(levelname)s:%(message)s", level=logging.DEBUG
    )
    _port = sys.argv[1]
    _baud = 9600

    def print_data(data):
        print(data)

    if "tty" not in _port:
        unittest = True
    else:
        unittest = False

    _gps = SerialGPS(
        serial_port=_port,
        serial_baud=_baud,
        callback=print_data,
        uberdebug=True,
        unittest=unittest,
    )

    if unittest:
        _f = open(_port, "r")
        for line in _f:
            _gps.parse_nmea(line)
            time.sleep(0.2)
        _f.close()
    else:
        time.sleep(100)
    _gps.close()
