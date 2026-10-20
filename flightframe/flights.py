"""Find the aircraft overhead and work out where it is going.

Positions come from free community ADS-B networks: adsb.fi first (1 request a
second, no daily cap), adsb.lol as a fallback (capped at 500 requests a day per
connection, so it's only used when adsb.fi is down). Airline, route and aircraft
details come from adsbdb. All are for personal, non-commercial use.

Each source is paused when it says so: a 429 waits for its reset time, a 403
waits hours, and timeouts or server errors back off gradually. A struggling
source is never hammered, and the next one is tried straight away.
"""
import logging
import math
import time
from dataclasses import dataclass, field

import requests

log = logging.getLogger(__name__)

UA = {"User-Agent": "flightframe-pi/1.1 (personal flight display)"}
KM_PER_NM = 1.852

ADSBDB = "https://api.adsbdb.com/v0/aircraft/{hex}?callsign={callsign}"


@dataclass
class Feed:
    name: str
    url: str
    daily_budget: int = 0          # 0 = no cap
    paused_until: float = 0.0
    fails: int = 0
    last_ok: float = 0.0
    last_error: str = ""
    used_today: int = 0
    day: str = ""

    def available(self, now):
        if now < self.paused_until:
            return False
        today = time.strftime("%Y-%m-%d", time.localtime(now))
        if today != self.day:
            self.day, self.used_today = today, 0
        return not self.daily_budget or self.used_today < self.daily_budget

    def status(self, now):
        if now < self.paused_until:
            state = "paused"
        elif self.last_ok and not self.fails:
            state = "ok"
        elif self.fails:
            state = "failing"
        else:
            state = "standby"
        return {"name": self.name, "state": state, "error": self.last_error,
                "resumes": time.strftime("%H:%M", time.localtime(self.paused_until))
                if now < self.paused_until else "",
                "last_ok": time.strftime("%H:%M", time.localtime(self.last_ok)) if self.last_ok else "",
                "used_today": self.used_today}


def default_feeds():
    return [
        Feed("adsb.fi", "https://opendata.adsb.fi/api/v3/lat/{lat:.4f}/lon/{lon:.4f}/dist/{nm}"),
        # 500 a day per connection; keep some headroom
        Feed("adsb.lol", "https://api.adsb.lol/v2/lat/{lat:.4f}/lon/{lon:.4f}/dist/{nm}",
             daily_budget=450),
    ]


def _pause_seconds(resp, default):
    """How long a 429 asks us to wait, from Retry-After or x-ratelimit-reset."""
    for h in ("Retry-After", "x-ratelimit-reset", "X-RateLimit-Reset"):
        v = resp.headers.get(h)
        if not v:
            continue
        try:
            n = float(v)
        except ValueError:
            continue
        if n > 1e9:                     # an absolute epoch time
            n -= time.time()
        if n > 0:
            return min(n, 24 * 3600)
    return default


