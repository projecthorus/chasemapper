import logging
import socket
import threading
import time

import aprslib


class APRSISListener:
    def __init__(
        self,
        server,
        port,
        login_callsign,
        balloon_callsigns,
        car_callsigns,
        active_car_callsign,
        summary_callback,
        car_callback,
    ):
        self.server = server
        self.port = port
        self.login_callsign = login_callsign
        self.balloon_callsigns = set(cs.upper() for cs in balloon_callsigns)
        self.car_callsigns = set(cs.upper() for cs in car_callsigns)
        self.active_car_callsign = active_car_callsign.upper() if active_car_callsign else ""
        self.summary_callback = summary_callback
        self.car_callback = car_callback

        self._sock = None
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def close(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=5)

    def set_active_car_callsign(self, callsign):
        self.active_car_callsign = callsign.upper()
        with self._lock:
            self._send_filter()

    def add_car_callsign(self, callsign):
        self.car_callsigns.add(callsign.upper())
        with self._lock:
            self._send_filter()

    def add_balloon_callsign(self, callsign):
        self.balloon_callsigns.add(callsign.upper())
        with self._lock:
            self._send_filter()

    def _send_filter(self):
        """Send updated budlist filter. Must be called under self._lock.

        Strip SSIDs from the filter so the server matches all SSIDs of each
        base callsign — this avoids case-sensitivity issues with alphabetic
        SSIDs (e.g. -i from aprs.fi iOS). Exact matching still happens in
        _handle_line using the full stored callsign.
        """
        if self._sock is None:
            return
        all_callsigns = self.balloon_callsigns | self.car_callsigns
        if not all_callsigns:
            return
        base_callsigns = sorted(set(cs.split("-")[0] for cs in all_callsigns))
        filter_line = "#filter b/{}\r\n".format("/".join(b + "*" for b in base_callsigns))
        logging.info("APRS-IS: sending filter: %s" % filter_line.strip())
        try:
            self._sock.sendall(filter_line.encode())
        except Exception as e:
            logging.error("APRS-IS: failed to send filter: %s" % e)

    def _run(self):
        while self._running:
            try:
                logging.info("APRS-IS: connecting to %s:%d" % (self.server, self.port))
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(60)
                sock.connect((self.server, self.port))

                with self._lock:
                    self._sock = sock

                # Build initial filter and include it in the login line — this
                # is the most reliable way to set the filter (some servers
                # apply login-line filters more aggressively than #filter).
                # Use wildcard SSIDs (e.g. "KC1RBW*") so all SSIDs of a base
                # callsign match — this also avoids case issues with alphabetic
                # SSIDs like "-i" used by aprs.fi iOS.
                all_callsigns = self.balloon_callsigns | self.car_callsigns
                base_callsigns = sorted(set(cs.split("-")[0] for cs in all_callsigns))
                filter_text = (
                    "b/" + "/".join(b + "*" for b in base_callsigns)
                    if base_callsigns
                    else ""
                )

                login_line = "user {} pass -1 vers chasemapper 1.0 filter {}\r\n".format(
                    self.login_callsign, filter_text
                )
                logging.info("APRS-IS: login: %s" % login_line.strip())
                sock.sendall(login_line.encode())

                logging.info("APRS-IS: connected and filter sent")

                fh = sock.makefile("r", encoding="latin-1")
                while self._running:
                    line = fh.readline()
                    if not line:
                        logging.warning("APRS-IS: connection closed by server")
                        break
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("#"):
                        logging.info("APRS-IS server msg: %s" % line)
                        continue
                    logging.info("APRS-IS RAW: %s" % line)
                    self._handle_line(line)

            except Exception as e:
                if self._running:
                    logging.error("APRS-IS: connection error: %s" % e)
            finally:
                with self._lock:
                    self._sock = None
                try:
                    sock.close()
                except Exception:
                    pass

            if self._running:
                logging.info("APRS-IS: reconnecting in 10s")
                time.sleep(10)

    def _handle_line(self, line):
        try:
            packet = aprslib.parse(line)
        except Exception as e:
            logging.debug("APRS-IS: parse error: %s" % e)
            return

        from_ = packet.get("from", "").upper()
        if not from_:
            return

        lat = packet.get("latitude")
        lon = packet.get("longitude")

        logging.info(
            "APRS-IS packet: from=%s lat=%s lon=%s | balloon_cs=%s active_car=%s"
            % (from_, lat, lon, self.balloon_callsigns, self.active_car_callsign)
        )

        if lat is None or lon is None:
            return

        alt_m = float(packet.get("altitude") or 0.0)

        if from_ in self.balloon_callsigns:
            try:
                self.summary_callback(
                    {
                        "callsign": from_,
                        "latitude": lat,
                        "longitude": lon,
                        "altitude": alt_m,
                    }
                )
            except Exception as e:
                logging.error("APRS-IS: summary_callback error: %s" % e)

        if from_ == self.active_car_callsign.upper():
            try:
                self.car_callback(
                    {
                        "latitude": lat,
                        "longitude": lon,
                        "altitude": alt_m,
                    }
                )
            except Exception as e:
                logging.error("APRS-IS: car_callback error: %s" % e)
