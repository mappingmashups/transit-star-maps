"""Assemble station locations for the Sound Transit 3 build-out map.

    .venv/bin/python scripts/seattle_st3_stations.py
    -> cities/seattle_st3/stations.csv

Sources, recorded per row:
  gtfs     stations in service, from Sound Transit's GTFS (data/raw/seattle_link)
  stlayer  planned Seattle stations, from Sound Transit's station layer on
           ArcGIS Online (sound_transit_stations, "In Planning")
  geocode  other planned stations, placed with the ArcGIS World Geocoder at
           the street location named below. These are approximate (station
           sites are not final); fix any row by editing the CSV by hand.

Planned station names and lines follow Wikipedia's "List of Link light rail
stations" (planned stations table, citing Sound Transit's 2026 future
service map). Provisional (unfunded) stations are left out.
"""

import csv
import json
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "cities" / "seattle_st3" / "stations.csv"
UA = {"User-Agent": "transit-star-maps (https://github.com/mappingmashups/transit-star-maps)"}

ST_LAYER = (
    "https://services.arcgis.com/ZOyb2t4B0UYuYNYH/ArcGIS/rest/services/sound_transit_stations/"
    "FeatureServer/0/query?where=STATUS%3D%27In+Planning%27&outFields=NAME&outSR=4326&f=geojson"
)
# station name -> name in Sound Transit's layer
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
# station name -> geocoder query
GEOCODE = {
    "Mariner": "128th St SW and 4th Ave W, Everett, WA",
    "Ash Way": "Ash Way and 164th St SW, Lynnwood, WA",
    "West Alderwood": "Alderwood Mall, Lynnwood, WA",
    "SW Everett Industrial Center": "Seaway Blvd and 75th St SW, Everett, WA",
    "SR 526/Evergreen": "SR 526 and Evergreen Way, Everett, WA",
    "Everett Station": "Everett Station, 3201 Smith Ave, Everett, WA",
    "South Federal Way": "S 352nd St and Enchanted Pkwy S, Federal Way, WA",
    "Fife": "54th Ave E and 20th St E, Fife, WA",
    "Portland Ave": "Portland Ave E and E 25th St, Tacoma, WA",
    "South Kirkland": "10610 NE 38th Pl, Kirkland, WA",
    "Richards Road": "Richards Rd SE and SE 32nd St, Bellevue, WA",
    "Eastgate": "14200 SE Eastgate Way, Bellevue, WA",
    "Central Issaquah": "1050 17th Ave NW, Issaquah, WA",
    # Tacoma Community College extension, west along S 19th St
    "Ainsworth": "S 19th St and S Ainsworth Ave, Tacoma, WA",
    "Union": "S 19th St and S Union Ave, Tacoma, WA",
    "Sprague": "S 19th St and S Sprague Ave, Tacoma, WA",
    "Stevens": "S 19th St and S Stevens St, Tacoma, WA",
    "Pearl": "S 19th St and S Pearl St, Tacoma, WA",
    "Tacoma Community College": "Tacoma Community College, 6501 S 19th St, Tacoma, WA",
}


def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)


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

    for name, query in GEOCODE.items():
        url = (
            "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates?"
            + urllib.parse.urlencode({"SingleLine": query, "maxLocations": 1, "f": "json"})
        )
        cands = get_json(url).get("candidates") or []
        if not cands:
            print(f"no geocode result for {name!r} ({query})", file=sys.stderr)
            continue
        c = cands[0]
        rows.append((name, c["location"]["y"], c["location"]["x"], "geocode", f"{query} -> {c['address']} ({c['score']:.0f})"))
        print(f"{name:30s} {c['address']} score {c['score']:.0f}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "lat", "lon", "source", "detail"])
        for name, lat, lon, src, detail in rows:
            w.writerow([name, f"{lat:.6f}", f"{lon:.6f}", src, detail])
    print(f"wrote {OUT.relative_to(ROOT)} ({len(rows)} stations)")


if __name__ == "__main__":
    main()
