#!/usr/bin/env python3
"""
find_companies.py — Find local businesses in a niche + location using free
OpenStreetMap data (Nominatim geocoding + Overpass API). No API key needed.

Usage:
    python find_companies.py "plumbers" "Tulsa, OK" -o companies.csv
    python find_companies.py "dentists" "Denver, CO" --radius 15000

Output CSV columns: name,url,phone,address

Notes:
- OSM coverage of small-business websites varies by region. A blank `url`
  is itself a useful signal (no site at all = easy outreach target).
- Be polite to the free Nominatim/Overpass endpoints: this script sleeps
  between requests and sets a descriptive User-Agent, per their usage policy.
"""
import argparse
import csv
import json
import sys
import time
import urllib.parse
import urllib.request

USER_AGENT = "website-outreach-tool/1.0 (personal lead-gen script)"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Map common niche keywords to OSM tag queries. Extend as needed.
NICHE_TAGS = {
    "plumber": ['craft=plumber', 'shop=plumber'],
    "plumbers": ['craft=plumber', 'shop=plumber'],
    "electrician": ['craft=electrician'],
    "electricians": ['craft=electrician'],
    "roofer": ['craft=roofer'],
    "roofers": ['craft=roofer'],
    "roofing": ['craft=roofer'],
    "dentist": ['amenity=dentist'],
    "dentists": ['amenity=dentist'],
    "lawyer": ['office=lawyer'],
    "lawyers": ['office=lawyer'],
    "attorney": ['office=lawyer'],
    "restaurant": ['amenity=restaurant'],
    "restaurants": ['amenity=restaurant'],
    "cafe": ['amenity=cafe'],
    "hair salon": ['shop=hairdresser'],
    "hairdresser": ['shop=hairdresser'],
    "barber": ['shop=hairdresser'],
    "auto repair": ['shop=car_repair'],
    "mechanic": ['shop=car_repair'],
    "accountant": ['office=accountant'],
    "accountants": ['office=accountant'],
    "real estate": ['office=estate_agent'],
    "realtor": ['office=estate_agent'],
    "veterinarian": ['amenity=veterinary'],
    "vet": ['amenity=veterinary'],
    "florist": ['shop=florist'],
    "hvac": ['craft=hvac'],
    "landscaper": ['craft=gardener'],
    "landscaping": ['craft=gardener'],
    "insurance": ['office=insurance'],
    "chiropractor": ['healthcare=chiropractor'],
}


def geocode(location):
    params = urllib.parse.urlencode({"q": location, "format": "json", "limit": 1})
    req = urllib.request.Request(f"{NOMINATIM_URL}?{params}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not data:
        raise SystemExit(f"Could not geocode location: {location!r}")
    lat, lon = float(data[0]["lat"]), float(data[0]["lon"])
    return lat, lon


def build_overpass_query(niche, lat, lon, radius):
    niche_key = niche.strip().lower()
    tag_filters = NICHE_TAGS.get(niche_key)

    clauses = []
    if tag_filters:
        for tag in tag_filters:
            k, v = tag.split("=")
            clauses.append(f'node["{k}"="{v}"](around:{radius},{lat},{lon});')
            clauses.append(f'way["{k}"="{v}"](around:{radius},{lat},{lon});')
    else:
        # Fallback: search by name/keyword match so unlisted niches still work.
        escaped = niche.replace('"', '')
        clauses.append(f'node["name"~"{escaped}",i](around:{radius},{lat},{lon});')
        clauses.append(f'way["name"~"{escaped}",i](around:{radius},{lat},{lon});')

    body = "[out:json][timeout:30];(" + "".join(clauses) + ");out center tags;"
    return body


def query_overpass(query):
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    req = urllib.request.Request(OVERPASS_URL, data=data, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_row(el):
    tags = el.get("tags", {})
    name = tags.get("name")
    if not name:
        return None
    url = tags.get("website") or tags.get("contact:website", "")
    phone = tags.get("phone") or tags.get("contact:phone", "")
    addr_parts = [
        tags.get("addr:housenumber", ""),
        tags.get("addr:street", ""),
        tags.get("addr:city", ""),
        tags.get("addr:state", ""),
        tags.get("addr:postcode", ""),
    ]
    address = " ".join(p for p in addr_parts if p)
    return {"name": name, "url": url, "phone": phone, "address": address}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("niche", help='e.g. "plumbers", "dentists", "restaurants"')
    ap.add_argument("location", help='e.g. "Tulsa, OK" or "Denver, Colorado"')
    ap.add_argument("-o", "--output", default="companies.csv")
    ap.add_argument("--radius", type=int, default=10000, help="search radius in meters (default 10000 = ~6mi)")
    args = ap.parse_args()

    print(f"Geocoding '{args.location}'...", file=sys.stderr)
    lat, lon = geocode(args.location)
    time.sleep(1)  # be polite to the free Nominatim endpoint

    print(f"Querying OpenStreetMap for '{args.niche}' near ({lat:.4f},{lon:.4f})...", file=sys.stderr)
    query = build_overpass_query(args.niche, lat, lon, args.radius)
    result = query_overpass(query)

    rows = []
    seen = set()
    for el in result.get("elements", []):
        row = extract_row(el)
        if row and row["name"] not in seen:
            seen.add(row["name"])
            rows.append(row)

    if not rows:
        print("No results found. Try a broader --radius or a different niche keyword.", file=sys.stderr)

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "url", "phone", "address"])
        writer.writeheader()
        writer.writerows(rows)

    no_site = sum(1 for r in rows if not r["url"])
    print(f"Found {len(rows)} businesses ({no_site} with no listed website) -> {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
