"""Download a city's source data into data/raw/<city>/, once.

The download is kept with a small JSON record of where and when it came from
and its SHA-256, so later builds reuse exactly the same snapshot until you ask
for a refresh.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path

from .config import RAW_DIR

USER_AGENT = "transit-star-maps (https://github.com/mappingmashups/transit-star-maps)"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def gtfs_path(cfg: dict) -> Path:
    return RAW_DIR / cfg["id"] / "gtfs.zip"


def fetch(cfg: dict, refresh: bool = False) -> Path | None:
    src = cfg["source"]
    if src["type"] != "gtfs":
        return None  # linework sources point at files already in the repo
    dest = gtfs_path(cfg)
    meta_path = dest.with_suffix(".json")
    if dest.exists() and not refresh:
        print(f"[{cfg['id']}] using cached {dest.relative_to(RAW_DIR.parent.parent)}")
        return dest
    if not src.get("url"):
        raise SystemExit(f"[{cfg['id']}] no source.url to download")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    print(f"[{cfg['id']}] downloading {src['url']}")
    req = urllib.request.Request(src["url"], headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=300) as resp, tmp.open("wb") as out:
        shutil.copyfileobj(resp, out)
    try:
        with zipfile.ZipFile(tmp) as zf:
            names = {n.rsplit("/", 1)[-1] for n in zf.namelist()}
    except zipfile.BadZipFile:
        names = set()
    if not {"stops.txt", "routes.txt", "trips.txt", "stop_times.txt"} <= names:
        tmp.unlink()
        raise SystemExit(f"[{cfg['id']}] {src['url']} did not return a GTFS zip (got {sorted(names)[:8]})")
    digest = sha256(tmp)
    if src.get("sha256") and src["sha256"] != digest:
        print(
            f"[{cfg['id']}] WARNING: download differs from pinned sha256 "
            f"{src['sha256'][:12]}… (got {digest[:12]}…). The feed has changed; "
            "update the pin in the city config once you have checked the result."
        )
    tmp.replace(dest)
    meta = {
        "url": src["url"],
        "fetched": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "sha256": digest,
        "bytes": dest.stat().st_size,
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    print(f"[{cfg['id']}] saved {dest} ({meta['bytes'] / 1e6:.1f} MB, sha256 {digest[:12]}…)")
    return dest


def source_meta(cfg: dict) -> dict:
    meta_path = gtfs_path(cfg).with_suffix(".json")
    if meta_path.exists():
        return json.loads(meta_path.read_text())
    return {}
