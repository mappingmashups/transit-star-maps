"""Turn raw stations and route geometry into a clean station graph.

The graph has one node per star and one edge per pair of neighboring
stations, however many routes, directions or tracks run between them. Edges
keep their real-world shape. Nodes are stations, plus hidden junction nodes
where track splits between stations; junctions are never drawn.

Two inputs feed the same graph:

* GTFS stop patterns (`from_patterns`): each pattern's shape is cut at its
  stations, and the pieces are keyed by the unordered station pair, so both
  directions and every route on a shared trunk collapse to one edge.
* Plain linework (`from_linework`), such as old GeoJSON files or OSM track:
  the lines are noded, stations are snapped onto them, and the result is
  cleaned the same way.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx
import numpy as np
from pyproj import CRS, Transformer
from shapely import STRtree
from shapely.geometry import LineString, Point, mapping, shape
from shapely.ops import linemerge, substring, unary_union

from .config import NETWORKS_DIR


# ---------------------------------------------------------------- projection


class LocalProjection:
    """Transverse Mercator centered on the network, in meters."""

    def __init__(self, lon0: float, lat0: float):
        self.lon0, self.lat0 = lon0, lat0
        crs = CRS.from_proj4(
            f"+proj=tmerc +lat_0={lat0} +lon_0={lon0} +k=1 +x_0=0 +y_0=0 +ellps=WGS84 +units=m +no_defs"
        )
        self._fwd = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        self._inv = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)

    def xy(self, lon, lat):
        return self._fwd.transform(lon, lat)

    def lonlat(self, x, y):
        return self._inv.transform(x, y)

    def line(self, ls: LineString) -> LineString:
        xs, ys = self._fwd.transform(*np.asarray(ls.coords).T[:2])
        return LineString(np.column_stack([xs, ys]))

    def line_inv(self, ls: LineString) -> LineString:
        lon, lat = self._inv.transform(*np.asarray(ls.coords).T[:2])
        return LineString(np.column_stack([np.round(lon, 6), np.round(lat, 6)]))

    @classmethod
    def around(cls, lonlats):
        arr = np.asarray(lonlats)
        lon0, lat0 = (arr.min(axis=0) + arr.max(axis=0)) / 2
        return cls(round(float(lon0), 4), round(float(lat0), 4))


# ------------------------------------------------------------ station merging


def _key(name_or_id: str) -> str:
    return str(name_or_id).strip().lower()


def merge_stations(stations: dict, cfg: dict, proj: LocalProjection):
    """Cluster stations into stars.

    Returns (mapping original id -> star id, stars dict). Stations listed in
    `stations.drop` map to None.
    """
    scfg = cfg["stations"]
    ids = list(stations)
    drop = {_key(d) for d in scfg["drop"]}
    parent = {i: i for i in ids}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    pts = {i: proj.xy(stations[i]["lon"], stations[i]["lat"]) for i in ids}
    if ids:
        tree = STRtree([Point(pts[i]) for i in ids])
        d = scfg["merge_distance_m"]
        for n, i in enumerate(ids):
            for m in tree.query(Point(pts[i]).buffer(d)):
                if m != n and math.dist(pts[i], pts[ids[m]]) <= d:
                    union(i, ids[m])

    by_key = defaultdict(list)
    for i in ids:
        by_key[_key(i)].append(i)
        by_key[_key(stations[i]["name"])].append(i)
    for group in scfg["merge"]:
        members = [i for g in group for i in by_key.get(_key(g), [])]
        missing = [g for g in group if _key(g) not in by_key]
        if missing:
            print(f"  note: merge entries not found: {missing}")
        for a, b in zip(members, members[1:]):
            union(a, b)

    clusters = defaultdict(list)
    for i in ids:
        clusters[find(i)].append(i)

    mapping, stars = {}, {}
    for root, members in clusters.items():
        names = Counter(stations[m]["name"] for m in members)
        name = min(names, key=lambda n: (-names[n], len(n)))
        if any(_key(m) in drop for m in members) or _key(name) in drop:
            for m in members:
                mapping[m] = None
            continue
        xy = np.mean([pts[m] for m in members], axis=0)
        areas = sorted({a for m in members for a in stations[m].get("areas", [])})
        stars[root] = {
            "name": name, "x": float(xy[0]), "y": float(xy[1]), "members": sorted(members), "areas": areas,
        }
        for m in members:
            mapping[m] = root
    return mapping, stars


# -------------------------------------------------------------- graph building


def _oriented(geom: LineString, start_xy) -> LineString:
    c = geom.coords
    if math.dist(c[0], start_xy) > math.dist(c[-1], start_xy):
        return LineString(c[::-1])
    return geom


def _pin_ends(geom: LineString, a_xy, b_xy) -> LineString:
    coords = list(geom.coords)
    coords[0], coords[-1] = tuple(a_xy), tuple(b_xy)
    return LineString(coords)


def _add_edge(G, u, v, geom, weight=1, routes=()):
    """Add or reinforce the edge u-v. The best-supported geometry wins."""
    if u == v:
        return
    if G.has_edge(u, v):
        e = G.edges[u, v]
        e["routes"].update(routes)
        e["support"][geom.wkb] = e["support"].get(geom.wkb, 0) + weight
        best = max(e["support"], key=e["support"].get)
        if best != e["geometry"].wkb:
            from shapely import from_wkb

            e["geometry"] = from_wkb(best)
        return
    G.add_edge(u, v, geometry=geom, routes=set(routes), support={geom.wkb: weight})


def from_patterns(stars, mapping, patterns, proj, max_offset_m=400):
    G = nx.Graph()
    for sid, s in stars.items():
        G.add_node(sid, kind="station", **s)
    used = set()
    for pat in patterns:
        seq = []
        for orig in pat["stations"]:
            sid = mapping.get(orig)
            if sid is None or (seq and seq[-1] == sid):
                continue
            seq.append(sid)
        if len(seq) < 2:
            continue
        used.update(seq)
        xy = [(stars[s]["x"], stars[s]["y"]) for s in seq]
        line = proj.line(pat["shape"]) if pat["shape"] is not None else None
        pos = [None] * len(seq)
        if line is not None and line.length > 0:
            cur = 0.0
            for k, p in enumerate(xy):
                reach = line.length if k == 0 else min(line.length, cur + 3 * math.dist(xy[k - 1], p) + 1000)
                window = substring(line, cur, reach)
                if window.length == 0:
                    continue
                d = cur + window.project(Point(p))
                if line.interpolate(d).distance(Point(p)) <= max_offset_m:
                    pos[k] = cur = d
        for k in range(len(seq) - 1):
            a, b = seq[k], seq[k + 1]
            if pos[k] is not None and pos[k + 1] is not None and pos[k + 1] > pos[k]:
                geom = substring(line, pos[k], pos[k + 1])
                if geom.geom_type != "LineString" or len(geom.coords) < 2:
                    geom = LineString([xy[k], xy[k + 1]])
            else:
                geom = LineString([xy[k], xy[k + 1]])
            geom = _pin_ends(geom, xy[k], xy[k + 1])
            u, v = sorted((a, b))
            if u != a:
                geom = LineString(geom.coords[::-1])
            _add_edge(G, u, v, geom, pat["trips"], [pat["route"]])
    for sid in list(G.nodes):
        if sid not in used:
            G.remove_node(sid)
    return G


def from_linework(stars, lines, snap_m, junction_snap_m=800):
    """Build the graph from projected linework (list of LineStrings)."""
    G = nx.Graph()
    for sid, s in stars.items():
        G.add_node(sid, kind="station", **s)
    noded = unary_union([l for l in lines if l.length > 0])
    merged = linemerge(noded)
    pieces = list(merged.geoms) if hasattr(merged, "geoms") else [merged]

    ids = list(stars)
    tree = STRtree([Point(stars[i]["x"], stars[i]["y"]) for i in ids])

    def junction(xy):
        nid = f"j:{xy[0]:.1f},{xy[1]:.1f}"
        if nid not in G:
            G.add_node(nid, kind="junction", x=xy[0], y=xy[1], name="")
        return nid

    for piece in pieces:
        hits = []
        for m in tree.query(piece.buffer(snap_m)):
            sid = ids[m]
            p = Point(stars[sid]["x"], stars[sid]["y"])
            if piece.distance(p) <= snap_m:
                hits.append((piece.project(p), sid))
        hits.sort()
        stops = [(0.0, junction(piece.coords[0]))]
        stops += hits
        stops.append((piece.length, junction(piece.coords[-1])))
        for (d0, n0), (d1, n1) in zip(stops, stops[1:]):
            if n0 == n1:
                continue
            a_xy = (G.nodes[n0]["x"], G.nodes[n0]["y"])
            b_xy = (G.nodes[n1]["x"], G.nodes[n1]["y"])
            if d1 - d0 > 1e-6:
                geom = substring(piece, d0, d1)
                if geom.geom_type != "LineString":
                    geom = LineString([a_xy, b_xy])
            else:
                geom = LineString([a_xy, b_xy])
            geom = _pin_ends(geom, a_xy, b_xy)
            u, v = sorted((n0, n1))
            if u != n0:
                geom = LineString(geom.coords[::-1])
            # Prefer the shortest when two tracks join the same pair.
            if G.has_edge(u, v) and G.edges[u, v]["geometry"].length <= geom.length:
                continue
            if G.has_edge(u, v):
                G.remove_edge(u, v)
            _add_edge(G, u, v, geom)

    # Track that splits just outside a station splits *at* that station as far
    # as the map is concerned: fold nearby junctions into it, nearest first.
    tidy_junctions(G)
    while True:
        best = None
        for u, v, d in G.edges(data=True):
            kinds = (G.nodes[u]["kind"], G.nodes[v]["kind"])
            if sorted(kinds) == ["junction", "station"] and d["geometry"].length <= junction_snap_m:
                if best is None or d["geometry"].length < best[0]:
                    best = (d["geometry"].length, u, v)
        if best is None:
            break
        _, u, v = best
        st, j = (u, v) if G.nodes[u]["kind"] == "station" else (v, u)
        _absorb(G, j, st)
    unsnapped = [s for s in ids if G.degree(s) == 0]
    if unsnapped:
        print(f"  note: {len(unsnapped)} stations not on any line: "
              + ", ".join(stars[s]["name"] for s in unsnapped[:10]))
        G.remove_nodes_from(unsnapped)
    return G


def from_routes(stars, routes, lines, snap_m, junction_snap_m=800, max_detour=3.0):
    """Build the graph from hand-listed station orders.

    `routes` is [{"name", "stations": [star ids in order]}]. Between each pair
    of neighbors the edge follows the linework (shortest path through the
    track network) when there is a sensible path, and is a straight line
    otherwise (planned lines with no drawn alignment yet).
    """
    LW = from_linework({k: dict(v) for k, v in stars.items()}, lines, snap_m, junction_snap_m) if lines else None
    G = nx.Graph()
    for sid, s in stars.items():
        G.add_node(sid, kind="station", **s)
    used, straight = set(), 0
    for route in routes:
        seq = route["stations"]
        used.update(seq)
        for a, b in zip(seq, seq[1:]):
            a_xy = (stars[a]["x"], stars[a]["y"])
            b_xy = (stars[b]["x"], stars[b]["y"])
            geom = None
            if LW is not None and a in LW and b in LW:
                try:
                    path = nx.shortest_path(LW, a, b, weight=lambda u, v, d: d["geometry"].length)
                except nx.NetworkXNoPath:
                    path = None
                if path:
                    coords = []
                    for u, v in zip(path, path[1:]):
                        g = list(_edge_geom(LW, u, v).coords)
                        coords += g[1:] if coords else g
                    cand = LineString(coords)
                    if cand.length <= max_detour * max(math.dist(a_xy, b_xy), 1):
                        geom = cand
            if geom is None:
                geom = LineString([a_xy, b_xy])
                straight += 1
            geom = _pin_ends(geom, a_xy, b_xy)
            u, v = sorted((a, b))
            if u != a:
                geom = LineString(geom.coords[::-1])
            _add_edge(G, u, v, geom, routes=[route["name"]])
    G.remove_nodes_from([n for n in list(G.nodes) if n not in used])
    if straight:
        print(f"  {straight} segments have no track drawn and are straight")
    return G


def _absorb(G, j, st):
    """Fold junction j into station st, rerouting j's other edges."""
    sxy = (G.nodes[st]["x"], G.nodes[st]["y"])
    for nb in list(G.neighbors(j)):
        if nb == st:
            continue
        e = G.edges[j, nb]
        geom = _oriented(e["geometry"], (G.nodes[j]["x"], G.nodes[j]["y"]))
        geom = LineString([sxy] + list(geom.coords)[1:])
        u, v = sorted((st, nb))
        if u != st:
            geom = LineString(geom.coords[::-1])
        if not G.has_edge(u, v):
            _add_edge(G, u, v, geom, routes=e["routes"])
    G.remove_node(j)


