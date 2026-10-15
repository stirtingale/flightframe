"""Output: Pimoroni Inky Impression, Waveshare 7.3" (E), or a PNG preview for testing.

Both panels are E Ink Spectra 6 (800x480, black, white, yellow, red, blue, green).
"""
import logging
import os
import sys
import threading

from PIL import Image

from .config import STATE_DIR
from .render import for_panel

log = logging.getLogger(__name__)
PREVIEW_PATH = os.path.join(STATE_DIR, "screen.png")

# install.sh puts the Waveshare library here (only for Waveshare panels)
for p in ("/opt/flightframe/vendor/waveshare/lib",
          os.path.join(os.path.dirname(__file__), "..", "vendor", "waveshare", "lib")):
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

# The six pure colours, in the order Pimoroni's driver expects
PURE = [(0, 0, 0), (255, 255, 255), (255, 255, 0), (255, 0, 0), (0, 0, 255), (0, 255, 0)]


def _to_palette(img):
    """Map an image already drawn in the six panel colours to a 'P' image, no dithering."""
    pal = Image.new("P", (1, 1))
    pal.putpalette([v for c in PURE for v in c] + [0, 0, 0] * (256 - len(PURE)))
    return img.convert("RGB").quantize(palette=pal, dither=Image.Dither.NONE)


class PreviewDisplay:
    name = "preview"

    def __init__(self, flip=False):
        self.flip = flip

    def panel_image(self, img):
        img = for_panel(img)
        return img.rotate(180) if self.flip else img

    def show(self, img):
        os.makedirs(STATE_DIR, exist_ok=True)
        img.save(PREVIEW_PATH)


class InkyDisplay(PreviewDisplay):
    """Pimoroni Inky Impression 7.3" (Spectra 6), found through its ID chip."""
    name = "inky"

    def __init__(self, flip=False):
        super().__init__(flip)
        from inky.auto import auto
        self._inky = auto()
        if self._inky is None:
            raise RuntimeError("no Inky board detected (is I2C switched on?)")
        if (self._inky.width, self._inky.height) != (800, 480):
            raise RuntimeError(f"unexpected Inky size {self._inky.width}x{self._inky.height}")
        self._lock = threading.Lock()
        log.info("Inky detected: %s", type(self._inky).__module__)

    def show(self, img):
        super().show(img)
        with self._lock:
            try:
                self._inky.set_border(self._inky.WHITE)
            except Exception:
                pass
            # A 'P' image in the pure colours stops the driver from dithering.
            self._inky.set_image(_to_palette(self.panel_image(img)))
            self._inky.show()


class WaveshareDisplay(PreviewDisplay):
    """Waveshare 7.3inch e-Paper HAT (E)."""
    name = "waveshare"

    def __init__(self, flip=False):
        super().__init__(flip)
        from waveshare_epd import epd7in3e   # fail early if missing
        self._mod = epd7in3e
        self._lock = threading.Lock()

    def show(self, img):
        super().show(img)
        with self._lock:
            epd = self._mod.EPD()
            try:
                epd.init()
                epd.display(epd.getbuffer(self.panel_image(img)))
            finally:
                epd.sleep()            # always rest the panel; leaving it powered harms it


def make_display(kind="auto", flip=False):
    if kind == "eink":
        kind = "waveshare"             # older config name
    order = {"auto": [InkyDisplay, WaveshareDisplay],
             "inky": [InkyDisplay], "waveshare": [WaveshareDisplay]}.get(kind, [])
    for cls in order:
        try:
            d = cls(flip)
            log.info("using %s panel", d.name)
            return d
        except Exception as e:
            if kind != "auto":
                raise
            log.info("%s panel not available: %s", cls.name, e)
    if kind == "auto":
        log.warning("no E Ink panel found; writing PNG previews only")
    return PreviewDisplay(flip)
