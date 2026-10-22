"""The flight tracker screen: a clean outline map with the route, where the
aircraft is now, the path it has flown, and its figures beside the map.

Coastlines and borders are Natural Earth (public domain), built into
data/coast.json by tools/build_coast.py, so the map works offline.
"""
import json
import math
import os
from datetime import datetime

from PIL import Image, ImageDraw

from . import render as R
from .flights import haversine_km

COAST_PATH = os.path.join(os.path.dirname(__file__), "data", "coast.json")
_coast = None


def _load():
    global _coast
    if _coast is None:
        try:
            with open(COAST_PATH) as f:
                raw = json.load(f)
        except (OSError, ValueError):
            raw = {"coast": [], "borders": []}
        out = {}
        for key in ("coast", "borders"):
            rings = []
            for flat in raw.get(key, []):
                pts = [(flat[i] / 100, flat[i + 1] / 100) for i in range(0, len(flat), 2)]
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                rings.append((min(xs), max(xs), min(ys), max(ys), pts))
            out[key] = rings
        _coast = out
    return _coast


# ------------------------------------------------------------------ geometry
def great_circle(a, b, n=64):
    """Points along the shortest path from a to b, as (lat, lon)."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    v1 = (math.cos(la1) * math.cos(lo1), math.cos(la1) * math.sin(lo1), math.sin(la1))
    v2 = (math.cos(la2) * math.cos(lo2), math.cos(la2) * math.sin(lo2), math.sin(la2))
    dot = max(-1.0, min(1.0, sum(x * y for x, y in zip(v1, v2))))
    om = math.acos(dot)
    if om < 1e-6:
        return [a, b]
    out = []
    for i in range(n + 1):
        t = i / n
        k1, k2 = math.sin((1 - t) * om) / math.sin(om), math.sin(t * om) / math.sin(om)
        x, y, z = (k1 * p + k2 * q for p, q in zip(v1, v2))
        out.append((math.degrees(math.atan2(z, math.hypot(x, y))), math.degrees(math.atan2(y, x))))
    return out


def _merc(lat):
    lat = max(-80.0, min(80.0, lat))
    return math.degrees(math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))


class View:
    """Mercator view fitted to some points, unwrapped around a reference longitude."""

    def __init__(self, pts, w, h, pad=0.12, min_span=4.0):
        self.ref = pts[0][1]
        xs = [self.unwrap(lon) for _, lon in pts]
        ys = [_merc(lat) for lat, _ in pts]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        sx, sy = max(x1 - x0, min_span), max(y1 - y0, min_span * 0.6)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        sx *= 1 + 2 * pad
        sy *= 1 + 2 * pad
        if sx / sy < w / h:                      # match the box's shape
            sx = sy * w / h
        else:
            sy = sx * h / w
        self.x0, self.y1 = cx - sx / 2, cy + sy / 2
        self.k = w / sx
        self.w, self.h = w, h
        self.lon_lo, self.lon_hi = self.x0, self.x0 + sx

    def unwrap(self, lon):
        return self.ref + ((lon - self.ref + 180) % 360) - 180

    def xy(self, lat, lon, raw=False):
        x = lon if raw else self.unwrap(lon)
        return (x - self.x0) * self.k, (self.y1 - _merc(lat)) * self.k


def _dashed(d, pts, fill, width=2, on=7, off=6):
    carry, drawing = 0.0, True
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        seg = math.hypot(x1 - x0, y1 - y0)
        pos = 0.0
        while pos < seg:
            step = min((on if drawing else off) - carry, seg - pos)
            t0, t1 = pos / seg, (pos + step) / seg
            if drawing:
                d.line([x0 + (x1 - x0) * t0, y0 + (y1 - y0) * t0,
                        x0 + (x1 - x0) * t1, y0 + (y1 - y0) * t1], fill=fill, width=width)
            pos += step
            carry += step
            if carry >= (on if drawing else off) - 1e-9:
                carry, drawing = 0.0, not drawing


def _plane_icon(d, x, y, track, size, fill=R.BLACK, edge=R.WHITE):
    """A top-down airliner pointing along track."""
    shape = [(0, -1), (0.09, -0.8), (0.1, -0.25), (0.95, 0.12), (0.95, 0.25), (0.1, 0.08),
             (0.08, 0.6), (0.38, 0.82), (0.38, 0.93), (0, 0.85)]
    shape = shape + [(-px, py) for px, py in reversed(shape[1:-1])]
    a = math.radians(track or 0)
    ca, sa = math.cos(a), math.sin(a)
    pts = [(x + (px * ca - py * sa) * size / 2, y + (px * sa + py * ca) * size / 2) for px, py in shape]
    d.polygon(pts, fill=fill, outline=edge)


def draw_map(w, h, origin, dest, now, trail, accent, track=None, home=None):
    """origin/dest: airport dicts with lat/lon (or {}), now: (lat, lon) or None,
    trail: [(lat, lon), ...] already flown. Returns an RGB image."""
    img = Image.new("RGB", (w, h), R.WHITE)
    d = ImageDraw.Draw(img)
    d.fontmode = "1"                 # crisp labels on E Ink
    o = (origin["lat"], origin["lon"]) if origin.get("lat") is not None else None
    t = (dest["lat"], dest["lon"]) if dest.get("lat") is not None else None
    route = great_circle(o, t) if o and t else []
    interest = route + list(trail) + ([now] if now else [])
    if not interest:
        interest = [o or t or home or (51.5, 0.0)]
    view = View(interest, w, h, min_span=4.0 if (route or trail or now) else 16.0)

    # coastline only: no borders, no specks (rings smaller than 6 px across)
    data = _load()
    for lo, hi, la_lo, la_hi, pts in data["coast"]:
        if la_hi < -80 or la_lo > 82:
            continue
        for shift in (-360, 0, 360):
            if hi + shift < view.lon_lo or lo + shift > view.lon_hi:
                continue
            xy = [view.xy(lat, lon + shift, raw=True) for lon, lat in pts]
            xs = [p[0] for p in xy]
            ys = [p[1] for p in xy]
            if max(ys) < 0 or min(ys) > h or max(xs) < 0 or min(xs) > w:
                continue
            if max(xs) - min(xs) < 6 and max(ys) - min(ys) < 6:
                continue
            d.line(xy, fill=R.BLACK, width=2)

    # route still to fly, dashed 3 px; flown path 6 px in the accent on a 12 px paper channel
    if route:
        _dashed(d, [view.xy(*p) for p in route], R.BLACK, width=3, on=8, off=7)
    flown = ([o] if o else []) + list(trail) + ([now] if now else [])
    if len(flown) >= 2:
        line = [view.xy(*p) for p in flown]
        d.line(line, fill=R.WHITE, width=12, joint="curve")
        d.line(line, fill=accent, width=6, joint="curve")

    # aircraft first, then airport labels (halo), then markers on top
    if now:
        x, y = view.xy(*now)
        d.ellipse([x - 22, y - 22, x + 22, y + 22], fill=R.WHITE)
        _plane_icon(d, x, y, track, 40)
    elif home and not route:
        x, y = view.xy(*home)
        d.polygon([(x, y - 9), (x - 8, y - 1), (x + 8, y - 1)], fill=R.BLACK)
        d.rectangle([x - 6, y - 1, x + 6, y + 7], fill=R.BLACK)
    f_code = R.font("semi", 16)
    marks = []
    for ap, filled in ((origin, True), (dest, False)):
        if ap.get("lat") is None:
            continue
        x, y = view.xy(ap["lat"], ap["lon"])
        other = dest if ap is origin else origin
        ox = view.xy(other["lat"], other["lon"])[0] if other.get("lat") is not None else x - 1
        code = ap.get("iata") or ap.get("icao") or ""
        tw = R.text_w(d, code, f_code)
        left = ox > x                      # label on the side away from the route
        if left and x - 12 - tw < 4:       # no room: flip, never sit on the marker
            left = False
        elif not left and x + 12 + tw > w - 4:
            left = True
        tx = x - 12 if left else x + 12
        ty = max(12, min(h - 12, y))
        d.text((tx, ty), code, font=f_code, fill=R.BLACK, anchor="rm" if left else "lm",
               stroke_width=4, stroke_fill=R.WHITE)
        marks.append((x, y, filled))
    for x, y, filled in marks:
        d.ellipse([x - 9, y - 9, x + 9, y + 9], fill=R.WHITE)
        d.ellipse([x - 6, y - 6, x + 6, y + 6], fill=R.BLACK if filled else R.WHITE,
                  outline=R.BLACK, width=3)
    return img


# ------------------------------------------------------------------ screen
def _fmt_left(minutes):
    h, m = divmod(int(round(minutes)), 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


def tracker(cfg, query, f=None, route=None, trail=(), state="live", seen_at=None, wx=None):
    """state: live | waiting | landed | lost | unknown."""
    from .flights import _airport
    c = R.Canvas(cfg.get("orientation", "landscape"))
    night = R.is_night(cfg, wx)
    c.setup(cfg, night)
    accent, units = c.accent, c.units
    route = route or {}
    origin = (f.origin if f and f.origin else None) or _airport(route.get("origin"))
    dest = (f.destination if f and f.destination else None) or _airport(route.get("destination"))
    R._header(c, "TRACKING", f"Updated {R._now()}")
    top = R.CONTENT_TOP
    if c.portrait:
        mx, my, mw, mh = c.m, top, c.inner, 288
        px, pw = c.m, c.inner
        b0 = my + mh + 24 + R.cap(R.TITLE)
    else:
        mx, my, mw, mh = c.m, top, c.half, c.bottom - top
        px, pw = c.mid, c.w - c.m - c.mid
        b0 = R.L_NUM

    now = (f.lat, f.lon) if f else None
    trail = list(trail)
    if not now and state in ("lost", "landed") and trail:
        now = trail[-1]
    m = draw_map(mw - 4, mh - 4, origin or {}, dest or {}, now,
                 trail[:-1] if now and trail and now == trail[-1] else trail,
                 accent, track=f.track if f else None,
                 home=(float(cfg["lat"]), float(cfg["lon"])) if cfg.get("lat") is not None else None)
    c.img.paste(m, (mx + 2, my + 2))
    c.d.rectangle([mx, my, mx + mw - 1, my + mh - 1], outline=R.BLACK, width=2)   # the map's window

    # --- panel: same order and sizes as the poster
    number = (R.ident(f) if f else "") or query.upper()
    ff, _ = R.fit_scale(c, number, R.TITLE, pw, 26)
    c.text((px - 1, b0), number, ff, fill=accent, anchor="ls")
    y = b0 + 36
    if f:
        y = R._identity(c, px, y, f, pw, R.SUB, max_lines=1)
    else:
        name = (route.get("airline") or {}).get("name", "")
        if name:
            fw, _ = R.fit_scale(c, name, R.SUB, pw)
            c.text((px, y), name, fw, anchor="ls")
        else:
            y -= 36
    if origin and dest:
        y += 18 + R.cap(R.DISPLAY)
        R.route_line(c, px - 2, y, origin.get("iata"), dest.get("iata"), R.DISPLAY, pw)
        y += 28
        cities = f"{origin.get('city')} to {dest.get('city')}"
        fs = R.F(R.BODY)
        if R.text_w(c.d, cities, fs) > pw:
            cities = f"{origin.get('city')} to"
            c.text((px, y), cities, fs, anchor="ls")
            y += 22
            cities = dest.get("city") or ""
        c.text((px, y), cities, fs, anchor="ls")
    # progress
    total = flown = left = None
    if origin and dest and origin.get("lat") is not None and dest.get("lat") is not None:
        total = haversine_km(origin["lat"], origin["lon"], dest["lat"], dest["lon"])
        if now:
            left = haversine_km(now[0], now[1], dest["lat"], dest["lon"])
            flown = max(0.0, total - left)
        elif state == "landed":
            flown, left = total, 0.0
        elif state == "waiting":
            flown, left = 0.0, total
    if total and flown is not None:
        frac = max(0.0, min(1.0, flown / total)) if total else 0
        bt = y + 16
        c.d.rectangle([px, bt, px + pw - 1, bt + 9], outline=R.BLACK, width=2)
        if frac > 0:
            c.d.rectangle([px, bt, px + max(4, (pw - 1) * frac), bt + 9], fill=accent)
        c.text((px, bt + 34), f"{R.fmt_dist(flown, units)} flown", R.F(R.BODY), anchor="ls")
        c.text((px + pw, bt + 34), f"{R.fmt_dist(left, units)} to go", R.F(R.BODY), anchor="rs")
        y = bt + 34

    # figures, or what's going on
    if state == "live" and f:
        mins = (left / (f.speed_kt * 1.852) * 60) if left is not None and f.speed_kt else None
        col = (pw - R.GUTTER) // 2
        cells = [("Altitude", R.fmt_alt(f.altitude_ft, units), R.phase(f)),
                 ("Speed", R.fmt_speed(f.speed_kt, units)),
                 ("Time left", _fmt_left(mins) if mins is not None else "–"),
                 ("Aircraft", R.aircraft_value(c, f, col))]
        R._stats(c, y + 36, cells, [px, px + col + R.GUTTER], col)
    else:
        title, lines = {
            "waiting": ("Not flying yet", ["It hasn't taken off, or isn't sending its position.",
                                           "The frame checks every 5 minutes."]),
            "landed": ("Landed", [f"Arrived {seen_at.strftime('%H:%M')}." if seen_at else "",
                                  "Back to the sky above in 30 minutes."]),
            "lost": ("Out of range", [f"Last heard {seen_at.strftime('%H:%M')}." if seen_at else "",
                                      "Over the ocean there are few receivers; it should reappear."]),
            "unknown": ("Can't find it", ["Check the flight number on the settings page.",
                                          "It will appear once it's in the air."]),
        }.get(state, ("", []))
        y += 18 + R.cap(R.DISPLAY) if not (origin and dest) else 48
        ft, _ = R.fit_scale(c, title, R.DISPLAY, pw, 26)
        c.text((px - 2, y), title, ft, anchor="ls")
        y += 32
        fs = R.F(R.BODY)
        for line in lines:
            for chunk in R._wrap(c.d, line, fs, pw):
                if chunk:
                    c.text((px, y), chunk, fs, anchor="ls")
                    y += 22
    R._footer_wx(c, wx)
    return R.finish(c, cfg, wx, night, decorate=False)


def time_of(ts):
    return datetime.fromtimestamp(ts) if ts else None
