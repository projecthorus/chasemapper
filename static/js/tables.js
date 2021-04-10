//
//   Project Horus - Browser-Based Chase Mapper - Table Handlers
//
//   Copyright (C) 2019  Mark Jessop <vk5qi@rfhead.net>
//   Released under GNU GPL v3 or later
//

// Allow for the summary window to be expanded with a tap.
var summary_enlarged = false;

function toggleSummarySize(){
    var row = $("#summary_table").tabulator("getRow", 1);
    if(summary_enlarged == false){
        row.getElement().addClass("largeTableRow");
        summary_enlarged = true;
    }else{
        row.getElement().removeClass("largeTableRow");
        summary_enlarged = false;
    }
    $("#summary_table").tabulator("redraw", true);
}

// Allow for the telemetry table to be expanded/hidden with a click.
var telemetry_table_hidden = false;

function toggleTelemTableHide(){
    if(telemetry_table_hidden == false){
        $('#telem_table_btn').html("<i class='fa fa-angle-left fa-4x text-center'></i>");
        $("#telem_table").hide("slide", { direction: "right" }, "fast" );
        telemetry_table_hidden = true;
    }else{
        $('#telem_table_btn').html("<i class='fa fa-angle-right fa-4x text-center'></i>");
        $("#telem_table").show("slide", { direction: "right" }, "fast" );
        telemetry_table_hidden = false;
    }
}

function markPayloadRecovered(callsign){
    // Grab the most recent telemetry, along with a few other parameters.
    var _recovery_data = {
        my_call: chase_config.habitat_call,
        payload_call: callsign,
        recovery_title: callsign + " recovered by " + chase_config.habitat_call, 
        last_pos: balloon_positions[callsign].latest_data.position,
        message: ""
    };

    // Populate fields in the dialog window.
    $('#customRecoveryTitle').val(_recovery_data.recovery_title);
    $('#recoveryPosition').html(_recovery_data.last_pos[0].toFixed(5) + ", " + _recovery_data.last_pos[1].toFixed(5));

    // Pop up a dialog box so the user can enter a custom message if they want.
    var divObj = $('#mark-recovered-dialog');
    divObj.dialog({
        autoOpen: false,
        //bgiframe: true,
        modal: true,
        resizable: false,
        height: "auto",
        width: 500,
        title: "Mark " + callsign + " recovered",
        buttons: {
        "Submit": function() {
          $( this ).dialog( "close" );
          _recovery_data.message = $('#customRecoveryMessage').val();
          _recovery_data.recovery_title = $('#customRecoveryTitle').val();

          // If the user has requested to use the chase car position, override the last position with it.
          if(document.getElementById("recoveryCarPosition").checked == true){
            _recovery_data.last_pos = chase_car_position.latest_data;
          }

          socket.emit('mark_recovered', _recovery_data);
        },
        Cancel: function() {
          $( this ).dialog( "close" );
        }
      }
    });
    divObj.dialog('open');
}


function setRecoveryCarPosition(){
    // Set recovery position to the chase car position.
    $('#recoveryPosition').html(chase_car_position.latest_data[0].toFixed(5) + ", " + chase_car_position.latest_data[0].toFixed(5));
}


// Dialog box for when a user clicks/taps on a row of the telemetry table.
function telemetryTableDialog(e, row){
    callsign = row.row.data.callsign;

    if (callsign === "None"){
        return;
    }

    // Add the last position to the dialog box, and create it as a geo link.
    var _last_pos = balloon_positions[callsign].latest_data.position;
    $('#telemDialogPosition').html("<a href='geo:" + _last_pos[0].toFixed(5) + "," + _last_pos[1].toFixed(5) + "'>" + _last_pos[0].toFixed(5) + ", " + _last_pos[1].toFixed(5) + "</a>");

    if(balloon_positions[callsign].pred_marker != null){
        var _pred_latlng = balloon_positions[callsign].pred_marker.getLatLng();
        $('#telemDialogPredPosition').html("<a href='geo:" + _pred_latlng.lat.toFixed(5) + "," + _pred_latlng.lng.toFixed(5) + "'>" + _pred_latlng.lat.toFixed(5) + ", " + _pred_latlng.lng.toFixed(5) + "</a>");

    }else{
        $('#telemDialogPredPosition').html("Unknown");
    }

    var _buttons = {
        "Follow": function() {
          // Follow the currently selected callsign.
          balloon_currently_following = callsign;
          $( this ).dialog( "close" );
        },
        "Mark Recovered": function() {
          $( this ).dialog( "close" );
          // Pop up another dialog box to enter details for marking the payload as recovered.
          markPayloadRecovered(callsign);
        }
      };

      if (balloon_positions[callsign].visible == true){
          _buttons["Hide"] = function() {
            // Follow the currently selected callsign.
            hideBalloon(callsign);
            $( this ).dialog( "close" );
          };
      } else{
        _buttons["Show"] = function() {
            // Follow the currently selected callsign.
            showBalloon(callsign);
            $( this ).dialog( "close" );
          };
      }

    _buttons.Cancel = function() {
        $( this ).dialog( "close" );
      };

    var divObj = $('#telemetry-select-dialog');
    divObj.dialog({
        autoOpen: false,
        //bgiframe: true,
        modal: true,
        resizable: false,
        height: "auto",
        width: 400,
        title: "Payload: " + callsign,
        buttons: _buttons
    });
    divObj.dialog('open');
}


