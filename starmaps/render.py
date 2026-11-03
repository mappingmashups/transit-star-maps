"""Draw a station network as a constellation SVG.

Lines are drawn under a mask that cuts a clear gap around every star, so the
same drawing works on black or on a transparent background (for printing on
dark shirts) with no editing afterward.
"""

from __future__ import annotations

import math
import re
from html import escape
from pathlib import Path

from shapely.geometry import LineString

from .config import OUTPUT_DIR, STAR_SVG

VARIANTS = ("black", "transparent")


def star_path() -> str:
    """The star outline from assets/star.svg, in a 100 × 100 box."""
    return " ".join(re.search(r'<path d="([^"]+)"', STAR_SVG.read_text()).group(1).split())


def _fmt(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def layout(stations, segments, cfg):
    """Fit the rotated network into the page. Returns (to_px, width_px, height_px)."""
    m = cfg["map"]
    dpi = m["dpi"]
    a = math.radians(m["rotate_deg"])
    cos, sin = math.cos(a), math.sin(a)

    def rot(x, y):
        return x * cos - y * sin, x * sin + y * cos

    pts = [rot(s["x"], s["y"]) for s in stations]
    for seg in segments:
        pts += [rot(x, y) for x, y in seg["geometry"].coords]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    margin = m["margin_in"] * dpi
    width = round(m["width_in"] * dpi)
    max_h = m["max_height_in"] * dpi
    scale = min((width - 2 * margin) / max(maxx - minx, 1), (max_h - 2 * margin) / max(maxy - miny, 1))
    height = round((maxy - miny) * scale + 2 * margin)
    # Center horizontally when height was the limit.
    xoff = (width - (maxx - minx) * scale) / 2

    def to_px(x, y):
        rx, ry = rot(x, y)
        return xoff + (rx - minx) * scale, margin + (maxy - ry) * scale

    return to_px, width, height


def declutter(stations, segments, min_px, px_per_m):
    """Combine stars that would sit closer than `min_px` on the page.

    Clusters grow greedily from the closest pair, and only while their
    centers stay `min_px` apart, so a long row of evenly spaced stations
    doesn't collapse into one star. Lines are reattached to the new stars.
    """
    if min_px <= 0:
        return stations, segments
    limit = min_px / px_per_m
    clusters = [[s] for s in stations]

    def center(c):
        return (sum(s["x"] for s in c) / len(c), sum(s["y"] for s in c) / len(c))

    while True:
        best = None
        centers = [center(c) for c in clusters]
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                d = math.dist(centers[i], centers[j])
                if d < limit and (best is None or d < best[0]):
                    best = (d, i, j)
        if best is None:
            break
        _, i, j = best
        clusters[i] += clusters.pop(j)

    new_stations, rep = [], {}
    for c in clusters:
        x, y = center(c)
        main = max(c, key=lambda s: (s["rank"], s.get("degree", 0)))
        new_stations.append({**main, "x": x, "y": y, "rank": max(s["rank"] for s in c)})
        for s in c:
            rep[s["id"]] = new_stations[-1]
    new_segments = []
    for seg in segments:
        a, b = rep.get(seg["from"]), rep.get(seg["to"])
        if a is not None and a is b:
            continue
        coords = list(seg["geometry"].coords)
        for end, idx in ((a, 0), (b, -1)):
            if end is None:
                continue
            # Pin whichever end of the line is nearer this star.
            near = 0 if math.dist(coords[0], (end["x"], end["y"])) < math.dist(coords[-1], (end["x"], end["y"])) else -1
            coords[near] = (end["x"], end["y"])
        new_segments.append({**seg, "geometry": LineString(coords)})
    return new_stations, new_segments


def svg(stations, segments, cfg, variant: str = "black") -> str:
    st = cfg["style"]
    dpi = cfg["map"]["dpi"]
    to_px, W, H = layout(stations, segments, cfg)
    if st["minor_star_size_in"] <= 0:
        stations = [s for s in stations if s["rank"] != 0]
    p0, p1 = to_px(0, 0), to_px(1000, 0)
    stations, segments = declutter(
        stations, segments, st["min_star_spacing_in"] * dpi, math.dist(p0, p1) / 1000
    )
    if st["line_style"] == "straight":
        # Constellation-chart style: a straight stroke from star to star.
        segments = [
            {**seg, "geometry": LineString([seg["geometry"].coords[0], seg["geometry"].coords[-1]])}
            for seg in segments
        ]
    line_w = st["line_width_in"] * dpi
    gap = st["gap_in"] * dpi
    sizes = {0: st["minor_star_size_in"] * dpi, 1: st["star_size_in"] * dpi, 2: st["large_star_size_in"] * dpi}

    def star_transform(s):
        size = sizes.get(s["rank"], sizes[1])
        x, y = to_px(s["x"], s["y"])
        return size, f"translate({_fmt(x - size / 2)} {_fmt(y - size / 2)}) scale({size / 100:.4f})"

    # Big stars last so they sit on top where stars touch.
    ordered = sorted(stations, key=lambda s: (s["rank"], s["y"]))
    cut, stars = [], []
    for s in ordered:
        size, tf = star_transform(s)
        # The stroke is centered on the outline, so it is twice the gap, in star units.
        # Smaller stars get a proportionally smaller gap.
        g = gap * min(1.0, size / sizes[1])
        cut.append(f'<use href="#star" transform="{tf}" stroke-width="{2 * g * 100 / size:.2f}"/>')
        stars.append(f'<use href="#star" transform="{tf}"><title>{escape(s["name"])}</title></use>')

    paths = []
    for seg in segments:
        pts = [to_px(x, y) for x, y in seg["geometry"].coords]
        d = "M" + " L".join(f"{_fmt(x)} {_fmt(y)}" for x, y in pts)
        paths.append(f'<path d="{d}"/>')

    bg = f'<rect width="{W}" height="{H}" fill="{st["background"]}"/>' if variant == "black" else ""
    nl = "\n    "
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <title>{escape(cfg["name"])}</title>
  <defs>
    <path id="star" d="{star_path()}"/>
    <mask id="gaps" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}">
      <rect width="{W}" height="{H}" fill="#fff"/>
      <g fill="#000" stroke="#000" stroke-linejoin="round">
    {nl.join(cut)}
      </g>
    </mask>
  </defs>
  {bg}
  <g mask="url(#gaps)" fill="none" stroke="{st["line_color"]}" stroke-width="{_fmt(line_w)}" stroke-linecap="round" stroke-linejoin="round">
    {nl.join(paths)}
  </g>
  <g fill="{st["star_color"]}">
    {nl.join(stars)}
  </g>
</svg>
"""


def output_paths(cfg) -> dict[str, Path]:
    out = OUTPUT_DIR / cfg["id"]
    return {v: out / f"{cfg['id']}_{v}.svg" for v in VARIANTS}


def render(stations, segments, cfg) -> list[Path]:
    written = []
    for variant, path in output_paths(cfg).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(svg(stations, segments, cfg, variant))
        written.append(path)
    return written
