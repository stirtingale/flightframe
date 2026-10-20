"""Aircraft drawings built from each type's own measurements.

Every type in data/airframes.json is described in metres: fuselage length and
height, fin, wing, engines, nose shape, winglets, tail layout and so on. The
builders below turn that into simple line-art shapes, so an A321neo looks
longer than an A319, a 737 MAX gets its split winglets, a 747 its hump and an
A380 two decks.

The file is refreshed from GitHub once a day (see refresh()), so new types can
be added to the archive without reinstalling. A copy ships with the app in
case GitHub can't be reached.

Coordinates: the fuselage runs from x=0 (nose) to x=100 (tail), y grows
downwards, centreline at y=0. plane.draw() scales, flips and renders.
"""
import copy
import json
import logging
import math
import os
import threading
import time

log = logging.getLogger(__name__)

BUNDLED = os.path.join(os.path.dirname(__file__), "data", "airframes.json")
REMOTE = "https://raw.githubusercontent.com/stirtingale/flightframe/main/flightframe/data/airframes.json"
REFRESH_EVERY = 24 * 3600

_lock = threading.Lock()
_specs = None          # resolved type code -> spec
_meta = {}
_last_try = 0.0


# ===================================================================== data
def _resolve(types):
    """Apply 'like' inheritance. Unknown parents or loops are skipped."""
    out = {}

    def get(code, seen=()):
        if code in out:
            return out[code]
        raw = types.get(code)
        if raw is None or code in seen:
            return None
        spec = {}
        if raw.get("like"):
            parent = get(raw["like"], seen + (code,))
            if parent is None:
                return None
            spec = copy.deepcopy(parent)
        spec.update({k: v for k, v in raw.items() if k != "like"})
        spec["code"] = code
        out[code] = spec
        return spec

    for code in types:
        get(code)
    return out


def _load_file(path):
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("types"), dict):
        raise ValueError("not an airframes file")
    return data


def _validate(specs):
    """Keep only types that actually build; a bad entry must never break the frame."""
    good = {}
    for code, spec in specs.items():
        try:
            ops = build(spec)
            if len(ops) < 2:
                raise ValueError("empty")
            good[code] = spec
        except Exception as e:
            log.warning("airframe %s skipped: %s", code, e)
    return good


def specs():
    global _specs, _meta
    with _lock:
        if _specs is None:
            data = _load_file(BUNDLED)
            cached = _cache_path()
            try:
                if os.path.exists(cached):
                    remote = _load_file(cached)
                    if remote.get("version", 0) >= data.get("version", 0):
                        merged = dict(data["types"])
                        merged.update(remote["types"])
                        data = dict(remote, types=merged)
            except Exception as e:
                log.warning("cached airframes ignored: %s", e)
            _specs = _validate(_resolve(data["types"]))
            _meta = {k: v for k, v in data.items() if k != "types"}
        return _specs


def _cache_path():
    from .config import STATE_DIR
    return os.path.join(STATE_DIR, "airframes.json")


def refresh(session=None, force=False):
    """Fetch the latest archive from GitHub at most once a day. Never raises."""
    global _specs, _last_try
    path = _cache_path()
    if not force and time.time() - _last_try < 3600:      # at most one attempt an hour
        return False
    _last_try = time.time()
    try:
        if not force and os.path.exists(path) and time.time() - os.path.getmtime(path) < REFRESH_EVERY:
            return False
        import requests
        s = session or requests
        r = s.get(REMOTE, timeout=15)
        if r.status_code != 200:
            return False
        data = json.loads(r.text)
        if not isinstance(data.get("types"), dict) or len(data["types"]) < 20:
            return False
        good = _validate(_resolve(data["types"]))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, path)
        with _lock:
            _specs = None           # reload on next use
        log.info("airframes updated: %d types", len(good))
        return True
    except Exception as e:
        log.info("airframes refresh failed: %s", e)
        try:
            os.utime(path) if os.path.exists(path) else None   # don't retry every poll
        except OSError:
            pass
        return False


# ===================================================================== lookup
_FAMILY_FALLBACK = {   # broadcast category -> a representative type
    "A1": "C172", "A2": "C68A", "A3": "A320", "A4": "B752", "A5": "B789",
    "A6": "EUFI", "A7": "EC35", "B1": "GLID", "B2": "BALL", "B4": "C172",
}
_FAMILY_NAMES = {  # older family names used by tools and tests
    "narrow": "A320", "wide": "A332", "jumbo": "B744", "a380": "A388", "quad": "A343",
    "regional": "CRJ9", "turboprop": "AT76", "bizjet": "C68A", "light": "C172", "heli": "EC35",
}


def lookup(type_code="", category=""):
    """The spec for a type code, else one for its category, else an A320."""
    sp = specs()
    t = (type_code or "").upper().strip()
    if t in sp:
        return sp[t]
    if t in _FAMILY_NAMES:
        return sp[_FAMILY_NAMES[t]]
    # close relatives (B739ER -> B739): the code sharing the longest prefix, at least 3 characters
    best, best_n = None, 2
    for code in sp:
        n = 0
        while n < min(len(code), len(t)) and code[n] == t[n]:
            n += 1
        if n > best_n:
            best, best_n = code, n
    if best:
        return sp[best]
    cat = (category or "").upper()
    return sp.get(_FAMILY_FALLBACK.get(cat, "A320"), sp["A320"])


