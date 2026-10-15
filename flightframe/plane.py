"""Simple side-view line drawings of aircraft, with the airline's logo on the tail.

The drawings are generic shapes for each family (narrowbody, widebody, jumbo,
regional jet, turboprop, business jet, light aircraft, helicopter). Only the
logo is airline-specific: it's downloaded at run time (see logos.py) and fitted
inside the tail fin. With no logo, the fin is filled with the accent colour.

Shapes are drawn at 4x in greyscale, scaled down and thresholded, so the curves
are smooth but every pixel is still pure black or white for the E Ink panel.
"""
import math

from PIL import Image, ImageDraw

SS = 4                       # supersampling factor
WHITE, BLACK = 255, 0
PANEL = [(0, 0, 0), (255, 255, 255), (255, 255, 0), (255, 0, 0), (0, 0, 255), (0, 255, 0)]


# --------------------------------------------------------------- classify
_PREFIX = [
    ("a380", ["A388"]),
    ("jumbo", ["B74"]),
    ("quad", ["A34", "IL96", "B52", "K35", "E3", "C17"]),
    ("wide", ["A30", "A310", "A33", "A35", "B76", "B77", "B78", "MD11", "DC10", "L101"]),
    ("regional", ["CRJ", "E135", "E145", "E35L", "E45X", "F100", "F70", "B712", "MD8", "MD9", "DC9"]),
    ("turboprop", ["AT4", "AT7", "DH8", "SF34", "SB20", "D328", "F50", "JS41", "E120", "C130",
                   "A400", "AN2", "B190", "C295", "SW4"]),
    ("bizjet", ["C25", "C50", "C51", "C52", "C55", "C56", "C68", "C700", "C750", "CL30", "CL35",
                "CL60", "GLEX", "GL5T", "GL7T", "GLF", "G150", "G280", "LJ", "FA", "F2TH", "F900",
                "PC24", "E50P", "E55P", "E545", "E550", "H25", "HDJT", "BE40", "PRM1"]),
    ("heli", ["EC", "AS3", "AS5", "AS6", "A109", "A119", "A139", "A149", "A169", "A189", "B06",
              "B407", "B412", "B429", "R22", "R44", "R66", "H60", "S76", "S92", "NH90", "EH10",
              "MI8", "H160", "LYNX", "PUMA", "WILD"]),
    ("light", ["C15", "C17", "C18", "C20", "C21", "P28", "PA", "SR2", "DA4", "DA2", "DR40", "TB",
               "BE3", "AA5", "M20", "PC12", "RV", "TOBA", "GLID"]),
    ("narrow", ["A31", "A32", "A19N", "A20N", "A21N", "B73", "B37M", "B38M", "B39M", "B3XM",
                "B75", "BCS", "E17", "E19", "E29", "E75", "A22", "C919", "SU95"]),
]
_BY_CATEGORY = {"A1": "light", "A2": "bizjet", "A3": "narrow", "A4": "narrow",
                "A5": "wide", "A7": "heli", "B1": "light"}


def classify(type_code="", category=""):
    t = (type_code or "").upper()
    if t:
        for kind, prefixes in _PREFIX:
            if any(t.startswith(p) for p in prefixes):
                return kind
    return _BY_CATEGORY.get((category or "").upper(), "narrow")


# --------------------------------------------------------------- geometry helpers
def _bez(p0, p1, p2, n=10):
    out = []
    for i in range(n + 1):
        t = i / n
        a, b, c = (1 - t) ** 2, 2 * (1 - t) * t, t * t
        out.append((a * p0[0] + b * p1[0] + c * p2[0], a * p0[1] + b * p1[1] + c * p2[1]))
    return out


def _fuselage(r, nose=None, tail_top=86, tail_bottom=66, end_top=None, end_bot=None,
              hump=None, L=100.0):
    """Outline of a fuselage, nose at x=0 pointing left... we flip later so it faces right."""
    nose = nose or 1.7 * 2 * r
    end_top = -0.62 * r if end_top is None else end_top
    end_bot = -0.30 * r if end_bot is None else end_bot
    tip = (0, 0.22 * r)
    top = _bez(tip, (0.04 * nose, -0.98 * r), (nose, -r))
    if hump:   # (x_end, height) e.g. 747 upper deck
        hx, hh = hump
        top = _bez(tip, (0.02 * nose, -0.95 * r), (nose * 0.9, -r - hh * 0.55))
        top += _bez((nose * 0.9, -r - hh * 0.55), (nose * 1.6, -r - hh), (hx * 0.6, -r - hh), 6)[1:]
        top += _bez((hx * 0.6, -r - hh), (hx * 0.95, -r - hh), (hx * 1.15, -r), 8)[1:]
    top += [(tail_top, -r)]
    top += _bez((tail_top, -r), ((tail_top + L) / 2 + 2, -r * 0.92), (L, end_top), 6)[1:]
    bottom = _bez(tip, (0.02 * nose, r), (0.7 * nose, r))
    bottom += [(tail_bottom, r)]
    bottom += _bez((tail_bottom, r), ((tail_bottom + L) / 2 + 6, r * 0.6), (L, end_bot), 8)[1:]
    return top + list(reversed(bottom))


