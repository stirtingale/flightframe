"""Day and night: the real moon, stars, rain, and turning the screen dark.

Screens are always drawn black on white. At night `night()` swaps black and
white across the whole picture and puts the aircraft drawings back the right way
round (white body, dark sky around it). Sky details are drawn before the swap,
in the colour they should end up the other side of it.
"""
import math
import random
from datetime import datetime, timezone

from PIL import ImageChops, ImageDraw, ImageFilter

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0)

SYNODIC = 29.530588853
NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)


# ------------------------------------------------------------------ time of day
def moon_phase(when=None):
    """0 = new, 0.25 = first quarter, 0.5 = full, 0.75 = last quarter."""
    when = when or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.astimezone()
    days = (when - NEW_MOON).total_seconds() / 86400
    return (days / SYNODIC) % 1.0


def moon_name(p):
    names = ["New moon", "Waxing crescent", "First quarter", "Waxing gibbous",
             "Full moon", "Waning gibbous", "Last quarter", "Waning crescent"]
    return names[int((p * 8) + 0.5) % 8]


def is_night(sun, mode="auto", now=None):
    """sun = (sunrise, sunset) for today, local datetimes or (None, None)."""
    if mode == "dark":
        return True
    if mode == "light" or not sun or not sun[0]:
        return False
    now = now or datetime.now().astimezone()
    return now < sun[0] or now >= sun[1]


# ------------------------------------------------------------------ drawing
def draw_moon(d, cx, cy, r, phase, south=False, lit=BLACK, dark=WHITE):
    """The moon as it looks tonight. Colours are pre-swap: lit part BLACK becomes white."""
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=dark, outline=lit, width=2)
    waxing = phase < 0.5
    k = math.cos(2 * math.pi * phase)
    for yy in range(-r, r + 1):
        w = math.sqrt(max(0.0, r * r - yy * yy))
        if waxing:
            x0, x1 = w * k, w            # lit on the right
        else:
            x0, x1 = -w, -w * k          # lit on the left
        if south:                        # southern hemisphere sees it mirrored
            x0, x1 = -x1, -x0
        if x1 - x0 >= 0.5:
            d.line([cx + x0, cy + yy, cx + x1, cy + yy], fill=lit)


def _sun(d, cx, cy, r):
    for i in range(8):
        a = math.radians(i * 45 + 22.5)
        d.line([cx + math.cos(a) * r * 1.4, cy + math.sin(a) * r * 1.4,
                cx + math.cos(a) * r * 1.9, cy + math.sin(a) * r * 1.9], fill=BLACK, width=2)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=YELLOW, outline=BLACK, width=2)


def _cloud(d, cx, cy, sz):
    parts = [(cx - sz * 0.32, cy + sz * 0.05, sz * 0.26), (cx, cy - sz * 0.10, sz * 0.34),
             (cx + sz * 0.32, cy + sz * 0.06, sz * 0.24)]
    base = (cx - sz * 0.56, cy + sz * 0.02, cx + sz * 0.56, cy + sz * 0.30)
    for grow, colour in ((1.6, BLACK), (0, WHITE)):
        for x, y, r in parts:
            d.ellipse([x - r - grow, y - r - grow, x + r + grow, y + r + grow], fill=colour)
        d.rounded_rectangle([base[0] - grow, base[1] - grow, base[2] + grow, base[3] + grow],
                            radius=sz * 0.14 + grow, fill=colour)


class Free:
    """Where in a box nothing has been drawn yet (with a margin)."""

    def __init__(self, img, box, margin=7):
        self.box = [int(v) for v in box]
        x0, y0, x1, y1 = self.box
        crop = img.crop((x0, y0, x1, y1)).convert("L").point(lambda v: 255 if v < 250 else 0)
        size = margin * 2 + 1
        self.mask = crop.filter(ImageFilter.MaxFilter(size)) if margin else crop
        self.px = self.mask.load()
        self.d = ImageDraw.Draw(self.mask)

    def ok(self, x, y, rx, ry=None):
        ry = rx if ry is None else ry
        x0, y0, x1, y1 = self.box
        if x - rx < x0 or x + rx >= x1 or y - ry < y0 or y + ry >= y1:
            return False
        for yy in range(int(y - ry), int(y + ry) + 1, 2):
            for xx in range(int(x - rx), int(x + rx) + 1, 2):
                if self.px[xx - x0, yy - y0]:
                    return False
        return True

    def take(self, x, y, rx, ry=None):
        ry = rx if ry is None else ry
        x0, y0 = self.box[:2]
        self.d.rectangle([x - rx - x0 - 4, y - ry - y0 - 4, x + rx - x0 + 4, y + ry - y0 + 4], fill=255)