# ===================================================================== geometry helpers
def _bez(p0, p1, p2, n=10):
    out = []
    for i in range(n + 1):
        t = i / n
        a, b, c = (1 - t) ** 2, 2 * (1 - t) * t, t * t
        out.append((a * p0[0] + b * p1[0] + c * p2[0], a * p0[1] + b * p1[1] + c * p2[1]))
    return out


def _windows(x0, x1, y, step, rad, oval=False):
    out = []
    x = x0
    while x <= x1:
        if oval:
            out.append(("ellipse", (x - rad * 1.25, y - rad, x + rad * 1.25, y + rad)))
        else:
            out.append(("ellipse", (x - rad, y - rad, x + rad, y + rad)))
        x += step
    return out


_NOSES = {          # (nose length in fuselage heights, tip height as fraction of r, cockpit style)
    "airbus": (1.65, 0.20, "airbus"), "a220": (1.75, 0.22, "airbus"),
    "a350": (2.05, 0.16, "mask"), "a380": (1.30, 0.32, "airbus"),
    "boeing": (1.85, 0.26, "boeing"), "b737": (1.75, 0.34, "boeing"),
    "b757": (1.95, 0.34, "boeing"), "b787": (2.15, 0.14, "mask"),
    "b747": (1.55, 0.36, "boeing"), "embraer": (1.85, 0.24, "boeing"),
    "crj": (2.30, 0.28, "boeing"), "bizjet": (2.45, 0.14, "boeing"),
    "dc9": (2.00, 0.30, "boeing"), "military": (1.55, 0.30, "boeing"),
}


def _fuselage(r, nose_len, tip, tail_bot, tail_top, end_top, end_bot, hump=None, blunt=False):
    tip_pt = (0, tip * r)
    c1 = (0.03 * nose_len, -0.96 * r) if not blunt else (0.0, -0.80 * r)
    if hump:
        hx, hh = hump
        top = _bez(tip_pt, (0.02 * nose_len, -0.92 * r), (nose_len * 0.85, -r - hh * 0.62))
        top += _bez((nose_len * 0.85, -r - hh * 0.62), (nose_len * 1.5, -r - hh), (hx * 0.62, -r - hh), 6)[1:]
        top += _bez((hx * 0.62, -r - hh), (hx * 0.93, -r - hh), (hx * 1.1, -r), 8)[1:]
    else:
        top = _bez(tip_pt, c1, (nose_len, -r))
    top += [(tail_top, -r)]
    top += _bez((tail_top, -r), ((tail_top + 100) / 2 + 2, -r * 0.93), (100, end_top), 6)[1:]
    c2 = (0.02 * nose_len, r) if not blunt else (0.0, 0.85 * r)
    bottom = _bez(tip_pt, c2, (0.7 * nose_len, r))
    bottom += [(tail_bot, r)]
    bottom += _bez((tail_bot, r), ((tail_bot + 100) / 2 + 5, r * 0.55), (100, end_bot), 8)[1:]
    return top + list(reversed(bottom))


def _cockpit(nose_len, r, style, y_top=None):
    n = nose_len
    if style == "mask":       # 787 / A350 swept windscreen
        return ("cockpit", [(0.40 * n, -0.30 * r), (0.62 * n, -0.70 * r),
                            (0.95 * n, -0.78 * r), (0.90 * n, -0.46 * r)])
    if style == "airbus":
        return ("cockpit", [(0.34 * n, -0.38 * r), (0.50 * n, -0.70 * r),
                            (0.84 * n, -0.80 * r), (0.82 * n, -0.42 * r)])
    top = y_top if y_top is not None else -0.82 * r
    return ("cockpit", [(0.38 * n, -0.34 * r), (0.55 * n, -0.70 * r),
                        (0.88 * n, top), (0.86 * n, -0.40 * r)])


def _nacelle(x, y, length, h, style="round", pylon_to=None):
    ops = []
    if pylon_to is not None:
        ops.append(("poly", [(x + length * 0.20, y - h * 0.45), (x + length * 0.50, pylon_to),
                             (x + length * 0.78, pylon_to), (x + length * 0.62, y - h * 0.35)]))
    if style == "flat":       # 737 'hamster pouch': flattened underside
        ops.append(("poly", [(x, y - h / 2), (x + length * 0.85, y - h * 0.42), (x + length, y - h * 0.18),
                             (x + length, y + h * 0.20), (x + length * 0.8, y + h * 0.36),
                             (x + h * 0.15, y + h * 0.36), (x, y + h * 0.10)]))
        ops.append(("ellipse", (x - h * 0.10, y - h / 2, x + h * 0.22, y + h * 0.30)))
    else:
        ops.append(("rrect", (x, y - h / 2, x + length, y + h / 2), h * 0.42))
        ops.append(("ellipse", (x - h * 0.10, y - h / 2, x + h * 0.26, y + h / 2)))
        if style == "chevron":
            xe = x + length
            pts = [(xe - h * 0.05, y - h * 0.46)]
            n = 5
            for i in range(n + 1):
                yy = y - h * 0.46 + (h * 0.92) * i / n
                pts.append((xe + (h * 0.18 if i % 2 else 0), yy))
            pts.append((xe - h * 0.05, y + h * 0.46))
            ops.append(("poly", pts))
    ops.append(("poly", [(x + length, y - h * 0.20), (x + length + h * 0.45, y), (x + length, y + h * 0.20)]))
    return ops