# ------------------------------------------------------------------ cleanup


def _edge_geom(G, u, v):
    return _oriented(G.edges[u, v]["geometry"], (G.nodes[u]["x"], G.nodes[u]["y"]))


def tidy_junctions(G):
    """Drop dead-end junctions (tail tracks, yard leads) and merge pass-through ones."""
    changed = True
    while changed:
        changed = False
        for n in list(G.nodes):
            if n not in G or G.nodes[n]["kind"] != "junction":
                continue
            deg = G.degree(n)
            if deg <= 1:
                G.remove_node(n)
                changed = True
            elif deg == 2:
                a, b = list(G.neighbors(n))
                if G.has_edge(a, b):
                    G.remove_node(n)  # parallel track; keep the existing edge
                    changed = True
                    continue
                g1 = _edge_geom(G, a, n)
                g2 = _edge_geom(G, n, b)
                geom = LineString(list(g1.coords) + list(g2.coords)[1:])
                routes = G.edges[a, n]["routes"] | G.edges[n, b]["routes"]
                G.remove_node(n)
                u, v = sorted((a, b))
                if u != a:
                    geom = LineString(geom.coords[::-1])
                _add_edge(G, u, v, geom, routes=routes)
                changed = True


def prune_express(G, ratio):
    """Remove A-C edges that skip stations already linked A-B-C (express runs)."""
    for u, v in sorted(G.edges, key=lambda e: -G.edges[e]["geometry"].length):
        data = G.edges[u, v]
        length = data["geometry"].length
        G.remove_edge(u, v)
        try:
            path = nx.shortest_path(G, u, v, weight=lambda a, b, d: d["geometry"].length)
            alt = sum(G.edges[a, b]["geometry"].length for a, b in zip(path, path[1:]))
        except nx.NetworkXNoPath:
            path, alt = [], math.inf
        if len(path) >= 3 and alt <= ratio * length:
            for a, b in zip(path, path[1:]):
                G.edges[a, b]["routes"].update(data["routes"])
            continue
        G.add_edge(u, v, **data)


