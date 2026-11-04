"""Command line: python -m starmaps <step> <city ...|all>

Steps:
  fetch    download the city's GTFS feed into data/raw/ (cached)
  network  build networks/<city>.geojson from the source data
  render   draw outputs/<city>/<city>_{black,transparent}.svg and .png
  build    all three in order
"""

from __future__ import annotations

import argparse

from . import config, fetch, network, raster, render


def _read_layers(paths, query=None):
    """Read one or more vector files into a single WGS84 GeoDataFrame."""
    import geopandas as gpd
    import pandas as pd

    paths = [paths] if isinstance(paths, str) else paths
    frames = []
    for p in paths:
        path = config.ROOT / p
        if path.suffix.lower() == ".csv":
            # Point tables with lat/lon columns.
            df = pd.read_csv(path, dtype={"name": str})
            frames.append(gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs=4326))
        else:
            frames.append(gpd.read_file(path).to_crs(4326))
    gdf = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=4326)
    return gdf.query(query, engine="python") if query else gdf


def build_network(cfg):
    src = cfg["source"]
    print(f"[{cfg['id']}] building network ({src['type']})")
    if src["type"] == "gtfs":
        from . import gtfs

        path = fetch.fetch(cfg)
        stations, patterns, routes = gtfs.read(path, src)
        print(f"  {len(routes)} routes, {len(patterns)} stop patterns, {len(stations)} GTFS stations")
        proj = network.LocalProjection.around([(s["lon"], s["lat"]) for s in stations.values()])
        mapping, stars = network.merge_stations(stations, cfg, proj)
        G = network.from_patterns(stars, mapping, patterns, proj)
        meta = {**fetch.source_meta(cfg), "routes": sorted(str(r) for r in routes["route_id"])}
    elif src["type"] == "linework":
        st = _read_layers(src["stations"], src.get("stations_query"))
        ln = _read_layers(src["lines"], src.get("lines_query"))
        field = src["station_name_field"]
        stations = {
            f"s{i}": {"name": str(row[field]), "lon": row.geometry.x, "lat": row.geometry.y}
            for i, row in st.reset_index(drop=True).iterrows()
            if row.geometry is not None
        }
        proj = network.LocalProjection.around([(s["lon"], s["lat"]) for s in stations.values()])
        mapping, stars = network.merge_stations(stations, cfg, proj)
        lines = []
        for geom in ln.geometry:
            for part in getattr(geom, "geoms", [geom]):
                lines.append(proj.line(part))
        G = network.from_linework(stars, lines, src["snap_m"], src["junction_snap_m"])
        meta = {"stations": src["stations"], "lines": src["lines"]}
    elif src["type"] == "routes":
        fetch.fetch(cfg)
        st = _read_layers(src["stations"], src.get("stations_query"))
        field = src["station_name_field"]
        key = network._key
        wanted = {key(n): n for r in src["routes"] for n in r["stations"]}
        stations, by_name = {}, {}
        for i, row in st.reset_index(drop=True).iterrows():
            name = str(row[field]).strip()
            if key(name) in wanted and row.geometry is not None and key(name) not in by_name:
                sid = f"s{i}"
                stations[sid] = {"name": name, "lon": row.geometry.x, "lat": row.geometry.y}
                by_name[key(name)] = sid
        missing = [n for k, n in wanted.items() if k not in by_name]
        if missing:
            names = sorted(str(n) for n in st[field])
            raise SystemExit(f"stations not found: {missing}\navailable: {names}")
        proj = network.LocalProjection.around([(s["lon"], s["lat"]) for s in stations.values()])
        mapping, stars = network.merge_stations(stations, cfg, proj)
        routes = [
            {"name": r["name"], "stations": [mapping[by_name[key(n)]] for n in r["stations"]]}
            for r in src["routes"]
        ]
        lines = []
        if src.get("lines"):
            ln = _read_layers(src["lines"], src.get("lines_query"))
            for geom in ln.geometry:
                for part in getattr(geom, "geoms", [geom]):
                    lines.append(proj.line(part))
        G = network.from_routes(stars, routes, lines, src["snap_m"], src["junction_snap_m"])
        meta = {**fetch.downloads_meta(cfg), "stations": src["stations"], "lines": src.get("lines")}
    else:
        raise SystemExit(f"unknown source type {src['type']}")
    network.finalize(G, cfg)
    n_st = sum(1 for _, d in G.nodes(data=True) if d["kind"] == "station")
    n_big = sum(1 for _, d in G.nodes(data=True) if d.get("rank") == 2)
    path = network.save(G, proj, cfg, meta)
    print(f"  {n_st} stars ({n_big} large), {G.number_of_edges()} segments -> {path.relative_to(config.ROOT)}")


def render_city(cfg, png=True):
    _, stations, segments = network.load(cfg["id"])
    svgs = render.render(stations, segments, cfg)
    for p in svgs:
        print(f"[{cfg['id']}] wrote {p.relative_to(config.ROOT)}")
    if png:
        for p in raster.to_png(svgs, cfg["map"]["dpi"]):
            print(f"[{cfg['id']}] wrote {p.relative_to(config.ROOT)}")


def main():
    ap = argparse.ArgumentParser(prog="starmaps", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["fetch", "network", "render", "build"])
    ap.add_argument("cities", nargs="+", help="city config names from cities/, or 'all'")
    ap.add_argument("--refresh", action="store_true", help="re-download source data")
    ap.add_argument("--no-png", action="store_true", help="only write SVGs")
    args = ap.parse_args()
    cities = config.all_cities() if args.cities == ["all"] else args.cities
    for city in cities:
        cfg = config.load(city)
        if args.step in ("fetch", "build"):
            fetch.fetch(cfg, refresh=args.refresh)
        if args.step in ("network", "build"):
            build_network(cfg)
        if args.step in ("render", "build"):
            render_city(cfg, png=not args.no_png)


if __name__ == "__main__":
    main()