def _winglet(style, tx, ty, chord, s):
    """A winglet rising from the wing tip, whose chord runs tx..tx+chord at height ty."""
    if style in (None, "none", "raked"):
        return []
    h = {"fence": 1.2, "sharklet": 2.4, "blended": 2.5, "split": 2.4, "a330": 2.7,
         "a350": 3.2, "a380": 2.4, "small": 1.3}.get(style, 2.0) * s
    te = tx + chord
    if style == "fence":
        return [("poly", [(tx + chord * 0.15, ty), (te + chord * 0.05, ty - h), (te + chord * 0.40, ty - h),
                          (te + chord * 0.15, ty)]),
                ("poly", [(tx + chord * 0.25, ty), (te + chord * 0.05, ty + h * 0.75),
                          (te + chord * 0.35, ty + h * 0.75), (te + chord * 0.15, ty)])]
    if style in ("blended", "a330", "small"):      # straighter, upright
        up = [(tx, ty), (tx + chord * 0.30, ty - h * 0.30), (tx + chord * 0.55, ty - h),
              (te + chord * 0.10, ty - h), (te, ty - h * 0.15), (te, ty)]
    else:                                          # sharklet / split / a350: curved, raked back
        up = [(tx, ty), (tx + chord * 0.20, ty - h * 0.25), (tx + chord * 0.70, ty - h * 0.80),
              (te + chord * 0.25, ty - h), (te + chord * 0.50, ty - h), (te + chord * 0.10, ty - h * 0.25),
              (te, ty)]
    ops = [("poly", up)]
    if style == "split":
        ops.append(("poly", [(tx + chord * 0.35, ty), (te + chord * 0.15, ty + h * 0.5),
                             (te + chord * 0.40, ty + h * 0.5), (te + chord * 0.05, ty)]))
    return ops


# ===================================================================== builders
def build(spec):
    fam = spec.get("family", "jet")
    fn = {"jet": _jet, "turboprop": _turboprop, "light": _light, "heli": _heli,
          "tandem": _tandem, "fighter": _fighter, "balloon": _balloon, "glider": _glider}.get(fam)
    if fn is None:
        raise ValueError(f"unknown family {fam}")
    return fn(spec)


