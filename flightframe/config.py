"""Settings, stored as JSON so the phone settings page can edit them."""
import json
import os
import threading

STATE_DIR = os.environ.get("FRAME_STATE_DIR", "/var/lib/flightframe")
CONFIG_PATH = os.path.join(STATE_DIR, "config.json")

DEFAULTS = {
    "label": "",                 # shown in the footer, e.g. "Home, Bath"
    "lat": None,
    "lon": None,
    "radius_km": 15,             # how far out counts as "overhead"
    "max_altitude_ft": 0,        # 0 = no limit
    "units": "metric",           # metric | imperial
    "orientation": "landscape",  # landscape | portrait
    "accent": "red",             # red | blue | green | yellow
    "show_plane": True,          # aircraft drawing with the airline logo on the tail
    "poll_seconds": 30,          # how often to ask the API
    "min_refresh_seconds": 180,  # Spectra 6 panels want >= 180 s between refreshes
    "stats_refresh_minutes": 10, # redraw the same flight this often to update height/speed
    "quiet_start": "",           # "23:00", empty = off
    "quiet_end": "",             # "07:00"
    "display": "auto",           # auto | inky | waveshare | preview
    "flip": False,               # turn the picture upside down to suit the mounting
    "hotspot_ssid": "Flightframe-Setup",
    "hotspot_password": "skyabove",
}

_lock = threading.Lock()


def load():
    with _lock:
        cfg = dict(DEFAULTS)
        try:
            with open(CONFIG_PATH) as f:
                cfg.update(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return cfg


def save(cfg):
    with _lock:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump({k: cfg.get(k, v) for k, v in DEFAULTS.items()}, f, indent=2)
        os.replace(tmp, CONFIG_PATH)


def has_location(cfg):
    return cfg.get("lat") is not None and cfg.get("lon") is not None
