"""Draw the screens for a 6-colour (Spectra 6) E Ink panel.

Everything is drawn with the panel's exact colours and with anti-aliasing
off, so nothing needs dithering and text stays crisp on paper.
"""
import glob
import math
import os
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

from . import plane
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
        return f"{mi:.1f} mi" if mi < 10 else f"{mi:.0f} mi"
    return f"{km:.1f} km" if km < 10 else f"{km:.0f} km"


def phase(f):
    v = f.vertical_fpm
    if v is None or abs(v) < 400:
        return "level"
    return "climbing" if v > 0 else "descending"


def _now():
    return datetime.now().strftime("%H:%M")


# ---------------------------------------------------------------- pieces
def _header(c, left, right, accent):
    y = c.m - 6
    c.text((c.m, y), left, font("bold", 14), fill=accent)
    if right:
        c.text((c.w - c.m, y), right, font("semi", 14), anchor="ra")
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
            c.text((x + 30, mid), t.strftime("%H:%M"), f_time, anchor="lm")
            x += 30 + int(text_w(c.d, "00:00", f_time)) + 16
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
    units = cfg.get("units", "metric")
    accent = ACCENTS.get(cfg.get("accent"), GREEN)
    show_plane = cfg.get("show_plane", True)
    where = f"{fmt_dist(f.distance_km, units)} {compass(f.bearing)}".strip()
    top = _header(c, "OVERHEAD NOW", where, accent) + 18
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
            c.img.paste(img, (c.m + (inner - img.width) // 2, y + 8))
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
            c.img.paste(img, (c.w - c.m - img.width + 4, top + (block_h - img.height) // 2))
        y = max(ty, top + block_h) + 28

    rows = 2 if c.portrait else 1
    stats_top = c.h - c.m + 10 - FOOTER_WX - rows * ROW_H - 14

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
                cy = y + ah + 12
                fc_ = fit(c.d, ap["city"], "semi", 20, inner, 14)
                c.text((c.m, cy), ellipsize(c.d, ap["city"], fc_, inner), fc_, anchor="lt")
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
            cy = y + ah + 14
            c.text((c.m, cy), ellipsize(c.d, o["city"], fc, code_w), fc, anchor="lt")
            c.text((c.w - c.m, cy), ellipsize(c.d, d["city"], fc, code_w), fc, anchor="rt")
            y = cy + fc.size + 10
    else:
        name = f.type_name or f.type_code or "Aircraft"
        room = stats_top - 22 - y
        size = 46 if not c.portrait else 38
        while size > 22 and font("bold", size).getbbox("Ag")[3] > room:
            size -= 2
        fb = fit(c.d, name, "bold", size, inner, 22)
        nh = fb.getbbox("Ag")[3]
        ny = y + max(0, (room - nh) // 2) - 4
        c.text((c.m - 2, ny), ellipsize(c.d, name, fb, inner), fb, anchor="lt")
        y = ny + nh

    # --- figures
    y = max(y + 10, stats_top)
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
    return c.img


def quiet(cfg, last=None, wx=None):
    c = Canvas(cfg.get("orientation", "landscape"))
    accent = ACCENTS.get(cfg.get("accent"), GREEN)
    units = cfg.get("units", "metric")
    y = _header(c, "THE SKY ABOVE", "", accent) + 30
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
    return c.img


def message(cfg, title, lines, qr_data=None, header="SETUP"):
    """Setup and status screens."""
    c = Canvas(cfg.get("orientation", "landscape"))
    accent = ACCENTS.get(cfg.get("accent"), GREEN)
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
    return c.img


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