def decorate(img, box, kind, night, phase=None, lat=0.0, seed=None, big=15):
    """Sky details in the empty parts of box: sun or moon, clouds, stars, rain.

    kind: the weather now ("clear", "partly", "cloudy", "rain", ...), or None.
    Call before night(); the colours are chosen to come out right after it.
    """
    if box[2] - box[0] < 60 or box[3] - box[1] < 40:
        return
    d = ImageDraw.Draw(img)
    free = Free(img, box)
    kind = kind or "clear"
    wet = kind in ("rain", "showers", "thunder", "sleet")
    snow = kind == "snow"
    overcast = kind in ("cloudy", "fog") or wet or snow
    rng = random.Random(seed if seed is not None else datetime.now().strftime("%Y%m%d"))

    # sun or moon: as high and as far right as there's room
    spot = None
    # rightmost first, then highest: the seat is always the top-right of the sky
    for x in range(box[2] - big - 4, box[0] + big + 4, -6):
        for y in range(box[1] + big + 4, box[3] - big - 4, 4):
            if free.ok(x, y, big + 10):
                spot = (x, y)
                break
        if spot:
            break
    if spot:
        x, y = spot
        if night:
            if not overcast:
                draw_moon(d, x, y, big, moon_phase() if phase is None else phase, south=lat < 0)
        elif not overcast:
            _sun(d, x, y, big * 0.7)
        if kind == "partly" or overcast:
            cx, cy = (x - big * 0.5, y + big * 0.45) if not overcast else (x, y)
            _cloud(d, cx, cy, big * (1.9 if overcast else 1.6))
        free.take(x, y, big + 12)

    # stars on a clear or partly cloudy night
    if night and not overcast:
        want = 14 if kind == "clear" else 7
        for _ in range(want * 30):
            if want <= 0:
                break
            x = rng.randint(box[0] + 4, box[2] - 5)
            y = rng.randint(box[1] + 4, box[3] - 5)
            if not free.ok(x, y, 5):
                continue
            if rng.random() < 0.18:      # a few brighter ones
                d.rectangle([x - 3, y, x + 3, y + 1], fill=BLACK)
                d.rectangle([x - 1, y - 2, x, y + 3], fill=BLACK)
            else:
                d.rectangle([x, y, x + 1, y + 1], fill=BLACK)
            free.take(x, y, 6)
            want -= 1

    # rain or snow falling through the empty sky
    if wet or snow:
        ink = BLACK if night else BLUE           # black turns white at night
        want = 22 if kind in ("rain", "thunder") else 14
        for _ in range(want * 30):
            if want <= 0:
                break
            x = rng.randint(box[0] + 6, box[2] - 7)
            y = rng.randint(box[1] + 6, box[3] - 9)
            if not free.ok(x, y, 5, 7):
                continue
            if snow:
                for a in (0, 60, 120):
                    ra = math.radians(a)
                    d.line([x - math.cos(ra) * 3, y - math.sin(ra) * 3,
                            x + math.cos(ra) * 3, y + math.sin(ra) * 3], fill=ink, width=2)
            else:
                d.line([x + 2, y - 5, x - 2, y + 5], fill=ink, width=2)
            free.take(x, y, 4, 6)
            want -= 1


# ------------------------------------------------------------------ the swap
def _where(img, colour):
    """Mask of the pixels that are exactly this colour."""
    chans = img.split()
    m = None
    for ch, v in zip(chans, colour):
        part = ch.point(lambda p, v=v: 255 if p == v else 0)
        m = part if m is None else ImageChops.multiply(m, part)
    return m


def outside_mask(im):
    """White pixels connected to the edge of an aircraft drawing (its background)."""
    w, h = im.size
    work = im.convert("RGB").copy()
    marker = (1, 2, 3)
    px = work.load()
    seeds = [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)] + \
            [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)]
    for s in seeds:
        if px[s] == WHITE:
            ImageDraw.floodfill(work, s, marker, thresh=0)
    return _where(work, marker)


def night(img, keep=()):
    """Swap black and white. keep: [(drawing, (x, y))] aircraft pasted on the screen,
    put back with their white bodies and the sky around them dark."""
    out = img.convert("RGB").copy()
    whites, blacks = _where(out, WHITE), _where(out, BLACK)
    out.paste(BLACK, mask=whites)
    out.paste(WHITE, mask=blacks)
    for drawing, (x, y) in keep:
        inside = outside_mask(drawing).point(lambda v: 0 if v else 255)
        out.paste(drawing, (x, y), inside)
    return out
