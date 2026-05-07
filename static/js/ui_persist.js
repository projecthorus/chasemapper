//
// Project Horus - Browser-Based Chase Mapper - UI State Persistence
//
// Saves transient UI state (autofollow, airspace overlay toggles, parcel
// toggle + radius) to localStorage so a page refresh during a chase day
// restores the same view. State is stamped with the UTC date and discarded
// on day rollover.
//
(function () {
    "use strict";

    var STORAGE_KEY = "chasemapper.ui_state.v1";

    function todayUTC() {
        var d = new Date();
        return d.getUTCFullYear() + "-" +
            String(d.getUTCMonth() + 1).padStart(2, "0") + "-" +
            String(d.getUTCDate()).padStart(2, "0");
    }

    function load() {
        try {
            var raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return null;
            var parsed = JSON.parse(raw);
            if (!parsed || parsed.day !== todayUTC()) {
                localStorage.removeItem(STORAGE_KEY);
                return null;
            }
            return parsed.state || {};
        } catch (e) {
            return null;
        }
    }

    function save(state) {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify({
                day: todayUTC(),
                state: state || {}
            }));
        } catch (e) { /* quota / disabled — fail silent */ }
    }

    var current = load() || {};

    function setAndSave(key, value) {
        current[key] = value;
        save(current);
    }

    // ---- Public API -----------------------------------------------------

    function restoreCheckbox(id, key, onChangeExtra) {
        var el = document.getElementById(id);
        if (!el) return;
        if (current[key] !== undefined) {
            el.checked = !!current[key];
        }
        el.addEventListener("change", function () {
            setAndSave(key, el.checked);
            if (typeof onChangeExtra === "function") onChangeExtra(el);
        });
    }

    function restoreInputValue(id, key, onChangeExtra) {
        var el = document.getElementById(id);
        if (!el) return;
        if (current[key] !== undefined) {
            el.value = current[key];
        }
        // 'input' fires for sliders mid-drag; 'change' fires for text fields.
        ["input", "change"].forEach(function (evt) {
            el.addEventListener(evt, function () {
                setAndSave(key, el.value);
                if (typeof onChangeExtra === "function") onChangeExtra(el);
            });
        });
    }

    function restoreRadioGroup(name, key) {
        var radios = document.querySelectorAll('input[type="radio"][name="' + name + '"]');
        if (!radios.length) return;
        if (current[key] !== undefined) {
            radios.forEach(function (r) {
                r.checked = (r.value === current[key]);
            });
        }
        radios.forEach(function (r) {
            r.addEventListener("change", function () {
                if (r.checked) setAndSave(key, r.value);
            });
        });
    }

    window.UIPersist = {
        restoreCheckbox: restoreCheckbox,
        restoreInputValue: restoreInputValue,
        restoreRadioGroup: restoreRadioGroup,
        get: function (k) { return current[k]; },
        set: setAndSave
    };
})();