def _jet(sp):
    L = float(sp["length"])
    s = 100.0 / L
    D = float(sp.get("diameter", L * 0.1)) * s
    r = D / 2
    nose_kind = sp.get("nose", "airbus")
    nk, tip, ck = _NOSES.get(nose_kind, _NOSES["airbus"])
    nose_len = nk * D
    up = float(sp.get("upsweep", 2.4)) * D
    tail_bot, tail_top = 100 - up, 100 - 1.0 * D
    hump = None
    if sp.get("hump"):
        hump = (float(sp["hump"][0]) * 100, float(sp["hump"][1]) * s)
    fus = _fuselage(r, nose_len, tip, tail_bot, tail_top, -0.62 * r, -0.28 * r,
                    hump=hump, blunt=(nose_kind == "a380"))

    # fin
    fin_h = float(sp.get("fin", L * 0.16)) * s
    fin_c = float(sp.get("fin_chord", L * 0.16)) * s
    fin_sw = math.tan(math.radians(float(sp.get("fin_sweep", 38)))) * fin_h
    fin_te = 99.0
    fin_le = fin_te - fin_c
    tip_c = fin_c * float(sp.get("fin_taper", 0.38))
    fin = [(fin_le, -0.25 * r)]
    if sp.get("dorsal"):
        fin = [(fin_le - float(sp["dorsal"]) * s, -0.9 * r), (fin_le, -r - 0.10 * fin_h)]
    fin += [(fin_le + fin_sw, -r - fin_h), (fin_le + fin_sw + tip_c, -r - fin_h), (fin_te, -0.55 * r)]

    ops = [("fin", fin), ("poly", fus)]

    # windows
    win_end = min(fin_le - 1.5, tail_bot + up * 0.15)
    if sp.get("oval_windows"):
        step = float(sp.get("window_pitch", 1.4)) * s
        ops += _windows(nose_len + 0.8 * D, win_end - 0.15 * (win_end - nose_len), -0.10 * r, step, 0.24 * r, oval=True)
    else:
        step = max(1.9, min(3.0, 0.62 * s)) if L > 22 else 2.6
        rad = min(0.17 * r, 0.75)
        ops += _windows(nose_len + 0.55 * D, win_end, -0.22 * r, step, rad)
        if int(sp.get("decks", 1)) == 2:
            ops += _windows(nose_len + 0.4 * D, win_end - 2, -0.64 * r, step, rad * 0.9)
    if hump:
        ops += _windows(nose_len + 0.3 * D, hump[0] * 0.9, -r - hump[1] * 0.45, max(1.9, 0.62 * s), min(0.15 * r, 0.7))
    ops.append(_cockpit(nose_len, r, ck, y_top=(-r - hump[1] * 0.35) if hump else None))

    tail = sp.get("tail", "low")
    hs_c = float(sp.get("hstab_chord", fin_c * 0.75 / s)) * s
    if tail == "t":
        ty = -r - fin_h
        x0 = fin_le + fin_sw - hs_c * 0.25
        ops.append(("poly", [(x0, ty + 0.7), (x0 + hs_c * 0.45, ty - 0.8), (x0 + hs_c * 1.25, ty - 0.8),
                             (x0 + hs_c * 1.15, ty + 0.8)]))
    elif tail == "cruciform":
        ty = -r - fin_h * 0.45
        x0 = fin_le + fin_sw * 0.45 - hs_c * 0.2
        ops.append(("poly", [(x0, ty + 0.6), (x0 + hs_c * 0.45, ty - 0.7), (x0 + hs_c * 1.2, ty - 0.7),
                             (x0 + hs_c * 1.1, ty + 0.7)]))
    else:
        x0 = 99.6 - hs_c * 1.35
        ops.append(("poly", [(x0, -0.12 * r), (x0 + hs_c * 0.55, -0.12 * r - 1.0), (99.6, -0.12 * r - 1.0),
                             (99.6 - 1.2, -0.12 * r + 0.4)]))

    # centre engine at the tail (Falcon 7X/900, MD-11, 727)
    if sp.get("tail_engine"):
        ex = fin_le - 5
        ops += [("rrect", (ex, -r - 0.62 * D * 0.5, fin_le + 3, -r + 0.25), 0.3 * r)]

    # wing
    wing_mount = sp.get("wing_mount", "low")
    wx = float(sp.get("wing_x", 0.38)) * 100
    wc = float(sp.get("wing_chord", L * 0.15)) * s
    semi = float(sp.get("span", L)) / 2 * s
    sweep = math.tan(math.radians(float(sp.get("sweep", 25)))) * semi * 0.70
    tipc = wc * 0.36
    if wing_mount == "high":
        a = -r - 0.02 * D
        drop = -0.10 * D
    else:
        a = 0.42 * r
        drop = 0.55 * D
    ops.append(("poly", [(wx, a), (wx + wc, a + 0.04 * D), (wx + sweep + tipc, a + drop),
                         (wx + sweep, a + drop)]))
    ops += _winglet(sp.get("winglet"), wx + sweep, a + drop, tipc, s)
    if sp.get("winglet") == "raked":
        ops.append(("poly", [(wx + sweep, a + drop), (wx + sweep + tipc, a + drop),
                             (wx + sweep + tipc * 2.2, a + drop + 0.15 * D)]))

    # engines
    n = int(sp.get("eng_n", 2))
    mount = sp.get("eng_mount", "wing")
    el = float(sp.get("eng_len", 4.5)) * s
    eh = float(sp.get("eng_dia", 2.2)) * s
    style = sp.get("eng_style", "round")
    if mount == "wing" and n:
        def wing_y(x):           # height of the wing's leading edge at x
            if sweep <= 0:
                return a
            return a + drop * min(1.0, max(0.0, (x - wx) / sweep))
        ex = float(sp.get("eng_x", wx / 100 - 0.06)) * 100
        pylon = wing_y(ex + el * 0.6)
        ey = pylon + eh * (0.62 if wing_mount != "high" else 0.70)
        ops += _nacelle(ex, ey, el, eh, style, pylon_to=pylon)
        if n >= 4:
            ex2 = ex + sweep * 0.45
            pylon2 = wing_y(ex2 + el * 0.6)
            ops += _nacelle(ex2, pylon2 + eh * 0.6, el * 0.95, eh * 0.95, style, pylon_to=pylon2)
    elif mount == "rear" and n:
        ex = float(sp.get("eng_x", 0.62)) * 100
        ey = -0.62 * r
        ops.append(("poly", [(ex + el * 0.30, ey + eh * 0.30), (ex + el * 0.70, ey + eh * 0.30),
                             (ex + el * 0.72, 0.0), (ex + el * 0.35, 0.0)]))
        ops += [("rrect", (ex, ey - eh / 2, ex + el, ey + eh / 2), eh * 0.45),
                ("ellipse", (ex - eh * 0.10, ey - eh / 2, ex + eh * 0.24, ey + eh / 2))]
    if sp.get("rotodome"):
        rx = float(sp["rotodome"]) * 100
        ops += [("poly", [(rx - 1, -r), (rx, -r - 0.9 * D * 0.5), (rx + 3, -r - 0.9 * D * 0.5), (rx + 4, -r)]),
                ("rrect", (rx - 6, -r - 0.95 * D, rx + 9, -r - 0.45 * D), 0.25 * D)]
    return ops