def _windows(x0, x1, y, step, rad, rows=1, row_gap=0):
    dots = []
    for k in range(rows):
        x = x0
        while x <= x1:
            dots.append(("ellipse", (x - rad, y + k * row_gap - rad, x + rad, y + k * row_gap + rad)))
            x += step
    return dots


def _cockpit(nose, r):
    n = nose
    return ("cockpit", [(0.36 * n, -0.36 * r), (0.52 * n, -0.70 * r),
                        (0.86 * n, -0.80 * r), (0.84 * n, -0.40 * r)])


def _engine(x, y, length, h):
    """Underwing turbofan seen from the side: nacelle, intake ring, exhaust cone."""
    return [
        ("poly", [(x + length * 0.15, y - h * 0.55), (x + length * 0.55, y - h * 0.62),
                  (x + length * 0.70, y - h * 0.62), (x + length * 0.60, y - h * 0.40)]),   # pylon
        ("rrect", (x, y - h / 2, x + length, y + h / 2), h * 0.42),
        ("ellipse", (x - h * 0.12, y - h / 2, x + h * 0.26, y + h / 2)),
        ("poly", [(x + length, y - h * 0.22), (x + length + h * 0.45, y), (x + length, y + h * 0.22)]),
    ]


def _fin(x0, base_y, r, h, sweep, tip_chord, end_x=99.2, end_y=None):
    end_y = -0.55 * r if end_y is None else end_y
    return [(x0, base_y), (x0 + sweep, -r - h), (x0 + sweep + tip_chord, -r - h), (end_x, end_y)]


def _hstab(x0, y, length=13, thick=1.4, end=99.6):
    return ("poly", [(x0, y), (x0 + length * 0.55, y - thick), (end, y - thick),
                     (end - 1.2, y + thick * 0.4)])


def _low_wing(x, r, chord, sweep, drop, tip):
    a = 0.42 * r
    return ("poly", [(x, a), (x + chord, a), (x + sweep + tip, a + drop), (x + sweep, a + drop)])


# --------------------------------------------------------------- the families
def _airliner(r, fin_h, engines, wing, eng_size, fin_x=70, windows_to=76, quad=False,
              hump=None, double=False, eng_x=33):
    nose = 3.4 * r
    fus = _fuselage(r, nose=nose, hump=hump)
    fin = _fin(fin_x, -0.2 * r, r, fin_h, sweep=17, tip_chord=7)
    ops = [("fin", fin), ("poly", fus)]
    ops += _windows(nose + 3, windows_to, -0.22 * r, 2.15, 0.17 * r)
    if double:
        ops += _windows(nose + 1, windows_to - 2, -0.62 * r, 2.15, 0.15 * r)
    if hump:
        ops += _windows(nose + 2, hump[0] - 4, -r - hump[1] * 0.45, 2.15, 0.15 * r)
    ops += [_cockpit(nose, r) if not hump else
            ("cockpit", [(0.40 * nose, -0.45 * r), (0.55 * nose, -0.86 * r),
                         (0.92 * nose, -r - hump[1] * 0.42), (0.88 * nose, -0.55 * r)])]
    ops += [_hstab(84, -0.15 * r, thick=0.95)]
    ops += [_low_wing(eng_x + 2, r, wing[0], wing[1], wing[2], wing[3])]
    el, eh = eng_size
    ey = 0.42 * r + eh * 0.62
    ops += _engine(eng_x - 2, ey, el, eh)
    if quad:
        ops = ops[:-4] + _engine(eng_x + 9, ey + wing[2] * 0.45, el * 0.92, eh * 0.92) + ops[-4:]
    return ops


