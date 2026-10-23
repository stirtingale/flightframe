"""Draw the screens for a 6-colour (Spectra 6) E Ink panel.

Everything is drawn with the panel's exact colours and with anti-aliasing
off, so nothing needs dithering and text stays crisp on paper.
"""
import glob
import math
import re
import os
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

from . import plane, sky
from .flights import compass

# Exact panel colours (Waveshare 7.3" E / Spectra 6)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
YELLOW = (255, 255, 0)
RED = (255, 0, 0)
BLUE = (0, 0, 255)
GREEN = (0, 255, 0)
ACCENTS = {"green": GREEN, "red": RED, "blue": BLUE, "yellow": YELLOW}

PANEL_W, PANEL_H = 800, 480

_FONT_CANDIDATES = {
    "bold": ["Inter-Bold.*", "InterDisplay-Bold.*", "DejaVuSans-Bold.ttf"],
    "semi": ["Inter-SemiBold.*", "InterDisplay-SemiBold.*", "DejaVuSans-Bold.ttf"],
    "regular": ["Inter-Medium.*", "Inter-Regular.*", "DejaVuSans.ttf"],
    "display": ["InterDisplay-Bold.*", "Inter-Bold.*", "DejaVuSans-Bold.ttf"],
}
_font_paths = {}
_font_cache = {}


def _find_font(kind):
    if kind in _font_paths:
        return _font_paths[kind]
    roots = [os.path.join(os.path.dirname(__file__), "fonts"), "/usr/share/fonts"]
    for pattern in _FONT_CANDIDATES[kind]:
        for root in roots:
            hits = sorted(glob.glob(os.path.join(root, "**", pattern), recursive=True))
            if hits:
                _font_paths[kind] = hits[0]
                return hits[0]
    _font_paths[kind] = None
    return None


def font(kind, size):
    key = (kind, size)
    if key not in _font_cache:
        path = _find_font(kind)
        _font_cache[key] = ImageFont.truetype(path, size) if path else ImageFont.load_default(size)
    return _font_cache[key]


def text_w(d, s, f):
    return d.textlength(s, font=f)


def fit(d, s, kind, size, max_w, min_size=12):
    """Largest font (<= size) at which s fits in max_w."""
    while size > min_size and text_w(d, s, font(kind, size)) > max_w:
        size -= 2
    return font(kind, size)


def ellipsize(d, s, f, max_w):
    if text_w(d, s, f) <= max_w:
        return s
    while s and text_w(d, s + "…", f) > max_w:
        s = s[:-1]
    return s.rstrip() + "…"

# ================================================================ the system
# One grid, one type scale, one set of components for every screen.
#
# Landscape 800 x 480: side margins 40, top and bottom 32. Four columns of 165
# with 20 gutters (column starts 40, 225, 410, 595); halves 40-370 and 410-760.
# Portrait 480 x 800: side margins 32, top and bottom 32, two columns of 198.
#
# Fixed baselines: header 44, rule 54-55, content from 72, footer h - 32.
SIDE_L, SIDE_P, TOPM = 40, 32, 32
GUTTER = 20
HEAD_BASE = TOPM + 12          # 44
RULE_Y = HEAD_BASE + 10        # 54, 2 px
CONTENT_TOP = RULE_Y + 18      # 72

# The type scale: seven sizes, nothing else. Long text steps down the scale.
SCALE = (116, 88, 56, 36, 26, 16, 13)
# Styles: (font kind, px, tracking px)
LABEL = ("bold", 13, 1)        # small capitals: labels, the screen name, radar labels
BODY = ("regular", 16, 0)      # secondary lines, footer (Medium, never below 16)
BODY_S = ("semi", 16, 0)       # emphasised body: footer temperatures, table names
UNIT = ("semi", 16, 0)         # units after a figure: 0.6 of the value size
VALUE = ("semi", 26, 0)        # figures
SUB = ("regular", 26, 0)       # identity line and cities: value size, lighter weight
TITLE = ("display", 36, 0)     # flight numbers (accent)
DISPLAY = ("display", 56, 0)   # duo and tracker routes, aircraft names, setup titles
HERO_S = ("display", 88, 0)    # "Quiet skies"; the first step down for long codes
HERO = ("display", 116, 0)     # airport codes

ARROW_HERO = 8                 # the poster's arrow stroke
ARROW_ROUTE = 6                # the route arrow at Display size


def F(style, size=None):
    return font(style[0], size or style[1])


def step(style, size):
    """The same style at another size on the scale."""
    return (style[0], size, style[2] if len(style) > 2 else 0)


def fit_scale(c, s, style, max_w, floor=16):
    """Largest size on the scale (<= style's) at which s fits in max_w."""
    sizes = [z for z in SCALE if z <= style[1] and z >= floor]
    for z in sizes:
        if text_w(c.d, s, font(style[0], z)) <= max_w:
            return font(style[0], z), z
    z = sizes[-1] if sizes else style[1]
    return font(style[0], z), z


class Canvas:
    def __init__(self, orientation="landscape"):
        self.portrait = orientation == "portrait"
        self.w, self.h = (PANEL_H, PANEL_W) if self.portrait else (PANEL_W, PANEL_H)
        self.img = Image.new("RGB", (self.w, self.h), WHITE)
        self.d = ImageDraw.Draw(self.img)
        self.d.fontmode = "1"   # no anti-aliasing: crisp on E Ink
        self.m = SIDE_P if self.portrait else SIDE_L
        self.inner = self.w - 2 * self.m
        cols = 2 if self.portrait else 4
        self.col_w = (self.inner - (cols - 1) * GUTTER) // cols
        self.cols = [self.m + i * (self.col_w + GUTTER) for i in range(cols)]
        self.half = (self.inner - GUTTER) // 2
        self.mid = self.m + self.half + GUTTER          # start of the right half
        self.foot = self.h - TOPM                       # footer baseline
        self.bottom = self.foot - 36                    # lowest content baseline
        self.keep = []          # aircraft drawings: put back the right way round at night
        self.sky = None         # empty area where sun, moon, stars and rain may go
        self.accent = GREEN
        self.facing = 0
        self.units = "metric"

    def setup(self, cfg, night):
        self.accent = _accent(cfg, night)
        self.facing = float(cfg.get("facing", 0) or 0)
        self.units = cfg.get("units", "metric")

    def paste_plane(self, img, xy):
        xy = (int(xy[0]), int(xy[1]))
        self.img.paste(img, xy)
        self.keep.append((img, xy))

    def text(self, xy, s, f, fill=BLACK, anchor="la"):
        self.d.text(xy, s, font=f, fill=fill, anchor=anchor)

    def rule(self, y, thick=2, fill=BLACK):
        self.d.rectangle([self.m, y, self.w - self.m, y + thick - 1], fill=fill)


