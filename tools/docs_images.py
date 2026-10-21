"""Regenerate the README screenshots in docs/images, in on-paper colours.

    python3 tools/docs_images.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image, ImageDraw, ImageFilter          # noqa: E402

from flightframe import config, render                 # noqa: E402
from flightframe.render import as_seen                  # noqa: E402
from tools.preview import SAMPLES, _logo, sample_radar, sample_track, sample_wx  # noqa: E402
from flightframe import trackmap                        # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "docs", "images")


def save(img, name):
    as_seen(img).save(os.path.join(OUT, f"{name}.png"), optimize=True)


def hero(screen):
    mat, border, pad = 70, 34, 60
    W, H = screen.width + 2 * (mat + border), screen.height + 2 * (mat + border)
    canvas = Image.new("RGB", (W + 2 * pad, H + 2 * pad), (232, 229, 223))
    sh = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(sh).rectangle([pad + 10, pad + 18, pad + W + 10, pad + H + 18], fill=110)
    canvas.paste((150, 145, 138), mask=sh.filter(ImageFilter.GaussianBlur(18)))
    d = ImageDraw.Draw(canvas)
    d.rectangle([pad, pad, pad + W, pad + H], fill=(28, 27, 26))
    d.rectangle([pad + border, pad + border, pad + W - border, pad + H - border], fill=(250, 249, 246))
    x0, y0 = pad + border + mat, pad + border + mat
    d.rectangle([x0 - 3, y0 - 3, x0 + screen.width + 2, y0 + screen.height + 2], fill=(214, 211, 205))
    canvas.paste(screen, (x0, y0))
    canvas.save(os.path.join(OUT, "hero.png"), optimize=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    cfg = dict(config.DEFAULTS, label="Home, Bath", lat=51.38, lon=-2.36, night_mode="light")
    wx = sample_wx()
    shots = {}
    for name in ["ba-widebody", "ryanair", "easyjet-climbing", "emirates-a380", "air-ambulance"]:
        f = SAMPLES[name]
        shots[name] = render.poster(f, cfg, 4, logo=_logo(f), wx=wx)
        save(shots[name], f"screen-{name}")
    save(render.quiet(cfg, "BA283 LHR–LAX at 21:14", wx=wx), "screen-quiet")
    a, b = SAMPLES["ba-widebody"], SAMPLES["easyjet-climbing"]
    save(render.duo([a, b], cfg, 2, logos=(_logo(a), _logo(b)), wx=wx), "screen-duo")
    save(render.radar(sample_radar(), cfg, wx=wx), "screen-radar")
    q, f, trail = sample_track()[0]
    save(trackmap.tracker(cfg, q, f, trail=trail, wx=wx), "screen-tracker")
    night = dict(cfg, night_mode="dark")
    nwx = sample_wx()
    nwx["slots"][0]["kind"] = "clear"
    save(render.poster(a, night, 4, logo=_logo(a), wx=nwx), "screen-night")
    save(render.quiet(night, "BA283 LHR–LAX at 21:14", wx=nwx), "screen-night-quiet")
    nwx["slots"][0]["kind"] = "rain"
    save(render.duo([a, b], night, 2, logos=(_logo(a), _logo(b)), wx=nwx), "screen-night-rain")
    p = dict(cfg, orientation="portrait")
    f = SAMPLES["easyjet-climbing"]
    save(render.poster(f, p, 4, logo=_logo(f), wx=wx), "screen-portrait")
    save(render.message(cfg, "Connect me to Wi-Fi",
                        ["Join the Wi-Fi network Flightframe-Setup (password skyabove).",
                         "Then open http://10.42.0.1 and choose your home Wi-Fi."],
                        "WIFI:T:WPA;S:Flightframe-Setup;P:skyabove;;"), "screen-wifi-setup")
    save(render.message(cfg, "Almost there", ["Set your location from your phone:", "http://flightframe.local",
                                              "Your phone needs to be on the same Wi-Fi."],
                        "http://flightframe.local"), "screen-almost-there")
    save(render.message(cfg, "Settings", ["Open this on your phone (same Wi-Fi):", "http://flightframe.local",
                                          "Press the top button to go back to the sky."],
                        "http://flightframe.local"), "screen-settings-qr")
    save(render.message(cfg, "Waiting for flight data",
                        ["The flight data services haven't answered since 13:42.",
                         "The frame keeps trying and will pick up again by itself.",
                         "Details: http://flightframe.local"], header="STATUS"), "screen-outage")
    hero(as_seen(shots["ba-widebody"]))
    print("images written to", os.path.normpath(OUT))


if __name__ == "__main__":
    main()
