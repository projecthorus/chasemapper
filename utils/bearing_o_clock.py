#!/usr/bin/env python
#
#   ChaseMapper - Bearing o'Clock
#
#   Add bearings based on O'Clock position (1 through 12)
#   Run with: python bearing_o_clock.py bearing_source_name
#
#   Copyright (C) 2019  Mark Jessop <vk5qi@rfhead.net>
#   Released under GNU GPL v3 or later
#
#   
import json
import socket
import sys
import time
import datetime
import traceback


def send_relative_bearing(bearing, source, heading_override=False, udp_port=55672):
    """
    Send a basic relative bearing
    """
    packet = {
        'type' : 'BEARING',
        'bearing' : bearing,
        'bearing_type': 'relative', 
        'source': source
    }

    if heading_override:
        packet["heading_override"] = True

    # Set up our UDP socket
    s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    s.settimeout(1)
    # Set up socket for broadcast, and allow re-use of the address
    s.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except:
        pass
    s.bind(('',udp_port))
    try:
        s.sendto(json.dumps(packet).encode('ascii'), ('<broadcast>', udp_port))
    except socket.error:
        s.sendto(json.dumps(packet).encode('ascii'), ('127.0.0.1', udp_port))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        _source = sys.argv[1]
    else:
        _source = "o_clock_entry"
    
    try:
        while True:

            print("Enter O-Clock Bearing (1-12):")
            _val = input()

            try:
                _val_int = int(_val)

                _bearing = (_val_int%12)*30

                print(f"Sending Relative Bearing: {_bearing}")

                send_relative_bearing(_bearing, _source, heading_override=True)
            except Exception as e:
                print(f"Error handling input: {str(e)}")
    except KeyboardInterrupt:
        sys.exit(0)
            

