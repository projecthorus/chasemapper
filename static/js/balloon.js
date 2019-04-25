//
//   Project Horus - Browser-Based Chase Mapper - Balloon Telemetry Handlers
//
//   Copyright (C) 2019  Mark Jessop <vk5qi@rfhead.net>
//   Released under GNU GPL v3 or later
//


function add_new_balloon(data){
    // Add a new balloon to the telemetry store.
    // This function accepts a dictionary which conttains:
    //  telem: Latest telemetry dictionary, containing:
    //      callsign:
    //      position: [lat, lon, alt]
    //      vel_v
    //  path: Flight path so far.
    //  pred_path: Predicted flight path (can be empty)
    //  pred_landing: [lat, lon, alt] coordinate for predicted landing.
    //  abort_path: Abort prediction path
    //  abort_landing: Abort prediction landing location


    var telem = data.telem;
    var callsign = data.telem.callsign;

    balloon_positions[callsign] = {
        latest_data: telem,
        age: 0,
        colour: colour_values[colour_idx],
        visible: true
    };
    // Balloon Path
    balloon_positions[callsign].path = L.polyline(data.path,{title:callsign + " Path", color:balloon_positions[callsign].colour}).addTo(map);
    // Balloon position marker
    balloon_positions[callsign].marker = L.marker(telem.position,{title:callsign, icon: balloonAscentIcons[balloon_positions[callsign].colour]})
        .bindTooltip(callsign,{permanent:false,direction:'right'})
        .addTo(map);

    // Set the balloon icon to a parachute if it is descending.
    if (telem.vel_v < 0){
            balloon_positions[callsign].marker.setIcon(balloonDescentIcons[balloon_positions[callsign].colour]);
    }
    
    // If we have 'landed' (this is a bit of a guess), set the payload icon.
    if (telem.position[2] < parachute_min_alt){
        balloon_positions[callsign].marker.setIcon(balloonPayloadIcons[balloon_positions[callsign].colour]);
    }


    // If the balloon is in descent, or is above the burst altitude, clear out the abort path and marker
    // so they don't get shown.
    if (telem.position[2] > chase_config.pred_burst || telem.vel_v < 0.0){
        balloon_positions[callsign].abort_path = [];
        balloon_positions[callsign].abort_landing = [];
    }

    // Add predicted landing path
    balloon_positions[callsign].pred_path = L.polyline(data.pred_path,{title:callsign + " Prediction", color:balloon_positions[callsign].colour, opacity:prediction_opacity}).addTo(map);

    // Landing position marker
    // Only add if there is data to show
    if (data.pred_landing.length == 3){
        balloon_positions[callsign].pred_marker = L.marker(data.pred_landing,{title:callsign + " Landing", icon: balloonLandingIcons[balloon_positions[callsign].colour]})
            .bindTooltip(callsign + " Landing",{permanent:false,direction:'right'})
            .addTo(map);
    } else{
        balloon_positions[callsign].pred_marker = null;
    }

    // Burst position marker
    // Only add if there is data to show
    if (data.burst.length == 3){
        balloon_positions[callsign].burst_marker = L.marker(data.burst,{title:callsign + " Burst", icon: burstIcon})
            .bindTooltip(callsign + " Burst",{permanent:false,direction:'right'})
            .addTo(map);
    } else{
        balloon_positions[callsign].burst_marker = null;
    }

    // Abort path
    balloon_positions[callsign].abort_path = L.polyline(data.abort_path,{title:callsign + " Abort Prediction", color:'red', opacity:prediction_opacity});

    if (chase_config.show_abort == true){
        balloon_positions[callsign].abort_path.addTo(map);
    }

    // Abort position marker
    if (data.abort_landing.length == 3){
        balloon_positions[callsign].abort_marker = L.marker(data.abort_landing,{title:callsign + " Abort", icon: abortIcon})
            .bindTooltip(callsign + " Abort Landing",{permanent:false,direction:'right'});
        if(chase_config.show_abort == true){
            balloon_positions[callsign].abort_marker.addTo(map);
        }
    }else{
        balloon_positions[callsign].abort_marker = null;
    }

    
    colour_idx = (colour_idx+1)%colour_values.length; 

}

function updateSummaryDisplay(){
    // Update the 'Payload Summary' display.
    var _summary_update = {id:1};
    // See if there is any payload data.
    if (balloon_positions.hasOwnProperty(balloon_currently_following) == true){
        // There is balloon data!
        var _latest_telem = balloon_positions[balloon_currently_following].latest_data;
        
        _summary_update.alt = _latest_telem.position[2].toFixed(0) + "m (" + _latest_telem.max_alt.toFixed(0) + ")";
        var _speed = _latest_telem.speed*3.6;
        _summary_update.speed = _speed.toFixed(0) + " kph";
        _summary_update.vel_v = _latest_telem.vel_v.toFixed(1) + " m/s";


        if (chase_car_position.latest_data.length == 3){
            // We have a chase car position! Calculate relative position.
            var _bal = {lat:_latest_telem.position[0], lon:_latest_telem.position[1], alt:_latest_telem.position[2]};
            var _car = {lat:chase_car_position.latest_data[0], lon:chase_car_position.latest_data[1], alt:chase_car_position.latest_data[2]};

            var _look_angles = calculate_lookangles(_car, _bal);

            _summary_update.elevation = _look_angles.elevation.toFixed(0) + "°";
            _summary_update.azimuth = _look_angles.azimuth.toFixed(0) + "°";
            _summary_update.range = (_look_angles.range/1000).toFixed(1) + "km";
        }else{
            // No Chase car position data - insert dummy values
            _summary_update.azimuth = "---°";
            _summary_update.elevation = "--°";
            _summary_update.range = "----m";
        }

    }else{
        // No balloon data!
        _summary_update = {id: 1, alt:'-----m', speed:'---kph', vel_v:'-.-m/s', azimuth:'---°', elevation:'--°', range:'----m'}
    }
    // Update table
    $("#summary_table").tabulator("setData", [_summary_update]);
    if (summary_enlarged == true){
        var row = $("#summary_table").tabulator("getRow", 1);
        row.getElement().addClass("largeTableRow");
        $("#summary_table").tabulator("redraw", true);
    }
}

