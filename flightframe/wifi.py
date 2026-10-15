"""Wi-Fi setup through NetworkManager (Raspberry Pi OS Bookworm and later).

If the Pi has no network at boot it opens its own hotspot. You join it from
your phone, pick your home Wi-Fi on the settings page, and it switches over.
"""
import logging
import shutil
import subprocess
import time

log = logging.getLogger(__name__)
IFACE = "wlan0"
HOTSPOT_CON = "flightframe-hotspot"
HOTSPOT_IP = "10.42.0.1"   # NetworkManager's default for shared connections

_cached_networks = []


def available():
    return shutil.which("nmcli") is not None


def _nmcli(*args, timeout=30):
    r = subprocess.run(["nmcli", *args], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip() or f"nmcli {' '.join(args)} failed")
    return r.stdout


def online():
    """True when NetworkManager reports a full internet connection."""
    if not available():
        return True   # not our problem on a dev machine
    try:
        state = _nmcli("-t", "-f", "CONNECTIVITY", "general", timeout=10).strip()
        return state == "full"
    except Exception:
        return False


def hotspot_active():
    if not available():
        return False
    try:
        out = _nmcli("-t", "-f", "NAME", "connection", "show", "--active", timeout=10)
        return HOTSPOT_CON in out.split()
    except Exception:
        return False


def wait_for_network(seconds=45):
    end = time.time() + seconds
    while time.time() < end:
        if online():
            return True
        time.sleep(3)
    return online()


def scan():
    """Visible networks, strongest first. Cached so it still works in hotspot mode
    (the radio can't scan properly while it is the access point)."""
    global _cached_networks
    if not available():
        return []
    try:
        if not hotspot_active():
            _nmcli("device", "wifi", "rescan", "ifname", IFACE, timeout=20)
            time.sleep(2)
        out = _nmcli("-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list",
                     "ifname", IFACE, timeout=20)
    except Exception as e:
        log.info("wifi scan failed: %s", e)
        return _cached_networks
    seen = {}
    for line in out.splitlines():
        parts = line.replace("\\:", "\0").split(":")
        if len(parts) < 3:
            continue
        ssid, signal, sec = (p.replace("\0", ":") for p in parts[:3])
        if not ssid:
            continue
        sig = int(signal or 0)
        if ssid not in seen or seen[ssid]["signal"] < sig:
            seen[ssid] = {"ssid": ssid, "signal": sig, "secure": bool(sec and sec != "--")}
    nets = sorted(seen.values(), key=lambda n: -n["signal"])
    if nets:
        _cached_networks = nets
    return nets or _cached_networks


def start_hotspot(ssid, password):
    scan()   # remember what's around before the radio becomes an access point
    try:
        _nmcli("connection", "delete", HOTSPOT_CON, timeout=15)
    except Exception:
        pass
    _nmcli("device", "wifi", "hotspot", "ifname", IFACE, "con-name", HOTSPOT_CON,
           "ssid", ssid, "password", password)
    log.info("hotspot %s up at %s", ssid, HOTSPOT_IP)


def stop_hotspot():
    try:
        _nmcli("connection", "down", HOTSPOT_CON, timeout=15)
    except Exception:
        pass


def connect(ssid, password=""):
    """Join a network. Drops the hotspot first; brings it back if joining fails."""
    was_hotspot = hotspot_active()
    if was_hotspot:
        stop_hotspot()
        time.sleep(2)
        try:
            _nmcli("device", "wifi", "rescan", "ifname", IFACE, timeout=20)
            time.sleep(4)
        except Exception:
            pass
    args = ["device", "wifi", "connect", ssid, "ifname", IFACE]
    if password:
        args += ["password", password]
    try:
        _nmcli(*args, timeout=60)
        return True, ""
    except Exception as e:
        log.warning("could not join %s: %s", ssid, e)
        return False, str(e)
