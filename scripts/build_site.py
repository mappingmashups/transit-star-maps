"""Build the GitHub Pages site in docs/ from site/maps.yaml.

    .venv/bin/python scripts/build_site.py

Copies each listed map's transparent SVG to docs/maps/ (re-rendered when the
list overrides the line style), and fills site/index.template.html.
"""

import datetime as dt
import random
import shutil
import sys
from html import escape
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from starmaps import config, network, render  # noqa: E402

DOCS = ROOT / "docs"
SITE = ROOT / "site"


def starfield(n, seed, size=2400):
    rng = random.Random(seed)
    return ", ".join(
        f"{rng.randrange(size)}px {rng.randrange(size)}px #fff" for _ in range(n)
    )


def map_svg(entry) -> Path:
    city = entry["city"]
    out = DOCS / "maps" / f"{city}.svg"
    out.parent.mkdir(parents=True, exist_ok=True)
    cfg = config.load(city)
    style = entry.get("line_style")
    if style and style != cfg["style"]["line_style"]:
        cfg["style"]["line_style"] = style
        _, stations, segments = network.load(city)
        out.write_text(render.svg(stations, segments, cfg, "transparent"))
    else:
        src = config.OUTPUT_DIR / city / f"{city}_transparent.svg"
        if not src.exists():
            raise SystemExit(f"{src.relative_to(ROOT)} missing; run `python -m starmaps build {city}`")
        shutil.copyfile(src, out)
    return out


def card(entry, svg_path):
    rel = svg_path.relative_to(DOCS).as_posix()
    place, system = escape(entry["place"]), escape(entry["system"])
    shop = entry.get("shop") or ""
    button = f'<a class="button" href="{escape(shop)}" target="_blank" rel="noopener">Shop</a>' if shop else ""
    note = f'<p class="note">{escape(entry["note"])}</p>' if entry.get("note") else ""
    alt = f"{entry['system']} in {entry['place']} drawn as a constellation"
    return f"""    <article class="card">
      <button class="frame" type="button" data-src="{rel}" data-title="{place} · {system}" data-shop="{escape(shop)}" aria-label="Enlarge {place}">
        <img src="{rel}" alt="{escape(alt)}" loading="lazy">
      </button>
      <div class="caption">
        <div><h2 class="place">{place}</h2><p class="system">{system}</p>{note}</div>
        {button}
      </div>
    </article>"""


def social_card(site, entry):
    """Render docs/social-card.png (1200 x 630), the link-preview image."""
    import os
    import tempfile

    from playwright.sync_api import sync_playwright

    html = (SITE / "card.template.html").read_text()
    values = {
        "tagline": escape(site["tagline"]),
        "caption": escape(f"{entry['system']} · {entry['place']}"),
        "map_src": "map.svg",
        "stars_small": starfield(180, 3, 1200),
        "stars_big": starfield(40, 4, 1200),
    }
    for key, value in values.items():
        html = html.replace("{{" + key + "}}", value)
    launch = {"executable_path": os.environ["CHROME_PATH"]} if os.environ.get("CHROME_PATH") else {}
    with tempfile.TemporaryDirectory() as tmp:
        page_path = Path(tmp) / "card.html"
        page_path.write_text(html)
        # The card shows the map at about a fifth of print size, so draw it
        # with bolder stars and lines than the print file.
        cfg = config.load(entry["city"])
        st = cfg["style"]
        for key, factor in (("star_size_in", 1.8), ("large_star_size_in", 1.8), ("minor_star_size_in", 1.8),
                            ("line_width_in", 1.7), ("gap_in", 1.6)):
            st[key] *= factor
        if entry.get("line_style"):
            st["line_style"] = entry["line_style"]
        _, stations, segments = network.load(entry["city"])
        (Path(tmp) / "map.svg").write_text(render.svg(stations, segments, cfg, "transparent"))
        with sync_playwright() as pw:
            browser = pw.chromium.launch(**launch)
            page = browser.new_page(viewport={"width": 1200, "height": 630})
            page.goto(page_path.as_uri())
            page.wait_for_load_state("networkidle")
            page.evaluate("document.fonts.ready")
            page.screenshot(path=str(DOCS / "social-card.png"))
            browser.close()


def main():
    site = yaml.safe_load((SITE / "maps.yaml").read_text())
    DOCS.mkdir(exist_ok=True)
    maps_dir = DOCS / "maps"
    if maps_dir.exists():
        shutil.rmtree(maps_dir)
    cards = [card(e, map_svg(e)) for e in site["maps"]]
    links = " ".join(
        f'<a href="{escape(l["url"])}">{escape(l["label"])}</a>' for l in site.get("links", []) if l.get("url")
    )
    shop_all = (
        f'<a class="button shop-all" href="{escape(site["shop_all"])}">Shop all shirts</a>' if site.get("shop_all") else ""
    )
    url = site["url"].rstrip("/") + "/"
    card_entry = next((e for e in site["maps"] if e["city"] == site["card_map"]), None)
    if card_entry is None:
        raise SystemExit(f"card_map {site['card_map']!r} must be one of the maps listed")
    card_alt = f"{site['title']}: {card_entry['system']} in {card_entry['place']} drawn as a constellation"
    social_card(site, card_entry)
    values = {
        "title": escape(site["title"]),
        "tagline": escape(site["tagline"]),
        "about": escape(site["about"].strip()),
        "shop_all": shop_all,
        "cards": "\n".join(cards),
        "links": links,
        "year": str(dt.date.today().year),
        "url": escape(url),
        "card_alt": escape(card_alt),
        "stars_small": starfield(260, 1),
        "stars_big": starfield(60, 2),
    }
    html = (SITE / "index.template.html").read_text()
    for key, value in values.items():
        html = html.replace("{{" + key + "}}", value)
    (DOCS / "index.html").write_text(html)
    shutil.copyfile(SITE / "favicon.svg", DOCS / "favicon.svg")
    (DOCS / ".nojekyll").write_text("")
    shutil.copyfile(SITE / "CNAME", DOCS / "CNAME")
    print(f"wrote docs/index.html with {len(cards)} maps")


if __name__ == "__main__":
    main()
