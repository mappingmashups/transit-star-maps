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
        "sha256": None,
        "headers": {},  # extra HTTP headers; ${VAR} is read from the environment  # optional pin; fetch warns if the download differs
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
        # routes sources: [{name, stations: [names in order]}] drawn over the
        # optional linework; `downloads` ({file: URL}) are fetched into
        # data/raw/<city>/ first.
        "routes": [],
        "downloads": {},
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
        "rank": {},  # name -> star rank (0 minor, 1 regular, 2 large) overrides
        "large": [],  # names (or ids) of stations that get a large star anyway
        "transfer_degree": 3,  # stations with this many neighbors get a large star
        # Regexes for GTFS fare areas (stop_areas.txt) whose stations are minor
        # stops, drawn with style.minor_star_size_in (rank 0).
        "minor_areas": [],
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
        # "curved" follows the track; "straight" joins neighboring stars with
        # straight strokes, like the figures drawn on star charts.
        "line_style": "straight",
        "line_width_in": 0.028,
        "star_size_in": 0.17,  # rank 1
        # rank 2 (hubs). Unset, it is star_size_in * large_star_scale, so the
        # difference between hubs and other stations is the same in every city.
        "large_star_size_in": None,
        "large_star_scale": 1.55,
        "minor_star_size_in": 0.07,  # rank 0; 0 hides minor stops entirely
        "gap_in": 0.035,  # clear space cut out of the lines around each star
        # Stars closer than this on the page are drawn as one (0 = keep all).
        # For systems with a dense downtown core.
        "min_star_spacing_in": 0,
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
    st = cfg["style"]
    if st["large_star_size_in"] is None:
        st["large_star_size_in"] = round(st["star_size_in"] * st["large_star_scale"], 4)
    cfg["name"] = cfg["name"] or city
    return cfg


def all_cities() -> list[str]:
    return sorted(p.stem for p in CITIES_DIR.glob("*.yaml"))