def tracked(c, xy, s, style, fill=BLACK, anchor="ls"):
    """Text with letter spacing (PIL has none): drawn a character at a time."""
    f = F(style)
    t = style[2]
    w = sum(c.d.textlength(ch, font=f) for ch in s) + t * max(0, len(s) - 1)
    x, y = xy
    if anchor[0] == "r":
        x -= w
    elif anchor[0] == "m":
        x -= w / 2
    for ch in s:
        c.d.text((x, y), ch, font=f, fill=fill, anchor="l" + anchor[1])
        x += c.d.textlength(ch, font=f) + t
    return w


def cap(style, size=None):
    """Cap height of a style in px."""
    return -F(style, size).getbbox("H", anchor="ls")[1]


def ident(f):
    """One name per flight on every screen."""
    return _ident(f)


def _ident(f):
    return f.flight_number or f.callsign or f.registration or (f.hex or "").upper()


_COUNTRY = {"United States": "USA", "United States of America": "USA",
            "United Arab Emirates": "UAE", "Russian Federation": "Russia",
            "Korea, Republic of": "South Korea", "Iran, Islamic Republic of": "Iran"}


def airport_name(ap):
    """'London Heathrow Airport' -> 'Heathrow'; 'Los Angeles International Airport' ->
    'Los Angeles Intl'; '' when it would only repeat the city."""
    name, city = (ap.get("name") or "").strip(), (ap.get("city") or "").strip()
    for w in (" International Airport", " Intl Airport", " Airport", " Aerodrome", " Airfield",
              " Air Base", " Airstrip", " Heliport"):
        if name.endswith(w):
            name = name[: -len(w)] + (" International" if "International" in w else "")
            break
    name = name.replace("International", "Intl").strip()
    if city and name.lower().startswith(city.lower() + " "):
        rest = name[len(city):].strip()
        if rest and rest.lower() != "intl":
            name = rest
    if name.lower() in (city.lower(), "", "intl"):
        return ""
    return name


def place(ap):
    """'Heathrow, London, United Kingdom': airport, city, country, without repeats."""
    country = (ap.get("country") or "").strip()
    country = _COUNTRY.get(country, country)
    bits = [airport_name(ap), (ap.get("city") or "").strip(), country]
    out = []
    for b in bits:
        if b and b.lower() not in (x.lower() for x in out):
            out.append(b)
    return ", ".join(out)


LOC = ("semi", 13, 0)       # the full location under an airport code: very small


def location(c, x, base, ap, max_w, anchor="ls", lines=2, prefix=""):
    """The place name under a code, wrapped to at most `lines` lines. Returns the last baseline."""
    f = F(LOC)
    text = prefix + place(ap)
    rows = _wrap(c.d, text, f, max_w)
    if len(rows) > lines:
        rows = rows[:lines - 1] + [ellipsize(c.d, " ".join(rows[lines - 1:]), f, max_w)]
    for i, row in enumerate(rows):
        c.text((x, base + i * 17), row, f, anchor=anchor)
    return base + (len(rows) - 1) * 17


def short_type(f):
    """'Airbus A350-1041' -> 'A350-1041'; the ICAO code when there's no name."""
    name = (f.type_name or "").strip()
    for maker in ("Airbus Helicopters ", "Airbus ", "Boeing ", "Embraer ", "Bombardier ", "Eurocopter "):
        if name.startswith(maker):
            name = name[len(maker):]
    return name or f.type_code or "–"


# ---------------------------------------------------------------- formatting
def fmt_alt(ft, units):
    if ft is None:
        return "–"
    if units == "imperial":
        return f"{round(ft, -2):,.0f} ft"
    return f"{round(ft * 0.3048, -1):,.0f} m"


def fmt_speed(kt, units):
    if kt is None:
        return "–"
    return f"{kt * 1.15078:.0f} mph" if units == "imperial" else f"{kt * 1.852:.0f} km/h"


def fmt_dist(km, units):
    if units == "imperial":
        mi = km * 0.621371
        return f"{mi:.1f} mi" if mi < 10 else f"{mi:,.0f} mi"
    return f"{km:.1f} km" if km < 10 else f"{km:,.0f} km"


def phase(f):
    v = f.vertical_fpm
    if v is None or abs(v) < 400:
        return "level"
    return "climbing" if v > 0 else "descending"


def _now():
    return datetime.now().strftime("%H:%M")


# ---------------------------------------------------------------- day and night
def _sun_today(cfg, wx):
    sun = (wx or {}).get("sun")
    if sun and sun[0]:
        return sun
    try:
        from .weather import sun_times
        return sun_times(float(cfg["lat"]), float(cfg["lon"]))
    except (KeyError, TypeError, ValueError):
        return (None, None)


def is_night(cfg, wx=None):
    return sky.is_night(_sun_today(cfg, wx), cfg.get("night_mode", "auto"))


def _accent(cfg, night):
    a = ACCENTS.get(cfg.get("accent"), GREEN)
    # Green and blue ink nearly vanish on black paper; at night they become yellow
    if night and a in (GREEN, BLUE):
        return YELLOW
    return a


def _weather_now(wx):
    slots = (wx or {}).get("slots") or []
    return slots[0]["kind"] if slots else None



# ---------------------------------------------------------------- weather
FOOTER_WX = 40     # height of the weather footer


def _cloud(d, cx, cy, sz, fill=WHITE):
    """A cloud with a black outline: three bumps on a flat base."""
    parts = [(cx - sz * 0.32, cy + sz * 0.05, sz * 0.26), (cx, cy - sz * 0.10, sz * 0.34),
             (cx + sz * 0.32, cy + sz * 0.06, sz * 0.24)]
    base = (cx - sz * 0.56, cy + sz * 0.02, cx + sz * 0.56, cy + sz * 0.30)
    for grow, colour in ((1.6, BLACK), (0, fill)):
        for x, y, r in parts:
            d.ellipse([x - r - grow, y - r - grow, x + r + grow, y + r + grow], fill=colour)
        d.rounded_rectangle([base[0] - grow, base[1] - grow, base[2] + grow, base[3] + grow],
                            radius=sz * 0.14 + grow, fill=colour)


