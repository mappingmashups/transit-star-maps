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


def svg(stations, segments, cfg, variant: str = "black") -> str:
    st = cfg["style"]
    dpi = cfg["map"]["dpi"]
    to_px, W, H = layout(stations, segments, cfg)
    line_w = st["line_width_in"] * dpi
    gap = st["gap_in"] * dpi
    sizes = {1: st["star_size_in"] * dpi, 2: st["large_star_size_in"] * dpi}

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
        cut.append(f'<use href="#star" transform="{tf}" stroke-width="{2 * gap * 100 / size:.2f}"/>')
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
