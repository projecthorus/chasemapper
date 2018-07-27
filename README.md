# Project Horus - Browser-Based HAB Chase Map

**Note: This is a work-in-progress. Features may be incomplete or non-functional!**

This folder contains code to display payload (and chase car!) position data in a web browser:

![ChaseMapper Screenshot](https://github.com/projecthorus/chasemapper/raw/master/doc/chasemapper.jpg)

For this to run, you will need the horuslib library installed. Refer to the [Installation guide](https://github.com/projecthorus/horus_utils/wiki/1.-Dependencies-&-Installation).

You also need flask, and flask-socketio, which can be installed using pip:
```
$ sudo pip install flask flask-socketio
```

You can then clone this repository with:
```
$ git clone https://github.com/projecthorus/chasemapper.git
```

## Configuration & Startup
Many settings are defined in the horusmapper.cfg configuration file.
Create a copy of the example config file using
```
$ cp horusmapper.cfg.example horusmapper.cfg
```
Edit this file with your preferred text editor. The configuration file is fairly descriptive - you will need to set:
 * At least one telemetry 'profile', which defines where payload and (optionally) car position telemetry data is sourced from.
 * A default latitude and longitude for the map to centre on.

You can then start-up the horusmapper server with:
```
$ python horusmapper.py
```

The server can be stopped with CTRL+C. Somes the server doesn't stop cleanly and may the process may need to be killed. (Sorry!)


## Live Predictions
We can also run live predictions of the flight path. 

To do this you need cusf_predictor_wrapper and it's dependencies installed. Refer to the [documentation on how to install this](https://github.com/darksidelemm/cusf_predictor_wrapper/).

Once compiled and installed, you will need to: 
 * Copy the 'pred' binary into this directory. If using the Windows build, this will be `pred.exe`; under Linux/OSX, just `pred`.
 * Copy the 'get_wind_data.py' script from cusf_predictor_wrapper/apps into this directory.

You will then need to modify the horusmapper.cfg Predictor section setting as necessary to reflect the predictory binary location, the appropriate model_download command, and set `[predictor] predictor_enabled = True`

You can then click 'Download Model' in the web interface's setting tab to trigger a download of the latest GFS model data. Predictions will start automatically once a valid model is available.


## Contacts
* [Mark Jessop](https://github.com/darksidelemm) - vk5qi@rfhead.net

You can often find me in the #highaltitude IRC Channel on [Freenode](https://webchat.freenode.net/).