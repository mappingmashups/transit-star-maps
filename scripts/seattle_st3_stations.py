"""Assemble station locations for the Sound Transit 3 build-out map.

    .venv/bin/python scripts/seattle_st3_stations.py
    -> cities/seattle_st3/stations.csv

Sources, recorded per row in the CSV:
  gtfs     stations in service, from Sound Transit's GTFS (data/raw/seattle_link)
  stlayer  planned stations inside Seattle, from the City of Seattle's layer of
           Sound Transit stations on ArcGIS Online (sound_transit_stations,
           "In Planning")
  placed   other planned stations, placed by hand from Sound Transit's own
           documents (see PLACED below for each station's document and the
           location it describes). The street location is turned into
           coordinates with OpenStreetMap data via Nominatim (© OpenStreetMap
           contributors, ODbL); responses are cached in data/raw/seattle_st3/.

Planned station names and lines follow Wikipedia's "List of Link light rail
stations" (planned stations table, citing Sound Transit's 2026 future
service map). Provisional (unfunded) stations are left out. Station sites
that Sound Transit hasn't settled are placed between the options it is
studying, so they are approximate.
"""

import csv
import hashlib
import json
import math
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd
from pyproj import Transformer
from shapely.geometry import LineString, MultiLineString, Point, shape
from shapely.ops import nearest_points, unary_union

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "cities" / "seattle_st3" / "stations.csv"
CACHE = ROOT / "data" / "raw" / "seattle_st3" / "nominatim"
UA = {"User-Agent": "transit-star-maps (https://github.com/mappingmashups/transit-star-maps)"}

ST_LAYER = (
    "https://services.arcgis.com/ZOyb2t4B0UYuYNYH/ArcGIS/rest/services/sound_transit_stations/"
    "FeatureServer/0/query?where=STATUS%3D%27In+Planning%27&outFields=NAME&outSR=4326&f=geojson"
)
# station name -> name in the City of Seattle's layer
FROM_LAYER = {
    "Ballard": "Ballard Station",
    "Interbay": "Interbay Station",
    "Smith Cove": "Smith Cove Station",
    "Seattle Center": "Seattle Center Station",
    "South Lake Union": "South Lake Union Station",
    "Denny": "Denny Station",
    "Midtown": "Midtown Station",
    "Delridge": "Delridge Station",
    "Alaska Junction": "Alaska Junction Station",
    "Graham Street": "Graham Street Station",
    "Boeing Access Road": "Boeing Access Road Station",
}

EVLE = "Everett Link Extension Draft EIS, Executive Summary"
TDLE = "Tacoma Dome Link Extension, Supporting Materials for 2022-2023 Screening, Figure 1"
SKI = "South Kirkland to Central Issaquah via Bellevue Light Rail (Sound Transit, 2020)"
TCC = "TCC Link Extension project page (along S 19th Street from St. Joseph)"

