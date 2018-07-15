//
//


// Initialise tables
function initTables(){
    // Telemetry data table
    $("#telem_table").tabulator({
        layout:"fitData", 
        layoutColumnsOnNewData:true,
        columns:[ //Define Table Columns
            {title:"Callsign", field:"callsign", headerSort:false},
            {title:"Time (Z)", field:"short_time", headerSort:false},
            {title:"Latitude", field:"lat", headerSort:false},
            {title:"Longitude", field:"lon", headerSort:false},
            {title:"Alt (m)", field:"alt", headerSort:false},
            {title:"V_rate (m/s)", field:"vel_v", headerSort:false}
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
        data:[{alt:'-----m', speed:'---kph', vel_v:'-.-m/s', azimuth:'---°', elevation:'--°', range:'----m'}]
    });

    //var dummy_data = {alt:'-----m', speed:'---kph', vel_v:'-.-m/s', azimuth:'---°', elev:'--°', range:'----m'};
    //$("#summary_table").tabulator("setData", dummy_data);
}

function updateTelemetryTable(){
    var telem_data = [];

    if (jQuery.isEmptyObject(balloon_positions)){
        telem_data = [{callsign:'None'}];
    }else{
        for (balloon_call in balloon_positions){
            var balloon_call_data = Object.assign({},balloon_positions[balloon_call].latest_data);
            var balloon_call_age = balloon_positions[balloon_call].age;
            //if ((Date.now()-balloon_call_age)>180000){
            //    balloon_call_data.callsign = "";
            //}
            // Modify some of the fields to fixed point values.
            balloon_call_data.lat = balloon_call_data.position[0].toFixed(5);
            balloon_call_data.lon = balloon_call_data.position[1].toFixed(5);
            balloon_call_data.alt = balloon_call_data.position[2].toFixed(1);
            balloon_call_data.vel_v = balloon_call_data.vel_v.toFixed(1);

            telem_data.push(balloon_call_data);
        }
    }

    $("#telem_table").tabulator("setData", telem_data);
}