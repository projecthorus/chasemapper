#!/usr/bin/env python
#
#   Project Horus - Chase Logging
#
#   Copyright (C) 2019  Mark Jessop <vk5qi@rfhead.net>
#   Released under GNU GPL v3 or later
#
import datetime
import json
import logging
import os
import pytz
import time
from threading import Thread, Lock

try:
    # Python 2
    from Queue import Queue
except ImportError:
    # Python 3
    from queue import Queue


class ChaseLogger(object):
    """ Chase Data Logger Class.
        Log all chase data into a file as lines of JSON.
    """

    def __init__(self, filename=None, log_dir="./log_files"):

        if filename is not None:
            # Use user-supplied filename if provided
            self.filename = filename
        else:
            # Otherwise, create a filename based on the current time.
            self.filename = os.path.join(
                log_dir, datetime.datetime.utcnow().strftime("%Y%m%d-%H%MZ.log")
            )

        self.file_lock = Lock()

        # Input Queue.
        self.input_queue = Queue()

        # Open the file.
        try:
            self.f = open(self.filename, "a")
            logging.info("Logging - Opened log file %s." % self.filename)
        except Exception as e:
            self.log_error("Logging - Could not open log file - %s" % str(e))
            return

        # Start queue processing thread.
        self.input_processing_running = True
        self.log_process_thread = Thread(target=self.process_queue)
        self.log_process_thread.start()

    def add_car_position(self, data):
        """ Log a chase car position update.
        Input dict expected to be in the format:
        {
            'time'  :   _time_dt,
            'lat'   :   _lat,
            'lon'   :   _lon,
            'alt'   :   _alt,
            'comment':  _comment
        }

        """

        data["log_type"] = "CAR POSITION"
        data["log_time"] = pytz.utc.localize(datetime.datetime.utcnow()).isoformat()

        # Convert the input datetime object into a string.
        data["time"] = data["time"].isoformat()

        # Add it to the queue if we are running.
        if self.input_processing_running:
            self.input_queue.put(data)
        else:
            self.log_error("Processing not running, discarding.")

    def add_balloon_telemetry(self, data):
        """ Log balloon telemetry.
        """

        data["log_type"] = "BALLOON TELEMETRY"
        data["log_time"] = pytz.utc.localize(datetime.datetime.utcnow()).isoformat()

        # Convert the input datetime object into a string.
        data["time"] = data["time_dt"].isoformat()
        # Remove the time_dt element (this cannot be serialised to JSON).
        data.pop("time_dt")

        # Add it to the queue if we are running.
        if self.input_processing_running:
            self.input_queue.put(data)
        else:
            self.log_error("Processing not running, discarding.")

    def add_balloon_prediction(self, data):
        """ Log a prediction run """

        data["log_type"] = "PREDICTION"
        data["log_time"] = pytz.utc.localize(datetime.datetime.utcnow()).isoformat()

        # Add it to the queue if we are running.
        if self.input_processing_running:
            self.input_queue.put(data)
        else:
            self.log_error("Processing not running, discarding.")

    def add_bearing(self, data):
        """ Log a packet of bearing data """

        data["log_type"] = "BEARING"
        data["log_time"] = pytz.utc.localize(datetime.datetime.utcnow()).isoformat()

        # Add it to the queue if we are running.
        if self.input_processing_running:
            self.input_queue.put(data)
        else:
            self.log_error("Processing not running, discarding.")

    def process_queue(self):
        """ Process data from the input queue, and write telemetry to log files.
        """
        self.log_info("Started Chase Logger Thread.")

        while self.input_processing_running:

            # Process everything in the queue.
            self.file_lock.acquire()
            while self.input_queue.qsize() > 0:
                try:
                    _data = self.input_queue.get_nowait()
                    _data_str = json.dumps(_data)
                    self.f.write(_data_str + "\n")
                except Exception as e:
                    self.log_error("Error processing data - %s" % str(e))

            self.file_lock.release()
            # Sleep while waiting for some new data.
            time.sleep(5)

    def running(self):
        """ Check if the logging thread is running. 

        Returns:
            bool: True if the logging thread is running.
        """
        return self.input_processing_running

    def close(self):
        try:
            self.input_processing_running = False
            self.f.close()
        except Exception as e:
            self.log_error("Error when closing - %s" % str(e))

        self.log_info("Stopped Telemetry Logger Thread.")

    def log_debug(self, line):
        """ Helper function to log a debug message with a descriptive heading. 
        Args:
            line (str): Message to be logged.
        """
        logging.debug("Chase Logger - %s" % line)

    def log_info(self, line):
        """ Helper function to log an informational message with a descriptive heading. 
        Args:
            line (str): Message to be logged.
        """
        logging.info("Chase Logger - %s" % line)

    def log_error(self, line):
        """ Helper function to log an error message with a descriptive heading. 
        Args:
            line (str): Message to be logged.
        """
        logging.error("Chase Logger - %s" % line)
