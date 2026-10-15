"""The four buttons on the side of the Inky Impression.

  A (top)     refresh the screen now
  B           (spare)
  C           (spare)
  D (bottom)  show the settings page address and QR code

Pin numbers are from Pimoroni's examples (BCM 5, 6, 16, 24). Does nothing if the
gpiod libraries aren't there, e.g. with a Waveshare panel or on a laptop.
"""
import logging
import threading
import time

log = logging.getLogger(__name__)
PINS = {5: "A", 6: "B", 16: "C", 24: "D"}


def start(worker):
    try:
        import gpiod
        import gpiodevice
        from gpiod.line import Bias, Direction, Edge
    except ImportError:
        log.info("buttons: gpiod not installed, skipping")
        return None
    try:
        chip = gpiodevice.find_chip_by_platform()
        settings = gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP,
                                      edge_detection=Edge.FALLING)
        offsets = {chip.line_offset_from_id(pin): label for pin, label in PINS.items()}
        request = chip.request_lines(consumer="flightframe-buttons",
                                     config=dict.fromkeys(offsets, settings))
    except Exception as e:
        log.info("buttons: not available (%s)", e)
        return None

    def loop():
        last = {}
        while True:
            try:
                for ev in request.read_edge_events():
                    label = offsets.get(ev.line_offset)
                    now = time.time()
                    if now - last.get(label, 0) < 1.0:   # debounce
                        continue
                    last[label] = now
                    log.info("button %s", label)
                    if label == "A":
                        worker.poke(force=True)
                    elif label == "D":
                        worker.show_settings_screen()
            except Exception:
                log.exception("button loop error")
                time.sleep(5)

    t = threading.Thread(target=loop, daemon=True, name="buttons")
    t.start()
    log.info("buttons ready (A refresh, D settings)")
    return t
