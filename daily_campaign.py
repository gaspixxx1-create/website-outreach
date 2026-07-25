#!/usr/bin/env python3
"""
daily_campaign.py — Run one day of the outreach campaign: mine the current
(country, niche) pair for qualified leads, and automatically advance to the
next niche (or next country, once every niche is exhausted) using persistent
state in campaign_state.json.

"Exhausted" means: a check-cap large enough to cover every remaining
candidate (after excluding already-contacted companies) was searched in a
single pass and the pool still fell short of the daily target. That pair is
then considered mined out and the state advances — it will not be retried.

Usage:
    python daily_campaign.py --daily-target 20

Outputs:
    campaign_state.json          — updated rotation position (commit + push this)
    daily_qualified.csv          — every qualified row found today, combined
    daily_report.json            — machine-readable summary for the day
"""
import argparse
import csv
import json
import os
import subprocess
import sys

STATE_FILE = "campaign_state.json"

NICHES = ["restaurant", "hairdresser", "dentist", "cafe", "auto repair", "pharmacy"]
COUNTRIES = ["NL", "DE"]

MAX_CHECK_PER_PASS = 3000
MAX_PASSES_PER_DAY = 6


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"country_index": 0, "niche_index": 0}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def run_batch(niche, country, target, batch_num):
    out_csv = f"daily_batch{batch_num}.csv"
    cmd = [
        sys.executable, "run_global.py", niche, "-o", out_csv,
        "--target", str(target), "--country", country,
        "--check-cap", str(MAX_CHECK_PER_PASS), "--exclude-file", "contacted.csv",
    ]
    print(f"Running: {' '.join(cmd)}", file=sys.stderr)
    subprocess.run(cmd, check=False)

    summary_path = out_csv.replace(".csv", "_summary.json")
    qualified_path = out_csv.replace(".csv", "_qualified.csv")
    summary = {}
    if os.path.exists(summary_path):
        with open(summary_path, encoding="utf-8") as f:
            summary = json.load(f)

    qualified_rows = []
    if os.path.exists(qualified_path):
        with open(qualified_path, newline="", encoding="utf-8") as f:
            qualified_rows = list(csv.DictReader(f))
        if qualified_rows:
            subprocess.run([sys.executable, "mark_contacted.py", qualified_path, "--log", "contacted.csv"], check=False)

    return summary, qualified_rows, qualified_path


def checkpoint(state, note):
    """Persist progress immediately so a killed/timed-out process doesn't
    lose everything found so far - push state + contacted.csv after every
    pass, not just at the very end."""
    save_state(state)
    try:
        subprocess.run(["git", "add", "contacted.csv", STATE_FILE], check=False, timeout=30)
        subprocess.run(["git", "commit", "-m", f"Campaign checkpoint: {note}"], check=False, timeout=30)
        subprocess.run(["git", "push"], check=False, timeout=60)
    except Exception as e:
        print(f"checkpoint push failed (non-fatal): {e}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--daily-target", type=int, default=20)
    args = ap.parse_args()

    print(f"daily_campaign.py starting. cwd={os.getcwd()} python={sys.version.split()[0]}", file=sys.stderr, flush=True)
    try:
        import urllib.request
        urllib.request.urlopen("https://overpass-api.de/api/interpreter", timeout=10)
    except Exception as e:
        print(f"WARNING: network connectivity check to overpass-api.de failed: {e}", file=sys.stderr, flush=True)
    else:
        print("Network connectivity check to overpass-api.de: OK", file=sys.stderr, flush=True)

    state = load_state()
    all_qualified = []
    all_qualified_paths = []
    passes = []

    for _ in range(MAX_PASSES_PER_DAY):
        if state["country_index"] >= len(COUNTRIES):
            print("All countries exhausted. No more configured markets to mine.", file=sys.stderr)
            break

        remaining = args.daily_target - len(all_qualified)
        if remaining <= 0:
            break

        country = COUNTRIES[state["country_index"]]
        niche = NICHES[state["niche_index"] % len(NICHES)]

        summary, qualified_rows, qualified_path = run_batch(niche, country, remaining, len(passes) + 1)
        passes.append({"country": country, "niche": niche, **summary})
        all_qualified.extend(qualified_rows)
        if qualified_rows:
            all_qualified_paths.append(qualified_path)
            checkpoint(state, f"pass {len(passes)} ({niche}/{country}): {len(qualified_rows)} found, {len(all_qualified)}/{args.daily_target} total")

        if summary.get("exhausted"):
            print(f"{niche} in {country} is exhausted (checked {summary.get('checked')} of {summary.get('candidates_found')} available).", file=sys.stderr)
            state["niche_index"] += 1
            if state["niche_index"] >= len(NICHES):
                state["niche_index"] = 0
                state["country_index"] += 1
                if state["country_index"] < len(COUNTRIES):
                    print(f"All niches exhausted for {country}. Advancing to {COUNTRIES[state['country_index']]}.", file=sys.stderr)
        else:
            # Pool not exhausted (either hit today's target, or there's more
            # left for tomorrow) - stay on this (country, niche) next time.
            break

    # Combine all qualified rows from every pass today into one CSV.
    fieldnames = ["name", "city", "url", "phone", "address", "verdict", "score", "flags",
                  "load_time_s", "notes", "found_email"]
    with open("daily_qualified.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_qualified)

    save_state(state)

    with open("daily_report.json", "w", encoding="utf-8") as f:
        json.dump({"passes": passes, "total_qualified_today": len(all_qualified), "state": state}, f, indent=2)

    print(f"\nDaily campaign done. {len(all_qualified)} qualified today -> daily_qualified.csv", file=sys.stderr)
    print(f"State: {state}", file=sys.stderr)


if __name__ == "__main__":
    main()
