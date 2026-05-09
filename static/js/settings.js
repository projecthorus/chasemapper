//
//   Project Horus - Browser-Based Chase Mapper - Settings
//
//   Copyright (C) 2019  Mark Jessop <vk5qi@rfhead.net>
//   Released under GNU GPL v3 or later
//

// Global map settings
var prediction_opacity = 0.6;
var parachute_min_alt = 300; // Show the balloon as a 'landed' payload below this altitude.

var car_bad_age = 5.0;
var payload_bad_age = 30.0;


// Chase Mapper Configuration Parameters.
// These are dummy values which will be populated on startup.
var chase_config = {
    // Start location for the map (until either a chase car position, or balloon position is available.)
    default_lat: -34.9,
    default_lon: 138.6,

    // Predictor settings
    pred_enabled: true,  // Enable running and display of predicted flight paths.
    // Default prediction settings (actual values will be used once the flight is underway)
    pred_desc_rate: 6.0,
    pred_burst: 28000,
    pred_update_rate: 15,
    pred_model: 'Disabled',
    show_abort: true, // Show a prediction of an 'abort' paths (i.e. if the balloon bursts *now*)
    offline_tile_layers: [],
    habitat_call: 'N0CALL'
};


// Refresh a "(N ft)" hint next to a meters input. Reads the live
// input value (so it updates as the user types), converts to feet,
// and formats with thousands separator + 1 decimal. Empty/invalid
// input clears the hint.
function updateAltFeet(inputId, spanId){
    var inp = document.getElementById(inputId);
    var span = document.getElementById(spanId);
    if (!inp || !span) return;
    var v = parseFloat(inp.value);
    if (isNaN(v)) { span.textContent = ""; return; }
    var ft = v * 3.28084;
    span.textContent = "(" + ft.toLocaleString(undefined, {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1
    }) + " ft)";
}

// Parse a duration string into hours (float).
// Accepts:
//   "2:30"   -> 2.5      (hh:mm)
//   "0:45"   -> 0.75
//   "24:00"  -> 24.0
//   "2.5"    -> 2.5      (legacy decimal hours)
//   "2"      -> 2.0
// Returns NaN on garbage. Minutes >= 60 are accepted (so "1:90" = 2.5h)
// because some users may type that and it's unambiguous.
function parseDurationHours(s){
    if (s === null || s === undefined) return NaN;
    s = String(s).trim();
    if (s === "") return NaN;
    if (s.indexOf(":") >= 0) {
        var parts = s.split(":");
        if (parts.length !== 2) return NaN;
        var h = parseInt(parts[0], 10);
        var m = parseFloat(parts[1]);
        if (isNaN(h) || isNaN(m) || h < 0 || m < 0) return NaN;
        return h + m / 60.0;
    }
    var v = parseFloat(s);
    return isNaN(v) ? NaN : v;
}

// Format hours (float) as "hh:mm". 2.5 -> "2:30", 0.75 -> "0:45".
// Rounds to nearest minute. Negative or non-finite -> "0:00".
function formatDurationHours(hours){
    if (typeof hours !== "number" || !isFinite(hours) || hours < 0) hours = 0;
    var totalMin = Math.round(hours * 60);
    var h = Math.floor(totalMin / 60);
    var m = totalMin % 60;
    return h + ":" + (m < 10 ? "0" + m : m);
}

// Refresh the "(N.NN h)" hint next to an hh:mm duration input.
function updateDurationHours(inputId, spanId){
    var inp = document.getElementById(inputId);
    var span = document.getElementById(spanId);
    if (!inp || !span) return;
    var h = parseDurationHours(inp.value);
    if (isNaN(h)) { span.textContent = ""; return; }
    span.textContent = "(" + h.toFixed(2) + " h)";
}