def _regional(r, fin_h, bizjet=False):
    nose = 3.3 * r
    fus = _fuselage(r, nose=nose, tail_top=80, tail_bottom=62)
    fin = _fin(74, -0.4 * r, r, fin_h, sweep=16, tip_chord=8.5, end_x=97.5)
    tip_y = -r - fin_h
    ops = [("fin", fin), ("poly", fus)]
    if bizjet:
        ops += _windows(nose + 5, 56, -0.18 * r, 6.5, 0.26 * r)
    else:
        ops += _windows(nose + 3, 64, -0.2 * r, 2.4, 0.17 * r)
    ops += [_cockpit(nose, r)]
    ops += [_low_wing(36, r, 18, 15, 2.5 * r * 0.28, 7)]
    # rear-mounted engine, near side
    ex, ey, el, eh = 64, -0.85 * r, 15, 0.95 * r
    ops += [("poly", [(ex + 4, ey + eh * 0.3), (ex + 10, ey + eh * 0.3), (ex + 11, -0.1 * r), (ex + 5, -0.1 * r)])]
    ops += [("rrect", (ex, ey - eh / 2, ex + el, ey + eh / 2), eh * 0.45),
            ("ellipse", (ex - eh * 0.12, ey - eh / 2, ex + eh * 0.25, ey + eh / 2))]
    # T-tail
    ops += [("poly", [(74 + 16 - 2, tip_y + 0.8), (74 + 16 + 3, tip_y - 0.9),
                      (74 + 16 + 8.5 + 4.5, tip_y - 0.9), (74 + 16 + 8.5 + 3, tip_y + 0.9)])]
    return ops


def _turboprop(r):
    nose = 2.9 * r
    fus = _fuselage(r, nose=nose, tail_top=78, tail_bottom=60, end_top=-0.75 * r, end_bot=-0.45 * r)
    fin_h = 2.0 * r
    fin = [(62, -0.6 * r), (74, -r - 0.35 * r), (80, -r - fin_h), (88, -r - fin_h), (99, -0.7 * r)]
    ops = [("fin", fin), ("poly", fus)]
    ops += _windows(31, 60, -0.05 * r, 3.0, 0.2 * r)
    ops += [_cockpit(nose, r)]
    # high wing fairing and wing
    ops += [("poly", [(30, -r + 0.3), (33, -r - 0.55 * r), (52, -r - 0.55 * r), (58, -r + 0.3)])]
    # nacelle hanging under the wing, prop at the front
    ny, nh = -r + 0.12 * r, 0.8 * r
    ops += [("rrect", (27, ny - nh / 2, 49, ny + nh / 2), nh * 0.48)]
    ops += [("ellipse", (24.2, ny - nh * 0.32, 28.2, ny + nh * 0.32))]                  # spinner
    ops += [("prop", (25.2, ny - 1.25 * r, 26.6, ny + 1.25 * r))]
    # T-tail
    ops += [("poly", [(77, -r - fin_h + 0.6), (81, -r - fin_h - 0.8), (93, -r - fin_h - 0.8),
                      (91.5, -r - fin_h + 0.8)])]
    return ops


def _light(r):
    nose = 1.4 * r
    fus = _fuselage(r, nose=nose, tail_top=46, tail_bottom=38, end_top=-0.55 * r, end_bot=-0.22 * r)
    fin_h = 1.15 * r
    fin = [(72, -0.5 * r), (86, -r - fin_h * 0.25), (90, -r - fin_h), (97, -r - fin_h), (99.5, -0.3 * r)]
    ops = [("fin", fin), ("poly", fus)]
    # cabin glazing
    ops += [("cockpit", [(nose * 0.75, -0.25 * r), (nose * 1.2, -0.92 * r), (nose * 1.9, -0.95 * r),
                         (nose * 1.9, -0.22 * r)])]
    ops += [("cockpit", [(nose * 2.05, -0.95 * r), (nose * 3.0, -0.95 * r), (nose * 3.15, -0.25 * r),
                         (nose * 2.05, -0.22 * r)])]
    ops += [("poly", [(nose * 1.0, -r - 0.05), (nose * 1.2, -r - 0.32 * r), (nose * 3.4, -r - 0.32 * r),
                      (nose * 3.5, -r - 0.05)])]                                      # high wing
    ops += [("poly", [(nose * 1.6, -r * 0.8), (nose * 1.75, -r * 0.8), (nose * 2.5, r * 0.9),
                      (nose * 2.35, r * 0.9)])]                                       # strut
    ops += [_hstab(84, -0.35 * r, length=14, thick=1.6)]
    ops += [("ellipse", (-2.4, -0.25 * r, 1.4, 0.55 * r))]                            # spinner
    ops += [("prop", (-1.2, -1.15 * r, 0.4, 1.45 * r))]
    return ops


