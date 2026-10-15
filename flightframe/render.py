"""Draw the screens for a 6-colour (Spectra 6) E Ink panel.

Everything is drawn with the panel's exact colours and with anti-aliasing
off, so nothing needs dithering and text stays crisp on paper.
"""
import glob
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
ACCENTS = {"red": RED, "blue": BLUE, "green": GREEN, "yellow": YELLOW}

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
    c.text((c.m, y), left, font("bold", 16), fill=accent)
    if right:
        c.text((c.w - c.m, y), right, font("semi", 16), anchor="ra")
    c.rule(y + 30)
    return y + 30


def _footer(c, cfg, extra=""):
    y = c.h - c.m + 4
    c.rule(y - 22, thick=1)
    label = cfg.get("label") or ""
    c.text((c.m, y), label, font("regular", 15), anchor="ls")
    right = f"{extra}  ·  {_now()}" if extra else f"Updated {_now()}"
    c.text((c.w - c.m, y), right, font("regular", 15), anchor="rs")


def _arrow(c, x0, x1, y, fill, head=14, thick=4):
    c.d.rectangle([x0, y - thick // 2, x1 - head + 2, y + thick // 2], fill=fill)
    c.d.polygon([(x1, y), (x1 - head, y - head * 0.7), (x1 - head, y + head * 0.7)], fill=fill)


def _stats(c, y, cells, cols):
    """cells: list of (label, value). Laid out in a grid of `cols` columns."""
    usable = c.w - 2 * c.m
    col_w = usable / cols
    row_h = 66
    for i, (label, value) in enumerate(cells):
        r, k = divmod(i, cols)
        x = c.m + k * col_w
        yy = y + r * row_h
        c.text((x, yy), label.upper(), font("bold", 13))
        fv = fit(c.d, value, "semi", 28, col_w - 14, 16)
        c.text((x, yy + 20), value, fv)
    rows = (len(cells) + cols - 1) // cols
    return y + rows * row_h


# ---------------------------------------------------------------- screens
def poster(f, cfg, nearby=0, logo=None):
    c = Canvas(cfg.get("orientation", "landscape"))
    units = cfg.get("units", "metric")
    accent = ACCENTS.get(cfg.get("accent"), RED)
    show_plane = cfg.get("show_plane", True)
    where = f"{fmt_dist(f.distance_km, units)} {compass(f.bearing)}".strip()
    top = _header(c, "OVERHEAD NOW", where, accent) + 16
    inner = c.w - 2 * c.m
    fn = f.flight_number
    airline = f.airline or f.operator or ""
    kind = plane.classify(f.type_code, f.category)

    # --- identity block: flight number + airline, aircraft drawing beside or below
    if c.portrait:
        ff = fit(c.d, fn, "bold", 44, inner, 24)
        c.text((c.m, top), fn, ff, fill=accent, anchor="lt")
        y = top + ff.size + 10
        if airline:
            fa = fit(c.d, airline, "semi", 24, inner, 16)
            c.text((c.m, y), ellipsize(c.d, airline, fa, inner), fa, anchor="lt")
            y += 34
        if show_plane:
            img = plane.draw(kind, inner, 132, logo=logo, accent=accent)
            c.img.paste(img, (c.m + (inner - img.width) // 2, y + 6))
            y += img.height + 22
        else:
            y += 20
    else:
        plane_w = 400 if show_plane else 0
        text_w_max = inner - plane_w - 16
        ff = fit(c.d, fn, "bold", 44, text_w_max, 24)
        c.text((c.m, top + 6), fn, ff, fill=accent, anchor="lt")
        ty = top + 6 + ff.size + 12
        if airline:
            fa = fit(c.d, airline, "semi", 26, text_w_max, 16)
            for line in _wrap(c.d, airline, fa, text_w_max)[:2]:
                c.text((c.m, ty), line, fa, anchor="lt")
                ty += fa.size + 6
        block_h = 114 if show_plane else 0
        if show_plane:
            img = plane.draw(kind, plane_w, block_h, logo=logo, accent=accent)
            c.img.paste(img, (c.w - c.m - img.width + 4, top + (block_h - img.height) // 2))
        y = max(ty, top + block_h) + 8

    rows = 2 if c.portrait else 1
    stats_top = c.h - c.m - 26 - rows * 66 - 4

    # --- route
    if f.has_route:
        o, d = f.origin, f.destination
        if c.portrait:
            fc = font("semi", 24)
            # two codes, two cities and the arrow must fit above the figures
            cap_room = (stats_top - 14 - y - 2 * (12 + fc.size + 14) - 26) / 2
            size = 110
            while size > 40 and font("bold", size).getbbox("A")[3] > cap_room:
                size -= 4
            big = min((fit(c.d, ap["iata"], "bold", size, inner, 40) for ap in (o, d)),
                      key=lambda f_: f_.size)
            ah = big.getbbox("A")[3]
            for i, ap in enumerate((o, d)):
                c.text((c.m - 3, y), ap["iata"], big, anchor="lt")
                cy = y + ah + 12
                fc_ = fit(c.d, ap["city"], "semi", 24, inner, 14)
                c.text((c.m, cy), ellipsize(c.d, ap["city"], fc_, inner), fc_, anchor="lt")
                y = cy + fc.size + 14
                if i == 0:
                    _arrow(c, c.m, c.m + 80, y + 6, accent, head=16, thick=5)
                    y += 26
        else:
            arrow_w = 100
            code_w = (inner - arrow_w) / 2
            fc = font("semi", 22)
            cap_room = stats_top - 14 - y - (12 + fc.size + 10)
            size = 120
            while size > 48 and font("bold", size).getbbox("A")[3] > cap_room:
                size -= 4
            big = min((fit(c.d, ap["iata"], "bold", size, code_w, 48) for ap in (o, d)),
                      key=lambda f_: f_.size)
            c.text((c.m - 4, y), o["iata"], big, anchor="lt")
            c.text((c.w - c.m, y), d["iata"], big, anchor="rt")
            ah = big.getbbox("A")[3]
            _arrow(c, c.m + code_w + 18, c.m + code_w + arrow_w - 18, y + ah * 0.55,
                   accent, head=16, thick=5)
            cy = y + ah + 12
            c.text((c.m, cy), ellipsize(c.d, o["city"], fc, code_w), fc, anchor="lt")
            c.text((c.w - c.m, cy), ellipsize(c.d, d["city"], fc, code_w), fc, anchor="rt")
            y = cy + fc.size + 10
    else:
        name = f.type_name or f.type_code or "Aircraft"
        fb = fit(c.d, name, "bold", 56 if not c.portrait else 44, inner, 24)
        c.text((c.m - 2, y + 4), ellipsize(c.d, name, fb, inner), fb, anchor="lt")
        y += fb.getbbox("Ag")[3] + 18
        c.text((c.m, y), "Route not published", font("regular", 22), anchor="lt")
        y += 44

    # --- figures
    y = max(y + 4, stats_top)
    c.rule(y - 12, thick=1)
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

    extra = f"{nearby} aircraft nearby" if nearby > 1 else ""
    _footer(c, cfg, extra)
    return c.img


def quiet(cfg, last=None):
    c = Canvas(cfg.get("orientation", "landscape"))
    accent = ACCENTS.get(cfg.get("accent"), RED)
    units = cfg.get("units", "metric")
    y = _header(c, "THE SKY ABOVE", "", accent) + 30
    big = font("bold", 120 if not c.portrait else 110)
    c.text((c.m - 4, y), "Quiet", big, anchor="lt")
    y += int(big.size * 1.0)
    c.text((c.m - 2, y), "skies", big, fill=accent, anchor="lt")
    y += int(big.size * 1.15)
    r = fmt_dist(float(cfg.get("radius_km") or 15), units)
    y = min(y, c.h - 120)
    c.text((c.m, y), f"Nothing within {r} right now.", font("semi", 22), anchor="lt")
    if last:
        c.text((c.m, y + 34), f"Last seen: {last}", font("regular", 20), anchor="lt")
    _footer(c, cfg)
    return c.img


def message(cfg, title, lines, qr_data=None):
    """Setup and status screens."""
    c = Canvas(cfg.get("orientation", "landscape"))
    accent = ACCENTS.get(cfg.get("accent"), RED)
    y = _header(c, "SETUP", "", accent) + 36
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


def for_panel(img):
    """Panel is natively 800x480; turn portrait renders on their side."""
    if img.size == (PANEL_H, PANEL_W):
        return img.rotate(90, expand=True)
    return img