def chaikin(coords, iterations):
    pts = np.asarray(coords, dtype=float)
    for _ in range(iterations):
        if len(pts) < 3:
            break
        q = 0.75 * pts[:-1] + 0.25 * pts[1:]
        r = 0.25 * pts[:-1] + 0.75 * pts[1:]
        mid = np.empty((2 * len(q), 2))
        mid[0::2], mid[1::2] = q, r
        pts = np.vstack([pts[:1], mid[1:-1], pts[-1:]])
    return pts


def smooth(G, simplify_m, iterations):
    for u, v, data in G.edges(data=True):
        g = data["geometry"].simplify(simplify_m, preserve_topology=False)
        if len(g.coords) < 2:
            g = LineString([data["geometry"].coords[0], data["geometry"].coords[-1]])
        data["geometry"] = LineString(chaikin(g.coords, iterations))


def rank_stations(G, scfg):
    overrides = {_key(k): v for k, v in scfg["rank"].items()}
    for n, d in G.nodes(data=True):
        if d["kind"] != "station":
            continue
        # Branches leaving the star. Junctions near stations were already
        # folded into them, so a junction left between stations does not make
        # its neighbors look like transfer stations.
        nbs = set(G.neighbors(n))
        d["degree"] = len(nbs)
        d["rank"] = 2 if len(nbs) >= scfg["transfer_degree"] else 1
        # Minor stops (rank 0) are matched by fare area, but line ends and
        # branch points always stay full stars.
        if d["rank"] == 1 and len(nbs) == 2 and any(
            re.search(p, a) for p in scfg["minor_areas"] for a in d.get("areas", [])
        ):
            d["rank"] = 0
        d["rank"] = overrides.get(_key(d["name"]), overrides.get(_key(n), d["rank"]))