def _turboprop(sp):
    L = float(sp["length"])
    s = 100.0 / L
    D = float(sp.get("diameter", L * 0.1)) * s
    r = D / 2
    nose_len = float(sp.get("nose_len", 1.4)) * D
    up = float(sp.get("upsweep", 2.2)) * D
    end_top = -0.75 * r if not sp.get("ramp") else -0.90 * r
    fus = _fuselage(r, nose_len, 0.22, 100 - up, 100 - 1.2 * D, end_top, -0.45 * r)
    fin_h = float(sp.get("fin", L * 0.17)) * s
    fin_c = float(sp.get("fin_chord", L * 0.18)) * s
    fin_sw = math.tan(math.radians(float(sp.get("fin_sweep", 30)))) * fin_h
    fin_le = 99 - fin_c
    tip_c = fin_c * 0.45
    fin = [(fin_le - 0.08 * 100 * float(sp.get("dorsal_frac", 0.0)), -0.6 * r),
           (fin_le, -r - 0.15 * fin_h), (fin_le + fin_sw, -r - fin_h),
           (fin_le + fin_sw + tip_c, -r - fin_h), (99, -0.70 * r)]
    ops = [("fin", fin), ("poly", fus)]
    wing = sp.get("wing", "high")
    wx = float(sp.get("wing_x", 0.36)) * 100
    wc = float(sp.get("wing_chord", L * 0.09)) * s
    # windows
    if sp.get("windows", True):
        step = 3.0 if L > 18 else 4.0
        ops += _windows(nose_len + 0.9 * D, 100 - up - 2, -0.10 * r, step, min(0.20 * r, 1.0))
    ops.append(_cockpit(nose_len, r, "boeing"))
    tail = sp.get("tail", "t")
    hs_c = fin_c * 0.8
    if tail == "t":
        ty = -r - fin_h
        x0 = fin_le + fin_sw - hs_c * 0.2
        ops.append(("poly", [(x0, ty + 0.6), (x0 + hs_c * 0.4, ty - 0.8), (x0 + hs_c * 1.2, ty - 0.8),
                             (x0 + hs_c * 1.1, ty + 0.8)]))
    elif tail == "cruciform":
        ty = -r - fin_h * 0.5
        x0 = fin_le + fin_sw * 0.5 - hs_c * 0.15
        ops.append(("poly", [(x0, ty + 0.6), (x0 + hs_c * 0.4, ty - 0.7), (x0 + hs_c * 1.15, ty - 0.7),
                             (x0 + hs_c * 1.05, ty + 0.7)]))
    else:
        x0 = 99.5 - hs_c * 1.3
        ops.append(("poly", [(x0, -0.3 * r), (x0 + hs_c * 0.5, -0.3 * r - 1.1), (99.5, -0.3 * r - 1.1),
                             (98.4, -0.3 * r + 0.4)]))
    n = int(sp.get("eng_n", 2))
    nl = float(sp.get("nacelle_len", 4.5)) * s
    nh = float(sp.get("nacelle_dia", 1.2)) * s
    pd = float(sp.get("prop", 3.9)) * s
    nx = float(sp.get("eng_x", wx / 100 - 0.03)) * 100
    if wing == "high":
        wy = -r
        ops.append(("poly", [(wx - wc * 0.1, wy + 0.3), (wx + wc * 0.05, wy - 0.45 * r),
                             (wx + wc * 1.0, wy - 0.45 * r), (wx + wc * 1.25, wy + 0.3)]))
        ny = wy + nh * 0.25
    else:
        wy = 0.55 * r
        ops.append(("poly", [(wx, wy), (wx + wc, wy), (wx + wc * 1.15, wy + 0.25 * D), (wx + wc * 0.15, wy + 0.25 * D)]))
        ny = wy - nh * 0.1
    if n == 1:      # single-engine turboprop (PC-12, Caravan): prop on the nose
        return ops + [("ellipse", (-2.0, -0.32 * r, 1.2, 0.42 * r)),
                      ("prop", (-1.0, -pd / 2, 0.3, pd / 2))]
    seq = [(nx, ny, 1.0)]
    if n >= 4:
        seq.append((nx + wc * 0.35, ny + (0.22 * D if wing != "high" else 0.12 * D), 0.95))
    for x, y, k in seq:
        ops += [("rrect", (x, y - nh * k / 2, x + nl * k, y + nh * k / 2), nh * k * 0.45),
                ("ellipse", (x - nh * 0.35, y - nh * 0.28, x + nh * 0.25, y + nh * 0.28)),
                ("prop", (x - nh * 0.2, y - pd * k / 2, x + nh * 0.05, y + pd * k / 2))]
    return ops