// Initialise tables
function initTables(){
    // Telemetry data table
    if (chase_config['unitselection'] == "imperial") {initTablesImperial() ; return ; } // else do everything in metric
    $("#telem_table").tabulator({
        layout:"fitData", 
        layoutColumnsOnNewData:true,
        //selectable:1, // TODO...
        columns:[ //Define Table Columns
            {title:"Callsign", field:"callsign", headerSort:false},
            {title:"Time (Z)", field:"short_time", headerSort:false},
            {title:"Latitude", field:"lat", headerSort:false},
            {title:"Longitude", field:"lon", headerSort:false},
            {title:"Alt (m)", field:"alt", headerSort:false},
            {title:"V_rate (m/s)", field:"vel_v", headerSort:false},
            {title:"SNR", field:'snr', headerSort:false, visible:false},
            {title:"Aux", field:'aux', headerSort:false, visible:false}
        ],
        rowClick:function(e, row){telemetryTableDialog(e, row);},
        rowTap:function(e, row){telemetryTableDialog(e, row);}

    });

    $("#summary_table").tabulator({
        layout:"fitData", 
        layoutColumnsOnNewData:true,
        columns:[ //Define Table Columns
            {title:"Alt (m)", field:"alt", headerSort:false},
            {title:"Speed (kph)", field:"speed", headerSort:false},
            {title:"Asc Rate (m/s)", field:"vel_v", headerSort:false},
            {title:"Azimuth", field:"azimuth", headerSort:false},
            {title:"Elevation", field:"elevation", headerSort:false},
            {title:"Range", field:"range", headerSort:false},
        ],
        data:[{id: 1, alt:'-----m', speed:'---kph', vel_v:'-.-m/s', azimuth:'---°', elevation:'--°', range:'----m'}],
        rowClick:function(e, row){
            toggleSummarySize();
        },
        rowTap:function(e, row){
            toggleSummarySize();
        }
    });


    $("#bearing_table").tabulator({
        layout:"fitData", 
        layoutColumnsOnNewData:true,
        //selectable:1, // TODO...
        columns:[ //Define Table Columns
            {title:"Bearing", field:"bearing", headerSort:false},
            {title:"Score", field:'confidence', headerSort:false},
            {title:"Power", field:'power', headerSort:false}
        ],
        data:[{id: 1, bearing:0.0, confidence:0.0}]
    });

    $("#bearing_table").hide();
}

// Initialise tables in Imperial - Vertical velocity feet/min, Horizontal velocity Miles/hr, Range Miles then feet for Range < config setting 
function initTablesImperial(){
    // Telemetry data table
    $("#telem_table").tabulator({
        layout:"fitData", 
        layoutColumnsOnNewData:true,
        //selectable:1, // TODO...
        columns:[ //Define Table Columns
            {title:"Callsign", field:"callsign", headerSort:false},
            {title:"Time (Z)", field:"short_time", headerSort:false},
            {title:"Latitude", field:"lat", headerSort:false},
            {title:"Longitude", field:"lon", headerSort:false},
            {title:"Alt (ft)", field:"alt", headerSort:false},
            {title:"V_rate (ft/min)", field:"vel_v", headerSort:false},
            {title:"SNR", field:'snr', headerSort:false, visible:false},
            {title:"Aux", field:'aux', headerSort:false, visible:false}
        ],
        rowClick:function(e, row){telemetryTableDialog(e, row);},
        rowTap:function(e, row){telemetryTableDialog(e, row);}

    });

    $("#summary_table").tabulator({
        layout:"fitData", 
        layoutColumnsOnNewData:true,
        columns:[ //Define Table Columns
            {title:"Alt (ft)", field:"alt", headerSort:false},
            {title:"Speed (mph)", field:"speed", headerSort:false},
            {title:"Asc Rate (ft/min)", field:"vel_v", headerSort:false},
            {title:"Azimuth", field:"azimuth", headerSort:false},
            {title:"Elevation", field:"elevation", headerSort:false},
            {title:"Range", field:"range", headerSort:false},
        ],
        data:[{id: 1, alt:'-----ft', speed:'---mph', vel_v:'---ft/min', azimuth:'---°', elevation:'--°', range:'---- miles'}],
        rowClick:function(e, row){
            toggleSummarySize();
        },
        rowTap:function(e, row){
            toggleSummarySize();
        }
    });


    $("#bearing_table").tabulator({
        layout:"fitData", 
        layoutColumnsOnNewData:true,
        //selectable:1, // TODO...
        columns:[ //Define Table Columns
            {title:"Bearing", field:"bearing", headerSort:false},
            {title:"Score", field:'confidence', headerSort:false},
            {title:"Power", field:'power', headerSort:false}
        ],
        data:[{id: 1, bearing:0.0, confidence:0.0}]
    });

    $("#bearing_table").hide();
}


