"""Draw the screens for a 6-colour (Spectra 6) E Ink panel.

Everything is drawn with the panel's exact colours and with anti-aliasing
off, so nothing needs dithering and text stays crisp on paper.
"""
import glob
import math
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


class Canvas:
    def __init__(self, orientation="landscape"):
        self.portrait = orientation == "portrait"
        self.w, self.h = (PANEL_H, PANEL_W) if self.portrait else (PANEL_W, PANEL_H)
        self.img = Image.new("RGB", (self.w, self.h), WHITE)
        self.d = ImageDraw.Draw(self.img)
        self.d.fontmode = "1"   # no anti-aliasing: crisp on E Ink
        self.m = 32 if self.portrait else 40
        self.keep = []          # aircraft drawings: put back the right way round at night
        self.sky = None         # empty area where sun, moon, stars and rain may go

    def paste_plane(self, img, xy):
        xy = (int(xy[0]), int(xy[1]))
        self.img.paste(img, xy)
        self.keep.append((img, xy))

    def text(self, xy, s, f, fill=BLACK, anchor="la"):
        self.d.text(xy, s, font=f, fill=fill, anchor=anchor)

    def rule(self, y, thick=2, fill=BLACK):
        self.d.rectangle([self.m, y, self.w - self.m, y + thick - 1], fill=fill)


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


def finish(c, cfg, wx, night, decorate=True):
    """Add the sky (sun or moon, stars, rain) and turn the screen dark at night."""
    if decorate and c.sky:
        try:
            sky.decorate(c.img, c.sky, _weather_now(wx), night,
                         lat=float(cfg.get("lat") or 0), big=13 if c.portrait else 15)
        except Exception:
            pass
    return sky.night(c.img, c.keep) if night else c.img


def compass_glyph(d, cx, cy, r, bearing, facing=0, accent=RED):
    """A small dial with a needle towards the aircraft, turned to suit the frame's facing."""
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=BLACK, width=2)
    a = math.radians((bearing - (facing or 0)) % 360)
    tip = (cx + math.sin(a) * (r - 2), cy - math.cos(a) * (r - 2))
    side = math.radians(90)
    w = max(2.5, r * 0.32)
    back = (cx - math.sin(a) * r * 0.35, cy + math.cos(a) * r * 0.35)
    left = (cx + math.sin(a - side) * w, cy - math.cos(a - side) * w)
    right = (cx + math.sin(a + side) * w, cy - math.cos(a + side) * w)
    d.polygon([tip, left, back, right], fill=accent)
    # north mark on the rim
    n = math.radians((0 - (facing or 0)) % 360)
    nx, ny = cx + math.sin(n) * r, cy - math.cos(n) * r
    d.ellipse([nx - 2, ny - 2, nx + 2, ny + 2], fill=BLACK)


# ---------------------------------------------------------------- pieces
def _header(c, left, right, accent, dial=None, rule=True):
    """dial: (bearing, facing) to draw a compass beside the right-hand text."""
    y = c.m - 6
    c.text((c.m, y), left, font("bold", 14), fill=accent)
    if right:
        fr = font("semi", 14)
        c.text((c.w - c.m, y), right, fr, anchor="ra")
        if dial is not None:
            x = c.w - c.m - text_w(c.d, right, fr) - 15
            compass_glyph(c.d, x, y + 8, 9, dial[0], dial[1], accent)
    if rule:
        c.rule(y + 26)
    return y + 26


def _footer(c, cfg, extra=""):
    y = c.h - c.m + 4
    label = cfg.get("label") or ""
    c.text((c.m, y), label, font("regular", 15), anchor="ls")
    right = f"{extra}  ·  {_now()}" if extra else f"Updated {_now()}"
    c.text((c.w - c.m, y), right, font("regular", 15), anchor="rs")


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


