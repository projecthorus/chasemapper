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
import traceback
from datetime import datetime
from threading import Thread

class SerialGPS(object):
    '''
    Read NMEA strings from a serial-connected GPS receiver
    '''

    def __init__(self,
        serial_port = '/dev/ttyUSB0',
        serial_baud = 9600,
        timeout = 5,
        callback = None,
        uberdebug = False):
        '''
        Initialise a SerialGPS object.

        This class assumes the serial-connected GPS outputs GPRMC and GPGGA NMEA strings
        using 8N1 RS232 framing. It also assumes the GPGGA string is send after GPRMC. If this
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
        '''

        self.serial_port = serial_port
        self.serial_baud = serial_baud
        self.timeout = timeout
        self.callback = callback
        self.uberdebug = uberdebug

        # Current GPS state, in a format which matches the Horus UDP
        # 'Chase Car Position' message.
        # Note that these packets do not contain a timestamp.
        self.gps_state = {
            'type': 'GPS',
            'latitude': 0.0,
            'longitude': 0.0,
            'altitude': 0.0,
            'speed': 0.0,
            'valid': False
        }

        self.serial_thread_running = False
        self.serial_thread = None
        self.ser = None

        self.start()


    def start(self):
        ''' Start the GPS thread '''
        if self.serial_thread != None:
            return
        else:
            self.serial_thread_running = True
            self.serial_thread = Thread(target=self.gps_thread)
            self.serial_thread.start()


    def close(self):
        ''' Stop the GPS thread. '''
        self.serial_thread_running = False
        # Wait for the thread to close.
        if self.serial_thread != None:
            self.serial_thread.join()


    def gps_thread(self):
        ''' 
        Attempt to connect to a serial port and read lines of text from it.
        Pass all lines on to the NMEA parser function.
        '''

        try:
            import serial
        except ImportError:
            logging.critical("Could not import pyserial library!")
            return


        while self.serial_thread_running:
            # Attempt to connect to the serial port.
            while self.ser == None and self.serial_thread_running:
                try:
                    self.ser = serial.Serial(port=self.serial_port,baudrate=self.serial_baud,timeout=self.timeout)
                    logging.info("SerialGPS - Connected to serial port %s" % self.serial_port)
                except Exception as e:
                    # Continue re-trying until we can connect to the serial port.
                    # This should let the user connect the gps *after* this object if instantiated if required.
                    logging.error("SerialGPS - Serial Port Error: %s" % e)
                    logging.error("SerialGPS - Sleeping 10s before attempting re-connect.")
                    time.sleep(10)
                    self.ser = None
                    continue

            # Read a line of (hopefully) NMEA from the serial port.
            try:
                data = self.ser.readline()
            except:
                # If we hit a serial read error, attempt to reconnect.
                logging.error("SerialGPS - Error reading from serial device! Attempting to reconnect.")
                self.ser = None
                continue

            # Attempt to parse data.
            try:
                self.parse_nmea(data.decode('ascii'))
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
        '''
        Converts a geographic coordiante given in "degres/minutes" dddmm.mmmm
        format (ie, "12319.943281" = 123 degrees, 19.953281 minutes) to a signed
        decimal (python float) format.
        Courtesy of https://github.com/Knio/pynmea2/
        '''
        # '12319.943281'
        if not dm or dm == '0':
            return 0.

        d, m = re.match(r'^(\d+)(\d\d\.\d+)$', dm).groups()
        return float(d) + float(m) / 60


    def parse_nmea(self, data):
        '''
        Attempt to parse a line of NMEA data.
        If we have received a GPGGA string containing a position valid flag,
        send the data on to the callback function.
        '''
        if self.uberdebug:
            print(data.strip())

        if "$GPRMC" in data:
            logging.debug("SerialGPS - Got GPRMC.")
            gprmc = data.split(",")
            gprmc_lat = self.dm_to_sd(gprmc[3])
            gprmc_latns = gprmc[4]
            gprmc_lon = self.dm_to_sd(gprmc[5])
            gprmc_lonew = gprmc[6]
            gprmc_speed = float(gprmc[7])

            if gprmc_latns == "S":
                self.gps_state['latitude'] = gprmc_lat*-1.0
            else:
                self.gps_state['latitude'] = gprmc_lat

            if gprmc_lon == "W":
                self.gps_state['longitude'] = gprmc_lon*-1.0
            else:
                self.gps_state['longitude'] = gprmc_lon

            self.gps_state['speed'] = gprmc_speed*0.51444*3.6

        elif "$GPGGA" in data:
            logging.debug("SerialGPS - Got GPGGA.")
            gpgga = data.split(",")
            gpgga_lat = self.dm_to_sd(gpgga[2])
            gpgga_latns = gpgga[3]
            gpgga_lon = self.dm_to_sd(gpgga[4])
            gpgga_lonew = gpgga[5]
            gpgga_fixstatus = gpgga[6]
            self.gps_state['altitude'] = float(gpgga[9])


            if gpgga_latns == "S":
                self.gps_state['latitude'] = gpgga_lat*-1.0
            else:
                self.gps_state['latitude'] = gpgga_lat

            if gpgga_lon == "W":
                self.gps_state['longitude'] = gpgga_lon*-1.0
            else:
                self.gps_state['longitude'] = gpgga_lon 

            if gpgga_fixstatus == 0:
                self.gps_state['valid'] = False
            else:
                self.gps_state['valid'] = True
                self.send_to_callback()

        else:
            # Discard all other lines
            pass


    def send_to_callback(self):
        '''
        Send the current GPS data snapshot onto the callback function,
        if one exists.
        '''
        # Generate a copy of the gps state
        _state = self.gps_state.copy()

        # Attempt to pass it onto the callback function.
        if self.callback != None:
            try:
                self.callback(_state)
            except Exception as e:
                traceback.print_exc()
                logging.error("SerialGPS - Error Passing data to callback - %s" % str(e))


class GPSDGPS(object):
    ''' Read GPS data from a GPSD server '''

    def __init__(self,
        hostname = '127.0.0.1',
        port = 2947,
        callback = None):
        ''' Init '''
        pass


if __name__ == '__main__':
    import sys, time
    logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', level=logging.DEBUG)
    _port = sys.argv[1]
    _baud = 9600

    def print_data(data):
        print(data)

    _gps = SerialGPS(serial_port=_port, serial_baud=_baud, callback=print_data, uberdebug=True)

    time.sleep(100)
    _gps.close()

