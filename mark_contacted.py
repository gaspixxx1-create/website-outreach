#!/usr/bin/env python3
"""
mark_contacted.py — Append companies from a qualified/emails CSV to the
contacted-log so future run_global.py runs skip them (no duplicate drafts).

Usage:
    python mark_contacted.py global_analyzed_qualified.csv --log contacted.csv
"""
import argparse
import csv
import os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_file", help="CSV with a 'url' column (e.g. the _qualified.csv)")
    ap.add_argument("--log", default="contacted.csv")
    args = ap.parse_args()

    with open(args.csv_file, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    existing = set()
    if os.path.exists(args.log):
        with open(args.log, newline="", encoding="utf-8") as f:
            existing = {r[0].strip().lower() for r in csv.reader(f) if r}

    new_urls = [r["url"].strip() for r in rows if r.get("url") and r["url"].strip().lower() not in existing]

    with open(args.log, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for url in new_urls:
            writer.writerow([url])

    print(f"Logged {len(new_urls)} newly-contacted companies to {args.log}")


if __name__ == "__main__":
    main()
