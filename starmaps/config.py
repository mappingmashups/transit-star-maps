"""Load per-city YAML configs and fill in defaults."""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CITIES_DIR = ROOT / "cities"
RAW_DIR = ROOT / "data" / "raw"
NETWORKS_DIR = ROOT / "networks"
OUTPUT_DIR = ROOT / "outputs"
STAR_SVG = ROOT / "assets" / "star.svg"

DEFAULTS = {
    "name": None,
    "source": {
        "type": "gtfs",  # gtfs | linework
        "url": None,
        "sha256": None,  # optional pin; fetch warns if the download differs
        # GTFS route_type values to keep: 0 tram/light rail, 1 subway/metro,
        # 2 rail, 12 monorail. Buses (3) are always left out unless listed.
        "route_types": [0, 1, 2, 12],
        # Regexes matched against route_id, route_short_name and route_long_name.
        "include_routes": [],
        "exclude_routes": [],
        # linework sources: path (or list of paths) to station points and to
        # route lines, in any format geopandas reads, with optional pandas
        # query strings to pick rows.
        "stations": None,
        "lines": None,
        "stations_query": None,
        "lines_query": None,
        "station_name_field": "name",
        "snap_m": 120,  # linework: how far a station may be from its line
        # linework: track junctions this close to a station (along the track)
        # count as being at the station.
        "junction_snap_m": 800,
    },
    "stations": {
        # Stations closer than this are one star (transfer stations listed
        # twice, platforms the agency did not give a parent station, ...).
        "merge_distance_m": 120,
        "merge": [],  # lists of station names/ids to force into one star
        "drop": [],  # station names/ids to leave out
        "rank": {},  # name -> star rank (1 regular, 2 large) overrides
        "transfer_degree": 3,  # stations with this many neighbors get a large star
    },
    "lines": {
        "simplify_m": 12,  # Douglas-Peucker tolerance in meters
        "smooth_iterations": 2,  # Chaikin corner cutting passes
        "express_ratio": 1.3,  # drop an A-C segment when A-B-C is at most this much longer
    },
    "map": {
        "rotate_deg": 0,  # counterclockwise
        "width_in": 10,
        "max_height_in": 12,
        "margin_in": 0.35,
        "dpi": 300,
    },
    "style": {
        "background": "#000000",
        "star_color": "#ffffaa",
        "line_color": "#d3d3d3",
        "line_width_in": 0.028,
        "star_size_in": 0.17,  # rank 1
        "large_star_size_in": 0.23,  # rank 2
        "gap_in": 0.035,  # clear space cut out of the lines around each star
    },
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load(city: str) -> dict:
    path = CITIES_DIR / f"{city}.yaml"
    if not path.exists():
        known = ", ".join(sorted(p.stem for p in CITIES_DIR.glob("*.yaml")))
        raise SystemExit(f"No config {path}. Known cities: {known}")
    with path.open() as f:
        cfg = _merge(DEFAULTS, yaml.safe_load(f) or {})
    cfg["id"] = city
    cfg["name"] = cfg["name"] or city
    return cfg


def all_cities() -> list[str]:
    return sorted(p.stem for p in CITIES_DIR.glob("*.yaml"))
