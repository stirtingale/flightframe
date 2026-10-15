"""Render every screen with sample data to PNGs, without a panel.

    python3 tools/preview.py out/

Airline logos are downloaded (and cached) if the internet is reachable;
otherwise the tail fins are filled with the accent colour.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flightframe import config, logos, plane, render      # noqa: E402
from flightframe.flights import Flight                     # noqa: E402


def _f(**kw):
    base = dict(hex="000000", lat=51.4, lon=-2.35, track=90, vertical_fpm=0, bearing=40)
    base.update(kw)
    return Flight(**base)


SAMPLES = {
    "ba-widebody": _f(
        callsign="BAW283", altitude_ft=36975, speed_kt=468, distance_km=3.2,
        registration="G-XWBC", type_code="A35K", type_name="Airbus A350-1041",
        airline="British Airways", airline_icao="BAW", airline_iata="BA", flight_iata="BA283",
        origin={"iata": "LHR", "city": "London"}, destination={"iata": "LAX", "city": "Los Angeles"}),
    "easyjet-climbing": _f(
        callsign="EZY63LK", altitude_ft=8400, speed_kt=262, vertical_fpm=2100, distance_km=6.8,
        bearing=300, registration="G-UZHA", type_code="A20N", type_name="Airbus A320-251N",
        airline="easyJet", airline_icao="EZY", airline_iata="U2", flight_iata="U26401",
        origin={"iata": "BRS", "city": "Bristol"},
        destination={"iata": "PMI", "city": "Palma de Mallorca"}),
    "ryanair": _f(
        callsign="RYR4TX", altitude_ft=34000, speed_kt=455, distance_km=5.1,
        registration="EI-HEA", type_code="B38M", type_name="Boeing 737 MAX 8",
        airline="Ryanair", airline_icao="RYR", airline_iata="FR", flight_iata="FR1882",
        origin={"iata": "DUB", "city": "Dublin"}, destination={"iata": "FAO", "city": "Faro"}),
    "emirates-a380": _f(
        callsign="UAE19", altitude_ft=38000, speed_kt=490, distance_km=8.9,
        registration="A6-EUV", type_code="A388", type_name="Airbus A380-861",
        airline="Emirates", airline_icao="UAE", airline_iata="EK", flight_iata="EK19",
        origin={"iata": "MAN", "city": "Manchester"}, destination={"iata": "DXB", "city": "Dubai"}),
    "loganair-atr": _f(
        callsign="LOG6KP", altitude_ft=14000, speed_kt=250, distance_km=4.0,
        registration="G-LMTE", type_code="AT76", type_name="ATR 72-600",
        airline="Loganair", airline_icao="LOG", airline_iata="LM", flight_iata="LM375",
        origin={"iata": "SOU", "city": "Southampton"}, destination={"iata": "EDI", "city": "Edinburgh"}),
    "raf-no-route": _f(
        callsign="RRR6513", altitude_ft=24000, speed_kt=330, vertical_fpm=-1200, distance_km=11.4,
        bearing=170, registration="ZZ336", type_code="A332", type_name="Airbus Voyager KC2",
        operator="Royal Air Force"),
    "air-ambulance": _f(
        callsign="HLE65", altitude_ft=1500, speed_kt=130, distance_km=2.2, bearing=220,
        registration="G-WASN", type_code="EC35", type_name="Eurocopter EC135",
        operator="Great Western Air Ambulance", category="A7"),
}


def _logo(f):
    return logos.get(logos.airline_icao(f.callsign, f.airline_icao), f.airline_iata)


def main(out):
    os.makedirs(out, exist_ok=True)
    cfg = dict(config.DEFAULTS, label="Home, Bath", lat=51.38, lon=-2.36)
    for orient in ("landscape", "portrait"):
        cfg["orientation"] = orient
        for name, f in SAMPLES.items():
            render.poster(f, cfg, nearby=4, logo=_logo(f)).save(f"{out}/{orient}-{name}.png")
        render.quiet(cfg, "BA283 LHR–LAX at 21:14").save(f"{out}/{orient}-quiet.png")
        render.message(cfg, "Connect me to Wi-Fi",
                       ["Join the Wi-Fi network Flightframe-Setup (password skyabove).",
                        "Then open http://10.42.0.1 and choose your home Wi-Fi."],
                       qr_data="WIFI:T:WPA;S:Flightframe-Setup;P:skyabove;;").save(f"{out}/{orient}-setup.png")
    # every aircraft family on one sheet
    from PIL import Image
    kinds = ["narrow", "wide", "jumbo", "a380", "quad", "regional", "turboprop", "bizjet", "light", "heli"]
    sheet = Image.new("RGB", (2 * 420, 5 * 150), (255, 255, 255))
    for i, k in enumerate(kinds):
        im = plane.draw(k, 400, 130)
        sheet.paste(im, (10 + (i % 2) * 420, 10 + (i // 2) * 150))
    sheet.save(f"{out}/aircraft-families.png")
    print("wrote previews to", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "previews")
