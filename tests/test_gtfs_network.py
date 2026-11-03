"""Checks the GTFS → station graph cleanup on a tiny made-up feed.

The feed (a test fixture, not real data) has:
  * a trunk A–B–C that splits at C into branches to D and to E,
  * every route run in both directions, with separate platforms per direction
    grouped under parent stations,
  * an express pattern A–C that skips B,
  * a bus route that must be left out,
  * a second station record for C ~40 m away (as agencies list transfers).
"""

import csv
import io
import zipfile

from starmaps import config, gtfs, network

# lon, lat roughly in Oakland; 0.01° lat ≈ 1.1 km
STATIONS = {"A": (-122.27, 37.80), "B": (-122.27, 37.81), "C": (-122.27, 37.82),
            "D": (-122.28, 37.83), "E": (-122.26, 37.83)}


def _csv(rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerows(rows)
    return buf.getvalue()


def make_feed(path):
    stops = [["stop_id", "stop_name", "stop_lat", "stop_lon", "location_type", "parent_station"]]
    for sid, (lon, lat) in STATIONS.items():
        stops.append([sid, f"Station {sid}", lat, lon, 1, ""])
        for d in ("n", "s"):  # one platform per direction, 15 m apart
            off = 0.00007 if d == "n" else -0.00007
            stops.append([f"{sid}{d}", f"Station {sid} platform", lat, lon + off, 0, sid])
    # The branch-E line lists C as its own station record.
    stops.append(["C2", "Station C", 37.82035, -122.27, 1, ""])
    stops.append(["C2n", "Station C", 37.82035, -122.27, 0, "C2"])
    stops.append(["C2s", "Station C", 37.82035, -122.27, 0, "C2"])
    stops.append(["bus1", "Bus stop", 37.805, -122.30, 0, ""])
    stops.append(["bus2", "Bus stop 2", 37.815, -122.30, 0, ""])

    routes = [["route_id", "route_short_name", "route_long_name", "route_type"],
              ["red", "R", "Red", 1], ["orange", "O", "Orange", 1], ["bus", "1", "Bus", 3]]
    patterns = {
        "red": ["A", "B", "C", "D"],
        "orange": ["A", "B", "C2", "E"],
    }
    trips = [["route_id", "service_id", "trip_id", "shape_id"]]
    st = [["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"]]
    shapes = [["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"]]

    def coord(s):
        return STATIONS.get(s.rstrip("ns"), (-122.27, 37.82035))

    def add_trip(route, tid, seq, plat, shape_id):
        trips.append([route, "wk", tid, shape_id])
        for k, s in enumerate(seq):
            st.append([tid, "08:00:00", "08:00:00", s + plat, k + 1])

    for route, seq in patterns.items():
        for d, ordered in (("n", seq), ("s", seq[::-1])):
            shape_id = f"{route}_{d}"
            # A shape with a bend between each pair of stations.
            k = 0
            for i, s in enumerate(ordered):
                lon, lat = coord(s)
                shapes.append([shape_id, lat, lon, k]); k += 1
                if i + 1 < len(ordered):
                    lon2, lat2 = coord(ordered[i + 1])
                    shapes.append([shape_id, (lat + lat2) / 2, (lon + lon2) / 2 + 0.002, k]); k += 1
            for n in range(3):
                add_trip(route, f"{route}_{d}_{n}", ordered, d, shape_id)
    add_trip("red", "red_express", ["A", "C", "D"], "n", "red_n")
    add_trip("bus", "bus_trip", ["bus1", "bus2"], "", "")

    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("stops.txt", _csv(stops))
        zf.writestr("routes.txt", _csv(routes))
        zf.writestr("trips.txt", _csv(trips))
        zf.writestr("stop_times.txt", _csv(st))
        zf.writestr("shapes.txt", _csv(shapes))


def build(tmp_path):
    feed = tmp_path / "gtfs.zip"
    make_feed(feed)
    cfg = config._merge(config.DEFAULTS, {})
    cfg.update(id="test", name="test")
    stations, patterns, routes = gtfs.read(feed, cfg["source"])
    proj = network.LocalProjection.around([(s["lon"], s["lat"]) for s in stations.values()])
    mapping, stars = network.merge_stations(stations, cfg, proj)
    G = network.from_patterns(stars, mapping, patterns, proj)
    network.finalize(G, cfg)
    return G, routes


def test_graph(tmp_path):
    G, routes = build(tmp_path)
    assert set(routes["route_id"]) == {"red", "orange"}
    names = sorted(d["name"] for _, d in G.nodes(data=True))
    assert names == [f"Station {s}" for s in "ABCDE"]  # platforms and C2 merged
    pairs = {tuple(sorted((G.nodes[u]["name"][-1], G.nodes[v]["name"][-1]))) for u, v in G.edges}
    assert pairs == {("A", "B"), ("B", "C"), ("C", "D"), ("C", "E")}  # no A–C express edge
    ranks = {d["name"][-1]: d["rank"] for _, d in G.nodes(data=True)}
    assert ranks == {"A": 1, "B": 1, "C": 2, "D": 1, "E": 1}
    # Edges follow the bent shape, not a straight line.
    ab = next(d["geometry"] for u, v, d in G.edges(data=True)
              if {G.nodes[u]["name"], G.nodes[v]["name"]} == {"Station A", "Station B"})
    assert len(ab.coords) > 2
    assert G.edges[next(iter(G.edges))]["routes"]
