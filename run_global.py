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
    ap.add_argument("--cities", default="", help="semicolon-separated city list to override the default CITIES")
    ap.add_argument("--country", default="", help="ISO 3166-1 alpha-2 country code for a single nationwide query instead of per-city (e.g. NL)")
    ap.add_argument("--check-cap", type=int, default=300, help="[--country mode] max candidates to check nationwide")
    args = ap.parse_args()

    global CITIES
    if args.cities:
        CITIES = [c.strip() for c in args.cities.split(";") if c.strip()]

    excluded = load_excluded(args.exclude_file)
    print(f"Excluding {len(excluded)} previously-contacted companies from {args.exclude_file}", file=sys.stderr)

    qualified = []
    all_rows = []
    seen_names = set()

    if args.country:
        print(f"\n=== Nationwide: {args.country.upper()} ===", file=sys.stderr)
        query = fc.build_overpass_country_query(args.niche, args.country)
        result = fc.query_overpass(query)

        companies = []
        for el in result.get("elements", []):
            row = fc.extract_row(el)
            if row and row["url"] and row["name"] not in seen_names and row["url"].strip().lower() not in excluded:
                seen_names.add(row["name"])
                companies.append(row)

        total_candidates = len(companies)
        print(f"  found {total_candidates} candidates with a listed website nationwide", file=sys.stderr)
        random.shuffle(companies)
        companies = companies[: args.check_cap]

        for i, c in enumerate(companies, 1):
            if len(qualified) >= args.target:
                break
            analysis = aw.analyze_one(c["name"], c["url"], check_contact_page=True)
            merged = {**c, "city": args.country.upper(), **analysis}
            all_rows.append(merged)
            if analysis["verdict"] == "bad" and analysis.get("found_email"):
                qualified.append(merged)
                print(f"  [{len(qualified)}/{args.target}] ({i}/{len(companies)}) BAD+EMAIL: {c['name']} -> {analysis['found_email']}", file=sys.stderr)
            elif i % 20 == 0:
                print(f"  ...checked {i}/{len(companies)}, {len(qualified)} qualified so far", file=sys.stderr)
            time.sleep(0.2)

        write_outputs(args, all_rows, qualified)
        # Only truly exhausted if the check-cap covered the ENTIRE remaining
        # pool (not just the post-cap slice) and we checked all of it without
        # stopping early because today's target was already reached.
        exhausted = total_candidates <= args.check_cap and len(all_rows) == len(companies)
        write_summary(args, niche=args.niche, country=args.country.upper(),
                      candidates_found=total_candidates, checked=len(all_rows),
                      qualified=len(qualified), exhausted=exhausted)
        print(f"\nChecked {len(all_rows)} companies nationwide in {args.country.upper()}.", file=sys.stderr)
        print(f"Qualified: {len(qualified)} -> {args.output.replace('.csv', '_qualified.csv')}", file=sys.stderr)
        print(f"Exhausted: {exhausted}", file=sys.stderr)
        return

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
        time.sleep(2)  # avoid Overpass 429 rate limiting between cities

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

    write_outputs(args, all_rows, qualified)
    print(f"\nChecked {len(all_rows)} companies total across {len(CITIES)} cities.", file=sys.stderr)
    print(f"Qualified (bad website + real contact email found): {len(qualified)} -> {args.output.replace('.csv', '_qualified.csv')}", file=sys.stderr)


def write_summary(args, **fields):
    import json
    summary_path = args.output.replace(".csv", "_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(fields, f)


def write_outputs(args, all_rows, qualified):
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


if __name__ == "__main__":
    main()