def _sun(d, cx, cy, r, rays=True):
    if rays:
        for i in range(8):
            a = math.radians(i * 45)
            d.line([cx + math.cos(a) * r * 1.35, cy + math.sin(a) * r * 1.35,
                    cx + math.cos(a) * r * 1.85, cy + math.sin(a) * r * 1.85], fill=BLACK, width=2)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=YELLOW, outline=BLACK, width=2)


def _moon(d, cx, cy, r, bg=WHITE):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=BLACK)
    d.ellipse([cx - r * 0.45, cy - r * 1.15, cx + r * 1.55, cy + r * 0.85], fill=bg)


def weather_icon(d, kind, day, cx, cy, sz):
    """Draw a weather symbol about sz pixels wide, centred on (cx, cy)."""
    if kind == "clear":
        (_sun(d, cx, cy, sz * 0.26) if day else _moon(d, cx, cy, sz * 0.34))
        return
    if kind == "partly":
        if day:
            _sun(d, cx - sz * 0.18, cy - sz * 0.16, sz * 0.21)
        else:
            _moon(d, cx - sz * 0.16, cy - sz * 0.18, sz * 0.24)
        _cloud(d, cx + sz * 0.08, cy + sz * 0.10, sz * 0.78)
        return
    if kind == "fog":
        for i, w in enumerate((0.9, 0.7, 0.9)):
            y = cy - sz * 0.22 + i * sz * 0.22
            d.line([cx - sz * w / 2, y, cx + sz * w / 2, y], fill=BLACK, width=3)
        return
    _cloud(d, cx, cy - sz * 0.12, sz * 0.92)
    below = cy + sz * 0.26
    if kind in ("rain", "showers", "sleet"):
        n = 3 if kind != "showers" else 2
        for i in range(n):
            x = cx - sz * 0.22 + i * sz * (0.22 if n == 3 else 0.44)
            d.line([x + 2, below, x - 2, below + sz * 0.22], fill=BLUE, width=3)
        if kind == "sleet":
            d.ellipse([cx + sz * 0.26, below + 1, cx + sz * 0.36, below + sz * 0.11], fill=BLACK)
    elif kind == "snow":
        for i in range(3):
            x = cx - sz * 0.22 + i * sz * 0.22
            for a in (0, 60, 120):
                ra = math.radians(a)
                d.line([x - math.cos(ra) * 3, below + 6 - math.sin(ra) * 3,
                        x + math.cos(ra) * 3, below + 6 + math.sin(ra) * 3], fill=BLUE, width=2)
    elif kind == "thunder":
        x, y = cx, below - 3
        bolt = [(x + 2, y), (x - 5, y + 9), (x, y + 9), (x - 3, y + 17), (x + 7, y + 6), (x + 2, y + 6), (x + 5, y)]
        d.polygon(bolt, fill=YELLOW, outline=BLACK)


def _sun_glyph(d, cx, cy, up):
    """Half sun on the horizon with an arrow, visually centred on (cx, cy)."""
    hy = cy + 4                                   # horizon
    d.pieslice([cx - 8, hy - 8, cx + 8, hy + 8], 180, 360, fill=YELLOW, outline=BLACK, width=2)
    d.line([cx - 11, hy, cx + 11, hy], fill=BLACK, width=2)
    ax = cx + 15
    if up:
        d.polygon([(ax, cy - 7), (ax - 4, cy - 2), (ax + 4, cy - 2)], fill=BLACK)
        d.line([ax, cy - 3, ax, hy], fill=BLACK, width=2)
    else:
        d.polygon([(ax, hy), (ax - 4, hy - 5), (ax + 4, hy - 5)], fill=BLACK)
        d.line([ax, cy - 7, ax, hy - 4], fill=BLACK, width=2)




# ---------------------------------------------------------------- finishing
def finish(c, cfg, wx, night, decorate=True):
    """Add the sky (sun or moon, stars, rain) and turn the screen dark at night."""
    if decorate and c.sky:
        try:
            sky.decorate(c.img, c.sky, _weather_now(wx), night,
                         lat=float(cfg.get("lat") or 0), big=13 if c.portrait else 15)
        except Exception:
            pass
    if not night:
        return c.img
    # Blue ink vanishes on black paper: anything blue (rain, snow) turns white at night
    c.img.paste(BLACK, mask=sky._where(c.img, BLUE))
    return sky.night(c.img, c.keep)


# ---------------------------------------------------------------- components
def open_arrow(d, tail, tip, thick, fill, head=None):
    """The one arrow: a straight shaft with an open, round-ended chevron head."""
    (x0, y0), (x1, y1) = tail, tip
    ln = math.hypot(x1 - x0, y1 - y0) or 1
    ux, uy = (x1 - x0) / ln, (y1 - y0) / ln
    h = head or max(thick * 2.4, 6)
    arm = h / math.sqrt(2)
    left = (x1 - arm * (ux - uy), y1 - arm * (uy + ux))
    right = (x1 - arm * (ux + uy), y1 - arm * (uy - ux))
    back = (x1 - ux * thick * 0.35, y1 - uy * thick * 0.35)
    w = max(2, int(round(thick)))
    d.line([tail, back], fill=fill, width=w)
    d.line([left, tip, right], fill=fill, width=w, joint="curve")
    r = w / 2 - 0.25
    for px, py in (tail, left, right, tip):
        d.ellipse([px - r, py - r, px + r, py + r], fill=fill)


def compass_glyph(d, cx, cy, r, bearing, facing=0, accent=RED):
    """The direction mark: the arrow pointing at the aircraft, turned to suit the
    way the frame faces."""
    a = math.radians((bearing - (facing or 0)) % 360)
    ux, uy = math.sin(a), -math.cos(a)
    k = r * 0.92
    thick = max(2, round(r / 3.2))
    open_arrow(d, (cx - ux * k, cy - uy * k), (cx + ux * k, cy + uy * k), thick, accent,
               head=r * 1.05)


UNITS = ("m", "ft", "km", "mi", "km/h", "mph", "h", "min")


def _is_big(tok):
    return tok not in UNITS


