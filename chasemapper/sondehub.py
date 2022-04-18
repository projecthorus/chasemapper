#!/usr/bin/env python
#
#   Project Horus - Browser-Based Chase Mapper
#   Sondehub Communication (Chase car position upload)
#
#   Copyright (C) 2021  Mark Jessop <vk5qi@rfhead.net>
#   Released under GNU GPL v3 or later
#
import chasemapper
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


class SondehubChaseUploader(object):
    """ Upload supplied chase car positions to Sondehub on a regular basis """

    SONDEHUB_STATION_POSITION_URL = "https://api.v2.sondehub.org/listeners"
    SONDEHUB_STATION_POSITION_URL_AMATEUR = "https://api.v2.sondehub.org/amateur/listeners"
    SONDEHUB_SONDE_RECOVERED_URL = "https://api.v2.sondehub.org/recovered"
    SONDEHUB_SONDE_RECOVERED_URL_AMATEUR = "https://api.v2.sondehub.org/amateur/recovered"

    def __init__(
        self,
        update_rate=30,
        callsign="N0CALL",
        upload_enabled=True,
        upload_timeout=10,
        upload_retries=2,
        amateur=False # Upload to amateur DB instead of regular sondehub
    ):
        """ Initialise the Sondehub Chase uploader, and start the update thread """

        self.update_rate = update_rate
        self.callsign = callsign
        self.callsign_init = False
        self.upload_enabled = upload_enabled
        self.upload_timeout = upload_timeout
        self.upload_retries = upload_retries
        self.amateur = amateur

        self.car_position = None
        self.car_position_lock = Lock()

        self.uploader_thread_running = True
        self.uploader_thread = Thread(target=self.upload_thread)
        self.uploader_thread.start()

        if amateur:
            self.position_url = self.SONDEHUB_STATION_POSITION_URL_AMATEUR
            self.recovery_url = self.SONDEHUB_SONDE_RECOVERED_URL_AMATEUR
            logging.info("Sondehub-Amateur - Chase-Car Position Uploader Started")
        else:
            self.position_url = self.SONDEHUB_STATION_POSITION_URL
            self.recovery_url = self.SONDEHUB_SONDE_RECOVERED_URL
            logging.info("Sondehub - Chase-Car Position Uploader Started")

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

                    # Upload the listener position.
                    self.upload_position(
                        self.callsign,
                        _position["latitude"],
                        _position["longitude"],
                        _position["altitude"],
                    )
                except Exception as e:
                    logging.error(
                        "Sondehub - Error uploading chase-car position - %s" % str(e)
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

    def upload_position(
        self, callsign, latitude, longitude, altitude, antenna="Chase Car", mobile=True
    ):
        """ Upload a chase car position to Sondehub 
        This uses the PUT /listeners API described here:
        https://github.com/projecthorus/sondehub-infra/wiki/API-(Beta)
        """

        _position = {
            "software_name": "ChaseMapper",
            "software_version": chasemapper.__version__,
            "uploader_callsign": callsign,
            "uploader_position": [latitude, longitude, altitude],
            "uploader_antenna": antenna,
            "uploader_contact_email": "none@none.com",
            "mobile": mobile,
        }

        _retries = 0
        _upload_success = False

        _start_time = time.time()

        while _retries < self.upload_retries:
            # Run the request.
            try:
                headers = {
                    "User-Agent": "chasemapper-" + chasemapper.__version__,
                    "Content-Type": "application/json",
                }
                _req = requests.put(
                    self.position_url,
                    json=_position,
                    # TODO: Revisit this second timeout value.
                    timeout=(self.upload_timeout, 6.1),
                    headers=headers,
                )
            except Exception as e:
                logging.error("Sondehub - Upload Failed: %s" % str(e))
                return

            if _req.status_code == 200:
                # 200 is the only status code that we accept.
                _upload_time = time.time() - _start_time
                logging.debug("Sondehub - Uploaded chase-car position to Sondehub.")
                _upload_success = True
                break

            elif _req.status_code == 500:
                # Server Error, Retry.
                _retries += 1
                continue

            else:
                logging.error(
                    "Sondehub - Error uploading chase-car position to Sondehub. Status Code: %d %s."
                    % (_req.status_code, _req.text)
                )
                break

        if not _upload_success:
            logging.error(
                "Sondehub - Chase-car position upload failed after %d retries"
                % (_retries)
            )
            logging.debug(f"Attempted to upload {json.dumps(_position)}")


    def mark_payload_recovered(self, serial=None, callsign=None, lat=0.0, lon=0.0, alt=0.0, message="", recovered=True):
        """ Upload an indication that a payload (radiosonde or otherwise) has been recovered """

        if serial is None:
            return
        
        _doc = {
            "serial": serial,
            "lat": lat,
            "lon": lon,
            "alt": alt,
            "recovered": recovered,
            "recovered_by": callsign,
            "description": message
        }

        _retries = 0
        _upload_success = False

        _start_time = time.time()

        while _retries < self.upload_retries:
            # Run the request.
            try:
                headers = {
                    "User-Agent": "chasemapper-" + chasemapper.__version__,
                    "Content-Type": "application/json",
                }
                _req = requests.put(
                    self.recovery_url,
                    json=_doc,
                    # TODO: Revisit this second timeout value.
                    timeout=(self.upload_timeout, 6.1),
                    headers=headers,
                )
            except Exception as e:
                logging.error("Sondehub - Recovery Upload Failed: %s" % str(e))
                return

            if _req.status_code == 200:
                # 200 is the only status code that we accept.
                _upload_time = time.time() - _start_time
                logging.info("Sondehub - Uploaded recovery notification to Sondehub.")
                _upload_success = True
                break

            elif _req.status_code == 400:
                try:
                    _resp = json.loads(_req.text)
                    logging.info(f"Sondehub - {_resp['message']}")
                except:
                    logging.info(f"Sondehub - Got code 400 from Sondehub.")

                _upload_success = True
                break
            
            elif _req.status_code == 500:
                # Server Error, Retry.
                _retries += 1
                continue

            else:
                logging.error(
                    "Sondehub - Error uploading recovery notification to Sondehub. Status Code: %d %s."
                    % (_req.status_code, _req.text)
                )
                break

        if not _upload_success:
            logging.error(
                "Sondehub - Recovery notification upload failed after %d retries"
                % (_retries)
            )
            logging.debug(f"Attempted to upload {json.dumps(_doc)}")



    def close(self):
        self.uploader_thread_running = False
        try:
            self.uploader_thread.join()
        except:
            pass
        logging.info("Sondehub - Chase-Car Position Uploader Closed")