def _light(sp):
    L = float(sp["length"])
    s = 100.0 / L
    D = float(sp.get("diameter", 1.5)) * s
    r = D / 2
    nose_len = 0.75 * D
    fus = _fuselage(r, nose_len, 0.25, 38, 46, -0.55 * r, -0.20 * r)
    fin_h = float(sp.get("fin", 1.4)) * s
    fin_c = float(sp.get("fin_chord", 1.4)) * s
    fin_le = 99.5 - fin_c
    fin = [(fin_le - fin_c * 0.6, -0.5 * r), (fin_le + fin_c * 0.35, -r - fin_h),
           (fin_le + fin_c * 0.85, -r - fin_h), (99.5, -0.3 * r)]
    ops = [("fin", fin), ("poly", fus)]
    wing = sp.get("wing", "high")
    wx = float(sp.get("wing_x", 0.28)) * 100
    wc = float(sp.get("wing_chord", 1.5)) * s
    # glazing
    ops += [("cockpit", [(nose_len * 1.05, -0.25 * r), (nose_len * 1.6, -0.92 * r),
                         (wx + wc * 0.15, -0.95 * r), (wx + wc * 0.15, -0.22 * r)])]
    if L > 7.5:
        ops += [("cockpit", [(wx + wc * 0.25, -0.95 * r), (wx + wc * 0.95, -0.90 * r),
                             (wx + wc * 1.05, -0.25 * r), (wx + wc * 0.25, -0.22 * r)])]
    if wing == "high":
        ops.append(("poly", [(wx - 0.5, -r - 0.05), (wx, -r - 0.30 * r), (wx + wc, -r - 0.30 * r), (wx + wc + 0.5, -r - 0.05)]))
        if sp.get("strut", True):
            ops.append(("poly", [(wx + wc * 0.35, -r * 0.8), (wx + wc * 0.45, -r * 0.8),
                                 (wx + wc * 0.15, r * 0.9), (wx + wc * 0.05, r * 0.9)]))
    else:
        ops.append(("poly", [(wx, 0.55 * r), (wx + wc, 0.55 * r), (wx + wc * 1.05, 0.95 * r), (wx + wc * 0.05, 0.95 * r)]))
    if sp.get("tail") == "t":
        ty = -r - fin_h
        ops.append(("poly", [(fin_le, ty + 0.6), (fin_le + fin_c * 0.3, ty - 0.9), (99.6, ty - 0.9), (99, ty + 0.7)]))
    else:
        ops.append(("poly", [(84, -0.35 * r), (90, -0.35 * r - 1.6), (99.6, -0.35 * r - 1.6), (98.4, -0.35 * r + 0.4)]))
    if int(sp.get("eng_n", 1)) == 2:
        nl, nh = 2.4 * s, 0.8 * s
        nx, ny = wx - nl * 0.35, (0.80 * r if wing != "high" else -r + nh * 0.3)
        ops += [("rrect", (nx, ny - nh / 2, nx + nl, ny + nh / 2), nh * 0.45),
                ("prop", (nx - 0.3, ny - 0.95 * s, nx + 0.3, ny + 0.95 * s))]
        ops += [("ellipse", (-2.0, -0.30 * r, 1.0, 0.45 * r))]       # nose cone
    else:
        ops += [("ellipse", (-2.4, -0.25 * r, 1.4, 0.55 * r)),
                ("prop", (-1.2, -1.15 * r, 0.4, 1.45 * r))]
    return ops


