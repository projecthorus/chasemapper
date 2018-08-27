#!/usr/bin/env python
#
#   Project Horus - Browser-Based Chase Mapper
#   Listeners
#
#   Copyright (C) 2018  Mark Jessop <vk5qi@rfhead.net>
#   Released under GNU GPL v3 or later
#

from math import radians, degrees, sin, cos, atan2, sqrt, pi

def position_info(listener, balloon):
    """
    Calculate and return information from 2 (lat, lon, alt) tuples

    Copyright 2012 (C) Daniel Richman; GNU GPL 3

    Returns a dict with:

     - angle at centre
     - great circle distance
     - distance in a straight line
     - bearing (azimuth or initial course)
     - elevation (altitude)

    Input and output latitudes, longitudes, angles, bearings and elevations are
    in degrees, and input altitudes and output distances are in meters.
    """

    # Earth:
    #radius = 6371000.0
    radius = 6364963.0 # Optimized for Australia :-)

    (lat1, lon1, alt1) = listener
    (lat2, lon2, alt2) = balloon

    lat1 = radians(lat1)
    lat2 = radians(lat2)
    lon1 = radians(lon1)
    lon2 = radians(lon2)

    # Calculate the bearing, the angle at the centre, and the great circle
    # distance using Vincenty's_formulae with f = 0 (a sphere). See
    # http://en.wikipedia.org/wiki/Great_circle_distance#Formulas and
    # http://en.wikipedia.org/wiki/Great-circle_navigation and
    # http://en.wikipedia.org/wiki/Vincenty%27s_formulae
    d_lon = lon2 - lon1
    sa = cos(lat2) * sin(d_lon)
    sb = (cos(lat1) * sin(lat2)) - (sin(lat1) * cos(lat2) * cos(d_lon))
    bearing = atan2(sa, sb)
    aa = sqrt((sa ** 2) + (sb ** 2))
    ab = (sin(lat1) * sin(lat2)) + (cos(lat1) * cos(lat2) * cos(d_lon))
    angle_at_centre = atan2(aa, ab)
    great_circle_distance = angle_at_centre * radius

    # Armed with the angle at the centre, calculating the remaining items
    # is a simple 2D triangley circley problem:

    # Use the triangle with sides (r + alt1), (r + alt2), distance in a
    # straight line. The angle between (r + alt1) and (r + alt2) is the
    # angle at the centre. The angle between distance in a straight line and
    # (r + alt1) is the elevation plus pi/2.

    # Use sum of angle in a triangle to express the third angle in terms
    # of the other two. Use sine rule on sides (r + alt1) and (r + alt2),
    # expand with compound angle formulae and solve for tan elevation by
    # dividing both sides by cos elevation
    ta = radius + alt1
    tb = radius + alt2
    ea = (cos(angle_at_centre) * tb) - ta
    eb = sin(angle_at_centre) * tb
    elevation = atan2(ea, eb)

    # Use cosine rule to find unknown side.
    distance = sqrt((ta ** 2) + (tb ** 2) - 2 * tb * ta * cos(angle_at_centre))

    # Give a bearing in range 0 <= b < 2pi
    if bearing < 0:
        bearing += 2 * pi

    return {
        "listener": listener, "balloon": balloon,
        "listener_radians": (lat1, lon1, alt1),
        "balloon_radians": (lat2, lon2, alt2),
        "angle_at_centre": degrees(angle_at_centre),
        "angle_at_centre_radians": angle_at_centre,
        "bearing": degrees(bearing),
        "bearing_radians": bearing,
        "great_circle_distance": great_circle_distance,
        "straight_distance": distance,
        "elevation": degrees(elevation),
        "elevation_radians": elevation
    }


def bearing_to_cardinal(bearing):
    """ Convert a bearing in degrees to a 16-point cardinal direction """
    bearing = bearing % 360.0

    if bearing < 11.25:
        cardinal = "N"
    elif 11.25 <= bearing < 33.75:
        cardinal = "NNE"
    elif 33.75 <= bearing < 56.25:
        cardinal = "NE"
    elif 56.25 <= bearing < 78.75:
        cardinal = "ENE"
    elif 78.75 <= bearing < 101.25:
        cardinal = "E"
    elif 101.25 <= bearing < 123.75:
        cardinal = "ESE"
    elif 123.75 <= bearing < 146.25:
        cardinal = "SE"
    elif 146.25 <= bearing < 168.75:
        cardinal = "SSE"
    elif 168.75 <= bearing < 191.25:
        cardinal = "S"
    elif 191.25 <= bearing < 213.75:
        cardinal = "SSW"
    elif 213.75 <= bearing < 236.25:
        cardinal = "SW"
    elif 236.25 <= bearing < 258.75:
        cardinal = "WSW"
    elif 258.75 <= bearing < 281.25:
        cardinal = "W"
    elif 281.25 <= bearing < 303.75:
        cardinal = "WNW"
    elif 303.75 <= bearing < 326.25:
        cardinal = "NW"
    elif 326.25 <= bearing < 348.75:
        cardinal = "NNW"
    elif bearing >= 348.75:
        cardinal = "N"
    else:
        cardinal = "?"

    return cardinal