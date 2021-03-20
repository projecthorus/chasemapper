//
//   Project Horus - Browser-Based Chase Mapper - Utility Functions
//
//   Copyright (C) 2019  Mark Jessop <vk5qi@rfhead.net>
//   Released under GNU GPL v3 or later
//

// Color cycling for balloon traces and icons - Hopefully 4 colors should be enough for now!
var colour_values = ['blue','green','purple'];
var colour_idx = 0;

// Create a set of icons for the different colour values.
var balloonAscentIcons = {};
var balloonDescentIcons = {};
var balloonLandingIcons = {};
var balloonPayloadIcons = {};

// TODO: Make these /static URLS be filled in with templates (or does it not matter?)
for (_col in colour_values){
	balloonAscentIcons[colour_values[_col]] =  L.icon({
        iconUrl: "/static/img/balloon-" + colour_values[_col] + '.png',
        iconSize: [46, 85],
        iconAnchor: [23, 76]
    });
    balloonDescentIcons[colour_values[_col]] = L.icon({
	    iconUrl: "/static/img/parachute-" + colour_values[_col] + '.png',
	    iconSize: [46, 84],
	    iconAnchor: [23, 76]
    });
    balloonLandingIcons[colour_values[_col]] = L.icon({
        iconUrl: "/static/img/target-" + colour_values[_col] + '.png',
        iconSize: [20, 20],
        iconAnchor: [10, 10]
    });  
    balloonPayloadIcons[colour_values[_col]] = L.icon({
        iconUrl: "/static/img/payload-" + colour_values[_col] + '.png',
        iconSize: [17, 18],
        iconAnchor: [8, 14]
    });  
}

// Burst Icon
var burstIcon = L.icon({
    iconUrl: "/static/img/balloon-pop.png",
    iconSize: [20,20],
    iconAnchor: [10,10]
});

// Abort prediction icon (red)
var abortIcon = L.icon({
    iconUrl: "/static/img/target-red.png",
    iconSize: [20,20],
    iconAnchor: [10,10]
});

// Icons for our own chase car.
var carIcon = L.icon({
    iconUrl: "/static/img/car-blue.png",
    iconSize: [55,25],
    iconAnchor: [27,12] // Revisit this
});

var carIconFlip = L.icon({
    iconUrl: "/static/img/car-blue-flip.png",
    iconSize: [55,25],
    iconAnchor: [27,12] // Revisit this
});

// Home Icon.
var homeIcon = L.icon({
    iconUrl: '/static/img/antenna-green.png',
    iconSize: [26, 34],
    iconAnchor: [13, 34]
});


// Habitat (or APRS?) sourced chase car icons.
var car_colour_values = ['red', 'green', 'yellow'];
var car_colour_idx = 0;
var habitat_car_icons = {};
var habitat_car_icons_flipped = {};
for (_col in car_colour_values){
    habitat_car_icons[car_colour_values[_col]] = L.icon({
    iconUrl: "/static/img/car-"+car_colour_values[_col]+".png",
    iconSize: [55,25],
    iconAnchor: [27,12] // Revisit this
    });

    habitat_car_icons_flipped[car_colour_values[_col]] = L.icon({
    iconUrl: "/static/img/car-"+car_colour_values[_col]+"-flip.png",
    iconSize: [55,25],
    iconAnchor: [27,12] // Revisit this
    });
}


// calculates look angles between two points
// format of a and b should be {lon: 0, lat: 0, alt: 0}
// returns {elevention: 0, azimut: 0, bearing: "", range: 0}
//
// based on earthmath.py
// Copyright 2012 (C) Daniel Richman; GNU GPL 3

var DEG_TO_RAD = Math.PI / 180.0;
var EARTH_RADIUS = 6371000.0;

function calculate_lookangles(a, b) {
    // degrees to radii
    a.lat = a.lat * DEG_TO_RAD;
    a.lon = a.lon * DEG_TO_RAD;
    b.lat = b.lat * DEG_TO_RAD;
    b.lon = b.lon * DEG_TO_RAD;

    var d_lon = b.lon - a.lon;
    var sa = Math.cos(b.lat) * Math.sin(d_lon);
    var sb = (Math.cos(a.lat) * Math.sin(b.lat)) - (Math.sin(a.lat) * Math.cos(b.lat) * Math.cos(d_lon));
    var bearing = Math.atan2(sa, sb);
    var aa = Math.sqrt(Math.pow(sa, 2) + Math.pow(sb, 2));
    var ab = (Math.sin(a.lat) * Math.sin(b.lat)) + (Math.cos(a.lat) * Math.cos(b.lat) * Math.cos(d_lon));
    var angle_at_centre = Math.atan2(aa, ab);
    var great_circle_distance = angle_at_centre * EARTH_RADIUS;

    ta = EARTH_RADIUS + a.alt;
    tb = EARTH_RADIUS + b.alt;
    ea = (Math.cos(angle_at_centre) * tb) - ta;
    eb = Math.sin(angle_at_centre) * tb;
    var elevation = Math.atan2(ea, eb) / DEG_TO_RAD;

    // Use Math.coMath.sine rule to find unknown side.
    var distance = Math.sqrt(Math.pow(ta, 2) + Math.pow(tb, 2) - 2 * tb * ta * Math.cos(angle_at_centre));

    // Give a bearing in range 0 <= b < 2pi
    bearing += (bearing < 0) ? 2 * Math.PI : 0;
    bearing /= DEG_TO_RAD;

    var value = Math.round(bearing % 90);
    value = ((bearing > 90 && bearing < 180) || (bearing > 270 && bearing < 360)) ? 90 - value : value;

    var str_bearing = "" + ((bearing < 90 || bearing > 270) ? 'N' : 'S')+ " " + value + '° ' + ((bearing < 180) ? 'E' : 'W');

    return {
        'elevation': elevation,
        'azimuth': bearing,
        'range': distance,
        'bearing': str_bearing
    };
}

function textToClipboard(text) {
    // Copy a string to the user's clipboard.
    // From here: https://stackoverflow.com/questions/33855641/copy-output-of-a-javascript-variable-to-the-clipboard
    var dummy = document.createElement("textarea");
    document.body.appendChild(dummy);
    dummy.value = text;
    dummy.select();
    document.execCommand("copy");
    document.body.removeChild(dummy);
}