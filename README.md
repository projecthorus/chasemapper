# Project Horus - Browser-Based HAB Chase Map

**Note: This is a work-in-progress. Not all of the features below are functional.**

This folder contains code to display payload (and chase car!) position data in a web browser:

![ChaseMapper Screenshot](https://github.com/projecthorus/chasemapper/raw/master/doc/chasemapper.jpg)

For this to run, you will need the horuslib library installed. Refer to the [Installation guide](https://github.com/projecthorus/horus_utils/wiki/1.-Dependencies-&-Installation).

You also need flask, and flask-socketio, which can be installed using pip:
```
$ sudo pip install flask flask-socketio
```

## Configuration & Startup
Many settings are defined in horusmapper.cfg configuration file.
Create a copy of the example config file using
```
$ cp horusmapper.cfg.example horusmapper.cfg
```
Edit this file with your preferred text editor. The config file contains descriptions of each setting.

You can then start-up the horusmapper server with:
```
$ python horusmapper.py
```

The server can be stopped with CTRL+C.


## Live Predictions
We can also run live predictions of the flight path. 

To do this you need cusf_predictor_wrapper and it's dependencies installed. Refer to the [documentation on how to install this](https://github.com/darksidelemm/cusf_predictor_wrapper/).

Once compiled and installed, you will need to: 
 * Copy the 'pred' binary into this directory. If using the Windows build, this will be `pred.exe`; under Linux/OSX, just `pred`.
 * [Download wind data](https://github.com/darksidelemm/cusf_predictor_wrapper/#3-getting-wind-data) for your area of interest, and place the .dat files into the gfs subdirectory. 

Modify the horusmapper.cfg Predictor section settings as necessary to reflect the gfs and predictor binary locations, and set `[predictor] predictor_enabled = True`