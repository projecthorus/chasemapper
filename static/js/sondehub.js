//
//   Project Horus - Browser-Based Chase Mapper - SondeHub Data Scraping
//
//   Copyright (C) 2021  Mark Jessop <vk5qi@rfhead.net>
//   Released under GNU GPL v3 or later
//


// URL to scrape recent vehicle position data from.
// TODO: Allow adjustment of the number of positions to request.
var sondehub_vehicle_url = "https://v2.api";

function process_sondehub_vehicles(data){
	// Check we have a 'valid' response to process.
	if (data === null ||
        !data.positions ||
        !data.positions.position ||
        !data.positions.position.length) {
		snear_request_running = false;
		return;
	}

	data.positions.position.forEach(function(position){
		// Update the highest position ID, so we don't request old data.
		if (position.position_id > spacenearus_last_position_id){
			spacenearus_last_position_id = position.position_id;
		}

		var vcallsign = position.vehicle;

		// Check this isn't our callsign.
		// If it is, don't process it.
		if (vcallsign.startsWith(chase_config.habitat_call)){
			return;
		}

		// Determine if the vehicle is a chase car.
		// This is denoted by _chase at the end of the callsign.
		if(vcallsign.search(/(chase)/i) != -1) {

			var v_lat = parseFloat(position.gps_lat);
			var v_lon = parseFloat(position.gps_lon);
			var v_alt = parseFloat(position.gps_alt);

			// If the vehicle is already known to us, then update it position.
			// Update any existing entries (even if the range is above the threshold)
			if (chase_vehicles.hasOwnProperty(vcallsign)){

				// Only update if the position ID of this position is newer than that last seen.
				if (chase_vehicles[vcallsign].position_id < position.position_id){
					//console.log("Updating: " + vcallsign);
					// Update the position ID.
					chase_vehicles[vcallsign].position_id = position.position_id;

					// Since we don't always get a heading with the vehicle position, calculate it.
					var old_v_pos = {lat:chase_vehicles[vcallsign].latest_data[0],
						lon: chase_vehicles[vcallsign].latest_data[1], 
						alt:chase_vehicles[vcallsign].latest_data[2]};
					var new_v_pos = {lat: v_lat, lon:v_lon, alt:v_alt};
					chase_vehicles[vcallsign].heading = calculate_lookangles(old_v_pos, new_v_pos).azimuth;

					// Update the position data.
					chase_vehicles[vcallsign].latest_data = [v_lat, v_lon, v_alt];

					// Update the marker position.
					chase_vehicles[vcallsign].marker.setLatLng(chase_vehicles[vcallsign].latest_data).update();

					// Rotate/replace the icon to match the bearing.
                    var _car_heading = chase_vehicles[vcallsign].heading - 90.0;
                    if (_car_heading<=90.0){
                        chase_vehicles[vcallsign].marker.setIcon(habitat_car_icons[chase_vehicles[vcallsign].colour]);
                        chase_vehicles[vcallsign].marker.setRotationAngle(_car_heading);
                    }else{
                        // We are travelling West - we need to use the flipped car icon.
                        _car_heading = _car_heading - 180.0;
                        chase_vehicles[vcallsign].marker.setIcon(habitat_car_icons_flipped[chase_vehicles[vcallsign].colour]);
                        chase_vehicles[vcallsign].marker.setRotationAngle(_car_heading);
                    }
					return;
				}


				// No need to go any further.

				return;
			}

			// Otherwise, we need to decide if we're going to add it or not.
			// Determine the vehicle distance from our current position.
			var v_pos = {lat: v_lat, lon:v_lon, alt:v_alt};
			if (chase_car_position.marker === "NONE"){
				var my_pos = {lat:chase_config.default_lat, lon:chase_config.default_lon, alt:0};
			}else{
				var my_pos = {lat:chase_car_position.latest_data[0], lon:chase_car_position.latest_data[1], alt:chase_car_position.latest_data[2]};
			}
			var v_range = calculate_lookangles(my_pos, v_pos).range/1000.0;

			// If the range is less than the threshold, add it to our list of chase vehicles.
			if(v_range < vehicle_max_range){
				//console.log("Adding: " + vcallsign);
				chase_vehicles[vcallsign] = {};
				// Initialise a few default values
				chase_vehicles[vcallsign].heading = 90;
				chase_vehicles[vcallsign].latest_data = [v_lat, v_lon, v_alt];
				chase_vehicles[vcallsign].position_id = position.position_id;

				// Get an index for the car icon. This is incremented for each vehicle,
				// giving each a different colour.
				chase_vehicles[vcallsign].colour = car_colour_values[car_colour_idx];
				car_colour_idx = (car_colour_idx+1)%car_colour_values.length; 

				// Create marker
				chase_vehicles[vcallsign].marker = L.marker(chase_vehicles[vcallsign].latest_data,
					{title:vcallsign, 
					icon: habitat_car_icons[chase_vehicles[vcallsign].colour], 
					rotationOrigin: "center center"})
                                .addTo(map);
                // Keep our own record of if this marker has been added to a map,
                // as we shouldn't be using the private _map property of the marker object.
                chase_vehicles[vcallsign].onmap = true;

                // Add tooltip, with custom CSS which removes all tooltip borders, and adds a text shadow.
                chase_vehicles[vcallsign].marker.bindTooltip(vcallsign, 
                	{permanent: true,
                		direction: 'center',
                		offset:[0,25],
                		className:'custom_label'}).openTooltip();
			}
		}

	});
	
	snear_request_running = false;
}


function get_sondehub_vehicles(){
    // nothing here yet.
    console.log("Requesting vehicles from Sondehub...")
}



