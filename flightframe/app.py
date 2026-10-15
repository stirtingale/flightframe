"""Main loop: watch the sky, decide when the paper is worth refreshing."""
import argparse
import logging
import socket
import threading
import time
from datetime import datetime

from . import config, logos, render, wifi
from .display import make_display
from .flights import FlightSource

log = logging.getLogger("flightframe")


def in_quiet_hours(cfg, now=None):
    start, end = cfg.get("quiet_start"), cfg.get("quiet_end")
    if not start or not end:
        return False
    now = (now or datetime.now()).strftime("%H:%M")
    if start <= end:
        return start <= now < end
    return now >= start or now < end      # overnight, e.g. 23:00 to 07:00


def settings_url():
    return f"http://{socket.gethostname()}.local"


class Worker:
    def __init__(self, display, source=None):
        self.display = display
        self.source = source or FlightSource()
        self.wake = threading.Event()
        self.force = False
        self.status = "starting"
        self.detail = ""
        self.flight = None
        self.nearby = 0
        self.last_key = None
        self.last_render = 0.0
        self.last_seen = ""
        self.fail_since = None
        self.setup_mode = False
        self._shown_message = None
        self._lock = threading.Lock()

    # ---- called from the web page ------------------------------------------
    def poke(self, force=True):
        self.force = self.force or force
        self.wake.set()

    def join_wifi(self, ssid, password):
        threading.Thread(target=self._join_wifi, args=(ssid, password), daemon=True).start()

    def show_settings_screen(self):
        cfg = config.load()
        url = settings_url()
        self._show(render.message(cfg, "Settings", [
            "Open this on your phone (same Wi-Fi):", url,
            "Press the top button to go back to the sky."], url), "msg:settings")
        self._shown_message = None

    def snapshot(self):
        f = self.flight
        return {
            "status": self.status,
            "detail": self.detail,
            "setup_mode": self.setup_mode,
            "nearby": self.nearby,
            "flight": None if not f else {
                "flight": f.flight_number, "airline": f.airline,
                "from": f.origin.get("city", ""), "to": f.destination.get("city", ""),
                "type": f.type_name or f.type_code, "distance_km": round(f.distance_km, 1),
            },
            "last_render": datetime.fromtimestamp(self.last_render).strftime("%H:%M:%S")
            if self.last_render else "",
            "display": self.display.name,
        }

    # ---- drawing ---------------------------------------------------------
    def _show(self, img, key):
        with self._lock:
            self.display.flip = bool(config.load().get("flip"))
            t0 = time.time()
            self.display.show(img)
            log.info("screen updated (%s) in %.1fs", key, time.time() - t0)
            self.last_key = key
            self.last_render = time.time()

    def _message(self, cfg, key, title, lines, qr=None):
        if self._shown_message == key and not self.force:
            return
        self._show(render.message(cfg, title, lines, qr), "msg:" + key)
        self._shown_message = key
        self.force = False

    # ---- Wi-Fi setup -----------------------------------------------------
    def _enter_setup(self, cfg, note=""):
        ssid, pw = cfg["hotspot_ssid"], cfg["hotspot_password"]
        try:
            wifi.start_hotspot(ssid, pw)
        except Exception as e:
            log.error("could not start hotspot: %s", e)
            self.status, self.detail = "offline", str(e)
            return
        self.setup_mode = True
        self.status = "setup"
        lines = ([note] if note else []) + [
            f"Join the Wi-Fi network {ssid} (password {pw}).",
            f"Then open http://{wifi.HOTSPOT_IP} and choose your home Wi-Fi.",
        ]
        self.force = True
        self._message(cfg, "setup:" + note, "Connect me to Wi-Fi", lines,
                      qr=f"WIFI:T:WPA;S:{ssid};P:{pw};;")

    def _join_wifi(self, ssid, password):
        time.sleep(2)   # let the web page answer before the hotspot drops
        cfg = config.load()
        self.status, self.detail = "joining", ssid
        ok, err = wifi.connect(ssid, password)
        if ok and wifi.wait_for_network(30):
            self.setup_mode = False
            self.status, self.detail = "online", ""
            self.force = True
            if not config.has_location(cfg):
                self._shown_message = None
            self.wake.set()
        else:
            self._enter_setup(cfg, note=f"Couldn't join {ssid}. Check the password and try again.")

    # ---- the loop --------------------------------------------------------
    def run(self):
        cfg = config.load()
        if wifi.available() and not wifi.wait_for_network(45):
            self._enter_setup(cfg)
        while True:
            try:
                self._tick()
            except Exception:
                log.exception("tick failed")
            cfg = config.load()
            self.wake.wait(max(10, int(cfg.get("poll_seconds") or 30)))
            self.wake.clear()

    def _tick(self):
        cfg = config.load()
        if self.setup_mode:
            return
        if not config.has_location(cfg):
            self.status = "needs_location"
            self._message(cfg, "location", "Almost there",
                          ["Set your location from your phone:", settings_url(),
                           "Your phone needs to be on the same Wi-Fi."],
                          qr=settings_url())
            return
        if in_quiet_hours(cfg) and not self.force:
            self.status = "quiet_hours"
            return

        try:
            flight, nearby = self.source.overhead(cfg)
            self.fail_since = None
        except ConnectionError as e:
            self.status, self.detail = "feed_error", str(e)
            self.fail_since = self.fail_since or time.time()
            if time.time() - self.fail_since > 600:
                if wifi.available() and not wifi.online():
                    self._enter_setup(cfg, note="Lost the internet connection.")
                else:
                    self._message(cfg, "feed", "No flight data",
                                  ["The flight data service isn't answering.",
                                   "Retrying every minute."])
            return

        self.flight, self.nearby = flight, nearby
        self.status = "flight" if flight else "quiet"
        self.detail = ""
        if flight:
            when = datetime.now().strftime("%H:%M")
            route = f" {flight.origin.get('iata')}–{flight.destination.get('iata')}" \
                if flight.has_route else ""
            self.last_seen = f"{flight.flight_number}{route} at {when}"

        key = flight.hex if flight else "quiet"
        since = time.time() - self.last_render
        min_gap = max(60, int(cfg.get("min_refresh_seconds") or 180))
        restats = int(cfg.get("stats_refresh_minutes") or 10) * 60
        changed = key != self.last_key
        due = (self.force
               or (changed and since >= min_gap)
               or (key != "quiet" and since >= restats)
               or (key == "quiet" and since >= restats * 3))
        if not due:
            return
        self.force = False
        self._shown_message = None
        if flight:
            logo = None
            if cfg.get("show_plane", True):
                logo = logos.get(logos.airline_icao(flight.callsign, flight.airline_icao),
                                 flight.airline_iata, session=self.source.s)
            img = render.poster(flight, cfg, nearby, logo=logo)
        else:
            img = render.quiet(cfg, self.last_seen if self.last_seen else None)
        self._show(img, key)


def main():
    ap = argparse.ArgumentParser(description="Flight frame for Raspberry Pi")
    ap.add_argument("--port", type=int, default=80)
    ap.add_argument("--display", choices=["auto", "inky", "waveshare", "eink", "preview"])
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = config.load()
    display = make_display(args.display or cfg.get("display", "auto"), bool(cfg.get("flip")))
    worker = Worker(display)
    threading.Thread(target=worker.run, daemon=True, name="sky").start()
    if display.name == "inky":
        from . import buttons
        buttons.start(worker)

    from .web import create_app
    app = create_app(worker)
    try:
        from waitress import serve
        serve(app, host="0.0.0.0", port=args.port, threads=4)
    except ImportError:
        app.run(host="0.0.0.0", port=args.port, threaded=True)


if __name__ == "__main__":
    main()
