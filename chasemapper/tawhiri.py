#!/usr/bin/env python
#
#   Project Horus - Browser-Based Chase Mapper - Tawhiri Interface
#
#   Grab predictions from the Tawhiri Predictions API
#   Refer here for documentation on Tawhiri: https://tawhiri.readthedocs.io/en/latest/api.html
#
#   Copyright (C) 2020  Mark Jessop <vk5qi@rfhead.net>
#   Released under GNU GPL v3 or later
#
import datetime
import logging
import pytz
import requests
import subprocess
from dateutil.parser import parse
from threading import Thread

TAWHIRI_API_URL = "http://predict.cusf.co.uk/api/v1/"

def get_tawhiri_prediction(
    launch_datetime,
    launch_latitude,
    launch_longitude,
    launch_altitude=0,
    ascent_rate=5.0,
    burst_altitude=30000.0,
    descent_rate=5.0,
    profile='standard_profile',
    dataset=None,
    timeout = 10
):
    """ Request a Prediction from the Tawhiri Predictor API """

    # Localise supplied time to UTC if not already done
    if launch_datetime.tzinfo is None:
        launch_datetime = pytz.utc.localize(launch_datetime)

    # Create RFC3339-compliant timestamp
    _dt_rfc3339 = launch_datetime.isoformat()


    _params = {
        "launch_latitude": launch_latitude,
        "launch_longitude": launch_longitude,
        "launch_altitude": launch_altitude,
        "launch_datetime": _dt_rfc3339,
        "ascent_rate": ascent_rate,
        "descent_rate": descent_rate,
        "burst_altitude": burst_altitude,
        "profile": profile
    }
    
    if dataset:
        _params["dataset"] = dataset

    logging.debug("Tawhiri - Requesting prediction using parameters: %s" % str(_params))

    try:
        _r = requests.get(TAWHIRI_API_URL, params=_params, timeout=timeout)

        _json = _r.json()

        if 'error' in _json:
            # The Tawhiri API has returned an error
            _error = "%s: %s" % (_json['error']['type'], _json['error']['description'])

            logging.error("Tawhiri - %s" % _error)

            return None

        else:
            return parse_tawhiri_data(_json)

    except Exception as e:
        logging.error("Tawhiri - Error running prediction: %s" % str(e))

        return None


def parse_tawhiri_data(data):
    """ Parse a returned flight trajectory from Tawhiri, and convert it to a cusf_predictor_wrapper compatible format """


    _epoch = pytz.utc.localize(datetime.datetime(1970,1,1))
    # Extract dataset information
    _dataset = parse(data['request']['dataset'])
    _dataset = _dataset.strftime("%Y%m%d%Hz")


    _path = []

    for _stage in data['prediction']:
        _trajectory = _stage['trajectory']

        for _point in _trajectory:

            # Create UTC timestamp without using datetime.timestamp(), for Python 2.7 backwards compatibility.
            _dt = parse(_point['datetime'])
            _dt_timestamp = (_dt - _epoch).total_seconds()
            _path.append([_dt_timestamp, _point['latitude'], _point['longitude'], _point['altitude']])


    _output = {
        "dataset": _dataset,
        "path": _path
    }

    return _output


if __name__ == "__main__":
    import datetime
    import pprint

    logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', level=logging.INFO)

    _now = datetime.datetime.utcnow()


    # Regular complete-flightpath prediction
    _data = get_tawhiri_prediction(
        launch_datetime=_now,
        launch_latitude=-34.9499,
        launch_longitude=138.5194,
        launch_altitude=0,
    )
    pprint.pprint(_data)

    # Descent prediction
    _data = get_tawhiri_prediction(
        launch_datetime=_now,
        launch_latitude=-34.9499,
        launch_longitude=138.5194,
        launch_altitude=10000,
        burst_altitude=10001,
        descent_rate=abs(-6.0)
    )
    pprint.pprint(_data)
