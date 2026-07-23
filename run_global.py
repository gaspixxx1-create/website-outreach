#!/usr/bin/env python3
"""
run_global.py — Search multiple cities around the world for a niche,
analyze all their websites, and collect flagged "bad website" companies
that have a real, self-published contact email (from their own site).

Usage:
    python run_global.py "restaurants" -o global_analyzed.csv --target 20

Edit CITIES below to change which cities/regions get searched.
"""
import argparse
import csv
import os
import random
import sys
import time

import find_companies as fc
import analyze_websites as aw


def load_excluded(path):
    excluded = set()
    if path and os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                if row:
                    excluded.add(row[0].strip().lower())
    return excluded

CITIES = [
    "New York, USA",
    "London, UK",
    "Paris, France",
    "Nairobi, Kenya",
    "Mumbai, India",
    "Bangkok, Thailand",
    "Sydney, Australia",
    "Sao Paulo, Brazil",
    "Dubai, UAE",
    "Tokyo, Japan",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("niche")
    ap.add_argument("-o", "--output", default="global_analyzed.csv")
    ap.add_argument("--target", type=int, default=20, help="stop once this many bad+emailed companies found")
    ap.add_argument("--radius", type=int, default=8000)
    ap.add_argument("--per-city-cap", type=int, default=40, help="max candidates to actually fetch/check per city")
    ap.add_argument("--exclude-file", default="contacted.csv",
                     help="CSV of previously-contacted company urls (one per line) to skip")
    args = ap.parse_args()

    excluded = load_excluded(args.exclude_file)
    print(f"Excluding {len(excluded)} previously-contacted companies from {args.exclude_file}", file=sys.stderr)

    qualified = []
    all_rows = []
    seen_names = set()
    cities = CITIES[:]
    random.shuffle(cities)

    for city in cities:
        if len(qualified) >= args.target:
            break
        print(f"\n=== {city} ===", file=sys.stderr)
        try:
            lat, lon = fc.geocode(city)
            time.sleep(1)
            try:
                query = fc.build_overpass_query(args.niche, lat, lon, args.radius)
                result = fc.query_overpass(query)
            except Exception:
                print("  overpass timed out, retrying with smaller radius...", file=sys.stderr)
                query = fc.build_overpass_query(args.niche, lat, lon, min(args.radius, 3000))
                result = fc.query_overpass(query)
        except Exception as e:
            print(f"  skip ({e})", file=sys.stderr)
            continue

        companies = []
        for el in result.get("elements", []):
            row = fc.extract_row(el)
            if row and row["url"] and row["name"] not in seen_names and row["url"].strip().lower() not in excluded:
                seen_names.add(row["name"])
                companies.append(row)

        print(f"  found {len(companies)} candidates with a listed website", file=sys.stderr)
        random.shuffle(companies)
        companies = companies[: args.per_city_cap]

        for c in companies:
            if len(qualified) >= args.target:
                break
            analysis = aw.analyze_one(c["name"], c["url"], check_contact_page=True)
            merged = {**c, "city": city, **analysis}
            all_rows.append(merged)
            if analysis["verdict"] == "bad" and analysis.get("found_email"):
                qualified.append(merged)
                print(f"  [{len(qualified)}/{args.target}] BAD+EMAIL: {c['name']} -> {analysis['found_email']}", file=sys.stderr)
            time.sleep(0.2)

    fieldnames = ["name", "city", "url", "phone", "address", "verdict", "score", "flags",
                  "load_time_s", "notes", "found_email"]
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)

    qualified_path = args.output.replace(".csv", "_qualified.csv")
    with open(qualified_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(qualified)

    print(f"\nChecked {len(all_rows)} companies total across {len(CITIES)} cities.", file=sys.stderr)
    print(f"Qualified (bad website + real contact email found): {len(qualified)} -> {qualified_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
