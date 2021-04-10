//
//   Project Horus - Browser-Based Chase Mapper - SondeHub Data Scraping
//
//   Copyright (C) 2021  Mark Jessop <vk5qi@rfhead.net>
//   Released under GNU GPL v3 or later
//


// URL to scrape recent vehicle position data from.
// TODO: Allow adjustment of the number of positions to request.
var sondehub_vehicle_url = "https://api.v2.sondehub.org/datanew?type=positions&mode=1hour&chase_only=true&position_id=0";


// Request the latest 100 vehicle positions from spacenear.us
function get_sondehub_vehicles(){

	if(!snear_request_running){
		snear_request_running = true;
		console.log("Requesting vehicles from Sondehub...")
	    $.ajax({
	      url: sondehub_vehicle_url,
	      dataType: 'json',
	      timeout: 15000,
	      async: true, // Yes, this is deprecated...
	      success: function(data) {
	        process_habitat_vehicles(data);
	      }
		});
	}
}


