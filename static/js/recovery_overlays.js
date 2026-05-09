//
// Project Horus - Browser-Based Chase Mapper - Recovery Overlays
//
// Self-contained module exposing window.RecoveryOverlays.
// Adds toggleable FAA airspace, TFR, and Maryland parcel overlays plus
// platform-aware Maps links on the predicted landing marker.
//
(function () {
    "use strict";

    var AIRSPACE_LAYERS = ["class_b", "class_c", "class_d", "class_e", "sua", "tfr"];

    var AIRSPACE_STYLE = {
        class_b: { color: "#1f4ed8", weight: 2, fillOpacity: 0.05 },
        class_c: { color: "#7c3aed", weight: 2, fillOpacity: 0.05 },
        class_d: { color: "#0ea5e9", weight: 2, fillOpacity: 0.05 },
        class_e: { color: "#64748b", weight: 1, fillOpacity: 0.03 },
        sua:     { color: "#dc2626", weight: 2, fillOpacity: 0.08 },
        tfr:     { color: "#f97316", weight: 2, fillOpacity: 0.15 }
    };

    var PARCEL_STYLE = { color: "#ea580c", weight: 1, fillOpacity: 0.08 };
    var SEARCH_CIRCLE_STYLE = { color: "#dc2626", weight: 2, dashArray: "6,6", fill: false };

    var state = {
        map: null,
        landing: null,
        airspaceData: {},
        airspaceLayers: {},
        parcelLayer: null,
        parcelCanvas: null,
        searchCircle: null,
        parcelTimer: null,
        airspaceFetching: {}
    };

    function $(id) { return document.getElementById(id); }

    function setStatus(elId, text, isWarning) {
        var el = $(elId);
        if (!el) return;
        el.textContent = text || "";
        el.style.color = isWarning ? "#dc2626" : "#6b7280";
    }

    function googleMapsUrl(lat, lon) {
        return "https://www.google.com/maps/search/?api=1&query=" + lat + "," + lon;
    }
    function appleMapsUrl(lat, lon) {
        return "https://maps.apple.com/?ll=" + lat + "," + lon + "&q=" + lat + "," + lon;
    }
    function googleMapsAddrUrl(addr) {
        return "https://www.google.com/maps/search/?api=1&query=" + encodeURIComponent(addr);
    }
    function appleMapsAddrUrl(addr) {
        return "https://maps.apple.com/?address=" + encodeURIComponent(addr);
    }

    function mapsLinksHtml(lat, lon, addr) {
        var g = addr ? googleMapsAddrUrl(addr) : googleMapsUrl(lat, lon);
        var a = addr ? appleMapsAddrUrl(addr) : appleMapsUrl(lat, lon);
        return (
            '<a href="' + g + '" target="_blank" rel="noopener">Google Maps</a> · ' +
            '<a href="' + a + '" target="_blank" rel="noopener">Apple Maps</a>'
        );
    }

    function fetchAirspace(layer) {
        if (state.airspaceData[layer] || state.airspaceFetching[layer]) {
            return Promise.resolve(state.airspaceData[layer]);
        }
        state.airspaceFetching[layer] = true;
        return fetch("/airspace/" + layer)
            .then(function (r) {
                if (!r.ok) throw new Error("HTTP " + r.status);
                return r.json();
            })
            .then(function (data) {
                state.airspaceData[layer] = data;
                state.airspaceFetching[layer] = false;
                return data;
            })
            .catch(function (e) {
                state.airspaceFetching[layer] = false;
                setStatus("airspace-status", "Failed to load " + layer + ": " + e.message, true);
                return null;
            });
    }

    // Field-name fallbacks vary across FAA endpoints (Class_Airspace,
    // Special_Use_Airspace, TFR). Try common variants and stop at the first hit.
    function pickFirst(obj, keys) {
        for (var i = 0; i < keys.length; i++) {
            var v = obj[keys[i]];
            if (v !== undefined && v !== null && v !== "") return v;
        }
        return "";
    }

    function formatAlt(value, unit, codeword) {
        if (value === "" || value === undefined || value === null) return "";
        var v = String(value).trim();
        // Don't double-suffix if value already looks like "12000 FT" or "SFC".
        if (/[A-Za-z]/.test(v)) return v;
        var parts = [v];
        if (unit) parts.push(String(unit));
        if (codeword) parts.push(String(codeword));  // e.g. MSL, AGL
        return parts.join(" ");
    }

    function buildAirspacePopup(layer, props) {
        var p = props || {};
        var name = pickFirst(p, [
            "NAME", "name", "Name",
            "LOCAL_TYPE", "TYPE_CODE",
            "notam_id", "NOTAM_ID"
        ]) || layer.toUpperCase();

        var ceilVal = pickFirst(p, [
            "UPPER_VAL", "upperVal", "UPPER_ALT", "UPPER_LIMIT",
            "max_altitude", "maxAltitude", "MAX_ALT", "ceiling",
            "UPPER_DESC"
        ]);
        var ceilUnit = pickFirst(p, ["UPPER_UOM", "upperUom"]);
        var ceilCode = pickFirst(p, ["UPPER_CD", "UPPER_CODE", "UPPER_DESC_CODE"]);

        var floorVal = pickFirst(p, [
            "LOWER_VAL", "lowerVal", "LOWER_ALT", "LOWER_LIMIT",
            "min_altitude", "minAltitude", "MIN_ALT", "floor",
            "LOWER_DESC"
        ]);
        var floorUnit = pickFirst(p, ["LOWER_UOM", "lowerUom"]);
        var floorCode = pickFirst(p, ["LOWER_CD", "LOWER_CODE", "LOWER_DESC_CODE"]);

        var ceil = formatAlt(ceilVal, ceilUnit, ceilCode);
        var floor = formatAlt(floorVal, floorUnit, floorCode);

        var html = "<b>" + name + "</b>";
        if (floor || ceil) {
            html += "<br>" + (floor || "SFC") + " &mdash; " + (ceil || "?");
        }

        // TFR-specific extras: NOTAM number, type, description, expiration.
        var notam = pickFirst(p, [
            "notam_id", "NOTAM_ID", "notamId",
            "notam_number", "NOTAM_NUMBER", "notamNumber",
            "NOTAM", "notam"
        ]);
        if (notam) html += "<br><small><b>NOTAM:</b> " + notam + "</small>";

        var tfrType = pickFirst(p, ["type", "TYPE", "tfr_type"]);
        if (tfrType) html += "<br><small>" + tfrType + "</small>";
        var tfrDesc = pickFirst(p, ["description", "DESCRIPTION", "remarks"]);
        if (tfrDesc) {
            var trimmed = String(tfrDesc);
            if (trimmed.length > 200) trimmed = trimmed.slice(0, 200) + "…";
            html += "<br><small>" + trimmed + "</small>";
        }
        var tfrExp = pickFirst(p, ["expires_dt", "EXPIRES", "expiration"]);
        if (tfrExp) html += "<br><small>Expires: " + tfrExp + "</small>";

        return html;
    }

    function showAirspaceLayer(layer) {
        if (state.airspaceLayers[layer]) {
            state.airspaceLayers[layer].addTo(state.map);
            return;
        }
        fetchAirspace(layer).then(function (data) {
            if (!data) return;
            if (!$("toggle-" + layer.replace("_", "-")).checked) return;
            if (!$("toggle-airspace").checked) return;
            var leafletLayer = L.geoJSON(data, {
                renderer: L.canvas(),
                style: AIRSPACE_STYLE[layer],
                onEachFeature: function (feature, lyr) {
                    lyr.bindPopup(buildAirspacePopup(layer, feature.properties));
                }
            });
            state.airspaceLayers[layer] = leafletLayer;
            leafletLayer.addTo(state.map);
            setStatus("airspace-status", "Loaded " + (data.features || []).length + " " + layer + " features");
        });
    }

    function hideAirspaceLayer(layer) {
        if (state.airspaceLayers[layer]) {
            state.map.removeLayer(state.airspaceLayers[layer]);
        }
    }

    function syncAirspace() {
        var masterOn = $("toggle-airspace").checked;
        AIRSPACE_LAYERS.forEach(function (layer) {
            var subId = "toggle-" + layer.replace("_", "-");
            var sub = $(subId);
            if (masterOn && sub && sub.checked) {
                showAirspaceLayer(layer);
            } else {
                hideAirspaceLayer(layer);
            }
        });
    }

    function clearParcels() {
        if (state.parcelLayer) {
            state.map.removeLayer(state.parcelLayer);
            state.parcelLayer = null;
        }
        if (state.searchCircle) {
            state.map.removeLayer(state.searchCircle);
            state.searchCircle = null;
        }
    }

    function getRadiusMiles() {
        var slider = $("parcel-radius");
        return slider ? parseFloat(slider.value) : 0.5;
    }

    function renderSearchCircle() {
        if (!state.landing) return;
        if (state.searchCircle) state.map.removeLayer(state.searchCircle);
        var radiusMeters = getRadiusMiles() * 1609.344;
        state.searchCircle = L.circle(state.landing, Object.assign(
            { radius: radiusMeters }, SEARCH_CIRCLE_STYLE
        )).addTo(state.map);
    }

    function fetchParcels() {
        if (!$("toggle-parcels").checked) return;
        if (!state.landing) {
            setStatus("parcel-status", "Waiting for predicted landing point…");
            return;
        }
        var radius = getRadiusMiles();
        renderSearchCircle();
        var url = "/parcels?lat=" + state.landing[0] +
                  "&lon=" + state.landing[1] +
                  "&radius=" + radius;
        setStatus("parcel-status", "Loading parcels…");
        fetch(url)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!$("toggle-parcels").checked) return;
                if (data.error) {
                    if (state.parcelLayer) {
                        state.map.removeLayer(state.parcelLayer);
                        state.parcelLayer = null;
                    }
                    setStatus("parcel-status", data.error, true);
                    return;
                }
                if (state.parcelLayer) {
                    state.map.removeLayer(state.parcelLayer);
                }
                if (!state.parcelCanvas) state.parcelCanvas = L.canvas();
                state.parcelLayer = L.geoJSON(data, {
                    renderer: state.parcelCanvas,
                    style: PARCEL_STYLE,
                    onEachFeature: function (feature, lyr) {
                        var p = feature.properties || {};
                        var owner = p.OWNNAME1 || "(no owner)";
                        var addr = p.PREMISEADD || "";
                        var acct = p.ACCTID || "";
                        var html =
                            "<b>" + owner + "</b><br>" +
                            (addr ? addr + "<br>" : "") +
                            (acct ? "<small>Acct: " + acct + "</small><br>" : "") +
                            mapsLinksHtml(0, 0, addr || (state.landing && (state.landing[0] + "," + state.landing[1])));
                        lyr.bindPopup(html);
                    }
                }).addTo(state.map);
                var count = (data.features || []).length;
                var msg = count + " parcels within " + radius + " mi";
                if (data._truncated) msg += " (TRUNCATED, results capped)";
                setStatus("parcel-status", msg, !!data._truncated);
            })
            .catch(function (e) {
                setStatus("parcel-status", "Parcel fetch failed: " + e.message, true);
            });
    }

    function debounceParcelFetch() {
        if (state.parcelTimer) clearTimeout(state.parcelTimer);
        state.parcelTimer = setTimeout(fetchParcels, 400);
    }

    function wireToggles() {
        $("toggle-airspace").addEventListener("change", syncAirspace);
        AIRSPACE_LAYERS.forEach(function (layer) {
            var el = $("toggle-" + layer.replace("_", "-"));
            if (el) el.addEventListener("change", syncAirspace);
        });

        $("toggle-parcels").addEventListener("change", function () {
            if (this.checked) {
                debounceParcelFetch();
            } else {
                clearParcels();
                setStatus("parcel-status", "");
            }
        });

        var slider = $("parcel-radius");
        var label = $("parcel-radius-val");
        if (slider) {
            slider.addEventListener("input", function () {
                if (label) label.textContent = parseFloat(slider.value).toFixed(2) + " mi";
                if ($("toggle-parcels").checked) debounceParcelFetch();
            });
            if (label) label.textContent = parseFloat(slider.value).toFixed(2) + " mi";
        }
    }

    function attachLandingPopup(marker, lat, lon) {
        // Augment existing prediction marker popup with Maps links.
        var html =
            "<b>Predicted Landing</b><br>" +
            lat.toFixed(5) + ", " + lon.toFixed(5) + "<br>" +
            mapsLinksHtml(lat, lon);
        marker.bindPopup(html);
    }

    var Api = {
        init: function (map) {
            state.map = map;
            // Defer wiring until DOM elements exist; index.html may load this script
            // before the sidebar HTML is parsed.
            if (document.readyState === "loading") {
                document.addEventListener("DOMContentLoaded", wireToggles);
            } else {
                wireToggles();
            }
        },

        updateLandingPoint: function (lat, lon) {
            if (typeof lat !== "number" || typeof lon !== "number") return;
            state.landing = [lat, lon];

            // Augment any existing prediction markers with Maps links.
            if (typeof balloon_positions !== "undefined") {
                for (var cs in balloon_positions) {
                    var bp = balloon_positions[cs];
                    if (bp && bp.pred_marker) {
                        attachLandingPopup(bp.pred_marker, lat, lon);
                    }
                }
            }

            if ($("toggle-parcels") && $("toggle-parcels").checked) {
                debounceParcelFetch();
            }
        },

        _state: function () { return state; }
    };

    window.RecoveryOverlays = Api;
})();