function serverSettingsUpdate(data){
    // Accept a json blob of settings data from the client, and update our local store.
    chase_config = data;
    // Update a few fields based on this data.
    $("#predictorModelValue").text(chase_config.pred_model);
    $('#burstAlt').val(chase_config.pred_burst.toFixed(0));
    updateAltFeet('burstAlt', 'burstAltFeet');
    $('#descentRate').val(chase_config.pred_desc_rate.toFixed(1));
    $('#predUpdateRate').val(chase_config.pred_update_rate.toFixed(0));
    $('#habitatUpdateRate').val(chase_config.habitat_update_rate.toFixed(0));
    $("#predictorEnabled").prop('checked', chase_config.pred_enabled);
    $("#habitatUploadEnabled").prop('checked', chase_config.habitat_upload_enabled);
    $("#showOtherCars").prop('checked', chase_config.habitat_upload_enabled);
    $("#habitatCall").val(chase_config.habitat_call);
    $("#abortPredictionEnabled").prop('checked', chase_config.show_abort);

    // Range ring settings.
    $('#ringQuantity').val(chase_config.range_ring_quantity.toFixed(0));
    $('#ringSpacing').val(chase_config.range_ring_spacing.toFixed(0));
    $('#ringWeight').val(chase_config.range_ring_weight.toFixed(1));
    $('#ringColorSelect').val(chase_config.range_ring_color);
    $('#ringCustomColor').val(chase_config.range_ring_custom_color);
    $('#rangeRingsEnabled').prop('checked', chase_config.range_rings_enabled);
    
    // Chase Car Speedometer
    $('#showCarSpeed').prop('checked', chase_config.chase_car_speed);

    // Bearing settings
    $('#bearingLength').val(chase_config.bearing_length.toFixed(0));
    $('#bearingWeight').val(chase_config.bearing_weight.toFixed(1));
    $('#bearingColorSelect').val(chase_config.bearing_color);
    $('#bearingCustomColor').val(chase_config.bearing_custom_color);
    $('#bearingMaximumAge').val((chase_config.max_bearing_age/60.0).toFixed(0));
    $('#bearingConfidenceThreshold').val(chase_config.doa_confidence_threshold.toFixed(1));

    $('#bearingsOnlyMode').prop('checked', chase_config.bearings_only_mode);
    toggleBearingsOnlyMode()
    // Add new time sync bearing settings here

    timeSeqEnabled = chase_config.time_seq_enabled;
    $("#timeSeqEnabled").prop('checked', timeSeqEnabled);
    timeSeqActive = chase_config.time_seq_active;
    timeSeqCycle = chase_config.time_seq_cycle;
    timeSeqTimes = chase_config.time_seq_times;
    updateTimeSeqStatus();


    // Clear and populate the profile selection.
    $('#profileSelect').children('option:not(:first)').remove();

    $.each(chase_config.profiles, function(key, value) {
         $('#profileSelect')
             .append($("<option></option>")
             .attr("value",key)
             .text(key));
    });
    $("#profileSelect").val(chase_config.selected_profile);

    // Float (GHOUL) settings — global toggle, applies to whichever
    // telemetry profile is active. Defaults match config.py.
    var _fe = !!chase_config.float_enabled;
    var _fa = (typeof chase_config.float_altitude === 'number') ? chase_config.float_altitude : 25000.0;
    var _fd = (typeof chase_config.float_duration_hours === 'number') ? chase_config.float_duration_hours : 24.0;
    $("#floatEnabled").prop('checked', _fe);
    $("#floatAltitude").val(_fa.toFixed(0));
    updateAltFeet('floatAltitude', 'floatAltitudeFeet');
    $("#floatDuration").val(formatDurationHours(_fd));
    updateDurationHours('floatDuration', 'floatDurationHours');

    // Update version
    $('#chasemapper_version').html(chase_config.version);

}

function clientSettingsUpdate(){
	// Read in changs to various user-modifyable settings, and send updates to the server.
	chase_config.pred_enabled = document.getElementById("predictorEnabled").checked;
    chase_config.show_abort = document.getElementById("abortPredictionEnabled").checked;
    chase_config.habitat_upload_enabled = document.getElementById("habitatUploadEnabled").checked;
    chase_config.habitat_call = $('#habitatCall').val()

    // Attempt to parse the text field values.
    var _burst_alt = parseFloat($('#burstAlt').val());
    if (isNaN(_burst_alt) == false){
        chase_config.pred_burst = _burst_alt;
    }
    var _desc_rate = parseFloat($('#descentRate').val());
    if (isNaN(_desc_rate) == false){
        chase_config.pred_desc_rate = _desc_rate
    }
    var _update_rate = parseInt($('#predUpdateRate').val());
    if (isNaN(_update_rate) == false){
        chase_config.pred_update_rate = _update_rate
    }

    var _habitat_update_rate = parseInt($('#habitatUpdateRate').val());
    if (isNaN(_habitat_update_rate) == false){
        chase_config.habitat_update_rate = _habitat_update_rate
    }

    // Float (GHOUL) settings — global, picked up server-side by the
    // existing client_settings_update handler.
    chase_config.float_enabled = document.getElementById("floatEnabled").checked;
    var _fa = parseFloat($('#floatAltitude').val());
    if (isNaN(_fa) == false) chase_config.float_altitude = _fa;
    var _fd = parseDurationHours($('#floatDuration').val());
    if (isNaN(_fd) == false) chase_config.float_duration_hours = _fd;

    // Add in a selection of the bearing settings here.
    // These don't change anything on the backend, but need to be propagated to other clients.
    chase_config.time_seq_times = timeSeqTimes;
    chase_config.time_seq_enabled = timeSeqEnabled;
    chase_config.time_seq_active = timeSeqActive;
    chase_config.time_seq_cycle = timeSeqCycle;

    socket.emit('client_settings_update', chase_config);
};