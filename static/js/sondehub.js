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


/* Habitat ChaseCar lib (copied from SondeHub Tracker)
 * Uploads geolocation for chase cars to habitat
 *
 * Author: Rossen Gerogiev / Mark Jessop
 * Requires: jQuery
 * 
 * Updated to SondeHub v2 by Mark Jessop
 */

ChaseCar = {
    db_uri: "https://api.v2.sondehub.org/listeners",   // Sondehub API
    recovery_uri: "https://api.v2.sondehub.org/recovered",
};

// Updated SondeHub position upload function.
// Refer PUT listeners API here: https://generator.swagger.io/?url=https://raw.githubusercontent.com/projecthorus/sondehub-infra/main/swagger.yaml
// @callsign string
// @position object (geolocation position object)
ChaseCar.updatePosition = function(callsign, position) {
    if(!position || !position.coords) return;

    // Set altitude to zero if not provided.
    _position_alt = ((!!position.coords.altitude) ? position.coords.altitude : 0);

    var _doc = {
        "software_name": "SondeHub Tracker",
        "software_version": "{VER}",
        "uploader_callsign": callsign,
        "uploader_position": [position.coords.latitude, position.coords.longitude, _position_alt],
        "uploader_antenna": "Mobile Station",
        "uploader_contact_email": "none@none.com",
        "mobile": true
    };

    // push the doc to sondehub
    $.ajax({
            type: "PUT",
            url: ChaseCar.db_uri,
            contentType: "application/json; charset=utf-8",
            dataType: "json",
            data: JSON.stringify(_doc),
    });
};


ChaseCar.markRecovered = function(serial, lat, lon, recovered, callsign, notes){

    var _doc = {
        "serial": serial,
        "lat": lat,
        "lon": lon,
        "alt": 0.0,
        "recovered": recovered,
        "recovered_by": callsign,
        "description": notes
    };

    $.ajax({
        type: "PUT",
        url: ChaseCar.recovery_uri,
        contentType: "application/json; charset=utf-8",
        dataType: "json",
        data: JSON.stringify(_doc),
    }).done(function(data) {
        console.log(data);
        alert("Recovery Reported OK!");
    })
    .fail(function(jqXHR, textStatus, error) {
        try {
            _fail_resp = JSON.parse(jqXHR.responseText);
            alert("Error Submitting Recovery Report: " + _fail_resp.message);
        } catch(err) {
            alert("Error Submitting Recovery Report.");
        }
    })

}