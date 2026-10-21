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


RADAR = [  # (callsign, type, alt ft, km, bearing, track)
    ("BAW283", "A35K", 36975, 3.2, 40, 280), ("EZY63LK", "A20N", 8400, 9.8, 300, 150),
    ("RYR4TX", "B38M", 34000, 14.5, 120, 300), ("UAE19", "A388", 38000, 21.0, 70, 110),
    ("LOG6KP", "AT76", 14000, 26.0, 200, 20), ("HLE65", "EC35", 1500, 6.1, 220, 260),
    ("VIR3", "B789", 39000, 33.0, 340, 270), ("DLH9CR", "A321", 31000, 37.5, 160, 95),
    ("KLM74P", "E190", 22000, 18.2, 255, 70), ("", "C172", 2500, 11.0, 15, 200),
]


def sample_radar():
    out = []
    for i, (cs, t, alt, km, brg, trk) in enumerate(RADAR):
        out.append(_f(hex=f"40{i:04x}", callsign=cs, type_code=t, altitude_ft=alt, distance_km=km,
                      bearing=brg, track=trk, speed_kt=300, registration="G-ABCD" if not cs else ""))
    return out


LHR = {"iata": "LHR", "city": "London", "lat": 51.4706, "lon": -0.46194}
LAX = {"iata": "LAX", "city": "Los Angeles", "lat": 33.9425, "lon": -118.408}
STN = {"iata": "STN", "city": "London", "lat": 51.885, "lon": 0.235}
DUB = {"iata": "DUB", "city": "Dublin", "lat": 53.4213, "lon": -6.27007}


def sample_track():
    """BA283 over Greenland, and a Ryanair hop to Dublin, with the paths flown so far."""
    from flightframe.trackmap import great_circle
    gc = great_circle((LHR["lat"], LHR["lon"]), (LAX["lat"], LAX["lon"]))
    ba = _f(callsign="BAW283", altitude_ft=38000, speed_kt=482, track=262, distance_km=0,
            lat=gc[27][0], lon=gc[27][1], registration="G-XWBC", type_code="A35K",
            airline="British Airways", airline_iata="BA", flight_iata="BA283", origin=LHR, destination=LAX)
    gc2 = great_circle((STN["lat"], STN["lon"]), (DUB["lat"], DUB["lon"]))
    fr = _f(callsign="RYR81SV", altitude_ft=36000, speed_kt=435, track=291, distance_km=0,
            lat=52.18, lon=-3.79, registration="EI-IFW", type_code="B38M",
            airline="Ryanair", airline_iata="FR", flight_iata="FR207", origin=STN, destination=DUB)
    return [("BA283", ba, gc[1:27:2]), ("FR207", fr, gc2[2:40:5])]


def sample_wx():
    from datetime import datetime, timedelta
    from flightframe import weather
    now = datetime.now().astimezone().replace(minute=0, second=0, microsecond=0)
    kinds = [("partly", True), ("showers", True), ("cloudy", True), ("clear", False), ("rain", False)]
    temps = [14, 13, 11, 9, 8]
    return {"sun": weather.sun_times(51.38, -2.36),
            "slots": [{"time": now + timedelta(hours=3 * i), "temp": t, "kind": k, "day": d}
                      for i, (t, (k, d)) in enumerate(zip(temps, kinds))]}


def _logo(f):
    return logos.get(logos.airline_icao(f.callsign, f.airline_icao), f.airline_iata)


def main(out):
    os.makedirs(out, exist_ok=True)
    cfg = dict(config.DEFAULTS, label="Home, Bath", lat=51.38, lon=-2.36, night_mode="light")
    for orient in ("landscape", "portrait"):
        cfg["orientation"] = orient
        for name, f in SAMPLES.items():
            render.poster(f, cfg, nearby=4, logo=_logo(f), wx=sample_wx()).save(f"{out}/{orient}-{name}.png")
        render.quiet(cfg, "BA283 LHR–LAX at 21:14", wx=sample_wx()).save(f"{out}/{orient}-quiet.png")
        a, b = SAMPLES["ba-widebody"], SAMPLES["easyjet-climbing"]
        render.duo([a, b], cfg, 2, logos=(_logo(a), _logo(b)), wx=sample_wx()).save(f"{out}/{orient}-duo.png")
        render.radar(sample_radar(), cfg, wx=sample_wx()).save(f"{out}/{orient}-radar.png")
        night = dict(cfg, night_mode="dark")
        wx = sample_wx()
        wx["slots"][0]["kind"] = "clear"
        render.poster(a, night, logo=_logo(a), wx=wx).save(f"{out}/{orient}-night.png")
        wx["slots"][0]["kind"] = "rain"
        render.duo([a, b], night, 2, logos=(_logo(a), _logo(b)), wx=wx).save(f"{out}/{orient}-night-duo-rain.png")
        render.radar(sample_radar(), night, wx=wx).save(f"{out}/{orient}-night-radar.png")
        from flightframe import trackmap
        for q, f, trail in sample_track():
            trackmap.tracker(cfg, q, f, trail=[(p[0], p[1]) for p in trail], wx=sample_wx()).save(
                f"{out}/{orient}-track-{q}.png")
        trackmap.tracker(night, "BA283", None, route={"origin": None}, state="unknown",
                         wx=sample_wx()).save(f"{out}/{orient}-track-unknown.png")
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
