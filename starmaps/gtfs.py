"""Read the rail part of a GTFS feed as stations and stop patterns.

A *pattern* is one distinct ordered list of stations that some trips run,
with the shape those trips follow. Thousands of trips collapse to a few
dozen patterns, one or two per route and direction.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections import Counter

import pandas as pd
from shapely.geometry import LineString

CHUNK = 1_000_000


def _open(zf: zipfile.ZipFile, name: str):
    # Some feeds put the files in a subfolder.
    for info in zf.infolist():
        if info.filename.rsplit("/", 1)[-1] == name:
            return io.TextIOWrapper(zf.open(info), encoding="utf-8-sig")
    return None


def _read(zf, name, usecols=None, required=True) -> pd.DataFrame | None:
    f = _open(zf, name)
    if f is None:
        if required:
            raise SystemExit(f"GTFS feed has no {name}")
        return None
    header = pd.read_csv(f, nrows=0).columns.str.strip()
    f = _open(zf, name)
    cols = [c for c in usecols if c in header] if usecols else None
    df = pd.read_csv(f, dtype=str, usecols=cols, keep_default_na=False)
    df.columns = df.columns.str.strip()
    return df


def _read_filtered(zf, name, usecols, key, keep: set) -> pd.DataFrame:
    """Read a large file in chunks, keeping rows whose `key` is in `keep`."""
    f = _open(zf, name)
    header = pd.read_csv(f, nrows=0).columns.str.strip()
    cols = [c for c in usecols if c in header]
    f = _open(zf, name)
    parts = []
    for chunk in pd.read_csv(f, dtype=str, usecols=cols, chunksize=CHUNK, keep_default_na=False):
        chunk.columns = chunk.columns.str.strip()
        parts.append(chunk[chunk[key].isin(keep)])
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=cols)


def _matches(row, patterns) -> bool:
    fields = [row.get("route_id", ""), row.get("route_short_name", ""), row.get("route_long_name", "")]
    return any(re.search(p, f or "", re.IGNORECASE) for p in patterns for f in fields)


def select_routes(routes: pd.DataFrame, src: dict) -> pd.DataFrame:
    types = {str(t) for t in src["route_types"]}
    keep = routes[routes["route_type"].str.strip().isin(types)]
    if src["include_routes"]:
        keep = keep[keep.apply(lambda r: _matches(r, src["include_routes"]), axis=1)]
    if src["exclude_routes"]:
        keep = keep[~keep.apply(lambda r: _matches(r, src["exclude_routes"]), axis=1)]
    return keep


def read(zip_path, src: dict):
    """Return (stations, patterns, routes_table).

    stations: {station_id: {"name", "lon", "lat"}} (parent stations where the
    feed has them).
    patterns: [{"route", "stations": [ids], "shape": LineString | None, "trips"}]
    """
    with zipfile.ZipFile(zip_path) as zf:
        routes = _read(zf, "routes.txt")
        chosen = select_routes(routes, src)
        if chosen.empty:
            types = Counter(routes["route_type"])
            raise SystemExit(
                f"No routes left after filtering. route_type counts in feed: {dict(types)}"
            )
        route_ids = set(chosen["route_id"])
        label = {
            r.route_id: (r.get("route_short_name") or r.get("route_long_name") or r.route_id)
            for _, r in chosen.iterrows()
        }

        trips = _read(zf, "trips.txt", ["route_id", "trip_id", "shape_id", "direction_id"])
        trips = trips[trips["route_id"].isin(route_ids)]
        if "shape_id" not in trips:
            trips["shape_id"] = ""

        st = _read_filtered(
            zf, "stop_times.txt", ["trip_id", "stop_id", "stop_sequence"], "trip_id", set(trips["trip_id"])
        )
        st["stop_sequence"] = st["stop_sequence"].astype(int)
        st = st.sort_values(["trip_id", "stop_sequence"])
        seqs = st.groupby("trip_id", sort=False)["stop_id"].apply(tuple)

        stops = _read(
            zf,
            "stops.txt",
            ["stop_id", "stop_name", "stop_lat", "stop_lon", "location_type", "parent_station"],
        ).set_index("stop_id")
        if "parent_station" not in stops:
            stops["parent_station"] = ""

        # Fare areas (GTFS-Fares v2). Agencies use them to set apart stops
        # with different fare handling, e.g. MBTA's street-running Green Line.
        stop_areas = _read(zf, "stop_areas.txt", ["area_id", "stop_id"], required=False)
        areas_of = (
            stop_areas.groupby("stop_id")["area_id"].apply(set).to_dict()
            if stop_areas is not None and not stop_areas.empty
            else {}
        )

        trips = trips.set_index("trip_id")
        trips["seq"] = seqs
        trips = trips.dropna(subset=["seq"])
        counts = trips.groupby(["route_id", "shape_id", "seq"]).size()

        shape_ids = {s for s in trips["shape_id"] if s}
        shapes = {}
        if shape_ids and _open(zf, "shapes.txt") is not None:
            sh = _read_filtered(
                zf,
                "shapes.txt",
                ["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"],
                "shape_id",
                shape_ids,
            )
            sh["shape_pt_sequence"] = sh["shape_pt_sequence"].astype(float)
            sh = sh.sort_values(["shape_id", "shape_pt_sequence"])
            for sid, g in sh.groupby("shape_id"):
                coords = list(zip(g["shape_pt_lon"].astype(float), g["shape_pt_lat"].astype(float)))
                if len(coords) >= 2:
                    shapes[sid] = LineString(coords)

    def station_of(stop_id: str) -> str:
        parent = stops.at[stop_id, "parent_station"] if stop_id in stops.index else ""
        return parent if parent and parent in stops.index else stop_id

    stations: dict[str, dict] = {}
    patterns = []
    for (route_id, shape_id, seq), n in counts.items():
        ids = [station_of(s) for s in seq]
        for sid in ids:
            if sid not in stations:
                row = stops.loc[sid]
                kids = stops.index[stops["parent_station"] == sid]
                areas = set(areas_of.get(sid, set())).union(*(areas_of.get(k, set()) for k in kids))
                stations[sid] = {
                    "name": row["stop_name"],
                    "lon": float(row["stop_lon"]),
                    "lat": float(row["stop_lat"]),
                    "areas": sorted(areas),
                }
        patterns.append(
            {"route": label[route_id], "stations": ids, "shape": shapes.get(shape_id), "trips": int(n)}
        )
    return stations, patterns, chosen
