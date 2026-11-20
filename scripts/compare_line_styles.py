"""Render cities with curved and with straight lines, side by side.

    python scripts/compare_line_styles.py [city ...]

Both styles are drawn explicitly, whatever the city config's default is:
  outputs/<city>/<city>_black_curved.{svg,png}
  outputs/<city>/<city>_black_straight.{svg,png}
  outputs/compare/<city>.png           one city, the two styles side by side
  outputs/compare_line_styles.png      every city in one sheet
"""

import base64
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from starmaps import config, network, raster, render  # noqa: E402

DEFAULT = ["bart", "la_metro", "trimet_max", "bc_skytrain", "montreal", "seattle_link",
           "boston_mbta", "dc_metro", "cahsr"]

STYLE = """<!doctype html><style>
  body { margin: 0; background: #222; color: #eee; font: 16px sans-serif; }
  table { border-spacing: 12px; } th { text-align: left; width: 110px; }
  td { background: #000; width: 600px; height: 600px; text-align: center; }
  img { max-width: 600px; max-height: 600px; vertical-align: middle; }
  thead th { text-align: center; }
  h1 { font-size: 22px; margin: 16px 12px 0; }
</style>"""


def img(p):
    return f'<img src="data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}">'


def screenshot(browser, html, path):
    page = browser.new_page(viewport={"width": 1280, "height": 700})
    page.set_content(html)
    page.screenshot(path=str(path), full_page=True)
    page.close()
    print(f"wrote {path.relative_to(ROOT)}")


def main(cities):
    from playwright.sync_api import sync_playwright

    rows = []
    for city in cities:
        if not network.network_path(city).exists():
            print(f"skip {city}: no network")
            continue
        _, stations, segments = network.load(city)
        out = config.OUTPUT_DIR / city
        out.mkdir(parents=True, exist_ok=True)
        pngs = {}
        for style in ("curved", "straight"):
            cfg = config.load(city)
            cfg["style"]["line_style"] = style
            svg_path = out / f"{city}_black_{style}.svg"
            svg_path.write_text(render.svg(stations, segments, cfg, "black"))
            (pngs[style],) = raster.to_png([svg_path], cfg["map"]["dpi"])
        default = config.load(city)["style"]["line_style"]
        rows.append((city, config.load(city)["name"], default, pngs["curved"], pngs["straight"]))

    def head(default):
        mark = lambda s: " (current)" if s == default else ""  # noqa: E731
        return (f"<thead><tr><th></th><th>Curved{mark('curved')}</th>"
                f"<th>Straight{mark('straight')}</th></tr></thead>")

    launch = {"executable_path": os.environ["CHROME_PATH"]} if os.environ.get("CHROME_PATH") else {}
    (config.OUTPUT_DIR / "compare").mkdir(exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch)
        for city, name, default, curved, straight in rows:
            html = (STYLE + f"<h1>{name}</h1><table>{head(default)}"
                    f"<tr><th></th><td>{img(curved)}</td><td>{img(straight)}</td></tr></table>")
            screenshot(browser, html, config.OUTPUT_DIR / "compare" / f"{city}.png")
        body = "".join(
            f"<tr><th>{name}<br><small>now: {default}</small></th><td>{img(c)}</td><td>{img(s)}</td></tr>"
            for _, name, default, c, s in rows
        )
        sheet = (STYLE + "<table><thead><tr><th></th><th>Curved</th><th>Straight</th></tr></thead>"
                 + body + "</table>")
        screenshot(browser, sheet, config.OUTPUT_DIR / "compare_line_styles.png")
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT)