def figure(c, x, base, value, style=VALUE, anchor="l", draw=True):
    """A figure: numbers (and compass points) at the value size, units at 0.6 of it,
    all on one baseline. Returns the width."""
    big = F(style)
    small = F(UNIT) if style[1] >= 26 else F(step(LABEL, 13))
    toks = value.split(" ")
    parts, w, prev = [], 0, None
    for t in toks:
        b = _is_big(t)
        f = big if b else small
        if prev is not None:
            w += max(3 if not b else 5, int(style[1] * (0.26 if b and prev else 0.12 if not b else 0.22)))
        parts.append((w, t, f))
        w += text_w(c.d, t, f)
        prev = b
    if draw:
        x0 = x - w if anchor == "r" else x
        for dx, t, f in parts:
            c.text((x0 + dx, base), t, f, anchor="ls")
    return w


def where(f, units):
    return f"{fmt_dist(f.distance_km, units)} {compass(f.bearing)}".strip()


def where_figure(c, x, base, f, style=VALUE, anchor="l", draw=True):
    """Chevron + '3.2 km NE'. The chevron is as tall as the figure's capitals."""
    s = where(f, c.units)
    r = max(6, round(cap(style) * 0.55))
    tw = figure(c, 0, 0, s, style, draw=False)
    total = 2 * r + 8 + tw
    if draw:
        x0 = x - total if anchor == "r" else x
        compass_glyph(c.d, x0 + r, base - cap(style) / 2, r, f.bearing, c.facing, c.accent)
        figure(c, x0 + 2 * r + 8, base, s, style)
    return total


def trend_mark(c, x, base, trend, style=VALUE):
    """Climbing or descending: a solid accent triangle, capital height tall."""
    h = cap(style)
    top, bot = base - h, base
    w = round(h * 0.8)
    if trend == "climbing":
        pts = [(x, bot), (x + w, bot), (x + w / 2, top)]
    else:
        pts = [(x, top), (x + w, top), (x + w / 2, bot)]
    c.d.polygon(pts, fill=c.accent)
    return w


def _header(c, left, right, accent=None, rule=True):
    """The screen name (small capitals, accent) at left, one status at right."""
    tracked(c, (c.m, HEAD_BASE), left, LABEL, fill=accent or c.accent)
    if right:
        c.text((c.w - c.m, HEAD_BASE), right, F(BODY), anchor="rs")
    if rule:
        c.rule(RULE_Y)
    return CONTENT_TOP


def _footer(c, cfg, extra=""):
    label = cfg.get("label") or ""
    c.text((c.m, c.foot), label, F(BODY), anchor="ls")
    right = f"{extra}  ·  {_now()}" if extra else f"Updated {_now()}"
    c.text((c.w - c.m, c.foot), right, F(BODY), anchor="rs")


