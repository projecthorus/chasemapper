//
//   Project Horus - Browser-Based Chase Mapper - Prediction Path Handlers
//
//   Copyright (C) 2019  Mark Jessop <vk5qi@rfhead.net>
//   Released under GNU GPL v3 or later
//

function handlePrediction(data){
    // We expect the fields: callsign, pred_path, pred_landing, and abort_path and abort_landing, if abort predictions are enabled.
    var _callsign = data.callsign;
    var _pred_path = data.pred_path;
    var _pred_landing = data.pred_landing;

    // It's possible (though unlikely) that we get sent a prediction track before telemetry data.
    // In this case, just return.
    if (balloon_positions.hasOwnProperty(data.callsign) == false){
        return;
    }

    // Add the landing marker if it doesnt exist.
    if (balloon_positions[_callsign].pred_marker == null){
        balloon_positions[_callsign].pred_marker = L.marker(data.pred_landing,{title:_callsign + " Landing", icon: balloonLandingIcons[balloon_positions[_callsign].colour]})
            .bindTooltip(_callsign + " Landing",{permanent:false,direction:'right'})
            .addTo(map);
    }else{
        balloon_positions[_callsign].pred_marker.setLatLng(data.pred_landing);
    }
    if(data.burst.length == 3){
        // There is burst data!
        var _burst_txt = _callsign + " Burst (" + data.burst[2].toFixed(0) + "m)";
        if (balloon_positions[_callsign].burst_marker == null){
            balloon_positions[_callsign].burst_marker = L.marker(data.burst,{title:_burst_txt, icon: burstIcon})
                .bindTooltip(_burst_txt,{permanent:false,direction:'right'})
                .addTo(map);
        }else{
            balloon_positions[_callsign].burst_marker.setLatLng(data.burst);
            balloon_positions[_callsign].burst_marker.setTooltipContent(_burst_txt);
        }
    }else{
        // No burst data, or we are in descent.
        if (balloon_positions[_callsign].burst_marker != null){
            // Remove the burst icon from the map.
            balloon_positions[_callsign].burst_marker.remove();
        }
    }
    // Update the predicted path.
    balloon_positions[_callsign].pred_path.setLatLngs(data.pred_path);

    if (data.abort_landing.length == 3){
        // Only update the abort data if there is actually abort data to show.
        if (balloon_positions[_callsign].abort_marker == null){
            balloon_positions[_callsign].abort_marker = L.marker(data.abort_landing,{title:_callsign + " Abort", icon: abortIcon})
            .bindTooltip(_callsign + " Abort Landing",{permanent:false,direction:'right'});
            if(chase_config.show_abort == true){
                balloon_positions[_callsign].abort_marker.addTo(map);
            }
        }else{
            balloon_positions[_callsign].abort_marker.setLatLng(data.abort_landing);
        }

        balloon_positions[_callsign].abort_path.setLatLngs(data.abort_path);
    }else{
        // Clear out the abort and abort marker data.
        balloon_positions[_callsign].abort_path.setLatLngs([]);

        if (balloon_positions[_callsign].abort_marker != null){
            balloon_positions[_callsign].abort_marker.remove();
        }
    }
    // Reset the prediction data age counter.
    pred_data_age = 0.0;

    // Update the routing engine.
    //if (balloon_currently_following === data.callsign){
    //    router.setWaypoints([L.latLng(chase_car_position.latest_data[0],chase_car_position.latest_data[1]), L.latLng(data.pred_landing[0], data.pred_landing[1])]);
    //}
}