def _heli(sp):
    """A helicopter from its dimensions (metres): cabin, cowling, boom, fin, rotor, gear."""
    L = float(sp.get("length", 11.0))           # fuselage, nose to tail, rotors excluded
    s = 100.0 / L
    H = float(sp.get("cabin_h", 1.8)) * s       # cabin height
    ce = float(sp.get("cabin_len", 0.42)) * 100  # where the cabin ends and the boom starts
    nose = sp.get("nose", "standard")           # bubble | pointed | blunt | standard
    top, bot = -H * 0.55, H * 0.45
    ops = []

    # ---- tail: fin first so the boom and body overlap its root
    tail_rotor = sp.get("tail_rotor", "rotor")
    fin_h = float(sp.get("fin", 1.6)) * s
    bh0 = float(sp.get("boom_h", 0.75)) * s       # boom height where it leaves the cabin
    bh1 = bh0 * 0.45                              # at the tail
    by0 = top + bh0 * 0.65                        # boom centreline at the cabin
    by1 = top + bh0 * 0.40                        # boom centreline at the tail
    if tail_rotor == "fenestron":
        fd = float(sp.get("tail_rotor_dia", 1.1)) * s
        cx, cy = 100 - fd * 0.95, by1 - fd * 0.30
        ops.append(("fin", [(100 - fd * 1.9, by1 + bh1 * 0.5), (100 - fd * 1.45, cy - fd * 0.85),
                            (100 - fd * 0.65, by1 - fin_h), (100 + fd * 0.05, by1 - fin_h),
                            (100, cy + fd * 0.55), (100 - fd * 0.40, by1 + bh1 * 0.9)]))
    else:
        ops.append(("fin", [(100 - fin_h * 0.55, by1 + bh1 * 0.3), (100 - fin_h * 0.20, by1 - fin_h),
                            (100 + fin_h * 0.10, by1 - fin_h), (100 + fin_h * 0.05, by1 + bh1 * 0.6)]))
    ops.append(("poly", [(ce - 4, by0 - bh0 / 2), (100, by1 - bh1 / 2), (100, by1 + bh1 / 2), (ce - 4, by0 + bh0 / 2)]))

    # ---- cabin
    if nose == "bubble":           # R44, AS350, Bell 206: rounded goldfish bowl
        body = _bez((0, top * 0.05), (0, top * 1.05), (ce * 0.38, top))
        body += [(ce * 0.80, top)] + _bez((ce * 0.80, top), (ce * 1.08, top * 0.6), (ce * 1.02, bot * 0.55), 6)[1:]
        body += _bez((ce * 1.02, bot * 0.55), (ce * 0.75, bot * 1.02), (ce * 0.35, bot), 6)[1:]
        body += _bez((ce * 0.35, bot), (0, bot * 1.0), (0, top * 0.05), 6)[1:]
    elif nose == "pointed":        # A109, S-76, H160: long tapering nose
        body = _bez((0, bot * 0.15), (ce * 0.12, top * 0.55), (ce * 0.36, top * 0.98))
        body += [(ce * 1.02, top), (ce * 1.10, top * 0.25), (ce * 1.05, bot)]
        body += [(ce * 0.32, bot)] + _bez((ce * 0.32, bot), (ce * 0.05, bot * 0.95), (0, bot * 0.15), 6)[1:]
    elif nose == "blunt":          # S-92, AW139, H175: bluff, tall cabin
        body = _bez((0, bot * 0.25), (0, top * 0.95), (ce * 0.16, top))
        body += [(ce * 1.02, top), (ce * 1.10, top * 0.3), (ce * 1.06, bot)]
        body += [(ce * 0.12, bot)] + _bez((ce * 0.12, bot), (0, bot * 0.95), (0, bot * 0.25), 5)[1:]
    else:                          # H135, H145, AW119
        body = _bez((0, bot * 0.10), (ce * 0.02, top * 0.95), (ce * 0.28, top))
        body += [(ce * 1.0, top), (ce * 1.10, top * 0.25), (ce * 1.04, bot)]
        body += [(ce * 0.26, bot)] + _bez((ce * 0.26, bot), (0, bot * 0.95), (0, bot * 0.10), 6)[1:]
    ops.append(("poly", body))

    # ---- glazing: windscreen, then cabin windows
    if nose == "bubble":
        ops.append(("cockpit", [(ce * 0.06, top * 0.10), (ce * 0.14, top * 0.80), (ce * 0.46, top * 0.92),
                                (ce * 0.50, bot * 0.25), (ce * 0.12, bot * 0.30)]))
    else:
        x0 = ce * (0.14 if nose == "pointed" else 0.05)
        ops.append(("cockpit", [(x0, top * 0.12), (x0 + ce * 0.10, top * 0.82), (ce * 0.36, top * 0.88),
                                (ce * 0.36, top * 0.10)]))
    n_win = int(sp.get("windows", 1))
    if n_win:
        wx0, wx1 = ce * 0.42, ce * 0.96
        step = (wx1 - wx0) / n_win
        for i in range(n_win):
            a = wx0 + i * step + step * 0.12
            ops.append(("cockpit", [(a, top * 0.78), (a + step * 0.76, top * 0.78),
                                    (a + step * 0.76, top * 0.05), (a, top * 0.05)]))

    # ---- engine cowling and mast
    ch = float(sp.get("cowl_h", 0.6)) * s
    ops.append(("poly", [(ce * 0.30, top + 0.2), (ce * 0.40, top - ch), (ce * 1.05, top - ch * 0.85),
                         (ce * 1.25, top * 0.55), (ce * 1.05, top + 0.2)]))
    mx = float(sp.get("mast_x", 0.5)) * ce + ce * 0.25
    mh = float(sp.get("mast_h", 0.45)) * s
    ops.append(("rrect", (mx - 0.9, top - ch - mh, mx + 0.9, top - ch + 0.4), 0.4))
    rd = float(sp.get("rotor", L * 0.95)) * s
    ry = top - ch - mh
    ops.append(("rotor", (mx - rd / 2, ry - 0.8, mx + rd / 2, ry + 0.5)))
    ops.append(("ellipse", (mx - 1.6, ry - 1.4, mx + 1.6, ry + 1.0)))        # rotor head

    # ---- tail rotor / fenestron and tailplane
    if tail_rotor == "fenestron":
        ops.append(("ellipse", (cx - fd * 0.42, cy - fd * 0.42, cx + fd * 0.42, cy + fd * 0.42)))
    else:
        tr = float(sp.get("tail_rotor_dia", L * 0.17)) * s
        tcx, tcy = 100 - fin_h * 0.15, by1 - fin_h * 0.45
        ops.append(("ring", (tcx - tr / 2, tcy - tr / 2, tcx + tr / 2, tcy + tr / 2)))
        ops.append(("ellipse", (tcx - 0.9, tcy - 0.9, tcx + 0.9, tcy + 0.9)))
    hx = 100 - float(sp.get("tailplane_x", 0.16)) * 100
    ops.append(("poly", [(hx, by1 + 0.3), (hx + 2.5, by1 - 1.0), (hx + 8.0, by1 - 1.0), (hx + 7.0, by1 + 0.6)]))

    # ---- undercarriage
    gear = sp.get("gear", "skids")
    if gear == "skids":
        sy = bot + float(sp.get("skid_h", 0.55)) * s
        ops += [("skid", [(ce * 0.05, sy), (ce * 1.05, sy)]),
                ("skid", [(ce * 0.22, bot * 0.8), (ce * 0.20, sy)]),
                ("skid", [(ce * 0.85, bot * 0.8), (ce * 0.88, sy)])]
    elif gear == "sponsons":
        ops.append(("rrect", (ce * 0.62, bot * 0.15, ce * 1.12, bot * 1.25), 2.0))
        wr = 0.30 * s
        ops += [("ellipse", (ce * 0.80 - wr, bot * 1.25 - wr * 0.6, ce * 0.80 + wr, bot * 1.25 + wr * 1.4)),
                ("ellipse", (ce * 0.12 - wr * 0.8, bot + wr * 0.2, ce * 0.12 + wr * 0.8, bot + wr * 1.8))]
    # gear == "wheels": retracted in flight, nothing to draw
    return ops


