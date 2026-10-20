"""A small weather forecast and the day's sunrise and sunset.

Forecast: MET Norway (api.met.no) first, Open-Meteo as a fallback. Both are
free and keyless; MET Norway asks for an identifying User-Agent and gentle use,
so the forecast is cached for 30 minutes and the last good one is kept for up
to 6 hours if both services are down.

Sunrise and sunset are calculated on the Pi (NOAA's method), so they never
depend on the internet.
"""
import logging
import math
import time
from datetime import date, datetime, timedelta, timezone

import requests

log = logging.getLogger(__name__)
UA = {"User-Agent": "flightframe/1.2 github.com/stirtingale/flightframe"}
METNO = "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={lat:.3f}&lon={lon:.3f}"
OPENMETEO = ("https://api.open-meteo.com/v1/forecast?latitude={lat:.3f}&longitude={lon:.3f}"
             "&hourly=temperature_2m,weather_code,is_day&forecast_days=2&timezone=UTC")
CACHE_FOR = 30 * 60
KEEP_FOR = 6 * 3600
STEPS = (0, 3, 6, 9, 12)          # hours ahead


# ------------------------------------------------------------------ icons
def kind_from_metno(symbol):
    s = (symbol or "").lower()
    day = not s.endswith("_night")
    if "thunder" in s:
        k = "thunder"
    elif "snow" in s:
        k = "snow"
    elif "sleet" in s:
        k = "sleet"
    elif "showers" in s:
        k = "showers"
    elif "rain" in s:
        k = "rain"
    elif s.startswith("fog"):
        k = "fog"
    elif s.startswith("cloudy"):
        k = "cloudy"
    elif s.startswith("partlycloudy") or s.startswith("fair"):
        k = "partly"
    elif s.startswith("clearsky"):
        k = "clear"
    else:
        k = "cloudy"
    return k, day


def kind_from_wmo(code, is_day=1):
    c = int(code or 0)
    if c == 0:
        k = "clear"
    elif c in (1, 2):
        k = "partly"
    elif c == 3:
        k = "cloudy"
    elif c in (45, 48):
        k = "fog"
    elif c in (51, 53, 55, 61, 63, 65):
        k = "rain"
    elif c in (56, 57, 66, 67):
        k = "sleet"
    elif c in (71, 73, 75, 77, 85, 86):
        k = "snow"
    elif c in (80, 81, 82):
        k = "showers"
    elif c >= 95:
        k = "thunder"
    else:
        k = "cloudy"
    return k, bool(is_day)


# ------------------------------------------------------------------ forecast
class Weather:
    def __init__(self, session=None):
        self.s = session or requests.Session()
        self.s.headers.update(UA)
        self._cache = None        # (fetched_at, (lat, lon), slots)
        self._last_try = 0.0
        self.source = ""
        self.error = ""

    def forecast(self, lat, lon):
        """Five slots: {'time': datetime (local), 'temp': float, 'kind': str, 'day': bool}, or None."""
        now = time.time()
        key = (round(lat, 2), round(lon, 2))
        if self._cache and self._cache[1] == key and now - self._cache[0] < CACHE_FOR:
            return self._cache[2]
        if now - self._last_try < 120:          # don't retry more than every 2 minutes
            return self._cached(key, now)
        self._last_try = now
        for name, fn in (("met.no", self._metno), ("open-meteo", self._openmeteo)):
            try:
                hours = fn(lat, lon)
                slots = _pick(hours)
                if slots:
                    self._cache = (now, key, slots)
                    self.source, self.error = name, ""
                    return slots
            except Exception as e:
                self.error = f"{name}: {type(e).__name__}"
                log.info("weather from %s failed: %s", name, e)
        return self._cached(key, now)

    def _cached(self, key, now):
        if self._cache and self._cache[1] == key and now - self._cache[0] < KEEP_FOR:
            return _pick_from(self._cache[2])
        return None

    def _metno(self, lat, lon):
        r = self.s.get(METNO.format(lat=lat, lon=lon), timeout=(5, 15))
        r.raise_for_status()
        out = []
        for t in r.json()["properties"]["timeseries"][:30]:
            when = datetime.fromisoformat(t["time"].replace("Z", "+00:00"))
            d = t["data"]
            sym = (d.get("next_1_hours") or d.get("next_6_hours") or {}).get("summary", {}).get("symbol_code")
            k, day = kind_from_metno(sym)
            out.append({"utc": when, "temp": d["instant"]["details"].get("air_temperature"), "kind": k, "day": day})
        return out

    def _openmeteo(self, lat, lon):
        r = self.s.get(OPENMETEO.format(lat=lat, lon=lon), timeout=(5, 15))
        r.raise_for_status()
        h = r.json()["hourly"]
        out = []
        for t, temp, code, isday in zip(h["time"], h["temperature_2m"], h["weather_code"], h["is_day"]):
            when = datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
            k, day = kind_from_wmo(code, isday)
            out.append({"utc": when, "temp": temp, "kind": k, "day": day})
        return out


def _pick(hours):
    """From hourly data, the hours nearest now, +3, +6, +9 and +12."""
    if not hours:
        return None
    now = datetime.now(timezone.utc)
    slots = []
    for step in STEPS:
        target = now + timedelta(hours=step)
        best = min(hours, key=lambda h: abs((h["utc"] - target).total_seconds()))
        if abs((best["utc"] - target).total_seconds()) > 2 * 3600 or best["temp"] is None:
            return None
        slots.append({"time": best["utc"].astimezone(), "temp": best["temp"], "kind": best["kind"],
                      "day": best["day"]})
    return slots


def _pick_from(slots):
    """Cached slots, dropping any that are now in the past."""
    now = datetime.now().astimezone()
    fresh = [s for s in slots if s["time"] >= now - timedelta(minutes=90)]
    return fresh if len(fresh) >= 3 else None


# ------------------------------------------------------------------ sun
def sun_times(lat, lon, day=None):
    """(sunrise, sunset) as local datetimes, or (None, None) in polar day/night."""
    day = day or date.today()
    n = day.timetuple().tm_yday
    out = []
    for rising in (True, False):
        lng_hour = lon / 15.0
        t = n + ((6 if rising else 18) - lng_hour) / 24.0
        m = 0.9856 * t - 3.289
        sun_l = (m + 1.916 * math.sin(math.radians(m)) + 0.020 * math.sin(math.radians(2 * m)) + 282.634) % 360
        ra = math.degrees(math.atan(0.91764 * math.tan(math.radians(sun_l)))) % 360
        ra = (ra + (math.floor(sun_l / 90) * 90 - math.floor(ra / 90) * 90)) / 15.0
        sin_dec = 0.39782 * math.sin(math.radians(sun_l))
        cos_dec = math.cos(math.asin(sin_dec))
        cos_h = (math.cos(math.radians(90.833)) - sin_dec * math.sin(math.radians(lat))) / \
            (cos_dec * math.cos(math.radians(lat)))
        if cos_h > 1 or cos_h < -1:
            return None, None
        h = (360 - math.degrees(math.acos(cos_h))) if rising else math.degrees(math.acos(cos_h))
        h /= 15.0
        local_t = h + ra - 0.06571 * t - 6.622
        ut = (local_t - lng_hour) % 24
        dt = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(hours=ut)
        out.append(dt.astimezone())
    return out[0], out[1]