# Each placed station: how to find it, and where the location comes from.
#   ("x", street_a, street_b, place)          intersection of two streets
#   ("poi", query)                            a named place
#   ("on", street, poi_query, place)          point on a street nearest a place
#   ("near", street_a, street_b, place)       point on street_a nearest street_b
#   ("xline", street_a, street_b, place)      like "x", with street_a taken as the
#                                             straight line through its segments
#                                             (for long, straight streets that come
#                                             back from Nominatim in too many pieces)
# Optional "shift": (meters, bearing in degrees) to move from that point.
PLACED = {
    "West Alderwood": dict(
        how=("x", "33rd Avenue West", "184th Street Southwest", "Lynnwood"), shift=(250, 180),
        src=f"{EVLE}, Figure ES-2: preferred station ALD-2D, on 33rd Ave W south of 184th St SW"),
    "Ash Way": dict(
        how=("x", "Ash Way", "164th Street Southwest", "Snohomish County"), shift=(350, 20),
        src=f"{EVLE}, Figure ES-3: no preferred site; between options A and D beside I-5 north of 164th St SW"),
    "Mariner": dict(
        how=("x", "4th Avenue West", "128th Street Southwest", "Snohomish County"), shift=(150, 180),
        src=f"{EVLE}, Figure ES-4: no preferred site; between options B and D at 4th Ave W and 128th St SW"),
    "SW Everett Industrial Center": dict(
        how=("near", "West Casino Road", "Seaway Boulevard", "Everett"),
        src=f"{EVLE}, Figure ES-6: preferred station SWI-1A, on SR 526 just west of Seaway Blvd "
            "(where W Casino Rd ends)"),
    "SR 526/Evergreen": dict(
        how=("x", "Evergreen Way", "East Casino Road", "Everett"), shift=(150, 200),
        src=f"{EVLE}, Figure ES-7: all station options at Evergreen Way and SR 526"),
    "Everett Station": dict(
        how=("x", "Broadway", "Pacific Avenue", "Everett"),
        src=f"{EVLE}, Figure ES-9: between preferred options EVT-2C and EVT-3D (Broadway/McDougall Ave)"),
    "South Federal Way": dict(
        how=("x", "Enchanted Parkway South", "South 352nd Street", "Federal Way"),
        src=f"{TDLE}: preferred SF Enchanted Parkway Station"),
    "Fife": dict(
        how=("x", "Pacific Highway East", "54th Avenue East", "Fife"),
        src=f"{TDLE} and Table 1: Fife station options around Pacific Hwy E and 54th Ave E"),
    "Portland Ave": dict(
        how=("x", "Portland Avenue", "East 25th Street", "Tacoma"),
        src=f"{TDLE}: Portland Avenue Station"),
    "South Kirkland": dict(
        how=("poi", "South Kirkland Park and Ride, Kirkland, Washington"),
        src=f"{SKI}: station at the South Kirkland Park-and-Ride"),
    "Richards Road": dict(
        how=("x", "Richards Road", "Southeast Eastgate Way", "Bellevue"),
        src=f"{SKI}: elevated station on the north side of I-90 near Richards Rd SE"),
    "Eastgate": dict(
        how=("poi", "Eastgate Park and Ride, Bellevue, Washington"),
        src=f"{SKI}: station along the south side of the Eastgate transit center"),
    "Central Issaquah": dict(
        how=("poi", "Issaquah Transit Center, Issaquah, Washington"),
        src=f"{SKI}: elevated Central Issaquah station south of I-90"),
    "Ainsworth": dict(how=("xline", "South 19th Street", "South Ainsworth Avenue", "Tacoma"), src=TCC),
    "Sprague": dict(how=("xline", "South 19th Street", "South Sprague Avenue", "Tacoma"), src=TCC),
    "Union": dict(how=("xline", "South 19th Street", "South Union Avenue", "Tacoma"), src=TCC),
    "Stevens": dict(how=("xline", "South 19th Street", "South Stevens Street", "Tacoma"), src=TCC),
    "Pearl": dict(how=("xline", "South 19th Street", "South Pearl Street", "Tacoma"),
                  src=f"{TCC}: 'a stop near Pearl Street'"),
    "Tacoma Community College": dict(
        how=("on", "South 19th Street", "Tacoma Community College, Tacoma, Washington", "Tacoma"),
        src=f"{TCC}: end of the line at the college"),
}

_last_call = [0.0]


def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)


