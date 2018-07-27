#!/usr/bin/env python
#
#   Project Horus - Browser-Based Chase Mapper - Config Reader
#
#   Copyright (C) 2018  Mark Jessop <vk5qi@rfhead.net>
#   Released under GNU GPL v3 or later
#
import logging

try:
    # Python 2
    from ConfigParser import RawConfigParser
except ImportError:
    # Python 3
    from configparser import RawConfigParser


default_config = {
    # Start location for the map (until either a chase car position, or balloon position is available.)
    'default_lat': -34.9,
    'default_lon': 138.6,

    'payload_max_age': 180,

    # Predictor settings
    'pred_enabled': False,  # Enable running and display of predicted flight paths.
    # Default prediction settings (actual values will be used once the flight is underway)
    'pred_model': "Disabled",
    'pred_desc_rate': 6.0,
    'pred_burst': 28000,
    'show_abort': True, # Show a prediction of an 'abort' paths (i.e. if the balloon bursts *now*)
    'pred_update_rate': 15 # Update predictor every 15 seconds.
    }


def parse_config_file(filename):
	""" Parse a Configuration File """

	chase_config = default_config.copy()

	config = RawConfigParser()
	config.read(filename)

	# Map Defaults
	chase_config['flask_host'] = config.get('map', 'flask_host')
	chase_config['flask_port'] = config.getint('map', 'flask_port')
	chase_config['default_lat'] = config.get('map', 'default_lat')
	chase_config['default_lon'] = config.get('map', 'default_lon')
	chase_config['payload_max_age'] = config.getint('map', 'payload_max_age')

	# Source Selection
	chase_config['data_source'] = config.get('source', 'type')
	chase_config['ozimux_port'] = config.getint('source', 'ozimux_port')
	chase_config['horus_udp_port'] = config.getint('source', 'horus_udp_port')

	# Car GPS Data
	chase_config['car_gps_source'] = config.get('car_gps','source')
	chase_config['car_gpsd_host'] = config.get('car_gps','gpsd_host')
	chase_config['car_gpsd_port'] = config.getint('car_gps','gpsd_port')

	# Predictor
	chase_config['pred_enabled'] = config.getboolean('predictor', 'predictor_enabled')
	chase_config['pred_burst'] = config.getfloat('predictor', 'default_burst')
	chase_config['pred_desc_rate'] = config.getfloat('predictor', 'default_descent_rate')
	chase_config['pred_binary'] = config.get('predictor','pred_binary')
	chase_config['pred_gfs_directory'] = config.get('predictor', 'gfs_directory')
	chase_config['pred_model_download'] = config.get('predictor', 'model_download')

	return chase_config




def read_config(filename, default_cfg="horusmapper.cfg.example"):
	""" Read in a Horus Mapper configuration file,and return as a dict. """

	try:
		config_dict = parse_config_file(filename)
	except Exception as e:
		logging.error("Could not parse %s, trying default: %s" % (filename, str(e)))
		try:
			config_dict = parse_config_file(default_cfg)
		except Exception as e:
			logging.critical("Could not parse example config file! - %s" % str(e))
			config_dict = None

	return config_dict

if __name__ == "__main__":
	import sys
	print(read_config(sys.argv[1]))


