#!/usr/bin/env python
#
#   Project Horus - Browser-Based Chase Mapper
#   Habitat Communication (Chase car position upload)
#
#   Copyright (C) 2018  Mark Jessop <vk5qi@rfhead.net>
#   Released under GNU GPL v3 or later
#
import datetime
import logging
import requests
import time
import traceback
import json
from base64 import b64encode
from hashlib import sha256
from threading import Thread, Lock

try:
    # Python 2
    from Queue import Queue
except ImportError:
    # Python 3
    from queue import Queue


HABITAT_URL = "http://habitat.habhub.org/"

url_habitat_uuids = HABITAT_URL + "_uuids?count=%d"
url_habitat_db = HABITAT_URL + "habitat/"
uuids = []


def ISOStringNow():
    return "%sZ" % datetime.datetime.utcnow().isoformat()


def postListenerData(doc, timeout=10):
    global uuids, url_habitat_db
    # do we have at least one uuid, if not go get more
    if len(uuids) < 1:
        fetchUuids()

    # Attempt to add UUID and time data to document.
    try:
        doc["_id"] = uuids.pop()
    except IndexError:
        logging.error("Habitat - Unable to post listener data - no UUIDs available.")
        return False

    doc["time_uploaded"] = ISOStringNow()

    try:
        _r = requests.post(url_habitat_db, json=doc, timeout=timeout)
        return True
    except Exception as e:
        logging.error("Habitat - Could not post listener data - %s" % str(e))
        return False


def fetchUuids(timeout=10):
    global uuids, url_habitat_uuids

    _retries = 5

    while _retries > 0:
        try:
            _r = requests.get(url_habitat_uuids % 10, timeout=timeout)
            uuids.extend(_r.json()["uuids"])
            logging.debug("Habitat - Got UUIDs")
            return
        except Exception as e:
            logging.error(
                "Habitat - Unable to fetch UUIDs, retrying in 10 seconds - %s" % str(e)
            )
            time.sleep(10)
            _retries = _retries - 1
            continue

    logging.error("Habitat - Gave up trying to get UUIDs.")
    return


def initListenerCallsign(callsign, antenna=None, radio=None):
    doc = {
        "type": "listener_information",
        "time_created": ISOStringNow(),
        "data": {"callsign": callsign},
    }

    if antenna != None:
        doc["data"]["antenna"] = antenna

    if radio != None:
        doc["data"]["radio"] = radio

    resp = postListenerData(doc)

    if resp is True:
        logging.debug("Habitat - Listener Callsign Initialized.")
        return True
    else:
        logging.error("Habitat - Unable to initialize callsign.")
        return False


def uploadListenerPosition(callsign, lat, lon, alt, chase=True):
    """ Upload Listener Position """

    doc = {
        "type": "listener_telemetry",
        "time_created": ISOStringNow(),
        "data": {
            "callsign": callsign,
            "chase": chase,
            "latitude": lat,
            "longitude": lon,
            "altitude": alt,
            "speed": 0,
        },
    }

    # post position to habitat
    resp = postListenerData(doc)
    if resp is True:
        logging.debug("Habitat - Listener information uploaded.")
        return True
    else:
        logging.error("Habitat - Unable to upload listener information.")
        return False


class HabitatChaseUploader(object):
    """ Upload supplied chase car positions to Habitat on a regular basis """

    def __init__(self, update_rate=30, callsign="N0CALL", upload_enabled=True):
        """ Initialise the Habitat Chase uploader, and start the update thread """

        self.update_rate = update_rate
        self.callsign = callsign
        self.callsign_init = False
        self.upload_enabled = upload_enabled

        self.car_position = None
        self.car_position_lock = Lock()

        self.uploader_thread_running = True
        self.uploader_thread = Thread(target=self.upload_thread)
        self.uploader_thread.start()

        logging.info("Habitat - Chase-Car Position Uploader Started")

    def update_position(self, position):
        """ Update the chase car position state
        This function accepts and stores a copy of the same dictionary structure produced by both
        Horus UDP broadcasts, and the serial GPS and GPSD modules
        """

        with self.car_position_lock:
            self.car_position = position.copy()

    def upload_thread(self):
        """ Uploader thread """
        while self.uploader_thread_running:

            # Grab a copy of the most recent car position.
            with self.car_position_lock:
                if self.car_position != None:
                    _position = self.car_position.copy()
                else:
                    _position = None

            if self.upload_enabled and _position != None:
                try:
                    # If the listener callsign has not been initialized, init it.
                    # We only need to do this once per callsign.
                    if self.callsign_init != self.callsign:
                        _resp = initListenerCallsign(self.callsign)
                        if _resp:
                            self.callsign_init = self.callsign

                    # Upload the listener position.
                    uploadListenerPosition(
                        self.callsign,
                        _position["latitude"],
                        _position["longitude"],
                        _position["altitude"],
                    )
                except Exception as e:
                    logging.error(
                        "Habitat - Error uploading chase-car position - %s" % str(e)
                    )

            # Wait for next update.
            _i = 0
            while (_i < self.update_rate) and self.uploader_thread_running:
                time.sleep(1)
                _i += 1

    def set_update_rate(self, rate):
        """ Set the update rate """
        self.update_rate = int(rate)

    def set_callsign(self, call):
        """ Set the callsign """
        self.callsign = call

    #def mark_payload_recovered(self, callsign, latitude, longitude, altitude, message):
    def mark_payload_recovered(self, serial=None, callsign=None, lat=0.0, lon=0.0, alt=0.0, message="", recovered=True):
        """ Upload an indication that a payload (radiosonde or otherwise) has been recovered """

        if serial is None:
            return

        if recovered:
            _call = serial + " recovered by " + callsign
        else:
            _call = serial + " not recovered by " + callsign

        try:
            initListenerCallsign(_call, radio="", antenna=message)
            uploadListenerPosition(_call, lat, lon, alt, chase=False)
        except Exception as e:
            logging.error(
                "Habitat - Unable to mark payload as recovered - %s" % (str(e))
            )
            return

        logging.info("Habitat - Payload marked as recovered.")

    def close(self):
        self.uploader_thread_running = False
        try:
            self.uploader_thread.join()
        except:
            pass
        logging.info("Habitat - Chase-Car Position Uploader Closed")
