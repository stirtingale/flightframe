"""Side-view line drawings of aircraft, with the airline's logo on the tail.

Each type is drawn from its own measurements (see airframes.py and
data/airframes.json). The logo is downloaded at run time (see logos.py) and
fitted inside the tail fin. With no logo, the fin is filled with the accent colour.

Shapes are drawn at 4x in greyscale, scaled down and thresholded, so the curves
are smooth but every pixel is still pure black or white for the E Ink panel.
"""
import math

from PIL import Image, ImageDraw

SS = 4                       # supersampling factor
WHITE, BLACK = 255, 0
PANEL = [(0, 0, 0), (255, 255, 255), (255, 255, 0), (255, 0, 0), (0, 0, 255), (0, 255, 0)]


# --------------------------------------------------------------- lookup
from . import airframes   # noqa: E402


def classify(type_code="", category=""):
    """The archive code to draw for this aircraft (exact type, close relative or category)."""
    return airframes.lookup(type_code, category)["code"]


def ops_for(kind):
    """Shapes for a type code (A20N, B38M...) or an old family name (narrow, heli...)."""
    return airframes.build(airframes.lookup(kind))


# --------------------------------------------------------------- drawing
def _bbox(ops):
    xs, ys = [], []
    for op in ops:
        pts = op[1]
        if op[0] in ("ellipse", "rrect", "prop", "rotor", "ring"):
            pts = [(pts[0], pts[1]), (pts[2], pts[3])]
        for x, y in pts:
            xs.append(x)
            ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def _fit_rect_in_poly(poly, aspect, inset):
    """Biggest axis-aligned rectangle of the given aspect (w/h) inside a convex polygon."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)

    def inside(px, py):
        sign = 0
        n = len(poly)
        for i in range(n):
            ax, ay = poly[i]
            bx, by = poly[(i + 1) % n]
            cr = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
            # distance from edge must exceed inset
            ln = math.hypot(bx - ax, by - ay) or 1
            d = cr / ln
            s = 1 if d > 0 else -1
            if abs(d) < inset:
                return False
            if sign == 0:
                sign = s
            elif s != sign:
                return False
        return True

    best = None
    hmax = y1 - y0
    for step in range(40):
        h = hmax * (1 - step / 40)
        w = h * aspect
        if w > x1 - x0:
            continue
        for gy in range(16):
            cy = y0 + h / 2 + (hmax - h) * gy / 15
            for gx in range(24):
                cx = x0 + w / 2 + (x1 - x0 - w) * gx / 23
                corners = [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2),
                           (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)]
                if all(inside(*c) for c in corners):
                    best = (cx - w / 2, cy - h / 2, w, h)
                    break
            if best:
                break
        if best:
            return best
    return None


def _quantise(img):
    pal = Image.new("P", (1, 1))
    flat = [v for c in PANEL for v in c]
    pal.putpalette(flat + [0, 0, 0] * (256 - len(PANEL)))
    return img.convert("RGB").quantize(palette=pal, dither=Image.Dither.NONE).convert("RGB")


def draw(kind, box_w, box_h, logo=None, accent=(255, 0, 0), stroke=2.2, face_right=True):
    """Return (RGB image, (w, h)) of the aircraft fitted inside box_w x box_h."""
    ops = ops_for(kind)
    bx0, by0, bx1, by1 = _bbox(ops)
    pad = stroke * 1.2
    scale = min((box_w - 2 * pad) / (bx1 - bx0), (box_h - 2 * pad) / (by1 - by0))
    w = int(math.ceil((bx1 - bx0) * scale + 2 * pad))
    h = int(math.ceil((by1 - by0) * scale + 2 * pad))

    def tx(p, k=1.0):
        x = (p[0] - bx0) * scale + pad
        if face_right:
            x = w - x
        return (x * k, ((p[1] - by0) * scale + pad) * k)

    big = Image.new("L", (w * SS, h * SS), WHITE)
    d = ImageDraw.Draw(big)
    sw = max(1, int(round(stroke * SS)))
    fin_px = None
    accent_px = []
    for op in ops:
        kind_ = op[0]
        if kind_ in ("poly", "fin", "cockpit"):
            pts = [tx(p, SS) for p in op[1]]
            fill = BLACK if kind_ == "cockpit" else WHITE
            d.polygon(pts, fill=fill, outline=BLACK, width=sw)
            if kind_ == "fin":
                fin_px = [tx(p) for p in op[1]]
        elif kind_ in ("ellipse", "rrect", "prop", "rotor", "ring"):
            (x0, y0), (x1, y1) = tx(op[1][:2], SS), tx(op[1][2:], SS)
            rect = [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]
            if kind_ == "ellipse":
                d.ellipse(rect, fill=WHITE, outline=BLACK, width=sw)
            elif kind_ == "ring":         # tail rotor disc: outline only, the fin shows through
                d.ellipse(rect, outline=BLACK, width=max(1, int(sw * 0.8)))
            elif kind_ == "rrect":
                d.rounded_rectangle(rect, radius=op[2] * scale * SS, fill=WHITE, outline=BLACK, width=sw)
            else:   # prop disc / rotor: a solid black blade line
                d.ellipse(rect, fill=BLACK)
        elif kind_ == "accentfill":
            accent_px.append([tx(p) for p in op[1]])
        elif kind_ == "skid":
            pts = [tx(p, SS) for p in op[1]]
            d.line(pts, fill=BLACK, width=int(sw * 1.3))

    mono = big.resize((w, h), Image.LANCZOS).point(lambda v: 255 if v > 150 else 0)
    out = Image.merge("RGB", (mono, mono, mono))
    for poly in accent_px:            # e.g. a balloon's envelope
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).polygon(poly, fill=255)
        m = Image.composite(mono, Image.new("L", (w, h), 0), m)
        out = Image.composite(Image.new("RGB", (w, h), accent), out, m)

    # Logo (or accent colour) inside the fin, above the fuselage line.
    if fin_px and not accent_px:
        visible = _fin_visible(fin_px, ops, tx)
        fin_mask = Image.new("L", (w, h), 0)
        if len(visible) >= 3:
            ImageDraw.Draw(fin_mask).polygon(visible, fill=255)
        # only fin pixels that are still white line-art interior
        interior = Image.composite(mono, Image.new("L", (w, h), 0), fin_mask)
        if logo is not None:
            lg = _trim(logo)
            rect = _fit_rect_in_poly(visible, lg.width / lg.height,
                                     inset=stroke * 1.2 + 0.5)
            if rect:
                x, y, rw, rh = rect
                lw, lh = max(1, int(rw)), max(1, int(rh))
                tile = _quantise(lg.resize((lw, lh), Image.LANCZOS))
                layer = out.copy()
                if _mostly_yellow(tile):
                    # a yellow mark vanishes on white paper; give it a dark fin
                    layer.paste((0, 0, 0), (0, 0, w, h))
                    ink = tile.convert("L").point(lambda v: 255 if v < 250 else 0)
                    layer.paste(tile, (int(round(x)), int(round(y))), ink)
                else:
                    layer.paste(tile, (int(round(x)), int(round(y))))
                out = Image.composite(layer, out, interior)
            else:
                logo = None
        if logo is None:
            fill = Image.new("RGB", (w, h), accent)
            shrink = interior.point(lambda v: 255 if v else 0)
            out = Image.composite(fill, out, shrink)
    return out


def _fin_visible(fin_px, ops, tx):
    """Fin polygon clipped to the part above the fuselage top line."""
    fus = next(op[1] for op in ops if op[0] == "poly")
    # top of the fuselage under the fin, in pixel space: smallest y over the fin's x range
    xs = [p[0] for p in fin_px]
    fus_px = [tx(p) for p in fus]
    under = [p[1] for p in fus_px if min(xs) <= p[0] <= max(xs)]
    cut = min(under) if under else max(p[1] for p in fin_px)
    return _clip_below(fin_px, cut)


def _clip_below(poly, y_cut):
    """Keep the part of the polygon with y <= y_cut (Sutherland-Hodgman, one edge)."""
    out = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        ain, bin_ = a[1] <= y_cut, b[1] <= y_cut
        if ain:
            out.append(a)
        if ain != bin_:
            t = (y_cut - a[1]) / (b[1] - a[1])
            out.append((a[0] + t * (b[0] - a[0]), y_cut))
    return out


def _mostly_yellow(tile):
    colours = [(n, c) for n, c in tile.getcolors(1 << 16) if c != (255, 255, 255)]
    ink = sum(n for n, _ in colours)
    yellow = sum(n for n, c in colours if c == (255, 255, 0))
    return ink > 0 and yellow / ink > 0.8


def _trim(logo):
    """Logo on white with surrounding whitespace removed."""
    im = logo.convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    rgb = bg.convert("RGB")
    diff = Image.eval(rgb.convert("L"), lambda v: 255 if v < 235 else 0)
    box = diff.getbbox()
    return rgb.crop(box) if box else rgb
