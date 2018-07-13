// Utility Functions
// Mark Jessop 2018-06-30




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

var abortIcon = L.icon({
    iconUrl: "/static/img/target-red.png",
    iconSize: [20,20],
    iconAnchor: [10,10]
});

var carIcon = L.icon({
    iconUrl: "/static/img/car-blue.png",
    iconSize: [55,25],
    iconAnchor: [27,12] // Revisit this
});

// Other Global map settings
var prediction_opacity = 0.6;
var parachute_min_alt = 300; // Show the balloon as a 'landed' payload below this altitude.