"""Rasterize SVGs to PNG with headless Chromium (Playwright)."""

from __future__ import annotations

import os
import re
import struct
import zlib
from pathlib import Path


def _set_dpi(png: bytes, dpi: int) -> bytes:
    """Insert a pHYs chunk so print tools read the intended size in inches."""
    ppm = round(dpi / 0.0254)
    data = b"pHYs" + struct.pack(">IIB", ppm, ppm, 1)
    chunk = struct.pack(">I", 9) + data + struct.pack(">I", zlib.crc32(data) & 0xFFFFFFFF)
    end_of_ihdr = 8 + 4 + 4 + 13 + 4
    return png[:end_of_ihdr] + chunk + png[end_of_ihdr:]


def to_png(svg_paths: list[Path], dpi: int) -> list[Path]:
    from playwright.sync_api import sync_playwright

    out = []
    launch = {}
    if os.environ.get("CHROME_PATH"):
        launch["executable_path"] = os.environ["CHROME_PATH"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch)
        for svg_path in svg_paths:
            text = svg_path.read_text()
            w, h = (int(v) for v in re.search(r'width="(\d+)" height="(\d+)"', text).groups())
            page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
            page.set_content(
                f"<!doctype html><html><body style='margin:0;background:transparent'>{text}</body></html>"
            )
            png = page.screenshot(omit_background=True, clip={"x": 0, "y": 0, "width": w, "height": h})
            page.close()
            png_path = svg_path.with_suffix(".png")
            png_path.write_bytes(_set_dpi(png, dpi))
            out.append(png_path)
        browser.close()
    return out
