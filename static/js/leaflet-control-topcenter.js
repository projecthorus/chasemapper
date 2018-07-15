/****************************************************************************
    leaflet-control-topcenter.js,

    (c) 2016, FCOO

    https://github.com/FCOO/leaflet-control-topcenter
    https://github.com/FCOO

****************************************************************************/
(function (L /*, window, document, undefined*/) {
    "use strict";

    //Extend Map._initControlPos to also create a topcenter-container
    L.Map.prototype._initControlPos = function ( _initControlPos ) {
        return function () {
            //Original function/method
            _initControlPos.apply(this, arguments);

            //Adding new control-containers

            //topcenter is the same as the rest of control-containers
            this._controlCorners['topcenter'] = L.DomUtil.create('div', 'leaflet-top leaflet-center', this._controlContainer);

            //bottomcenter need an extra container to be placed at the bottom
            this._controlCorners['bottomcenter'] =
                L.DomUtil.create(
                    'div', 
                    'leaflet-bottom leaflet-center',
                    L.DomUtil.create('div', 'leaflet-control-bottomcenter',    this._controlContainer)
                );
        };
    } (L.Map.prototype._initControlPos);
}(L, this, document));
