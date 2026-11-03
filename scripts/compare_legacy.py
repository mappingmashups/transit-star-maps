"""Put each 2016 TileMill render next to the new render of the same data.

    python scripts/compare_legacy.py   # -> outputs/compare_legacy.png
"""

import base64
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAIRS = [
    ("BART", "legacy/outputs/bart_v0.2.png", "outputs/bart_2016/bart_2016_black.png"),
    ("LA Metro", "legacy/outputs/la_metro_v0.1.png", "outputs/la_metro_2016/la_metro_2016_black.png"),
    ("TriMet MAX", "legacy/outputs/trimet_max_v0.1.png", "outputs/trimet_max_2016/trimet_max_2016_black.png"),
    ("SkyTrain", "legacy/outputs/bc_skytrain_v0.1.png", "outputs/bc_skytrain_2016/bc_skytrain_2016_black.png"),
    ("Toronto", "legacy/outputs/toronto_v0.1.png", "outputs/toronto_2016/toronto_2016_black.png"),
    ("Montréal", "legacy/outputs/montreal_v0.1.png", "outputs/montreal_2016/montreal_2016_black.png"),
]


def img(path):
    data = base64.b64encode((ROOT / path).read_bytes()).decode()
    return f'<img src="data:image/png;base64,{data}">'


def main(out=ROOT / "outputs" / "compare_legacy.png"):
    from playwright.sync_api import sync_playwright

    rows = "".join(
        f"<tr><th>{name}</th><td>{img(old)}</td><td>{img(new)}</td></tr>"
        for name, old, new in PAIRS
        if (ROOT / old).exists() and (ROOT / new).exists()
    )
    html = f"""<!doctype html><style>
      body {{ margin: 0; background: #222; color: #eee; font: 16px sans-serif; }}
      table {{ border-spacing: 12px; }} th {{ text-align: left; width: 90px; }}
      td {{ background: #000; width: 560px; height: 560px; text-align: center; }}
      img {{ max-width: 560px; max-height: 560px; vertical-align: middle; }}
      thead th {{ text-align: center; }}
    </style><table><thead><tr><th></th><th>2016 TileMill</th><th>New, same 2016 data</th></tr></thead>{rows}</table>"""
    launch = {"executable_path": os.environ["CHROME_PATH"]} if os.environ.get("CHROME_PATH") else {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch)
        page = browser.new_page(viewport={"width": 1260, "height": 800})
        page.set_content(html)
        page.screenshot(path=str(out), full_page=True)
        browser.close()
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main(*(Path(a) for a in sys.argv[1:]))
