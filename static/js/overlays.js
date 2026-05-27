//
//   Project Horus - Browser-Based Chase Mapper - Map Overlay Handlers
//
//   Released under GNU GPL v3 or later
//

function htmlEscape(value){
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}


function bindKmlPopup(feature, layer){
    if (!feature.properties){
        return;
    }

    var _popup_parts = [];
    if (feature.properties.name){
        _popup_parts.push("<b>" + htmlEscape(feature.properties.name) + "</b>");
    }
    if (feature.properties.description){
        _popup_parts.push(htmlEscape(feature.properties.description));
    }

    if (_popup_parts.length > 0){
        layer.bindPopup(_popup_parts.join("<br>"));
    }
}


function loadConfiguredKmlOverlays(config, map){
    var _overlay_layers = {};

    if (!config.hasOwnProperty("kml_overlays") || config.kml_overlays.length == 0){
        return _overlay_layers;
    }

    if (typeof omnivore === "undefined"){
        console.log("KML overlays configured, but leaflet-omnivore is not loaded.");
        return _overlay_layers;
    }

    for (var i = 0, len = config.kml_overlays.length; i < len; i++) {
        var _overlay = config.kml_overlays[i];
        var _custom_layer = L.geoJson(null, {
            onEachFeature: bindKmlPopup
        });

        var _layer = omnivore.kml(
            "/overlays/kml/" + encodeURIComponent(_overlay.id),
            null,
            _custom_layer
        );

        _layer.on("error", function(e) {
            console.log("Error loading KML overlay", e);
        });

        _overlay_layers[_overlay.name] = _layer;

        if (_overlay.visible == true){
            _layer.addTo(map);
        }
    }

    return _overlay_layers;
}
