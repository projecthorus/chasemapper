#!/usr/bin/env python
#
#   ChaseMapper - Interactive Bearing Test Utility
#
#   Send absolute, relative, and delete bearing messages from a simple CLI.
#

import argparse
import json
import socket
import sys


SOURCE = "test"


def send_packet(packet, udp_port=55672):
    """Send a packet via UDP broadcast, falling back to localhost."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except Exception:
        pass
    s.bind(("", udp_port))

    data = json.dumps(packet).encode("ascii")
    try:
        s.sendto(data, ("<broadcast>", udp_port))
    except socket.error:
        s.sendto(data, ("127.0.0.1", udp_port))
    finally:
        s.close()


def absolute_bearing_packet(bearing, latitude, longitude):
    return {
        "type": "BEARING",
        "bearing_type": "absolute",
        "bearing": bearing,
        "latitude": latitude,
        "longitude": longitude,
        "source": SOURCE,
    }


def relative_bearing_packet(bearing):
    return {
        "type": "BEARING",
        "bearing_type": "relative",
        "bearing": bearing,
        "heading_override": True,
        "source": SOURCE,
    }


def delete_bearing_packet(quantity):
    return {
        "type": "BEARING",
        "bearing_type": "delete",
        "quantity": quantity,
        "source": SOURCE,
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description="Interactively send test bearing messages to ChaseMapper."
    )
    parser.add_argument("--port", type=int, default=55672, help="UDP port to send to.")
    parser.add_argument(
        "--latitude",
        type=float,
        default=-34.7,
        help="Latitude used for absolute bearing messages.",
    )
    parser.add_argument(
        "--longitude",
        type=float,
        default=138.7,
        help="Longitude used for absolute bearing messages.",
    )
    return parser.parse_args()


def handle_entry(entry, args):
    command = entry[:1].lower()
    value = entry[1:].strip()

    if command == "a":
        bearing = float(value)
        packet = absolute_bearing_packet(bearing, args.latitude, args.longitude)
        send_packet(packet, udp_port=args.port)
        print(f"Sent absolute bearing {bearing} degrees")
    elif command == "r":
        bearing = float(value)
        packet = relative_bearing_packet(bearing)
        send_packet(packet, udp_port=args.port)
        print(f"Sent relative bearing {bearing} degrees")
    elif command == "d":
        quantity = int(value) if value else 1
        packet = delete_bearing_packet(quantity)
        send_packet(packet, udp_port=args.port)
        print(f"Sent delete request for {quantity} bearing(s)")
    else:
        raise ValueError("Entry must start with a, r, or d")


if __name__ == "__main__":
    args = parse_args()

    print("Enter a<degrees>, r<degrees>, or d<quantity>. Ctrl-C to exit.")

    try:
        while True:
            entry = input("> ").strip()
            if not entry:
                continue

            try:
                handle_entry(entry, args)
            except Exception as e:
                print(f"Error handling input: {str(e)}")
    except KeyboardInterrupt:
        sys.exit(0)
