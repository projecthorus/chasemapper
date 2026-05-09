//
// Project Horus - Browser-Based Chase Mapper - Geofence Overlay
//
// Renders a per-profile geofence polygon (uploaded as a HAB Bounder
// KML) on the Leaflet map. The active profile's geofence is drawn
// whenever it is set; switching profiles swaps the polygon.
//
// Backend contract:
//   - GET    /geofence/<profile_id>         -> {polygon, min_alt, max_alt, remain} | null
//   - POST   /geofence/<profile_id>         multipart 'kml' or raw KML body
//   - DELETE /geofence/<profile_id>
//   - SocketIO 'geofence_update' { profile, geofence } when any client uploads/clears
//   - chase_config.profiles[<id>].geofence is populated by /get_config and
//     server_settings_update so reloads / late connects render correctly.
//
// Drawing:
//   - "Remain inside" => green polygon (the safe region)
//   - "Remain outside" => red polygon (the keep-out region)
//   Popup shows min/max altitude (Leaflet is 2D — altitude is text only).
//
(function () {
    "use strict";

    var STYLE = {
        inside:  { color: "#16a34a", weight: 2, fillColor: "#16a34a", fillOpacity: 0.10 },
        outside: { color: "#dc2626", weight: 2, fillColor: "#dc2626", fillOpacity: 0.15 }
    };

    var state = {
        map: null,
        layer: null,        // current L.polygon, or null
        currentProfile: "", // profile name the drawn polygon belongs to
        cache: {},          // {profileName: geofenceDict | null} mirrored from server
        visible: true       // user-controlled toggle (independent of cache)
    };

    function $(id) { return document.getElementById(id); }

    function setStatus(text, isWarning) {
        var el = $("geofence-status");
        if (!el) return;
        el.textContent = text || "";
        el.style.color = isWarning ? "#dc2626" : "#6b7280";
    }

    function activeProfile() {
        // chase_config is the global populated by settings.js
        if (typeof chase_config !== "undefined" && chase_config) {
            return chase_config.selected_profile || "";
        }
        return "";
    }

    function clearLayer() {
        if (state.layer && state.map) {
            state.map.removeLayer(state.layer);
        }
        state.layer = null;
    }

    function popupHtml(profile, gf) {
        var altLine =
            "Min Alt: " + gf.min_alt + " m<br>" +
            "Max Alt: " + gf.max_alt + " m";
        return (
            "<b>Geofence — " + profile + "</b><br>" +
            "Remain <b>" + gf.remain + "</b><br>" +
            altLine + "<br>" +
            "<small>" + gf.polygon.length + " vertices</small>"
        );
    }

    function drawForProfile(profile) {
        clearLayer();
        state.currentProfile = profile;
        var gf = state.cache[profile];
        if (!gf || !gf.polygon || gf.polygon.length < 3) {
            setStatus(profile ? "No geofence uploaded for this profile." : "");
            updateButtons(false);
            return;
        }
        updateButtons(true);
        if (!state.visible) {
            // Cached but hidden by user toggle.
            setStatus(
                "Geofence hidden — remain " + gf.remain +
                " (" + gf.polygon.length + " pts, " +
                gf.min_alt + "–" + gf.max_alt + " m)"
            );
            return;
        }
        var style = STYLE[gf.remain] || STYLE.inside;
        state.layer = L.polygon(gf.polygon, style)
            .bindPopup(popupHtml(profile, gf))
            .addTo(state.map);
        setStatus(
            "Geofence: remain " + gf.remain +
            " (" + gf.polygon.length + " pts, " +
            gf.min_alt + "–" + gf.max_alt + " m)"
        );
    }

    function updateButtons(haveFence) {
        var clr = $("geofence-clear");
        if (clr) clr.disabled = !haveFence;
    }

    // Pull geofences out of a server config blob into our local cache.
    function syncCacheFromConfig(cfg) {
        if (!cfg || !cfg.profiles) return;
        Object.keys(cfg.profiles).forEach(function (name) {
            // undefined => never queried; null => server says no geofence.
            // Server now always stamps "geofence" (None / dict), so trust it.
            state.cache[name] = cfg.profiles[name].geofence || null;
        });
    }

    function uploadFile(file) {
        var profile = activeProfile();
        if (!profile) {
            setStatus("No profile selected.", true);
            return;
        }
        if (!file) return;
        var fd = new FormData();
        fd.append("kml", file);
        setStatus("Uploading " + file.name + "…");
        fetch("/geofence/" + encodeURIComponent(profile), {
            method: "POST",
            body: fd
        })
        .then(function (r) {
            return r.json().then(function (j) { return { ok: r.ok, body: j }; });
        })
        .then(function (res) {
            if (!res.ok) {
                setStatus("Upload failed: " + (res.body.error || "unknown"), true);
                return;
            }
            // Server will broadcast geofence_update; we still update locally
            // so the originating client doesn't wait for the round-trip.
            state.cache[profile] = res.body.geofence;
            if (profile === activeProfile()) drawForProfile(profile);
        })
        .catch(function (e) {
            setStatus("Upload error: " + e.message, true);
        });
    }

    function clearActive() {
        var profile = activeProfile();
        if (!profile) return;
        if (!confirm("Clear geofence for profile '" + profile + "'?")) return;
        fetch("/geofence/" + encodeURIComponent(profile), { method: "DELETE" })
            .then(function (r) {
                if (!r.ok) {
                    setStatus("Clear failed (HTTP " + r.status + ")", true);
                    return;
                }
                state.cache[profile] = null;
                if (profile === activeProfile()) drawForProfile(profile);
            })
            .catch(function (e) {
                setStatus("Clear error: " + e.message, true);
            });
    }

    function wireUI() {
        var fileInput = $("geofence-file");
        if (fileInput) {
            fileInput.addEventListener("change", function () {
                if (fileInput.files && fileInput.files[0]) {
                    uploadFile(fileInput.files[0]);
                    fileInput.value = ""; // allow re-uploading same filename
                }
            });
        }
        var clr = $("geofence-clear");
        if (clr) clr.addEventListener("click", clearActive);

        var vis = $("geofence-visible");
        if (vis) {
            // Sync starting state in case the checkbox default and our
            // state default ever drift apart.
            state.visible = vis.checked;
            vis.addEventListener("change", function () {
                state.visible = vis.checked;
                // Redraw current profile honoring the new visibility.
                drawForProfile(activeProfile());
            });
        }
    }

    var Api = {
        init: function (map) {
            state.map = map;
            if (document.readyState === "loading") {
                document.addEventListener("DOMContentLoaded", wireUI);
            } else {
                wireUI();
            }
        },

        // Called from serverSettingsUpdate (settings.js / index.html) so
        // we always reflect the latest server state.
        onConfig: function (cfg) {
            syncCacheFromConfig(cfg);
            var profile = activeProfile();
            if (profile && profile !== state.currentProfile) {
                drawForProfile(profile);
            } else if (profile) {
                // Same profile, but its geofence may have changed (rare via
                // this path; mostly server_settings_update during profile
                // switches). Redraw to be safe.
                drawForProfile(profile);
            }
        },

        // SocketIO 'geofence_update' handler.
        onSocketUpdate: function (msg) {
            if (!msg || !msg.profile) return;
            state.cache[msg.profile] = msg.geofence || null;
            if (msg.profile === activeProfile()) {
                drawForProfile(msg.profile);
            }
        },

        // Called when the user picks a different profile from #profileSelect,
        // before the round-trip completes. Reads from cache.
        onProfileChange: function (profile) {
            drawForProfile(profile);
        },

        _state: function () { return state; }
    };

    window.GeofenceOverlay = Api;
})();