def _tandem(sp):
    """Chinook-style tandem rotors."""
    r = 7.0
    fus = [(0, 3)] + _bez((0, 3), (1, -r), (12, -r))[1:] + [(88, -r), (100, -r - 4), (100, r * 0.5), (80, r)]
    fus += [(10, r)] + _bez((10, r), (0.5, r), (0, 3), 5)[1:]
    ops = [("fin", [(84, -r), (88, -r - 9), (98, -r - 9), (100, -r - 2)]), ("poly", fus)]
    ops += [("cockpit", [(2, 0), (5, -5.5), (12, -6), (12, 0)])]
    ops += _windows(20, 76, -1.5, 6, 1.2)
    ops += [("rrect", (6, -r - 4, 22, -r + 0.5), 1.5), ("rotor", (-22, -r - 6, 40, -r - 4.8)),
            ("rotor", (64, -r - 12, 126, -r - 10.8))]
    return ops


def _fighter(sp):
    kind = sp.get("shape", "delta")
    r = 4.0
    fus = [(0, 0.5)] + _bez((0, 0.5), (8, -3.5), (24, -r))[1:] + [(82, -r), (96, -3.0), (100, -2.6), (100, 2.2),
                                                                     (88, 3.4)]
    fus += [(30, 3.6)] + _bez((30, 3.6), (10, 3.2), (0, 0.5), 6)[1:]
    if kind == "delta":
        fin = [(68, -3.5), (82, -17), (90, -17), (97, -3.5)]
    elif kind == "trainer":
        fin = [(74, -3.5), (86, -14), (93, -14), (98, -3.0)]
    else:   # f35-style canted twin fins, seen as one
        fin = [(72, -3.5), (84, -13), (92, -13), (96, -3.5)]
    ops = [("fin", fin), ("poly", fus)]
    canopy_x = (18, 38) if kind != "trainer" else (16, 44)
    ops += [("cockpit", [(canopy_x[0], -r), (canopy_x[0] + 6, -r - 3.0), (canopy_x[1] - 4, -r - 3.0),
                         (canopy_x[1], -r)])]
    if kind == "delta":
        ops += [("poly", [(42, 1.5), (90, 1.5), (92, 3.5), (70, 4.0)])]           # delta wing
        ops += [("poly", [(22, -1.0), (27, -1.5), (30, 0.2), (24, 0.3)])]          # canard
        ops += [("rrect", (30, 1.0, 58, 5.0), 1.0)]                                 # intake
    elif kind == "trainer":
        ops += [("poly", [(44, 2.0), (60, 2.0), (66, 4.0), (50, 4.0)])]
        ops += [("poly", [(84, -1.0), (90, -2.0), (99, -2.0), (98, -0.5)])]
    else:
        ops += [("poly", [(48, 1.0), (76, 1.0), (80, 3.0), (60, 3.5)])]
        ops += [("poly", [(84, 0.0), (90, -0.8), (99, -0.8), (98, 0.6)])]
    return ops


def _balloon(sp):
    ops = []
    env = _bez((50, 62), (8, 40), (14, 18), 10) + _bez((14, 18), (20, -12), (50, -12), 10)[1:]
    env += _bez((50, -12), (80, -12), (86, 18), 10)[1:] + _bez((86, 18), (92, 40), (50, 62), 10)[1:]
    ops.append(("poly", env))
    ops.append(("accentfill", env))
    for x in (30, 42, 58, 70):     # gores
        ops.append(("skid", _bez((50, 62), (x - (50 - x) * 0.5, 20), (50 + (x - 50) * 0.35, -11), 8)))
    ops += [("skid", [(44, 63), (45, 76)]), ("skid", [(56, 63), (55, 76)])]
    ops.append(("rrect", (43, 76, 57, 86), 1.0))
    return ops


def _glider(sp):
    r = 3.0
    fus = [(0, 0.6)] + _bez((0, 0.6), (3, -r), (14, -r))[1:] + [(30, -2.0), (100, -0.8), (100, 0.6), (30, 1.6)]
    fus += [(14, r)] + _bez((14, r), (3, r), (0, 0.6), 5)[1:]
    ops = [("fin", [(86, -0.6), (92, -12), (98, -12), (100, -0.4)]), ("poly", fus)]
    ops += [("cockpit", [(5, -r * 0.6), (9, -r - 1.6), (20, -r - 1.2), (24, -r * 0.8)])]
    ops += [("poly", [(24, -r - 0.2), (34, -r - 0.2), (36, -r + 0.8), (25, -r + 0.8)])]
    ops += [("poly", [(90, -12.4), (94, -13.2), (101, -13.2), (100, -12)])]
    return ops