def _footer_wx(c, wx):
    """Bottom line: sunrise and sunset at left, then forecast cells on an even pitch.
    Every word in it is 16 px; temperatures in SemiBold."""
    mid = c.foot - cap(BODY) / 2
    f_time = F(BODY)
    f_temp = F(BODY_S)
    x = c.m
    sun = (wx or {}).get("sun") or (None, None)
    if sun[0]:
        for t, up in ((sun[0], True), (sun[1], False)):
            _sun_glyph(c.d, x + 11, mid, up)
            c.text((x + 38, c.foot), t.strftime("%H:%M"), f_time, anchor="ls")
            x += 38 + int(text_w(c.d, "00:00", f_time)) + 16
        x += 16
    slots = (wx or {}).get("slots") or []
    if not slots:
        c.text((c.w - c.m, c.foot), f"Updated {_now()}", f_time, anchor="rs")
        return
    hour_w = int(text_w(c.d, "00:00", f_time))
    temp_w = int(text_w(c.d, "00°", f_temp))
    icon = 24
    cell = hour_w + 8 + icon + 8 + temp_w
    room = c.w - c.m - x
    fits = max(1, (room + 8) // (cell + 8))
    if fits < len(slots):
        slots = slots[1:]               # short of space: the next hours matter more than now
    n = min(len(slots), fits)
    pitch = (room - cell) / (n - 1) if n > 1 else 0
    pitch = min(pitch, cell + 40)
    x0 = c.w - c.m - cell - (n - 1) * pitch
    first = ((wx or {}).get("slots") or [None])[0]
    for i, sl in enumerate(slots[:n]):
        cx = x0 + i * pitch
        label = "Now" if sl is first else sl["time"].strftime("%H:%M")
        c.text((cx + hour_w, c.foot), label, f_time, anchor="rs")
        weather_icon(c.d, sl["kind"], sl["day"], cx + hour_w + 8 + icon // 2, mid - 1, icon)
        c.text((cx + hour_w + 8 + icon + 8, c.foot), f"{round(sl['temp'])}°", f_temp, anchor="ls")


def _arrow(c, x0, x1, y, fill, thick=ARROW_ROUTE):
    """A horizontal route arrow (see open_arrow)."""
    open_arrow(c.d, (x0 + thick / 2, y), (x1 - thick / 2, y), thick, fill, head=thick * 2.6 + 4)


def route_line(c, x, base, o, d, style, max_w, anchor="l"):
    """'LHR -> LAX' with the drawn arrow, stepping down the scale until it fits."""
    for size in [z for z in SCALE if z <= style[1]] + [style[1]]:
        f = F(style, size)
        gap = int(size * 0.22)
        aw = int(size * 0.7)
        w = text_w(c.d, o, f) + gap + aw + gap + text_w(c.d, d, f)
        if w <= max_w or size <= 26:
            break
    x0 = x if anchor == "l" else x - w
    c.text((x0, base), o, f, anchor="ls")
    ax = x0 + text_w(c.d, o, f) + gap
    _arrow(c, ax, ax + aw, int(base - cap(style, size) / 2), c.accent,
           thick=ARROW_ROUTE if size >= 56 else 4)
    c.text((ax + aw + gap, base), d, f, anchor="ls")
    return size


ROW_H = 66          # label baseline to the next row's label baseline
VAL_DY = 32         # label baseline to value baseline


def _stats(c, base, cells, xs, col_w):
    """The figures row. cells: (label, value) or (label, value, extra) where extra is
    'climbing' / 'descending' or a Flight (draws the chevron and distance)."""
    per = len(xs)
    for i, cell in enumerate(cells):
        label, value = cell[0], cell[1]
        extra = cell[2] if len(cell) > 2 else None
        r, k = divmod(i, per)
        x = xs[k]
        yy = base + r * ROW_H
        tracked(c, (x, yy), label.upper(), LABEL)
        vb = yy + VAL_DY
        if extra is not None and not isinstance(extra, str):
            st = VALUE if where_figure(c, 0, 0, extra, VALUE, draw=False) <= col_w else BODY_S
            where_figure(c, x, vb, extra, st)
            continue
        room = col_w - (28 if extra in ("climbing", "descending") else 0)
        st = VALUE if figure(c, 0, 0, value, VALUE, draw=False) <= room else BODY_S
        w = figure(c, x, vb, value, st)
        if extra in ("climbing", "descending"):
            trend_mark(c, x + w + 8, vb, extra, st)


def _identity(c, x, base, f, max_w, style=SUB, max_lines=2):
    """'British Airways · G-XWBC'. The registration never splits from its dot.
    Returns the baseline of the last line."""
    who = f.airline or f.operator or ""
    reg = f.registration or ""
    words = who.split()
    if words and reg:       # the last word of the name travels with the registration
        words[-1] = f"{words[-1]}\u00a0·\u00a0{reg}"
    elif reg:
        words = [reg]
    for st in (style, step(style, 16)):
        fnt = F(st)
        lines, line = [], ""
        for wd in words:
            t = f"{line} {wd}".strip()
            if text_w(c.d, t, fnt) <= max_w or not line:
                line = t
            else:
                lines.append(line)
                line = wd
        if line:
            lines.append(line)
        if len(lines) <= max_lines:
            break
    lead = 30 if st[1] >= 26 else 22
    for i, ln in enumerate(lines):
        c.text((x, base + i * lead), ln, fnt, anchor="ls")
    return base + (len(lines) - 1) * lead


def aircraft_value(c, f, col_w):
    """The AIRCRAFT figure: the short type name if it fits, otherwise the code."""
    name = short_type(f)
    if text_w(c.d, name, F(VALUE)) <= col_w:
        return name
    return f.type_code or name


# ---------------------------------------------------------------- screens
# Shared baselines for the single-aircraft family (poster, no-route poster, quiet).
# The figures row never moves.
L_NUM, L_ID, L_HERO, L_CITY, L_STATS = 98, 134, 284, 320, 356
P_NUM, P_ID, P_PLANE, P_CODE1, P_STATS = 98, 134, 176, 376, 630


def _poster_cells(c, f, col_w):
    return [("Distance", "", f),
            ("Altitude", fmt_alt(f.altitude_ft, c.units), phase(f)),
            ("Speed", fmt_speed(f.speed_kt, c.units)),
            ("Aircraft", aircraft_value(c, f, col_w))]


def poster(f, cfg, nearby=0, logo=None, wx=None):
    c = Canvas(cfg.get("orientation", "landscape"))
    night = is_night(cfg, wx)
    c.setup(cfg, night)
    accent = c.accent
    show_plane = cfg.get("show_plane", True)
    _header(c, "OVERHEAD NOW", "")
    fn = ident(f)
    kind = plane.classify(f.type_code, f.category)

    if not c.portrait:
        text_max = c.half if show_plane else c.inner
        ff, _ = fit_scale(c, fn, TITLE, text_max, 26)
        c.text((c.m - 1, L_NUM), fn, ff, fill=accent, anchor="ls")
        _identity(c, c.m, L_ID, f, text_max)
        if show_plane:
            ph = 96
            img = plane.draw(kind, int(c.half), ph, logo=logo, accent=accent)
            right = c.w - c.m + 4
            corner = img.crop((img.width - 52, 0, img.width, 40)).convert("L").getextrema()[0]
            if corner < 250:        # keep the sky seat (top-right 52 x 52) for the sun or moon
                img = plane.draw(kind, int(c.half) - 52, ph, logo=logo, accent=accent)
                right -= 52
            c.paste_plane(img, (right - img.width, CONTENT_TOP + 14 + (ph - img.height) // 2))
            c.sky = (c.mid, CONTENT_TOP - 12, c.w - c.m + 8, L_HERO - cap(HERO) - 10)
        if f.has_route:
            o, d = f.origin, f.destination
            code_w = (c.inner - 120) // 2
            size = min(fit_scale(c, ap["iata"], HERO, code_w, 56)[1] for ap in (o, d))
            big = F(HERO, size)
            c.text((c.m - 4, L_HERO), o["iata"], big, anchor="ls")
            c.text((c.w - c.m + 3, L_HERO), d["iata"], big, anchor="rs")
            _arrow(c, c.w // 2 - 40, c.w // 2 + 40, int(L_HERO - cap(HERO, size) / 2), accent,
                   thick=ARROW_HERO)
            for ap, anchor, x in ((o, "ls", c.m), (d, "rs", c.w - c.m)):
                location(c, x, L_HERO + 26, ap, code_w + 30, anchor=anchor)
        else:
            name = f.type_name or f.type_code or "Aircraft"
            fb, z = fit_scale(c, name, DISPLAY, c.inner, 26)
            base = int(L_HERO - (cap(HERO) - cap(DISPLAY, z)) / 2)
            c.text((c.m - 2, base), name, fb, anchor="ls")
        _stats(c, L_STATS, _poster_cells(c, f, c.col_w), c.cols, c.col_w)
    else:
        ff, _ = fit_scale(c, fn, TITLE, c.inner, 26)
        c.text((c.m - 1, P_NUM), fn, ff, fill=accent, anchor="ls")
        last = _identity(c, c.m, P_ID, f, c.inner)
        top = max(P_PLANE, last + 22)
        if show_plane:
            img = plane.draw(kind, c.inner, 96, logo=logo, accent=accent)
            c.paste_plane(img, (c.m + (c.inner - img.width) // 2, top))
        c.sky = (c.m + c.inner // 2, CONTENT_TOP - 8, c.w - c.m, P_ID - 10)
        if f.has_route:
            o, d = f.origin, f.destination
            size = min(fit_scale(c, ap["iata"], HERO, c.inner, 56)[1] for ap in (o, d))
            big = F(HERO, size)
            b1 = P_CODE1 + (top - P_PLANE)
            c.text((c.m - 5, b1), o["iata"], big, anchor="ls")
            location(c, c.m, b1 + 26, o, c.inner)
            ay = b1 + 66
            _arrow(c, c.m, c.m + 80, ay, accent, thick=ARROW_HERO)
            b2 = ay + 28 + cap(HERO, size)
            c.text((c.m - 5, b2), d["iata"], big, anchor="ls")
            location(c, c.m, b2 + 26, d, c.inner)
        else:
            name = f.type_name or f.type_code or "Aircraft"
            fb = F(DISPLAY)
            lines = _wrap(c.d, name, fb, c.inner)
            if len(lines) > 3:
                fb = F(TITLE)
                lines = _wrap(c.d, name, fb, c.inner)
            y0 = P_CODE1 + 60
            for i, line in enumerate(lines[:4]):
                c.text((c.m - 2, y0 + i * 62), line, fb, anchor="ls")
        _stats(c, P_STATS, _poster_cells(c, f, c.col_w), c.cols, c.col_w)

    _footer_wx(c, wx)
    return finish(c, cfg, wx, night)


_LAST = re.compile(r"^(.*?)\b([A-Z0-9]{3,4})\s*[–\-→]\s*([A-Z0-9]{3,4})\b(.*)$")


def _last_seen(c, x, base, s, max_w):
    """'BA283 LHR–LAX at 21:14' drawn with the route arrow, like every other route."""
    m = _LAST.match(s or "")
    fv = F(VALUE)
    if not m:
        c.text((x, base), s, fit_scale(c, s, VALUE, max_w)[0], anchor="ls")
        return
    pre, o, d, post = m.groups()
    if pre.strip():
        c.text((x, base), pre.strip(), fv, anchor="ls")
        x += text_w(c.d, pre.strip() + " ", fv)
    gap, aw = 6, 22
    c.text((x, base), o, fv, anchor="ls")
    x += text_w(c.d, o, fv) + gap
    _arrow(c, x, x + aw, int(base - cap(VALUE) / 2), c.accent, thick=4)
    x += aw + gap
    c.text((x, base), d + post, fv, anchor="ls")


def quiet(cfg, last=None, wx=None):
    """Nothing overhead: the poster's skeleton, with the words where the codes go."""
    c = Canvas(cfg.get("orientation", "landscape"))
    night = is_night(cfg, wx)
    c.setup(cfg, night)
    _header(c, "THE SKY ABOVE", "")
    big = F(HERO_S)
    r = fmt_dist(float(cfg.get("radius_km") or 15), c.units)
    if not c.portrait:
        b2, sub, stats = L_HERO, L_CITY, L_STATS
    else:
        b2, sub, stats = 554, 590, P_STATS
    c.text((c.m - 4, b2 - 94), "Quiet", big, anchor="ls")
    c.text((c.m - 3, b2), "skies", big, fill=c.accent, anchor="ls")
    fs, _ = fit_scale(c, f"Nothing within {r} right now.", SUB, c.inner)
    c.text((c.m, sub), f"Nothing within {r} right now.", fs, anchor="ls")
    if last:
        tracked(c, (c.m, stats), "LAST SEEN", LABEL)
        _last_seen(c, c.m, stats + VAL_DY, last, c.inner)
    _footer_wx(c, wx)
    if c.portrait:
        c.sky = (c.m, CONTENT_TOP, c.w - c.m, b2 - 94 - cap(HERO_S) - 16)
    else:
        c.sky = (c.mid, CONTENT_TOP, c.w - c.m, b2 - cap(HERO_S) - 12)
    return finish(c, cfg, wx, night)


def message(cfg, title, lines, qr_data=None, header="SETUP"):
    """Setup and status screens."""
    c = Canvas(cfg.get("orientation", "landscape"))
    night = is_night(cfg) if cfg.get("lat") is not None else False
    c.setup(cfg, night)
    _header(c, header, "")
    qr_img = None
    qr_size = 0
    if qr_data:
        qr_img = _qr(qr_data, 228 if not c.portrait else 260)
        qr_size = qr_img.size[0] if qr_img else 0
    text_max = c.inner - qr_size - 40 if (qr_img and not c.portrait) else c.inner
    ft = F(DISPLAY)
    tl = _wrap(c.d, title, ft, text_max)
    if len(tl) > 2:
        ft = F(TITLE)
        tl = _wrap(c.d, title, ft, text_max)
    base = CONTENT_TOP + 8 + cap(DISPLAY if ft.size == DISPLAY[1] else TITLE)
    lead = int(ft.size * 1.05)
    for line in tl:
        c.text((c.m - 2, base), line, ft, anchor="ls")
        base += lead
    ty = base - lead + 48
    fl = F(SUB)
    room = (c.bottom - (qr_size + 24 if (qr_img and c.portrait) else 0)) - ty
    need = sum(len(_wrap(c.d, ln, fl, text_max)) for ln in lines) * 32 + 8 * len(lines)
    if need > room:
        fl = F(BODY)
    lh = 32 if fl.size >= 26 else 22
    for line in lines:
        for chunk in _wrap(c.d, line, fl, text_max):
            c.text((c.m, ty), chunk, fl, anchor="ls")
            ty += lh
        ty += 8
    qr_xy = None
    if qr_img:
        qr_xy = (c.m, min(ty + 8, c.bottom - qr_size)) if c.portrait \
            else (c.w - c.m - qr_size, CONTENT_TOP + 8)
        c.img.paste(qr_img, qr_xy)
    _footer(c, cfg, "")
    if qr_img and night:
        c.keep.append((_framed(qr_img), (qr_xy[0] - 8, qr_xy[1] - 8)))
    return finish(c, cfg, None, night, decorate=False)


def _framed(img, pad=8):
    """A QR code on a white card, kept light at night."""
    out = Image.new("RGB", (img.width + 2 * pad, img.height + 2 * pad), (1, 1, 1))
    out.paste(img, (pad, pad))
    return out


def _wrap(d, s, f, max_w):
    words, line, out = s.split(), "", []
    for w in words:
        t = f"{line} {w}".strip()
        if text_w(d, t, f) <= max_w:
            line = t
        else:
            if line:
                out.append(line)
            line = w
    if line:
        out.append(line)
    return out


def _qr(data, size):
    try:
        import qrcode
    except ImportError:
        return None
    q = qrcode.QRCode(border=1, box_size=1)
    q.add_data(data)
    q.make(fit=True)
    img = q.make_image(fill_color="black", back_color="white").convert("RGB")
    n = img.size[0]
    scale = max(1, size // n)
    return img.resize((n * scale, n * scale), Image.NEAREST)


# How the six inks look on the paper, for previews on screens (README, settings page).
# The panel itself always gets the exact colours above.
PAPER_LOOK = {GREEN: (34, 92, 58), RED: (196, 52, 44), BLUE: (38, 62, 140), YELLOW: (232, 200, 58)}


def as_seen(img):
    """A copy of a render with each ink mapped to how it looks on Spectra 6 paper."""
    out = img.convert("RGB").copy()
    px = out.load()
    w, h = out.size
    for y in range(h):
        for x in range(w):
            c = px[x, y]
            if c in PAPER_LOOK:
                px[x, y] = PAPER_LOOK[c]
    return out


def for_panel(img):
    """Panel is natively 800x480; turn portrait renders on their side."""
    if img.size == (PANEL_H, PANEL_W):
        return img.rotate(90, expand=True)
    return img




# ---------------------------------------------------------------- two at once
def duo(flights, cfg, nearby=2, logos=(None, None), wx=None):
    """Two aircraft: two equal half-posters (stacked in portrait). Figures line up."""
    c = Canvas(cfg.get("orientation", "landscape"))
    night = is_night(cfg, wx)
    c.setup(cfg, night)
    show_plane = cfg.get("show_plane", True)
    count = f"{nearby} overhead" if nearby > 2 else "Two overhead"
    _header(c, "OVERHEAD NOW", count)

    kinds = [plane.classify(f.type_code, f.category) for f in flights[:2]]

    def block(i, f, x, w, y0, ph, xs, col_w, ppm=None, rs=DISPLAY):
        if show_plane and ph:
            img = plane.draw(kinds[i], int(w), ph, ppm=ppm,
                             logo=logos[i] if i < len(logos) else None, accent=c.accent)
            px = x if not c.portrait else x + (w - img.width) // 2
            c.paste_plane(img, (px, y0 + (ph - img.height) // 2))
        b_num = y0 + ph + (16 if ph else 8) + cap(TITLE)
        fn, _ = fit_scale(c, ident(f), TITLE, w, 26)
        c.text((x - 1, b_num), ident(f), fn, fill=c.accent, anchor="ls")
        b_id = _identity(c, x, b_num + 24, f, w, BODY, max_lines=1)
        b_route = b_id + 16 + cap(rs)
        if f.has_route:
            route_line(c, x - 2, b_route, f.origin["iata"], f.destination["iata"], rs, w)
            b = location(c, x, b_route + 20, f.origin, w, lines=1, prefix="From ")
            b_route = location(c, x, b + 17, f.destination, w, lines=1, prefix="To ") - 4
        else:
            name = f.type_name or f.type_code or "Aircraft"
            fr, _ = fit_scale(c, name, rs, w, 26)
            c.text((x - 2, b_route), name, fr, anchor="ls")
        cells = [("Distance", "", f), ("Altitude", fmt_alt(f.altitude_ft, c.units), phase(f)),
                 ("Speed", fmt_speed(f.speed_kt, c.units)), ("Aircraft", aircraft_value(c, f, col_w))]
        _stats(c, b_route + 32, cells, xs, col_w)
        return b_route + 32 + ROW_H + VAL_DY

    if not c.portrait:
        ph = 60 if show_plane else 0
        col_w = (c.half - GUTTER) // 2
        ppm = plane.common_scale(kinds, c.half, ph) if ph else None
        for i, f in enumerate(flights[:2]):
            x = c.m if i == 0 else c.mid
            block(i, f, x, c.half, CONTENT_TOP - 2, ph, [x, x + col_w + GUTTER], col_w, ppm)
        c.sky = (c.m, CONTENT_TOP - 8, c.w - c.m + 8, CONTENT_TOP + ph) if show_plane else None
    else:
        ph = 44 if show_plane else 0
        ppm = plane.common_scale(kinds, c.inner, ph) if ph else None
        y = CONTENT_TOP - 2
        for i, f in enumerate(flights[:2]):
            y = block(i, f, c.m, c.inner, y, ph, c.cols, c.col_w, ppm, rs=TITLE) + 18
        c.sky = None
    _footer_wx(c, wx)
    return finish(c, cfg, wx, night, decorate=not c.portrait)


# ---------------------------------------------------------------- radar
def _dashed_ring(d, cx, cy, r, fill, width=2, dash_deg=4, gap_deg=4):
    a = 0
    while a < 360:
        d.arc([cx - r, cy - r, cx + r, cy + r], a, a + dash_deg, fill=fill, width=width)
        a += dash_deg + gap_deg


HALO = 3


def radar(contacts, cfg, wx=None, highlight=None):
    """The scope (an instrument, left) and the readout (nearest list, right)."""
    c = Canvas(cfg.get("orientation", "landscape"))
    night = is_night(cfg, wx)
    c.setup(cfg, night)
    accent, facing, units = c.accent, c.facing, c.units
    rng = float(cfg.get("radar_km") or 40)
    contacts = sorted(contacts, key=lambda f: f.distance_km)
    n = len(contacts)
    _header(c, "RADAR", f"{n} aircraft within {fmt_dist(rng, units)}")
    if c.portrait:
        r = c.inner // 2 - 14
        cx, cy = c.w // 2, CONTENT_TOP + 22 + r
        list_x, list_w = c.m, c.inner
        list_base = cy + r + 44
        rows = 5
    else:
        r = 152
        cx, cy = c.m + c.half // 2, CONTENT_TOP + 20 + r
        list_x, list_w = c.mid, c.w - c.m - c.mid
        list_base = CONTENT_TOP + cap(LABEL)
        rows = 5
    d = c.d
    # the instrument: solid outer ring, dashed half-range ring, ticks at the four points
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=BLACK, width=2)
    _dashed_ring(d, cx, cy, r / 2, BLACK)
    for k in range(4):
        a = math.radians(k * 90 - facing)
        d.line([cx + math.sin(a) * (r - 10), cy - math.cos(a) * (r - 10),
                cx + math.sin(a) * r, cy - math.cos(a) * r], fill=BLACK, width=2)
    f_lab = font("semi", 13)
    obstacles = []
    na = math.radians(-facing)
    nx, ny = cx + math.sin(na) * (r + 14), cy - math.cos(na) * (r + 14)
    tracked(c, (nx, ny + cap(LABEL) / 2), "N", LABEL, fill=accent, anchor="ms")
    # home
    d.polygon([(cx, cy - 8), (cx - 7, cy - 1), (cx + 7, cy - 1)], fill=BLACK)
    d.rectangle([cx - 5, cy - 1, cx + 5, cy + 6], fill=BLACK)
    obstacles.append(((cx - 9, cy - 10, cx + 9, cy + 8), None))

    def pos(f):
        a = math.radians(f.bearing - facing)
        k = min(1.0, f.distance_km / rng) * r
        return cx + math.sin(a) * k, cy - math.cos(a) * k

    hl = highlight.hex if highlight else (contacts[0].hex if contacts else None)

    def ident(f):
        if highlight is not None and f.hex == highlight.hex:
            return _ident(highlight)
        return _ident(f)

    for f in reversed(contacts):
        x, y = pos(f)
        if f.track is not None:
            a = math.radians(f.track - facing)
            ex, ey = x + math.sin(a) * 15, y - math.cos(a) * 15
            d.line([x, y, ex, ey], fill=BLACK, width=2)
            obstacles.append(((min(x, ex) - 1, min(y, ey) - 1, max(x, ex) + 1, max(y, ey) + 1), f.hex))
        rad = 7 if f.hex == hl else 5
        d.ellipse([x - rad, y - rad, x + rad, y + rad], fill=accent, outline=BLACK, width=2)
        obstacles.append(((x - rad - 1, y - rad - 1, x + rad + 1, y + rad + 1), f.hex))
    # both rings labelled, on a paper halo, where no aircraft is
    marks = [b for b, who in obstacles if who is not None]
    for rr, txt in ((r / 2, fmt_dist(rng / 2, units)), (r, fmt_dist(rng, units))):
        tw = text_w(d, txt, f_lab)
        for deg in (150, 210, 120, 240, 60, 300, 30, 330):
            a = math.radians(deg)
            lx, ly = cx + math.sin(a) * rr, cy - math.cos(a) * rr
            box = (lx - tw / 2 - HALO, ly - 7 - HALO, lx + tw / 2 + HALO, ly + 6 + HALO)
            if not any(_overlap(box, b) for b in marks) and box[3] < c.foot - 24:
                break
        d.rectangle(box, fill=WHITE)
        c.text((lx, ly + 5), txt, f_lab, anchor="ms")
        obstacles.append((box, None))
    order = sorted(contacts[:10], key=lambda f: f.hex != hl)        # the highlighted one first
    limit_x = list_x - 12 if not c.portrait else c.w - 4
    for f in order:
        x, y = pos(f)
        name = ident(f)
        alt = fmt_alt(f.altitude_ft, units)
        spots = [(dx, dy, anc, 2) for dx, dy, anc in
                 ((10, -13, "l"), (-10, -13, "r"), (10, 2, "l"), (-10, 2, "r"), (10, -24, "l"), (-10, -24, "r"),
                  (10, -32, "l"), (-10, -32, "r"), (-10, 10, "r"), (10, 10, "l"))]
        spots += [(dx, dy, anc, 1) for dx, dy, anc in
                  ((10, -7, "l"), (-10, -7, "r"), (-8, -24, "l"), (-8, 9, "l"), (-8, -24, "r"), (8, 9, "r"))]
        placed = None
        for dx, dy, anc, nl in spots:   # name and height; only the name when crowded
            tw = max(text_w(d, name, f_lab), text_w(d, alt, f_lab)) if nl == 2 else text_w(d, name, f_lab)
            x0 = x + dx if anc == "l" else x + dx - tw
            box = (x0 - HALO, y + dy - HALO, x0 + tw + HALO, y + dy + (29 if nl == 2 else 13) + HALO)
            inside = math.hypot(max(abs(box[0] - cx), abs(box[2] - cx)),
                                max(abs(box[1] - cy), abs(box[3] - cy))) < r + 44
            if inside and box[0] > 4 and box[2] < limit_x \
                    and not any(_overlap(box, b) for b, who in obstacles if who != f.hex):
                placed = (x0, dy, nl, box)
                break
        if placed is None and f.hex == hl:          # the nearest is always labelled
            tw = max(text_w(d, name, f_lab), text_w(d, alt, f_lab))
            x0 = x + 10
            placed = (x0, -13, 2, (x0 - HALO, y - 13 - HALO, x0 + tw + HALO, y + 16 + HALO))
        if placed:
            x0, dy, nl, box = placed
            obstacles.append((box, None))
            d.rectangle(box, fill=WHITE)
            c.text((x0, y + dy + 10), name, f_lab, anchor="ls")
            if nl == 2:
                c.text((x0, y + dy + 26), alt, f_lab, anchor="ls")
    # the readout: the nearest as a large row, then a quiet table
    tracked(c, (list_x, list_base), "NEAREST", LABEL)
    if contacts:
        top = next((f for f in contacts if f.hex == hl), contacts[0])
        hb = list_base + 14 + cap(TITLE)
        dw = where_figure(c, 0, 0, top, VALUE, draw=False)
        fn, _ = fit_scale(c, ident(top), TITLE, list_w - dw - 16, 26)
        c.text((list_x - 1, hb), ident(top), fn, fill=accent, anchor="ls")
        where_figure(c, list_x + list_w, hb, top, VALUE, anchor="r")
        sub = "  ·  ".join(b for b in (short_type(top), fmt_alt(top.altitude_ft, units)) if b and b != "–")
        c.text((list_x, hb + 28), sub, F(BODY), anchor="ls")
        yy = hb + 28 + 44
        rest = [f for f in contacts if f is not top][:rows]
        for f in rest:
            if yy > c.bottom:
                break
            c.text((list_x, yy), ident(f), F(BODY_S), anchor="ls")
            sub = " · ".join(b for b in (f.type_code, fmt_alt(f.altitude_ft, units)) if b and b != "–")
            c.text((list_x + (112 if not c.portrait else 132), yy), sub, F(BODY), anchor="ls")
            where_figure(c, list_x + list_w, yy, f, BODY_S, anchor="r")
            yy += 34
    else:
        c.text((list_x, list_base + 40), "Nothing on radar.", F(VALUE), anchor="ls")
    _footer_wx(c, wx)
    return finish(c, cfg, wx, night, decorate=False)


def _overlap(a, b):
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])