def _heli():
    r = 9.0
    ops = []
    # tail boom and fin
    ops += [("fin", [(84, -2.5), (88, -16), (95, -17), (97, -2.5)])]
    ops += [("poly", [(34, -6.5), (92, -3.2), (92, -0.6), (40, 3.5)])]
    # cabin
    cab = _bez((0, 2), (0.5, -r), (16, -r)) + [(30, -r), (38, -6.5)]
    cab += _bez((38, -6.5), (44, 0), (36, r * 0.75), 6)[1:] + [(8, r * 0.75)]
    cab += _bez((8, r * 0.75), (0.6, r * 0.7), (0, 2), 6)[1:]
    ops += [("poly", cab)]
    ops += [("cockpit", [(3, -1.2), (6.5, -7.2), (14, -7.6), (14.5, -1.0)])]
    ops += [("cockpit", [(17, -7.6), (26, -7.6), (26, -1.0), (17, -1.0)])]
    ops += [("poly", [(10, -r), (12, -r - 3.2), (32, -r - 3.2), (36, -6.8)])]          # engine cowl
    ops += [("rrect", (20.5, -r - 6.3, 22.5, -r - 3.0), 0.6)]                         # mast
    ops += [("rotor", (-6, -r - 7.5, 66, -r - 6.2))]                                  # main rotor
    ops += [("ellipse", (90, -13.5, 100, -3.5))]                                      # tail rotor
    ops += [("skid", [(6, r + 3.4), (36, r + 3.4)]), ("skid", [(12, r * 0.6), (12, r + 3.4)]),
            ("skid", [(29, r * 0.6), (29, r + 3.4)])]
    return ops


def ops_for(kind):
    if kind == "a380":
        return _airliner(6.4, 17.5, 4, (22, 18, 2.4, 8), (13, 6.2), quad=True, double=True, eng_x=30)
    if kind == "jumbo":
        return _airliner(5.4, 17, 4, (22, 18, 2.4, 8), (12, 5.4), quad=True, hump=(34, 3.6), eng_x=30)
    if kind == "quad":
        return _airliner(5.0, 15, 4, (21, 18, 2.2, 7), (11, 4.4), quad=True, eng_x=31)
    if kind == "wide":
        return _airliner(5.2, 16, 2, (21, 17, 2.4, 7), (13, 6.6), eng_x=31)
    if kind == "regional":
        return _regional(4.2, 12)
    if kind == "bizjet":
        return _regional(5.6, 13.5, bizjet=True)
    if kind == "turboprop":
        return _turboprop(5.0)
    if kind == "light":
        return _light(8.0)
    if kind == "heli":
        return _heli()
    return _airliner(5.4, 15, 2, (19, 15, 2.2, 6), (11, 5.2), eng_x=33)      # narrowbody


# --------------------------------------------------------------- drawing
def _bbox(ops):
    xs, ys = [], []
    for op in ops:
        pts = op[1]
        if op[0] in ("ellipse", "rrect", "prop", "rotor"):
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
    for op in ops:
        kind_ = op[0]
        if kind_ in ("poly", "fin", "cockpit"):
            pts = [tx(p, SS) for p in op[1]]
            fill = BLACK if kind_ == "cockpit" else WHITE
            d.polygon(pts, fill=fill, outline=BLACK, width=sw)
            if kind_ == "fin":
                fin_px = [tx(p) for p in op[1]]
        elif kind_ in ("ellipse", "rrect", "prop", "rotor"):
            (x0, y0), (x1, y1) = tx(op[1][:2], SS), tx(op[1][2:], SS)
            rect = [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]
            if kind_ == "ellipse":
                d.ellipse(rect, fill=WHITE, outline=BLACK, width=sw)
            elif kind_ == "rrect":
                d.rounded_rectangle(rect, radius=op[2] * scale * SS, fill=WHITE, outline=BLACK, width=sw)
            else:   # prop disc / rotor: a solid black blade line
                d.ellipse(rect, fill=BLACK)
        elif kind_ == "skid":
            pts = [tx(p, SS) for p in op[1]]
            d.line(pts, fill=BLACK, width=int(sw * 1.3))

    mono = big.resize((w, h), Image.LANCZOS).point(lambda v: 255 if v > 150 else 0)
    out = Image.merge("RGB", (mono, mono, mono))

    # Logo (or accent colour) inside the fin, above the fuselage line.
    if fin_px:
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