def finalize(G, cfg):
    tidy_junctions(G)
    prune_express(G, cfg["lines"]["express_ratio"])
    tidy_junctions(G)
    smooth(G, cfg["lines"]["simplify_m"], cfg["lines"]["smooth_iterations"])
    rank_stations(G, cfg["stations"])
    return G


# ---------------------------------------------------------------- save/load


def network_path(city: str) -> Path:
    return NETWORKS_DIR / f"{city}.geojson"


def save(G, proj: LocalProjection, cfg: dict, meta: dict) -> Path:
    features = []
    for u, v, d in sorted(G.edges(data=True), key=lambda e: (str(e[0]), str(e[1]))):
        features.append(
            {
                "type": "Feature",
                "properties": {"kind": "segment", "from": u, "to": v, "routes": sorted(d["routes"])},
                "geometry": mapping(proj.line_inv(d["geometry"])),
            }
        )
    for n, d in sorted(G.nodes(data=True), key=lambda x: str(x[0])):
        if d["kind"] != "station":
            continue
        lon, lat = proj.lonlat(d["x"], d["y"])
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "kind": "station",
                    "id": n,
                    "name": d["name"],
                    "rank": d["rank"],
                    "degree": d["degree"],
                    "members": d["members"],
                },
                "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
            }
        )
    fc = {
        "type": "FeatureCollection",
        "name": cfg["name"],
        "projection": {"lon_0": proj.lon0, "lat_0": proj.lat0},
        "source": meta,
        "features": features,
    }
    path = network_path(cfg["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fc, indent=1, ensure_ascii=False) + "\n")
    return path


def load(city: str):
    """Return (projection, stations, segments) with projected shapely geometry."""
    path = network_path(city)
    if not path.exists():
        raise SystemExit(f"No network for {city}; run `python -m starmaps network {city}` first")
    fc = json.loads(path.read_text())
    proj = LocalProjection(fc["projection"]["lon_0"], fc["projection"]["lat_0"])
    stations, segments = [], []
    for f in fc["features"]:
        p = f["properties"]
        if p["kind"] == "station":
            x, y = proj.xy(*f["geometry"]["coordinates"])
            stations.append({**p, "x": x, "y": y})
        else:
            segments.append({**p, "geometry": proj.line(shape(f["geometry"]))})
    return proj, stations, segments
