// Habitat data scraping functions

// URL to scrape recent vehicle position data from.
// TODO: Allow adjustment of the number of positions to request.
var spacenearus_url = "http://spacenear.us/tracker/datanew.php?mode=2hours&type=positions&format=json&max_positions=100&position_id=";
// Record of the last position ID, so we only request new data.
var spacenearus_last_position_id = 0;
// Keep track of whether an asynchronous AJAX request is in progress.
// Not really sure if this is necessary.
var snear_request_running = false;

// Store for vehicle data.
var habitat_vehicles = {};
// Only add chase cars which are (initially) within this range limit (km).
var habitat_vehicle_max_range = 200.0;


function process_habitat_vehicles(data){
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
			if (habitat_vehicles.hasOwnProperty(vcallsign)){

				// Only update if the position ID of this position is newer than that last seen.
				if (habitat_vehicles[vcallsign].position_id < position.position_id){
					//console.log("Updating: " + vcallsign);
					// Update the position ID.
					habitat_vehicles[vcallsign].position_id = position.position_id;

					// Since we don't always get a heading with the vehicle position, calculate it.
					var old_v_pos = {lat:habitat_vehicles[vcallsign].latest_data[0],
						lon: habitat_vehicles[vcallsign].latest_data[1], 
						alt:habitat_vehicles[vcallsign].latest_data[2]};
					var new_v_pos = {lat: v_lat, lon:v_lon, alt:v_alt};
					habitat_vehicles[vcallsign].heading = calculate_lookangles(old_v_pos, new_v_pos).bearing;

					// Update the position data.
					habitat_vehicles[vcallsign].latest_data = [v_lat, v_lon, v_alt];

					// Update the marker position.
					habitat_vehicles[vcallsign].marker.setLatLng(habitat_vehicles[vcallsign].latest_data).update();

					// Rotate/replace the icon to match the bearing.
                    var _car_heading = habitat_vehicles[vcallsign].heading - 90.0;
                    if (_car_heading<=90.0){
                        habitat_vehicles[vcallsign].marker.setIcon(habitat_car_icons[habitat_vehicles[vcallsign].colour]);
                        habitat_vehicles[vcallsign].marker.setRotationAngle(_car_heading);
                    }else{
                        // We are travelling West - we need to use the flipped car icon.
                        _car_heading = _car_heading - 180.0;
                        habitat_vehicles[vcallsign].marker.setIcon(habitat_car_icons_flipped[habitat_vehicles[vcallsign].colour]);
                        habitat_vehicles[vcallsign].marker.setRotationAngle(_car_heading);
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
			if(v_range < habitat_vehicle_max_range){
				//console.log("Adding: " + vcallsign);
				habitat_vehicles[vcallsign] = {};
				// Initialise a few default values
				habitat_vehicles[vcallsign].heading = 90;
				habitat_vehicles[vcallsign].latest_data = [v_lat, v_lon, v_alt];
				habitat_vehicles[vcallsign].position_id = position.position_id;

				// Get an index for the car icon. This is incremented for each vehicle,
				// giving each a different colour.
				habitat_vehicles[vcallsign].colour = car_colour_values[car_colour_idx];
				car_colour_idx = (car_colour_idx+1)%car_colour_values.length; 

				// Create marker
				habitat_vehicles[vcallsign].marker = L.marker(habitat_vehicles[vcallsign].latest_data,
					{title:vcallsign, 
					icon: habitat_car_icons[habitat_vehicles[vcallsign].colour], 
					rotationOrigin: "center center"})
                                .addTo(map);
                // Keep our own record of if this marker has been added to a map,
                // as we shouldn't be using the private _map property of the marker object.
                habitat_vehicles[vcallsign].onmap = true;

                // Add tooltip, with custom CSS which removes all tooltip borders, and adds a text shadow.
                habitat_vehicles[vcallsign].marker.bindTooltip(vcallsign, 
                	{permanent: true,
                		direction: 'center',
                		offset:[0,25],
                		className:'custom_label'}).openTooltip();
			}
		}

	});
	
	snear_request_running = false;
}

// Request the latest 100 vehicle positions from spacenear.us
function get_habitat_vehicles(){
	var snear_request_url = spacenearus_url + spacenearus_last_position_id;

	if(!snear_request_running){
		snear_request_running = true;
	    $.ajax({
	      url: snear_request_url,
	      dataType: 'json',
	      timeout: 15000,
	      async: true, // Yes, this is deprecated...
	      success: function(data) {
	        process_habitat_vehicles(data);
	      }
		});
	}
}


// Show/Hide all vehicles.
function show_habitat_vehicles(){
	var state = document.getElementById("showOtherCars").checked;
	for (_car in habitat_vehicles){
		// Add to map, if its not already on there.
		if(state){
			if(!habitat_vehicles[_car].onmap){
				habitat_vehicles[_car].marker.addTo(map);
				habitat_vehicles[_car].onmap = true;
			}
		} else{
			if(habitat_vehicles[_car].onmap){
				habitat_vehicles[_car].marker.remove();
				habitat_vehicles[_car].onmap = false;
			}
		}
	}

}