def _footer_wx(c, wx):
    """Bottom line on one row: sunrise and sunset, then the next 12 hours."""
    bottom = c.h - c.m + 10
    top = bottom - FOOTER_WX
    mid = top + FOOTER_WX // 2 + 1
    f_time = font("semi", 15)
    f_hour = font("regular", 15)          # same size as the sunrise/sunset times
    f_temp = font("semi", 15)
    x = c.m
    sun = (wx or {}).get("sun") or (None, None)
    if sun[0]:
        for t, up in ((sun[0], True), (sun[1], False)):
            _sun_glyph(c.d, x + 11, mid, up)
            c.text((x + 38, mid), t.strftime("%H:%M"), f_time, anchor="lm")
            x += 38 + int(text_w(c.d, "00:00", f_time)) + 18
    slots = (wx or {}).get("slots") or []
    if not slots:
        c.text((c.w - c.m, mid), f"Updated {_now()}", font("regular", 13), anchor="rm")
        return
    hour_w = int(text_w(c.d, "00:00", f_hour))
    temp_w = int(text_w(c.d, "00°", f_temp))
    icon = 24
    pad_l, pad_r = 12, 9                # space either side of each icon
    cell = hour_w + pad_l + icon + pad_r + temp_w
    gap = 16
    room = c.w - c.m - x - 6
    fits = max(0, (room + gap) // (cell + gap))
    if fits < len(slots):
        slots = slots[1:]               # short of space: the next hours matter more than now
    n = min(len(slots), fits)
    x0 = c.w - c.m - n * cell - max(0, n - 1) * gap
    for i, sl in enumerate(slots[:n]):
        cx = x0 + i * (cell + gap)
        label = "Now" if sl is (wx or {}).get("slots", [None])[0] else sl["time"].strftime("%H:%M")
        c.text((cx + hour_w, mid), label, f_hour, anchor="rm")
        weather_icon(c.d, sl["kind"], sl["day"], cx + hour_w + pad_l + icon // 2, mid, icon)
        c.text((cx + hour_w + pad_l + icon + pad_r, mid), f"{round(sl['temp'])}°", f_temp, anchor="lm")


def _arrow(c, x0, x1, y, fill, head=14, thick=4):
    c.d.rectangle([x0, y - thick // 2, x1 - head + 2, y + thick // 2], fill=fill)
    c.d.polygon([(x1, y), (x1 - head, y - head * 0.7), (x1 - head, y + head * 0.7)], fill=fill)


ROW_H = 56


def _stats(c, y, cells, cols):
    """cells: list of (label, value). Laid out in a grid of `cols` columns."""
    usable = c.w - 2 * c.m
    col_w = usable / cols
    row_h = ROW_H
    for i, (label, value) in enumerate(cells):
        r, k = divmod(i, cols)
        x = c.m + k * col_w
        yy = y + r * row_h
        c.text((x, yy), label.upper(), font("bold", 12))
        fv = fit(c.d, value, "semi", 24, col_w - 14, 14)
        c.text((x, yy + 18), value, fv)
    rows = (len(cells) + cols - 1) // cols
    return y + rows * row_h


# ---------------------------------------------------------------- screens
def poster(f, cfg, nearby=0, logo=None, wx=None):
    c = Canvas(cfg.get("orientation", "landscape"))
    night = is_night(cfg, wx)
    units = cfg.get("units", "metric")
    accent = _accent(cfg, night)
    show_plane = cfg.get("show_plane", True)
    where = f"{fmt_dist(f.distance_km, units)} {compass(f.bearing)}".strip()
    head = _header(c, "OVERHEAD NOW", where, accent, dial=(f.bearing, cfg.get("facing", 0)))
    top = head + 18
    inner = c.w - 2 * c.m
    fn = f.flight_number
    airline = f.airline or f.operator or ""
    kind = plane.classify(f.type_code, f.category)

    # --- identity block: flight number + airline, aircraft drawing beside or below
    if c.portrait:
        ff = fit(c.d, fn, "bold", 38, inner, 22)
        c.text((c.m, top), fn, ff, fill=accent, anchor="lt")
        y = top + ff.size + 10
        if airline:
            fa = fit(c.d, airline, "semi", 21, inner, 14)
            c.text((c.m, y), ellipsize(c.d, airline, fa, inner), fa, anchor="lt")
            y += 32
        if show_plane:
            img = plane.draw(kind, inner, 116, logo=logo, accent=accent)
            c.paste_plane(img, (c.m + (inner - img.width) // 2, y + 8))
            y += img.height + 30
        else:
            y += 20
    else:
        plane_w = 380 if show_plane else 0
        text_w_max = inner - plane_w - 24
        ff = fit(c.d, fn, "bold", 38, text_w_max, 22)
        c.text((c.m, top + 6), fn, ff, fill=accent, anchor="lt")
        ty = top + 6 + ff.size + 12
        if airline:
            fa = fit(c.d, airline, "semi", 21, text_w_max, 14)
            for line in _wrap(c.d, airline, fa, text_w_max)[:2]:
                c.text((c.m, ty), line, fa, anchor="lt")
                ty += fa.size + 6
        block_h = 100 if show_plane else 0
        if show_plane:
            img = plane.draw(kind, plane_w, block_h, logo=logo, accent=accent)
            c.paste_plane(img, (c.w - c.m - img.width + 4, top + (block_h - img.height) // 2))
        y = max(ty, top + block_h) + 28

    rows = 2 if c.portrait else 1
    stats_top = c.h - c.m + 10 - FOOTER_WX - rows * ROW_H - 14

    content_end = y
    c.sky = (c.m, head + 4, c.w - c.m, y - 10)
    # --- route
    if f.has_route:
        o, d = f.origin, f.destination
        if c.portrait:
            fc = font("semi", 20)
            # two codes, two cities and the arrow must fit above the figures
            cap_room = (stats_top - 22 - y - 2 * (12 + fc.size + 16) - 28) / 2
            size = 76
            while size > 40 and font("bold", size).getbbox("A")[3] > cap_room:
                size -= 4
            big = min((fit(c.d, ap["iata"], "bold", size, inner, 40) for ap in (o, d)),
                      key=lambda f_: f_.size)
            ah = big.getbbox("A")[3]
            for i, ap in enumerate((o, d)):
                c.text((c.m - 3, y), ap["iata"], big, anchor="lt")
                cy = y + ah - 3
                fc_ = fit(c.d, ap["city"], "semi", 20, inner, 14)
                c.text((c.m, cy), ellipsize(c.d, ap["city"], fc_, inner), fc_, anchor="lt")
                content_end = cy + fc_.getbbox("L")[3]
                y = cy + fc.size + 16
                if i == 0:
                    _arrow(c, c.m, c.m + 70, y + 6, accent, head=14, thick=4)
                    y += 28
        else:
            arrow_w = 100
            code_w = (inner - arrow_w) / 2
            fc = font("semi", 19)
            cap_room = stats_top - 24 - y - (14 + fc.size)
            size = 80
            while size > 48 and font("bold", size).getbbox("A")[3] > cap_room:
                size -= 4
            big = min((fit(c.d, ap["iata"], "bold", size, code_w, 48) for ap in (o, d)),
                      key=lambda f_: f_.size)
            c.text((c.m - 4, y), o["iata"], big, anchor="lt")
            c.text((c.w - c.m, y), d["iata"], big, anchor="rt")
            ah = big.getbbox("A")[3]
            _arrow(c, c.m + code_w + 22, c.m + code_w + arrow_w - 22, y + ah * 0.55,
                   accent, head=14, thick=4)
            cy = y + ah - 3                       # half the old gap below the codes
            c.text((c.m, cy), ellipsize(c.d, o["city"], fc, code_w), fc, anchor="lt")
            c.text((c.w - c.m, cy), ellipsize(c.d, d["city"], fc, code_w), fc, anchor="rt")
            content_end = cy + fc.getbbox("L")[3]
    else:
        name = f.type_name or f.type_code or "Aircraft"
        room = stats_top - 22 - y
        size = 46 if not c.portrait else 38
        while size > 22 and font("bold", size).getbbox("Ag")[3] > room:
            size -= 2
        fb = fit(c.d, name, "bold", size, inner, 22)
        c.text((c.m - 2, y), ellipsize(c.d, name, fb, inner), fb, anchor="lt")
        content_end = y + fb.getbbox("L")[3]

    # --- figures
    # figures follow the route with a 17px gap (half the old spacing); never past the bottom limit
    y = min(content_end + 12 - font("bold", 12).getbbox("A")[1], stats_top)
    ph = phase(f)
    cells = [
        ("Altitude" + ("" if ph == "level" else f" · {ph}"), fmt_alt(f.altitude_ft, units)),
        ("Speed", fmt_speed(f.speed_kt, units)),
        ("Aircraft", f.type_code or "–"),
        ("Registration", f.registration or "–"),
    ]
    if c.portrait and f.has_route and f.type_name:
        cells[2] = ("Aircraft", f.type_name)
    _stats(c, y, cells, 2 if c.portrait else 4)

    _footer_wx(c, wx)
    return finish(c, cfg, wx, night)


def quiet(cfg, last=None, wx=None):
    c = Canvas(cfg.get("orientation", "landscape"))
    night = is_night(cfg, wx)
    accent = _accent(cfg, night)
    units = cfg.get("units", "metric")
    head = _header(c, "THE SKY ABOVE", "", accent)
    y = head + 30
    big = font("bold", 120 if not c.portrait else 110)
    c.text((c.m - 4, y), "Quiet", big, anchor="lt")
    y += int(big.size * 1.0)
    c.text((c.m - 2, y), "skies", big, fill=accent, anchor="lt")
    y += int(big.size * 1.15)
    r = fmt_dist(float(cfg.get("radius_km") or 15), units)
    y = min(y, c.h - 150)
    c.text((c.m, y), f"Nothing within {r} right now.", font("semi", 22), anchor="lt")
    if last:
        c.text((c.m, y + 34), f"Last seen: {last}", font("regular", 20), anchor="lt")
    _footer_wx(c, wx)
    c.sky = (c.m, head + 4, c.w - c.m, c.h - c.m + 10 - FOOTER_WX - 8)
    return finish(c, cfg, wx, night)


def message(cfg, title, lines, qr_data=None, header="SETUP"):
    """Setup and status screens."""
    c = Canvas(cfg.get("orientation", "landscape"))
    night = is_night(cfg) if cfg.get("lat") is not None else False
    accent = _accent(cfg, night)
    y = _header(c, header, "", accent) + 36
    inner = c.w - 2 * c.m
    qr_size = 0
    qr_img = None
    if qr_data:
        qr_img = _qr(qr_data, 220 if not c.portrait else 260)
        qr_size = qr_img.size[0] if qr_img else 0
    text_w_max = inner - (qr_size + 30 if qr_img and not c.portrait else 0)
    ft = fit(c.d, title, "bold", 56, text_w_max, 28)
    c.text((c.m - 2, y), title, ft, anchor="lt")
    ty = y + ft.getbbox("Ag")[3] + 24
    fl = font("semi", 22)
    for line in lines:
        for chunk in _wrap(c.d, line, fl, text_w_max):
            c.text((c.m, ty), chunk, fl, anchor="lt")
            ty += 32
        ty += 6
    if qr_img:
        if c.portrait:
            c.img.paste(qr_img, (c.m, min(ty + 20, c.h - qr_size - 70)))
        else:
            c.img.paste(qr_img, (c.w - c.m - qr_size, y))
    _footer(c, cfg, "")
    if qr_img and night:
        # a QR code must stay dark on light to scan; give it a white surround
        c.keep.append((_framed(qr_img), (c.m - 8, min(ty + 12, c.h - qr_size - 78))
                       if c.portrait else (c.w - c.m - qr_size - 8, y - 8)))
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
def _route_text(f):
    if f.has_route:
        return f"{f.origin['iata']} → {f.destination['iata']}"
    return f.type_name or f.type_code or "Aircraft"


def _detail_line(f, units, number=True):
    bits = [f.airline or f.operator, f.flight_number if number else "",
            f.type_name if f.has_route else (f.registration or ""),
            fmt_alt(f.altitude_ft, units), fmt_speed(f.speed_kt, units)]
    return "  ·  ".join(b for b in bits if b and b != "–")


def duo(flights, cfg, nearby=2, logos=(None, None), wx=None):
    """Two aircraft overhead: both drawings in the sky, one line each below."""
    c = Canvas(cfg.get("orientation", "landscape"))
    night = is_night(cfg, wx)
    units = cfg.get("units", "metric")
    accent = _accent(cfg, night)
    facing = cfg.get("facing", 0)
    show_plane = cfg.get("show_plane", True)
    count = f"{nearby} overhead" if nearby > 2 else "Two overhead"
    head = _header(c, "OVERHEAD NOW", count, accent)
    inner = c.w - 2 * c.m
    y = head + 16
    f_num = font("bold", 15)

    def entry(i, f, y, w):
        """Number, route, distance and compass, then the details. Returns the bottom."""
        x = c.m
        c.text((x, y + 4), str(i + 1), f_num, fill=accent, anchor="lt")
        x += 24
        where = f"{fmt_dist(f.distance_km, units)} {compass(f.bearing)}"
        fw = font("semi", 16)
        where_w = text_w(c.d, where, fw) + 30
        fr = fit(c.d, _route_text(f), "bold", 34 if not c.portrait else 30, w - 24 - where_w, 20)
        c.text((x - 2, y), ellipsize(c.d, _route_text(f), fr, w - 24 - where_w), fr, anchor="lt")
        c.text((c.m + w, y + 4), where, fw, anchor="rt")
        compass_glyph(c.d, c.m + w - text_w(c.d, where, fw) - 16, y + 12, 10, f.bearing, facing, accent)
        ly = y + fr.getbbox("L")[3] + 12
        fd = font("regular", 16)
        line = _detail_line(f, units, number=not (show_plane and not c.portrait))
        c.text((x, ly), ellipsize(c.d, line, fd, w - 24), fd, anchor="lt")
        return ly + fd.getbbox("L")[3]

    if not c.portrait:
        if show_plane:
            pw = (inner - 40) // 2
            for i, f in enumerate(flights[:2]):
                img = plane.draw(plane.classify(f.type_code, f.category), pw, 84,
                                 logo=logos[i] if i < len(logos) else None, accent=accent)
                x0 = c.m + i * (pw + 40)
                c.paste_plane(img, (x0 + (pw - img.width) // 2, y + (84 - img.height) // 2))
                lab_y = y + 84 + 10
                c.text((x0 + (pw - img.width) // 2 + 4, lab_y), f"{i + 1}", f_num, fill=accent)
                c.text((x0 + (pw - img.width) // 2 + 22, lab_y), f.flight_number, f_num)
            sky_bottom = y + 84 + 10
            y += 84 + 44
        else:
            sky_bottom = y
            y += 10
        c.sky = (c.m, head + 4, c.w - c.m, sky_bottom)
        bottom = c.h - c.m + 10 - FOOTER_WX - 16
        gap = max(18, (bottom - y - 2 * 64) // 2)
        for i, f in enumerate(flights[:2]):
            y = entry(i, f, y, inner) + gap
    else:
        for i, f in enumerate(flights[:2]):
            if show_plane:
                img = plane.draw(plane.classify(f.type_code, f.category), inner, 92,
                                 logo=logos[i] if i < len(logos) else None, accent=accent)
                c.paste_plane(img, (c.m + (inner - img.width) // 2, y))
                y += img.height + 16
            y = entry(i, f, y, inner) + 40
        c.sky = (c.m, head + 4, c.w - c.m, head + 4) if show_plane else None
    _footer_wx(c, wx)
    return finish(c, cfg, wx, night, decorate=not c.portrait)


# ---------------------------------------------------------------- radar
def radar(contacts, cfg, wx=None, highlight=None):
    """Everything within the radar range, turned so the top is the way the frame faces."""
    c = Canvas(cfg.get("orientation", "landscape"))
    night = is_night(cfg, wx)
    units = cfg.get("units", "metric")
    accent = _accent(cfg, night)
    facing = float(cfg.get("facing", 0) or 0)
    rng = float(cfg.get("radar_km") or 40)
    n = len(contacts)
    head = _header(c, "RADAR", f"{n} aircraft within {fmt_dist(rng, units)}", accent)
    foot_top = c.h - c.m + 10 - FOOTER_WX
    if c.portrait:
        r = (c.w - 2 * c.m) // 2 - 6
        cx, cy = c.w // 2, head + 34 + r
        list_x, list_y, list_w = c.m, cy + r + 34, c.w - 2 * c.m
        rows = max(0, min(5, (foot_top - 16 - list_y - 24) // 50))
    else:
        r = (foot_top - head - 46) // 2
        cx, cy = c.m + r + 8, head + 28 + r
        list_x = cx + r + 48
        list_y, list_w, rows = head + 22, c.w - c.m - list_x, 6
    d = c.d
    # rings, cross and range labels
    for frac in (0.5, 1.0):
        rr = r * frac
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=BLACK, width=1 if frac < 1 else 2)
    d.line([cx - r, cy, cx + r, cy], fill=BLACK, width=1)
    d.line([cx, cy - r, cx, cy + r], fill=BLACK, width=1)
    fl = font("regular", 11)
    c.text((cx + 4, cy - r / 2 - 2), fmt_dist(rng / 2, units), fl, anchor="ld")
    # north marker outside the ring
    na = math.radians(-facing)
    nx, ny = cx + math.sin(na) * (r + 13), cy - math.cos(na) * (r + 13)
    c.text((nx, ny), "N", font("bold", 13), fill=accent, anchor="mm")
    # home
    d.polygon([(cx, cy - 7), (cx - 6, cy - 1), (cx + 6, cy - 1)], fill=BLACK)
    d.rectangle([cx - 4, cy - 1, cx + 4, cy + 5], fill=BLACK)

    def pos(f):
        a = math.radians(f.bearing - facing)
        k = min(1.0, f.distance_km / rng) * r
        return cx + math.sin(a) * k, cy - math.cos(a) * k

    labels = []
    f_cs, f_alt = font("bold", 13), font("regular", 11)
    hl = highlight.hex if highlight else (contacts[0].hex if contacts else None)
    for f in reversed(contacts):                       # nearest drawn last, on top
        x, y = pos(f)
        if f.track is not None:
            a = math.radians(f.track - facing)
            d.line([x, y, x + math.sin(a) * 13, y - math.cos(a) * 13], fill=BLACK, width=2)
        rad = 6 if f.hex == hl else 4
        d.ellipse([x - rad, y - rad, x + rad, y + rad], fill=accent, outline=BLACK, width=1)
    for f in contacts[:10]:                             # label the nearest ten if there's room
        x, y = pos(f)
        name = f.callsign or f.registration or f.hex.upper()
        alt = fmt_alt(f.altitude_ft, units)
        tw = max(text_w(d, name, f_cs), text_w(d, alt, f_alt))
        for dx, dy, anc in ((9, -12, "l"), (-9, -12, "r"), (9, 2, "l"), (-9, 2, "r")):
            x0 = x + dx if anc == "l" else x + dx - tw
            box = (x0 - 2, y + dy - 2, x0 + tw + 2, y + dy + 28)
            inside = math.hypot(max(abs(box[0] - cx), abs(box[2] - cx)),
                                max(abs(box[1] - cy), abs(box[3] - cy))) < r + 40
            if inside and box[0] > 4 and box[2] < (list_x - 20 if not c.portrait else c.w - 4) \
                    and not any(_overlap(box, b) for b in labels):
                labels.append(box)
                c.text((x0, y + dy), name, f_cs)
                c.text((x0, y + dy + 15), alt, f_alt)
                break
    # nearest list
    c.text((list_x, list_y), "NEAREST", font("bold", 12))
    yy = list_y + 24
    for f in contacts[:rows]:
        name = f.flight_number if f.callsign else (f.registration or f.hex.upper())
        where = f"{fmt_dist(f.distance_km, units)} {compass(f.bearing)}"
        c.text((list_x, yy), name, font("semi", 18), fill=accent if f.hex == hl else BLACK)
        fs = font("regular", 14)
        c.text((list_x + list_w, yy + 2), where, fs, anchor="ra")
        sub = "  ·  ".join(b for b in (f.type_code, fmt_alt(f.altitude_ft, units)) if b and b != "–")
        c.text((list_x, yy + 24), sub, fs)
        yy += 50
    if not contacts:
        c.text((list_x, yy), "Nothing on radar.", font("semi", 18))
    _footer_wx(c, wx)
    return finish(c, cfg, wx, night, decorate=False)


def _overlap(a, b):
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])
