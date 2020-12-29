#!/usr/bin/env python
#
#   Project Horus - Browser-Based Chase Mapper - Config Reader
#
#   Copyright (C) 2018  Mark Jessop <vk5qi@rfhead.net>
#   Released under GNU GPL v3 or later
#
import logging
import os

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
    'thunderforest_api_key': 'none',

    # Predictor settings
    'pred_enabled': True,  # Enable running and display of predicted flight paths.
	'offline_predictions': False, # Use an offline GFS model and predictor instead of Tawhiri.
    # Default prediction settings (actual values will be used once the flight is underway)
    'pred_model': "Disabled",
    'pred_desc_rate': 6.0,
    'pred_burst': 28000,
    'show_abort': True, # Show a prediction of an 'abort' paths (i.e. if the balloon bursts *now*)
    'pred_update_rate': 15, # Update predictor every 15 seconds.

    # Range Rings
    'range_rings_enabled': False,
    'range_ring_quantity': 5,
    'range_ring_spacing': 1000,
    'range_ring_weight': 1.5,
    'range_ring_color': 'red',
    'range_ring_custom_color': '#FF0000',

	# Chase Car Speedometer
	'chase_car_speed': True,

    # Bearing processing
    'max_bearings': 300,
    'max_bearing_age': 30*60,
    'car_speed_gate': 10,
    'bearing_length': 10,
    'bearing_weight': 1.0,
    'bearing_color': 'black',
    'bearing_custom_color': '#FF0000',

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
	chase_config['thunderforest_api_key'] = config.get('map', 'thunderforest_api_key')


	# GPSD Settings
	chase_config['car_gpsd_host'] = config.get('gpsd','gpsd_host')
	chase_config['car_gpsd_port'] = config.getint('gpsd','gpsd_port')

	# Serial GPS Settings
	chase_config['car_serial_port'] = config.get('gps_serial', 'gps_port')
	chase_config['car_serial_baud'] = config.getint('gps_serial', 'gps_baud')

	# Habitat Settings
	chase_config['habitat_upload_enabled'] = config.getboolean('habitat', 'habitat_upload_enabled')
	chase_config['habitat_call'] = config.get('habitat', 'habitat_call')
	chase_config['habitat_update_rate'] = config.getint('habitat', 'habitat_update_rate')

	# Predictor
	chase_config['pred_enabled'] = config.getboolean('predictor', 'predictor_enabled')
	chase_config['offline_predictions'] = config.getboolean('predictor', 'offline_predictions')
	chase_config['pred_burst'] = config.getfloat('predictor', 'default_burst')
	chase_config['pred_desc_rate'] = config.getfloat('predictor', 'default_descent_rate')
	chase_config['pred_binary'] = config.get('predictor','pred_binary')
	chase_config['pred_gfs_directory'] = config.get('predictor', 'gfs_directory')
	chase_config['pred_model_download'] = config.get('predictor', 'model_download')

	# Range Ring Settings
	chase_config['range_rings_enabled'] = config.getboolean('range_rings', 'range_rings_enabled')
	chase_config['range_ring_quantity'] = config.getint('range_rings', 'range_ring_quantity')
	chase_config['range_ring_spacing'] = config.getint('range_rings', 'range_ring_spacing')
	chase_config['range_ring_weight'] = config.getfloat('range_rings', 'range_ring_weight')
	chase_config['range_ring_color'] = config.get('range_rings', 'range_ring_color')
	chase_config['range_ring_custom_color'] = config.get('range_rings', 'range_ring_custom_color')

	# Bearing Processing
	chase_config['max_bearings'] = config.getint('bearings', 'max_bearings')
	chase_config['max_bearing_age'] = config.getint('bearings', 'max_bearing_age')*60 # Convert to seconds
	if chase_config['max_bearing_age'] < 60:
		chase_config['max_bearing_age'] = 60 # Make sure this number is something sane, otherwise things will break
	chase_config['car_speed_gate'] = config.getfloat('bearings', 'car_speed_gate')/3.6 # Convert to m/s
	chase_config['bearing_length'] = config.getfloat('bearings', 'bearing_length')
	chase_config['bearing_weight'] = config.getfloat('bearings', 'bearing_weight')
	chase_config['bearing_color'] = config.get('bearings', 'bearing_color')
	chase_config['bearing_custom_color'] = config.get('bearings', 'bearing_custom_color')

	# Offline Map Settings
	chase_config['tile_server_enabled'] = config.getboolean('offline_maps', 'tile_server_enabled')
	chase_config['tile_server_path'] = config.get('offline_maps', 'tile_server_path')

	# Determine valid offline map layers.
	chase_config['offline_tile_layers'] = []
	if chase_config['tile_server_enabled']:
		for _dir in os.listdir(chase_config['tile_server_path']):
			if os.path.isdir(os.path.join(chase_config['tile_server_path'],_dir)):
				chase_config['offline_tile_layers'].append(_dir)
		logging.info("Found Map Layers: %s" % str(chase_config['offline_tile_layers']))

	try:
		chase_config['chase_car_speed'] = config.getboolean('speedo', 'chase_car_speed')
	except:
		logging.info("Missing Chase Car Speedo Setting, using default (disabled)")
		chase_config['chase_car_speed'] = False

	# Telemetry Source Profiles

	_profile_count = config.getint('profile_selection', 'profile_count')
	_default_profile = config.getint('profile_selection', 'default_profile')

	chase_config['selected_profile'] = ""
	chase_config['profiles'] = {}


        # Unit Selection

	chase_config['unitselection'] = config.get('units', 'unitselection', fallback='metric')
	chase_config['switch_miles_feet'] = config.get('units', 'switch_miles_feet', fallback = '400')



	for i in range(1,_profile_count+1):
		_profile_section = "profile_%d" % i
		try:
			_profile_name = config.get(_profile_section, 'profile_name')
			_profile_telem_source_type = config.get(_profile_section, 'telemetry_source_type')
			_profile_telem_source_port = config.getint(_profile_section, 'telemetry_source_port')
			_profile_car_source_type = config.get(_profile_section, 'car_source_type')
			_profile_car_source_port = config.getint(_profile_section, 'car_source_port')

			chase_config['profiles'][_profile_name] = {
				'name': _profile_name,
				'telemetry_source_type': _profile_telem_source_type,
				'telemetry_source_port': _profile_telem_source_port,
				'car_source_type': _profile_car_source_type,
				'car_source_port': _profile_car_source_port
			}
			if _default_profile == i:
				chase_config['selected_profile'] = _profile_name

		except Exception as e:
			logging.error("Error reading profile section %d - %s" % (i, str(e)))

	if len(chase_config['profiles'].keys()) == 0:
		logging.critical("Could not read any profile data!")
		return None

	if chase_config['selected_profile'] not in chase_config['profiles']:
		logging.critical("Default profile selection does not exist.")
		return None

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
	logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', stream=sys.stdout, level=logging.DEBUG)
	print(read_config(sys.argv[1]))


