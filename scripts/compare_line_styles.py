"""Render every current city with curved and with straight lines, side by side.

    python scripts/compare_line_styles.py [city ...]
    -> outputs/<city>/<city>_black_straight.{svg,png} and outputs/compare_line_styles.png
"""

import base64
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from starmaps import config, network, raster, render  # noqa: E402


def main(cities):
    from playwright.sync_api import sync_playwright

    rows = []
    for city in cities:
        cfg = config.load(city)
        if not network.network_path(city).exists():
            continue
        _, stations, segments = network.load(city)
        out = config.OUTPUT_DIR / city
        curved = out / f"{city}_black.png"
        if not curved.exists():
            continue
        cfg["style"]["line_style"] = "straight"
        svg_path = out / f"{city}_black_straight.svg"
        svg_path.write_text(render.svg(stations, segments, cfg, "black"))
        (straight,) = raster.to_png([svg_path], cfg["map"]["dpi"])
        rows.append((cfg["name"], curved, straight))
        print(f"wrote {straight.relative_to(ROOT)}")

    def img(p):
        return f'<img src="data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}">'

    html = """<!doctype html><style>
      body { margin: 0; background: #222; color: #eee; font: 16px sans-serif; }
      table { border-spacing: 12px; } th { text-align: left; width: 110px; }
      td { background: #000; width: 560px; height: 560px; text-align: center; }
      img { max-width: 560px; max-height: 560px; vertical-align: middle; }
      thead th { text-align: center; }
    </style><table><thead><tr><th></th><th>Curved (follows the track)</th><th>Straight</th></tr></thead>"""
    html += "".join(f"<tr><th>{n}</th><td>{img(a)}</td><td>{img(b)}</td></tr>" for n, a, b in rows)
    html += "</table>"
    launch = {"executable_path": os.environ["CHROME_PATH"]} if os.environ.get("CHROME_PATH") else {}
    sheet = config.OUTPUT_DIR / "compare_line_styles.png"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.set_content(html)
        page.screenshot(path=str(sheet), full_page=True)
        browser.close()
    print(f"wrote {sheet.relative_to(ROOT)}")


if __name__ == "__main__":
    default = ["bart", "la_metro", "trimet_max", "bc_skytrain", "montreal",
               "seattle_link", "boston_mbta", "dc_metro"]
    main(sys.argv[1:] or default)
