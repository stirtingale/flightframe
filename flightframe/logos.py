"""Airline logos for the tail fin, downloaded once and kept on the SD card.

Sources, tried in order:
  1. FlightAware-style marks from github.com/Jxck-S/airline-logos (by ICAO code, e.g. BAW)
  2. RadarBox-style marks from the same repository (by ICAO code)
  3. Kiwi.com airline icons (by IATA code, e.g. BA)

Logos remain the trademarks of their airlines. They are fetched for display on
your own frame, the same way flight-tracking apps show them.
"""
import io
import logging
import os
import re
import time

import requests
from PIL import Image

from .config import STATE_DIR

log = logging.getLogger(__name__)
CACHE = os.path.join(STATE_DIR, "logos")
RETRY_MISS_AFTER = 7 * 24 * 3600
UA = {"User-Agent": "flightframe-pi/1.1 (personal flight display)"}
REPO = "https://raw.githubusercontent.com/Jxck-S/airline-logos/main"

_mem = {}


def airline_icao(callsign, known=""):
    """ICAO airline code: from the route database, or the callsign (BAW283 -> BAW)."""
    if known and re.fullmatch(r"[A-Z]{3}", known.upper()):
        return known.upper()
    m = re.match(r"^([A-Z]{3})\d", (callsign or "").upper())
    return m.group(1) if m else ""


def _sources(icao, iata):
    if icao:
        yield f"{REPO}/flightaware_logos/{icao}.png"
        yield f"{REPO}/radarbox_logos/{icao}.png"
    if iata and re.fullmatch(r"[A-Z0-9]{2}", iata.upper()):
        yield f"https://images.kiwi.com/airlines/128/{iata.upper()}.png"


def get(icao, iata="", session=None):
    """PIL image of the airline's logo, or None. Never raises."""
    key = icao or iata
    if not key:
        return None
    if key in _mem:
        return _mem[key]
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"{key}.png")
    miss = os.path.join(CACHE, f"{key}.miss")
    img = None
    if os.path.exists(path):
        try:
            img = Image.open(path)
            img.load()
        except Exception:
            img = None
    elif not (os.path.exists(miss) and time.time() - os.path.getmtime(miss) < RETRY_MISS_AFTER):
        img = _download(icao, iata, session or requests)
        if img is not None:
            img.save(path)
            if os.path.exists(miss):
                os.remove(miss)
        else:
            open(miss, "w").close()
    _mem[key] = img
    return img


def _download(icao, iata, s):
    for url in _sources(icao, iata):
        try:
            r = s.get(url, timeout=10, headers=UA)
            if r.status_code != 200 or len(r.content) < 200:
                continue
            img = Image.open(io.BytesIO(r.content))
            img.load()
            if min(img.size) < 24:
                continue
            log.info("logo for %s from %s", icao or iata, url.split("/")[2])
            return img.convert("RGBA")
        except Exception as e:
            log.debug("logo %s failed: %s", url, e)
    return None
