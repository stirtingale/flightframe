"""Build flightframe/data/coast.json from Natural Earth (public domain).

    curl -O https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_land.geojson
    curl -O https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_boundary_lines_land.geojson
    python3 tools/build_coast.py <folder with those files>

Output: {"coast": [[lon, lat, lon, lat, ...], ...], "borders": [...]}, coordinates
in hundredths of a degree, lightly simplified. About 400 KB, loaded only by the
flight tracker screen.
"""
import json
import os
import sys


def simplify(pts, tol):
    """Douglas-Peucker on a list of (x, y)."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = pts[a]; bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        norm = (dx * dx + dy * dy) ** 0.5 or 1e-12
        best, idx = 0.0, None
        for i in range(a + 1, b):
            px, py = pts[i]
            if norm < 1e-9:                     # closed ring: distance from the start point
                d = ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
            else:
                d = abs(dy * (px - ax) - dx * (py - ay)) / norm
            if d > best:
                best, idx = d, i
        if idx is not None and best > tol:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(pts, keep) if k]


def lines(geo, polygons):
    for feat in geo["features"]:
        g = feat["geometry"]
        t, cs = g["type"], g["coordinates"]
        if t == "Polygon":
            yield from cs
        elif t == "MultiPolygon":
            for poly in cs:
                yield from poly
        elif t == "LineString":
            yield cs
        elif t == "MultiLineString":
            yield from cs


def pack(geo, tol, min_pts):
    out = []
    for ring in lines(geo, True):
        s = simplify([tuple(p) for p in ring], tol)
        if len(s) < min_pts:
            continue
        flat = []
        for x, y in s:
            flat += [round(x * 100), round(y * 100)]
        out.append(flat)
    return out


def main(src):
    land = json.load(open(os.path.join(src, "ne_50m_land.geojson")))
    border = json.load(open(os.path.join(src, "ne_50m_admin_0_boundary_lines_land.geojson")))
    data = {"coast": pack(land, 0.03, 4), "borders": pack(border, 0.05, 2)}
    dst = os.path.join(os.path.dirname(__file__), "..", "flightframe", "data", "coast.json")
    with open(dst, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print(dst, os.path.getsize(dst), "bytes,", len(data["coast"]), "coast rings,",
          len(data["borders"]), "border lines")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
