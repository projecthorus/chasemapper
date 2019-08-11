//
//   Project Horus - Browser-Based Chase Mapper - Car Position
//
//   Copyright (C) 2019  Mark Jessop <vk5qi@rfhead.net>
//   Released under GNU GPL v3 or later
//

var range_rings = [];
var range_rings_on = false;


function destroyRangeRings(){
	// Remove each range ring from the map.
	range_rings.forEach(function(element){
		element.remove();
	});
	// Clear the range ring array.
	range_rings = [];
	range_rings_on = false;
}


function createRangeRings(position){
	var _ring_quantity = parseInt($('#ringQuantity').val());
	var _ring_weight = parseFloat($('#ringWeight').val());
	var _ring_spacing = parseFloat($('#ringSpacing').val());
	var _ring_color = $('#ringColorSelect').val();
	var _ring_custom_color = $('#ringCustomColor').val();

	var _radius = _ring_spacing;
	var _color = "#FF0000";

	if(_ring_color == "red"){
		_color = "#FF0000";
	} else if (_ring_color == "black"){
		_color = "#000000";
	} else if (_ring_color == "blue"){
		_color = "#0000FF";
	} else if (_ring_color == "green"){
		_color = "#00FF00";
	} else if (_ring_color == "custom"){
		_color = _ring_custom_color;
	}

	for(var i=0; i<_ring_quantity; i++){
		var _ring = L.circle(position, {
			fill: false,
			color: _color,
			radius: _radius,
			weight: _ring_weight,
			opacity: 0.7
		}).addTo(map);
		range_rings.push(_ring);

		_radius += _ring_spacing;
	}

	range_rings_on = true;

}


function recenterRangeRings(position){

	if ((document.getElementById("rangeRingsEnabled").checked == true) && (range_rings_on == false)){
		// We have rings enabled, but haven't been able to create them yet.
		// Create them.
		updateRangeRings();
		return;
	} else {
		// Otherwise, just update the centre position of each ring.
		range_rings.forEach(function(element){
			element.setLatLng(position);
		});
	}
}


function updateRangeRings(){

	// Grab the range ring settings.
	var _ring_enabled = document.getElementById("rangeRingsEnabled").checked;

	// Check if we actually have a chase car position to work with.
	var _position = chase_car_position.latest_data;

	if (_position.length == 0){
		// No position available yet. Don't do anything.
		return;
	}
	// Otherwise, it looks like we have a position.

	if ((_ring_enabled == true) && (range_rings_on == false)){
		// The user had just enabled the range rings, so we need to create them.
		createRangeRings(_position);


	} else if ((_ring_enabled == false) && (range_rings_on == true)){
		// The user has disabled the range rings, so we remove them from the map.
		destroyRangeRings();

	} else {
		// Some other parameter has been changed.
		// Destroy, then re-create the range rings.
		destroyRangeRings();
		createRangeRings(_position);

	}

}