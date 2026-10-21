"""Main loop: watch the sky, decide when the paper is worth refreshing."""
import argparse
import json
import logging
import os
import socket
import threading
import time
from datetime import datetime

from . import airframes, config, logos, render, trackmap, weather, wifi
from .display import make_display
from .flights import FlightSource, haversine_km

log = logging.getLogger("flightframe")
TRACK_PATH = os.path.join(config.STATE_DIR, "track.json")
TRACK_EVERY = 5 * 60          # tracked flight: new position every 5 minutes
LANDED_FOR = 30 * 60          # show "Landed" this long, then back to the sky


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
        self.weather = weather.Weather()
        self.wake = threading.Event()
        self.force = False
        self.status = "starting"
        self.detail = ""
        self.flight = None
        self.flights = []
        self.contacts = []
        self.nearby = 0
        self.track = self._load_track()
        self.last_key = None
        self.last_render = 0.0
        self.last_seen = ""
        self.fail_since = None
        self.setup_mode = False
        self.setup_since = 0.0
        self.last_rejoin = 0.0
        self.wifi_down_since = None
        self.joining = False
        self._shown_message = None
        self._lock = threading.Lock()

    # ---- called from the web page ------------------------------------------
    def poke(self, force=True):
        self.force = self.force or force
        self.wake.set()

    def join_wifi(self, ssid, password):
        threading.Thread(target=self._join_wifi, args=(ssid, password), daemon=True).start()

    def set_screen(self, screen):
        cfg = config.load()
        if screen == "track" and not cfg.get("track"):
            screen = "sky"
        cfg["screen"] = screen
        config.save(cfg)
        self.poke(force=True)

    def toggle_radar(self):
        """Button B: sky <-> radar."""
        cfg = config.load()
        self.set_screen("sky" if cfg.get("screen") == "radar" else "radar")

    def toggle_track(self):
        """Button C: the tracked flight, or back to the sky."""
        cfg = config.load()
        if not cfg.get("track"):
            url = settings_url()
            self._show(render.message(cfg, "No flight to track", [
                "Add a flight number on the settings page:", url,
                "Then press this button again."], url, header="TRACKER"), "msg:notrack")
            return
        self.set_screen("sky" if cfg.get("screen") == "track" else "track")

    def set_track(self, query):
        query = query.strip().upper()[:12]
        cfg = config.load()
        cfg["track"] = query
        cfg["screen"] = "track" if query else "sky"
        config.save(cfg)
        self.track = self._new_track(query)
        self._save_track()
        self.poke(force=True)

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
            "sources": self.source.feed_status() if hasattr(self.source, "feed_status") else [],
            "offline_since": datetime.fromtimestamp(self.fail_since).strftime("%H:%M")
            if self.fail_since else "",
            "screen": config.load().get("screen", "sky"),
            "track": self._track_summary(),
        }

    # ---- tracked flight ----------------------------------------------------
    @staticmethod
    def _new_track(query):
        return {"query": query, "trail": [], "route": {}, "last_seen": 0, "landed_at": 0,
                "last_poll": 0, "state": "waiting", "flight": None}

    def _load_track(self):
        try:
            with open(TRACK_PATH) as f:
                t = json.load(f)
            t.update(last_poll=0, flight=None)
            t["trail"] = [tuple(p) for p in t.get("trail", [])]
            return t
        except (OSError, ValueError):
            return self._new_track("")

    def _save_track(self):
        t = {k: v for k, v in self.track.items() if k not in ("flight", "last_poll")}
        try:
            os.makedirs(config.STATE_DIR, exist_ok=True)
            with open(TRACK_PATH + ".tmp", "w") as f:
                json.dump(t, f)
            os.replace(TRACK_PATH + ".tmp", TRACK_PATH)
        except OSError as e:
            log.info("could not save track: %s", e)

    def _track_summary(self):
        t = self.track
        if not t.get("query"):
            return None
        f = t.get("flight")
        out = {"query": t["query"], "state": t.get("state", "waiting"),
               "last_seen": datetime.fromtimestamp(t["last_seen"]).strftime("%H:%M") if t.get("last_seen") else ""}
        if f:
            out.update(altitude_ft=f.altitude_ft, lat=round(f.lat, 3), lon=round(f.lon, 3))
        r = t.get("route") or {}
        if r.get("origin") and r.get("destination"):
            out["route"] = f"{r['origin'].get('iata_code')} → {r['destination'].get('iata_code')}"
        return out

    # ---- drawing ---------------------------------------------------------
    def _show(self, img, key):
        with self._lock:
            self.display.flip = bool(config.load().get("flip"))
            t0 = time.time()
            self.display.show(img)
            log.info("screen updated (%s) in %.1fs", key, time.time() - t0)
            self.last_key = key
            self.last_render = time.time()

    def _message(self, cfg, key, title, lines, qr=None, header="SETUP"):
        if self._shown_message == key and not self.force:
            return
        self._show(render.message(cfg, title, lines, qr, header=header), "msg:" + key)
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
        self.setup_since = time.time()
        self.last_rejoin = time.time()
        self.status = "setup"
        lines = ([note] if note else []) + [
            f"Join the Wi-Fi network {ssid} (password {pw}).",
            f"Then open http://{wifi.HOTSPOT_IP} and choose your home Wi-Fi.",
        ]
        # _message only redraws when the screen's content actually changes
        self._message(cfg, "setup:" + note, "Connect me to Wi-Fi", lines,
                      qr=f"WIFI:T:WPA;S:{ssid};P:{pw};;")

    def _join_wifi(self, ssid, password):
        self.joining = True
        try:
            self._join_wifi_inner(ssid, password)
        finally:
            self.joining = False

    def _join_wifi_inner(self, ssid, password):
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
            self.wake.wait(self._next_wait(cfg))
            self.wake.clear()

    def _next_wait(self, cfg):
        base = max(10, int(cfg.get("poll_seconds") or 30))
        if not self.fail_since:
            return base
        # While nothing answers, ease off: 30 s for the first 5 min, then 1, then 2 min.
        down = time.time() - self.fail_since
        return base if down < 300 else (60 if down < 1800 else 120)

    # ---- outages ------------------------------------------------------
    OUTAGE_SCREEN_AFTER = 45 * 60      # keep the last picture this long
    HOTSPOT_AFTER = 30 * 60            # Wi-Fi itself down this long: offer setup

    def _outage(self, cfg, why):
        now = time.time()
        self.status, self.detail = "feed_error", why
        if not self.fail_since:
            self.fail_since = now
            log.warning("flight data unavailable: %s", why)
        if wifi.available() and not wifi.connected():
            self.wifi_down_since = self.wifi_down_since or now
            if now - self.wifi_down_since > self.HOTSPOT_AFTER:
                self._enter_setup(cfg, note="Couldn't reach your Wi-Fi.")
            return
        self.wifi_down_since = None
        if now - self.fail_since < self.OUTAGE_SCREEN_AFTER:
            return                          # short blip: leave the current screen alone
        since = datetime.fromtimestamp(self.fail_since).strftime("%H:%M")
        self._message(cfg, "outage", "Waiting for flight data",
                      [f"The flight data services haven't answered since {since}.",
                       "The frame keeps trying and will pick up again by itself.",
                       "Details: http://flightframe.local"], header="STATUS")

    def _maybe_rejoin(self, cfg):
        """In setup mode, every 10 minutes see if the home Wi-Fi is back."""
        if self.joining or time.time() - self.last_rejoin < 600:
            return
        self.last_rejoin = time.time()
        log.info("setup mode: trying saved Wi-Fi networks")
        if wifi.try_saved_networks():
            log.info("rejoined Wi-Fi, leaving setup mode")
            self.setup_mode = False
            self.status, self.detail = "online", ""
            self.fail_since = None
            self.force = True
            self._shown_message = None
        else:
            self._enter_setup(cfg, note="Couldn't reach your Wi-Fi.")

    def _wx(self, cfg):
        """Forecast and sun times for the bottom line. Never raises."""
        lat, lon = float(cfg["lat"]), float(cfg["lon"])
        out = {"sun": (None, None), "slots": None}
        try:
            out["sun"] = weather.sun_times(lat, lon)
        except Exception:
            log.exception("sun times")
        if cfg.get("show_weather", True):
            try:
                out["slots"] = self.weather.forecast(lat, lon)
            except Exception:
                log.exception("weather")
        return out

    def _tick(self):
        cfg = config.load()
        if self.setup_mode:
            self._maybe_rejoin(cfg)
            return
        if not config.has_location(cfg):
            self.status = "needs_location"
            self._message(cfg, "location", "Almost there",
                          ["Set your location from your phone:", settings_url(),
                           "Your phone needs to be on the same Wi-Fi."],
                          qr=settings_url())
            return
        airframes.refresh(self.source.s)     # at most daily; never raises
        if in_quiet_hours(cfg) and not self.force:
            self.status = "quiet_hours"
            return

        screen = cfg.get("screen", "sky")
        if screen == "track" and cfg.get("track"):
            self._tick_track(cfg)
            return
        radar = screen == "radar"
        want = 2 if cfg.get("duo", True) else 1
        try:
            flights, nearby, contacts = self.source.scan(cfg, want=want, radar=radar)
        except ConnectionError as e:
            self._outage(cfg, str(e))
            return
        flight = flights[0] if flights else None

        if self.fail_since:
            log.info("flight data back after %d min", (time.time() - self.fail_since) // 60)
            self.fail_since = None
            self.wifi_down_since = None
            if self._shown_message:          # an outage screen is up: replace it now
                self.force = True
        self.flight, self.flights, self.nearby, self.contacts = flight, flights, nearby, contacts
        self.status = "flight" if flight else "quiet"
        self.detail = ""
        if flight:
            when = datetime.now().strftime("%H:%M")
            route = f" {flight.origin.get('iata')}–{flight.destination.get('iata')}" \
                if flight.has_route else ""
            self.last_seen = f"{flight.flight_number}{route} at {when}"

        night = render.is_night(cfg)
        if radar:
            key = "radar"
        else:
            key = "+".join(f.hex for f in flights) if flights else "quiet"
        key += ":night" if night else ":day"
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
        if radar:
            img = render.radar(contacts, cfg, wx=self._wx(cfg), highlight=flight)
        elif len(flights) >= 2:
            img = render.duo(flights, cfg, nearby, logos=[self._logo(cfg, f) for f in flights[:2]],
                             wx=self._wx(cfg))
        elif flight:
            img = render.poster(flight, cfg, nearby, logo=self._logo(cfg, flight), wx=self._wx(cfg))
        else:
            img = render.quiet(cfg, self.last_seen if self.last_seen else None, wx=self._wx(cfg))
        self._show(img, key)

    def _logo(self, cfg, f):
        if not cfg.get("show_plane", True):
            return None
        return logos.get(logos.airline_icao(f.callsign, f.airline_icao), f.airline_iata,
                         session=self.source.s)

    def _tick_track(self, cfg):
        """Follow one flight on the map, with a new position every 5 minutes."""
        query = cfg["track"]
        t = self.track
        if t.get("query") != query:
            t = self.track = self._new_track(query)
        now = time.time()
        if not self.force and now - t["last_poll"] < TRACK_EVERY and (self.last_key or "").startswith("track:"):
            return
        t["last_poll"] = now
        try:
            f, route = self.source.find(query, float(cfg["lat"]), float(cfg["lon"]))
        except ConnectionError as e:
            self.status, self.detail = "feed_error", str(e)
            if self.last_key and self.last_key.startswith("track:") and not self.force:
                return                      # keep the last map up until a source answers
            f, route = None, {}
        self.force = False
        self._shown_message = None
        if route:
            t["route"] = route
        route = t["route"]
        dest = (route or {}).get("destination") or {}
        if f:
            t["flight"], t["last_seen"] = f, now
            if not t["trail"] or t["trail"][-1] != (f.lat, f.lon):
                t["trail"].append((round(f.lat, 4), round(f.lon, 4)))
                t["trail"] = t["trail"][-400:]
            low = (f.altitude_ft or 0) < 300 and (f.speed_kt or 0) < 80
            t["state"] = "landed" if low else "live"
        elif t["trail"]:
            last = t["trail"][-1]
            near = dest.get("latitude") is not None and \
                haversine_km(last[0], last[1], dest["latitude"], dest["longitude"]) < 40
            descending = t["flight"] is not None and (t["flight"].altitude_ft or 99999) < 5000
            gone = now - t["last_seen"]
            t["state"] = "landed" if (near or (descending and gone > 600)) else "lost"
        else:
            t["state"] = "waiting" if route else "unknown"
        if t["state"] == "landed":
            t["landed_at"] = t["landed_at"] or t["last_seen"] or now
            if now - t["landed_at"] > LANDED_FOR:
                log.info("tracked flight %s has landed; back to the sky", query)
                self.set_track("")
                return
        self._save_track()
        self.status = "tracking"
        seen = t["landed_at"] if t["state"] == "landed" else t["last_seen"]
        img = trackmap.tracker(cfg, query, t["flight"] if t["state"] != "live" else f,
                               route=route, trail=t["trail"], state=t["state"],
                               seen_at=trackmap.time_of(seen), wx=self._wx(cfg))
        self._show(img, f"track:{query}")


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
