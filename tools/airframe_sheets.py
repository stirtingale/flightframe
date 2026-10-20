"""Draw every type in the archive onto contact sheets, one per family.

    python3 tools/airframe_sheets.py            # writes docs/airframes/*.png and docs/airframes/README.md
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image, ImageDraw          # noqa: E402

from flightframe import airframes, plane  # noqa: E402
from flightframe.render import as_seen, font  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "docs", "airframes")
GREEN = (0, 255, 0)
FAMILY_TITLES = [("jet", "Jets"), ("turboprop", "Turboprops"), ("light", "Light aircraft"),
                 ("heli", "Helicopters"), ("other", "Military, gliders and balloons")]


def family_of(spec):
    f = spec.get("family", "jet")
    if f in ("tandem", "fighter", "glider", "balloon"):
        return "other"
    return f


def sheet(codes, sp, cols=4, cell=(300, 120), label_h=34):
    rows = (len(codes) + cols - 1) // cols
    W, H = cols * cell[0] + 20, rows * (cell[1] + label_h) + 20
    im = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.fontmode = "1"
    for i, code in enumerate(codes):
        x = 10 + (i % cols) * cell[0]
        y = 10 + (i // cols) * (cell[1] + label_h)
        art = plane.draw(code, cell[0] - 24, cell[1] - 10, accent=GREEN)
        im.paste(art, (x + (cell[0] - art.width) // 2, y + (cell[1] - art.height) // 2))
        d.text((x + 10, y + cell[1] + 2), code, font=font("bold", 15), fill=(0, 0, 0))
        name = sp[code]["name"]
        d.text((x + 10 + d.textlength(code, font=font("bold", 15)) + 8, y + cell[1] + 3), name,
               font=font("regular", 14), fill=(0, 0, 0))
    return im


def main():
    os.makedirs(OUT, exist_ok=True)
    sp = airframes.specs()
    groups = {}
    for code, spec in sp.items():
        groups.setdefault(family_of(spec), []).append(code)
    lines = ["# Aircraft drawings", "",
             f"Every type the frame can draw: {len(sp)} in total. Each is built from approximate dimensions in "
             "[`flightframe/data/airframes.json`](../../flightframe/data/airframes.json), "
             "generated from [`tools/build_airframes.py`](../../tools/build_airframes.py).", "",
             "The frame downloads the latest archive from this repository once a day, so new types appear "
             "without reinstalling. Unknown types fall back to the closest code, then to the broadcast category.",
             "", "To add a type, add a line to `tools/build_airframes.py` (often just `like=` an existing type with a "
             "different length), run it, then run `tools/airframe_sheets.py` and commit.", ""]
    for fam, title in FAMILY_TITLES:
        codes = groups.get(fam, [])
        if not codes:
            continue
        fname = f"{fam}.png"
        as_seen(sheet(codes, sp)).save(os.path.join(OUT, fname), optimize=True)
        lines += [f"## {title} ({len(codes)})", "", f"![{title}]({fname})", ""]
        lines += ["| Code | Aircraft |", "|---|---|"] + [f"| `{c}` | {sp[c]['name']} |" for c in codes] + [""]
    with open(os.path.join(OUT, "README.md"), "w") as f:
        f.write("\n".join(lines))
    print("sheets written to", os.path.normpath(OUT))


if __name__ == "__main__":
    main()
