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


function selectPayloadFollow(){}
// TODO. Allow selection of a specific payload to follow. 


// Initialise tables
function initTables(){
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
            {title:"Alt (m)", field:"alt", headerSort:false},
            {title:"V_rate (m/s)", field:"vel_v", headerSort:false},
            {title:"Aux", field:'aux', headerSort:false}
        ]
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
}


function updateTelemetryTable(){
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
            balloon_call_data.alt = balloon_call_data.position[2].toFixed(1) + " (" + balloon_call_data.max_alt.toFixed(0) + ")" ;
            balloon_call_data.vel_v = balloon_call_data.vel_v.toFixed(1);

            // Add in any extra data to the aux field.
            balloon_call_data.aux = "";

            if (balloon_call_data.hasOwnProperty('bt')){
                if ((balloon_call_data.bt >= 0) && (balloon_call_data.bt < 65535)) {
                    balloon_call_data.aux += "BT " + new Date(balloon_call_data.bt*1000).toISOString().substr(11, 8) + " ";
                }
            }

            // Update table
            telem_data.push(balloon_call_data);
        }
    }

    $("#telem_table").tabulator("setData", telem_data);
}