function updateTelemetryTable(){
    var telem_data = [];
    if (chase_config['unitselection'] == "imperial") {updateTelemetryTableImperial() ; return ; } // else do everything in metric
    if (jQuery.isEmptyObject(balloon_positions)){
        telem_data = [{callsign:'None'}];
    }else{
        for (balloon_call in balloon_positions){
            var balloon_call_data = Object.assign({},balloon_positions[balloon_call].latest_data);
            var balloon_call_age = balloon_positions[balloon_call].age;

            // Modify some of the fields to fixed point values.
            balloon_call_data.lat = balloon_call_data.position[0].toFixed(5);
            balloon_call_data.lon = balloon_call_data.position[1].toFixed(5);
            balloon_call_data.alt = balloon_call_data.position[2].toFixed(0) + " (" + balloon_call_data.max_alt.toFixed(0) + ")" ;
            balloon_call_data.vel_v = balloon_call_data.vel_v.toFixed(1);

            // Add in any extra data to the aux field.
            balloon_call_data.aux = "";
            balloon_call_data.snr = "";

            if (balloon_call_data.hasOwnProperty('bt')){
                if ((balloon_call_data.bt >= 0) && (balloon_call_data.bt < 65535)) {
                    balloon_call_data.aux += "BT " + new Date(balloon_call_data.bt*1000).toISOString().substr(11, 8) + " ";
                    $("#telem_table").tabulator("showColumn", "aux");
                }
            }

            if (balloon_positions[balloon_call].hasOwnProperty('snr')){
                if (balloon_positions[balloon_call].snr > -255.0){
                    balloon_call_data.snr = balloon_positions[balloon_call].snr.toFixed(1);
                    $("#telem_table").tabulator("showColumn", "snr");
                }
            }

            // Update table
            telem_data.push(balloon_call_data);
        }
    }

    $("#telem_table").tabulator("setData", telem_data);
}

function updateTelemetryTableImperial(){
    var telem_data = [];
    if (jQuery.isEmptyObject(balloon_positions)){
        telem_data = [{callsign:'None'}];
    }else{
        for (balloon_call in balloon_positions){
            var balloon_call_data = Object.assign({},balloon_positions[balloon_call].latest_data);
            var balloon_call_age = balloon_positions[balloon_call].age;

            // Modify some of the fields to fixed point values.
            balloon_call_data.lat = balloon_call_data.position[0].toFixed(5);
            balloon_call_data.lon = balloon_call_data.position[1].toFixed(5);
            balloon_call_data.alt = (balloon_call_data.position[2]*3.28084).toFixed(1) + " (" + (balloon_call_data.max_alt*3.28084).toFixed(0) + ")" ;
            balloon_call_data.vel_v = (balloon_call_data.vel_v*3.28084*60).toFixed(1);

            // Add in any extra data to the aux field.
            balloon_call_data.aux = "";
            balloon_call_data.snr = "";

            if (balloon_call_data.hasOwnProperty('bt')){
                if ((balloon_call_data.bt >= 0) && (balloon_call_data.bt < 65535)) {
                    balloon_call_data.aux += "BT " + new Date(balloon_call_data.bt*1000).toISOString().substr(11, 8) + " ";
                    $("#telem_table").tabulator("showColumn", "aux");
                }
            }

            if (balloon_positions[balloon_call].hasOwnProperty('snr')){
                if (balloon_positions[balloon_call].snr > -255.0){
                    balloon_call_data.snr = balloon_positions[balloon_call].snr.toFixed(1);
                    $("#telem_table").tabulator("showColumn", "snr");
                }
            }

            // Update table
            telem_data.push(balloon_call_data);
        }
    }

    $("#telem_table").tabulator("setData", telem_data);
}