function handleTelemetry(data){
    // Telemetry Event messages contain a dictionary of position data.
    // It should have the fields:
    //  callsign: string
    //  position: [lat, lon, alt]
    //  vel_v: float
    //  time_to_landing: String
    // If callsign = 'CAR', the lat/lon/alt will be considered to be a car telemetry position.

    if(initial_load_complete == false){
        // If we have not completed our initial load of telemetry data, discard this data.
        return;
    }

    // Handle chase car position updates.
    if (data.callsign == 'CAR'){
        // Update car position.
        chase_car_position.latest_data = data.position;
        chase_car_position.heading = data.heading; // degrees true
        chase_car_position.speed = data.speed; // m/s
        // TODO: Update car marker.
        if (chase_car_position.marker == 'NONE'){
            // Create marker!
            chase_car_position.marker = L.marker(chase_car_position.latest_data,{title:"Chase Car", icon: carIcon, rotationOrigin: "center center"})
                    .addTo(map);
            chase_car_position.path = L.polyline([chase_car_position.latest_data],{title:"Chase Car", color:'black', weight:1.5});
            // If the user wants the chase car tail, add it to the map.
            if (document.getElementById("chaseCarTrack").checked == true){
                chase_car_position.path.addTo(map);
            }
        } else {
            chase_car_position.path.addLatLng(chase_car_position.latest_data);
            chase_car_position.marker.setLatLng(chase_car_position.latest_data).update();
        }
        // Rotate car icon based on heading, but only if we're going faster than 20kph (5.5m/s).
        if(chase_car_position.speed > 5.5){ // TODO: Remove magic number!
            var _car_heading = chase_car_position.heading - 90.0;
            if (_car_heading<=90.0){
                chase_car_position.marker.setIcon(carIcon);
                chase_car_position.marker.setRotationAngle(_car_heading);
            }else{
                // We are travelling West - we need to use the flipped car icon.
                _car_heading = _car_heading - 180.0;
                chase_car_position.marker.setIcon(carIconFlip);
                chase_car_position.marker.setRotationAngle(_car_heading);
            }
        }
        car_data_age = 0.0;
    }else{

        // Otherwise, we have a balloon
        // Have we seen this ballon before? 
        if (balloon_positions.hasOwnProperty(data.callsign) == false){

            // Convert the incoming data into a format suitable for adding into the telem store.
            var temp_data = {};
            temp_data.telem = data;
            temp_data.path = [data.position];
            temp_data.burst = [];
            temp_data.pred_path = [];
            temp_data.pred_landing = [];
            temp_data.abort_path = [];
            temp_data.abort_landing = [];

            // Add it to the telemetry store and create markers.
            add_new_balloon(temp_data);

            // Update data age to indicate current time.
            balloon_positions[data.callsign].age = Date.now();

        } else {
            // Yep - update the sonde_positions entry.
            balloon_positions[data.callsign].latest_data = data;
            balloon_positions[data.callsign].age = Date.now();
            balloon_positions[data.callsign].path.addLatLng(data.position);
            balloon_positions[data.callsign].marker.setLatLng(data.position).update();

            if (data.vel_v < 0){
                balloon_positions[data.callsign].marker.setIcon(balloonDescentIcons[balloon_positions[data.callsign].colour]);
            }else{
                balloon_positions[data.callsign].marker.setIcon(balloonAscentIcons[balloon_positions[data.callsign].colour]);
            }

            if (data.position[2] < parachute_min_alt){
                balloon_positions[data.callsign].marker.setIcon(balloonPayloadIcons[balloon_positions[data.callsign].colour]);
            }
        }

        // Update the telemetry table display
        updateTelemetryTable();

        // Are we currently following any other sondes?
        if (balloon_currently_following === "none"){
            // If not, follow this one!
            balloon_currently_following = data.callsign;
        }

        // Update the Summary and time-to-landing displays
        if (balloon_currently_following === data.callsign){
            $('#time_to_landing').text(data.time_to_landing);

            payload_data_age = 0.0;
        }
    }

    // Auto Pan selection between balloon or car.
    var _current_follow = $('input[name=autoFollow]:checked').val();
    if (_current_follow == 'payload' && data.callsign == balloon_currently_following){
        map.panTo(data.position);
    } else if (_current_follow == 'car' && data.callsign == 'CAR'){
        map.panTo(data.position);
    }else{
        // Don't pan to anything.
    }

    // Updat the summary display.
    updateSummaryDisplay();
}