@dataclass
class Flight:
    hex: str
    callsign: str
    lat: float
    lon: float
    altitude_ft: float | None
    speed_kt: float | None
    track: float | None
    vertical_fpm: float | None
    distance_km: float
    bearing: float
    registration: str = ""
    type_code: str = ""
    type_name: str = ""
    operator: str = ""
    airline: str = ""
    airline_iata: str = ""
    airline_icao: str = ""
    category: str = ""
    flight_iata: str = ""
    origin: dict = field(default_factory=dict)       # iata, icao, city, name, country
    destination: dict = field(default_factory=dict)

    @property
    def flight_number(self):
        # Only trust the short form (BA283) when it carries the airline's code;
        # the route database sometimes drops it ("84U").
        fi = self.flight_iata
        if fi and self.airline_iata and fi.upper().startswith(self.airline_iata.upper()):
            return fi
        return self.callsign

    @property
    def has_route(self):
        return bool(self.origin and self.destination)


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def compass(deg):
    if deg is None:
        return ""
    pts = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return pts[int((deg + 22.5) // 45) % 8]


class FlightSource:
    def __init__(self, session=None):
        self.s = session or requests.Session()
        self.s.headers.update(UA)
        self._route_cache = {}   # (hex, callsign) -> (expires, details)
        self.last_error = ""
        self.feeds = default_feeds()

    # ---- positions -------------------------------------------------------
    def aircraft_near(self, lat, lon, radius_km):
        nm = max(1, min(250, math.ceil(radius_km / KM_PER_NM)))
        now = time.time()
        tried = []
        for feed in self.feeds:
            if not feed.available(now):
                continue
            tried.append(feed.name)
            feed.used_today += 1
            try:
                r = self.s.get(feed.url.format(lat=lat, lon=lon, nm=nm), timeout=(5, 12))
            except requests.RequestException as e:
                self._failed(feed, f"{type(e).__name__}", now)
                continue
            if r.status_code == 429:
                wait = _pause_seconds(r, 15 * 60)
                feed.paused_until = now + wait
                feed.last_error = f"rate limited, waiting {int(wait // 60)} min"
                log.warning("%s: %s", feed.name, feed.last_error)
                continue
            if r.status_code in (401, 403):
                feed.paused_until = now + 6 * 3600
                feed.last_error = f"refused ({r.status_code}), retrying in 6 hours"
                log.warning("%s: %s", feed.name, feed.last_error)
                continue
            if r.status_code != 200:
                self._failed(feed, f"HTTP {r.status_code}", now)
                continue
            try:
                data = r.json()
            except ValueError:
                self._failed(feed, "bad response", now)
                continue
            feed.fails, feed.last_ok, feed.last_error = 0, now, ""
            self.last_error = ""
            return data.get("ac") or data.get("aircraft") or []
        if not tried:
            nxt = min((f.paused_until for f in self.feeds if f.paused_until > now), default=0)
            when = time.strftime("%H:%M", time.localtime(nxt)) if nxt else "tomorrow"
            self.last_error = f"all sources paused until {when}"
        else:
            self.last_error = "; ".join(f"{f.name}: {f.last_error}" for f in self.feeds if f.last_error)
        raise ConnectionError(self.last_error or "no flight source reachable")

    def _failed(self, feed, why, now):
        """Timeouts and server errors: back off 30 s, 1, 2, 4, then every 5 min."""
        feed.fails += 1
        wait = min(300, 30 * 2 ** (feed.fails - 1))
        feed.paused_until = now + wait
        feed.last_error = f"{why}, retrying in {int(wait)} s" if wait < 120 else \
            f"{why}, retrying in {int(wait // 60)} min"
        log.warning("%s: %s", feed.name, feed.last_error)

    def feed_status(self):
        now = time.time()
        return [f.status(now) for f in self.feeds]

    # ---- route + aircraft details -----------------------------------------
    def details(self, hex_, callsign):
        key = (hex_, callsign)
        hit = self._route_cache.get(key)
        if hit and hit[0] > time.time():
            return hit[1]
        out = {}
        try:
            r = self.s.get(ADSBDB.format(hex=hex_, callsign=callsign), timeout=10)
            if r.status_code == 200:
                out = r.json().get("response") or {}
                if not isinstance(out, dict):
                    out = {}
        except (requests.RequestException, ValueError) as e:
            log.info("adsbdb lookup failed for %s: %s", callsign, e)
            # short cache so we retry soon
            self._route_cache[key] = (time.time() + 120, {})
            return {}
        self._route_cache[key] = (time.time() + 6 * 3600, out)
        if len(self._route_cache) > 500:
            now = time.time()
            self._route_cache = {k: v for k, v in self._route_cache.items() if v[0] > now}
        return out

    # ---- the one that matters -------------------------------------------
    def overhead(self, cfg):
        lat, lon = float(cfg["lat"]), float(cfg["lon"])
        radius = float(cfg.get("radius_km") or 15)
        max_alt = float(cfg.get("max_altitude_ft") or 0)
        candidates = []
        for ac in self.aircraft_near(lat, lon, radius):
            f = _parse(ac, lat, lon)
            if not f or f.distance_km > radius:
                continue
            if max_alt and f.altitude_ft and f.altitude_ft > max_alt:
                continue
            candidates.append(f)
        if not candidates:
            return None, 0
        # Nearest by slant distance, so a jet at 38,000 ft directly above
        # doesn't lose out to a light aircraft 5 km away at 1,500 ft.
        def slant(f):
            h = (f.altitude_ft or 0) * 0.0003048
            return math.hypot(f.distance_km, h * 0.5)
        candidates.sort(key=slant)
        # Prefer flights we can name a route for, if one is nearly as close.
        best = candidates[0]
        for f in candidates[:4]:
            enrich(f, self.details(f.hex, f.callsign))
            if f.has_route and slant(f) <= slant(best) * 1.6 + 1:
                return f, len(candidates)
        return best, len(candidates)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse(ac, home_lat, home_lon):
    lat, lon = ac.get("lat"), ac.get("lon")
    callsign = (ac.get("flight") or "").strip()
    if lat is None or lon is None or not callsign:
        return None
    if ac.get("alt_baro") == "ground":
        return None
    alt = _num(ac.get("alt_baro")) or _num(ac.get("alt_geom"))
    return Flight(
        hex=ac.get("hex", "").lstrip("~"),
        callsign=callsign,
        lat=lat, lon=lon,
        altitude_ft=alt,
        speed_kt=_num(ac.get("gs")),
        track=_num(ac.get("track")),
        vertical_fpm=_num(ac.get("baro_rate")) or _num(ac.get("geom_rate")),
        distance_km=haversine_km(home_lat, home_lon, lat, lon),
        bearing=bearing_deg(home_lat, home_lon, lat, lon),
        registration=ac.get("r", "") or "",
        type_code=ac.get("t", "") or "",
        type_name=(ac.get("desc") or "").title(),
        operator=ac.get("ownOp", "") or "",
        category=ac.get("category", "") or "",
    )


def _airport(a):
    if not a:
        return {}
    return {
        "iata": a.get("iata_code") or a.get("icao_code") or "",
        "icao": a.get("icao_code") or "",
        "city": a.get("municipality") or a.get("name") or "",
        "name": a.get("name") or "",
        "country": a.get("country_name") or "",
    }


def enrich(f, d):
    if not d:
        return f
    ac = d.get("aircraft") or {}
    if ac:
        f.registration = f.registration or ac.get("registration", "")
        f.type_code = f.type_code or ac.get("icao_type", "")
        name = " ".join(x for x in [ac.get("manufacturer", ""), ac.get("type", "")] if x)
        if name:
            f.type_name = _tidy_type(name)
        f.operator = ac.get("registered_owner") or f.operator
    fr = d.get("flightroute") or {}
    if fr:
        al = fr.get("airline") or {}
        f.airline = al.get("name", "")
        f.airline_iata = al.get("iata") or ""
        f.airline_icao = al.get("icao") or ""
        f.flight_iata = fr.get("callsign_iata") or ""
        f.origin = _airport(fr.get("origin"))
        f.destination = _airport(fr.get("destination"))
    return f


def _tidy_type(name):
    # "Airbus SAS Airbus A320-251N" -> "Airbus A320-251N"
    words = name.split()
    out = []
    for w in words:
        if out and w.lower() == out[0].lower():
            continue
        if w.upper() in {"SAS", "S.A.S.", "CO", "INC", "LTD", "GMBH"}:
            continue
        out.append(w)
    return " ".join(out)