def nominatim(query, geometry=False, viewbox=None):
    """Cached Nominatim search (at most one request per second, per its policy)."""
    params = {"q": query, "format": "jsonv2", "limit": 10, "countrycodes": "us"}
    if viewbox:
        params.update(viewbox=",".join(map(str, viewbox)), bounded=1)
    if geometry:
        # Every segment of the street, not just one representative way.
        params.update(polygon_geojson=1, dedupe=0, limit=40)
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(params)
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".json")
    if path.exists():
        return json.loads(path.read_text())
    wait = 1.1 - (time.time() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.time()
    data = get_json(url)
    path.write_text(json.dumps({"query": query, "results": data}))
    return {"query": query, "results": data}


# Search areas (west, north, east, south) for long streets that come back in
# more pieces than Nominatim returns at once.
VIEWBOX = {"Tacoma": (-122.54, 47.26, -122.39, 47.23)}


def street(name, place):
    """All OSM ways matching a street name in a city, as one geometry."""
    res = nominatim(f"{name}, {place}, Washington", geometry=True, viewbox=VIEWBOX.get(place))["results"]
    lines = [shape(r["geojson"]) for r in res if r.get("geojson", {}).get("type") in ("LineString", "MultiLineString")]
    if not lines:
        sys.exit(f"no street geometry for {name!r} in {place}")
    return unary_union(lines)


def shifted(lon, lat, meters, bearing):
    dlat = meters * math.cos(math.radians(bearing)) / 111_320
    dlon = meters * math.sin(math.radians(bearing)) / (111_320 * math.cos(math.radians(lat)))
    return lon + dlon, lat + dlat


def place(spec):
    how = spec["how"]
    if how[0] == "x":
        a, b = street(how[1], how[3]), street(how[2], how[3])
        hit = a.intersection(b)
        if hit.is_empty:
            # Streets that meet at a small gap in the data: use the closest approach.
            pa, pb = nearest_points(a, b)
            if pa.distance(pb) > 0.002:  # ~200 m
                sys.exit(f"{how[1]} and {how[2]} don't meet")
            hit = Point((pa.x + pb.x) / 2, (pa.y + pb.y) / 2)
        pt = hit if hit.geom_type == "Point" else hit.centroid
        lon, lat, how_text = pt.x, pt.y, f"{how[1]} & {how[2]}, {how[3]}"
    elif how[0] == "poi":
        r = nominatim(how[1])["results"]
        if not r:
            sys.exit(f"nothing found for {how[1]!r}")
        lon, lat, how_text = float(r[0]["lon"]), float(r[0]["lat"]), r[0]["display_name"]
    elif how[0] == "xline":
        import numpy as np

        a = street(how[1], how[3])
        xy = np.array([c for g in getattr(a, "geoms", [a]) for c in g.coords])
        slope, icept = np.polyfit(xy[:, 0], xy[:, 1], 1)
        x0, x1 = xy[:, 0].min() - 0.01, xy[:, 0].max() + 0.01
        line = LineString([(x0, slope * x0 + icept), (x1, slope * x1 + icept)])
        hit = line.intersection(street(how[2], how[3]))
        if hit.is_empty:
            sys.exit(f"{how[2]} doesn't cross {how[1]}")
        pt = hit if hit.geom_type == "Point" else hit.centroid
        lon, lat, how_text = pt.x, pt.y, f"{how[1]} & {how[2]}, {how[3]}"
    elif how[0] == "near":
        pt = nearest_points(street(how[1], how[3]), street(how[2], how[3]))[0]
        lon, lat, how_text = pt.x, pt.y, f"{how[1]} nearest {how[2]}, {how[3]}"
    else:  # "on"
        s = street(how[1], how[3])
        r = nominatim(how[2])["results"]
        poi = Point(float(r[0]["lon"]), float(r[0]["lat"]))
        pt = nearest_points(s, poi)[0]
        lon, lat, how_text = pt.x, pt.y, f"{how[1]} nearest {r[0]['display_name']}"
    if "shift" in spec:
        lon, lat = shifted(lon, lat, *spec["shift"])
        how_text += f", moved {spec['shift'][0]} m toward {spec['shift'][1]}°"
    return lat, lon, how_text


def main():
    rows = []
    # In service: GTFS parent stations of the Link and T Line routes.
    zf = zipfile.ZipFile(ROOT / "data" / "raw" / "seattle_link" / "gtfs.zip")
    read = lambda n: pd.read_csv(zf.open(n), dtype=str, keep_default_na=False)  # noqa: E731
    trips = read("trips.txt")
    trips = trips[trips["route_id"].isin({"100479", "2LINE", "TLINE"})]
    st = pd.read_csv(zf.open("stop_times.txt"), dtype=str, usecols=["trip_id", "stop_id"])
    stop_ids = set(st[st["trip_id"].isin(set(trips["trip_id"]))]["stop_id"])
    stops = read("stops.txt").set_index("stop_id")
    parents = {stops.at[s, "parent_station"] or s for s in stop_ids if s in stops.index}
    for p in sorted(parents):
        r = stops.loc[p]
        rows.append((r["stop_name"], float(r["stop_lat"]), float(r["stop_lon"]), "gtfs", p))

    layer = {f["properties"]["NAME"]: f["geometry"]["coordinates"] for f in get_json(ST_LAYER)["features"]}
    for name, layer_name in FROM_LAYER.items():
        lon, lat = layer[layer_name]
        rows.append((name, lat, lon, "stlayer", layer_name))

    for name, spec in PLACED.items():
        lat, lon, how_text = place(spec)
        rows.append((name, lat, lon, "placed", f"{spec['src']} | {how_text}"))
        print(f"{name:30s} {lat:.5f} {lon:.5f}  {how_text}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "lat", "lon", "source", "detail"])
        for name, lat, lon, src, detail in rows:
            w.writerow([name, f"{lat:.6f}", f"{lon:.6f}", src, detail])
    print(f"wrote {OUT.relative_to(ROOT)} ({len(rows)} stations)")


if __name__ == "__main__":
    main()
