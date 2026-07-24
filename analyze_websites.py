#!/usr/bin/env python3
"""
analyze_websites.py — Score companies' websites for "bad website" signals.

Usage:
    python analyze_websites.py companies.csv -o analyzed.csv

Input CSV must have at least: name,url  (extra columns like phone/address
are passed through untouched). A blank url is treated as "no website".

Output CSV adds: verdict, score, flags, load_time_s, notes
- verdict is "bad" (good outreach target) or "ok"
- flags is a semicolon-separated list of the specific issues found

Uses only the Python standard library — no pip installs required.
"""
import argparse
import csv
import re
import ssl
import sys
import time
import urllib.error
import urllib.request

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
TIMEOUT = 6
SLOW_THRESHOLD_S = 4.0
STALE_YEARS = 4

FLAG_WEIGHTS = {
    "no_website": 6,
    "unreachable": 4,
    "broken_status": 4,
    "no_https": 2,
    "not_mobile_friendly": 2,
    "outdated_tech": 3,
    "stale_copyright": 1,
    "slow_load": 1,
    "no_doctype": 1,
    "no_title": 1,
}

FLAG_LABELS = {
    "no_website": "no website found",
    "unreachable": "site did not respond",
    "broken_status": "site returned an error page",
    "no_https": "not using HTTPS (insecure)",
    "not_mobile_friendly": "not mobile-friendly (no responsive viewport tag)",
    "outdated_tech": "uses outdated tech (frames/Flash)",
    "stale_copyright": "footer copyright year looks stale",
    "slow_load": "slow to load",
    "no_doctype": "missing modern HTML doctype",
    "no_title": "missing page title",
}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    ctx = ssl.create_default_context()
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
        body = resp.read(2_000_000).decode("utf-8", errors="ignore")
        status = resp.status
        final_url = resp.geturl()
    elapsed = time.perf_counter() - start
    return status, body, final_url, elapsed


CONTACT_PATHS = ["/contact", "/contact-us", "/about"]


def find_contact_page_email(base_url):
    for path in CONTACT_PATHS:
        try:
            status, body, _, _ = fetch(base_url.rstrip("/") + path)
        except Exception:
            continue
        if status < 400:
            email = extract_email(body)
            if email:
                return email
    return ""


def analyze_one(name, url, check_contact_page=False):
    flags = []
    notes = []
    load_time = None

    if not url or not url.strip():
        return {"verdict": "bad", "score": FLAG_WEIGHTS["no_website"], "flags": "no_website",
                "load_time_s": "", "notes": "no url provided", "found_email": ""}

    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "http://" + url

    if url.lower().split("?")[0].endswith(BINARY_EXTENSIONS):
        return {"verdict": "bad", "score": FLAG_WEIGHTS["no_website"], "flags": "no_website",
                "load_time_s": "", "notes": "listed 'website' is a direct file link, not a page", "found_email": ""}

    try:
        status, body, final_url, elapsed = fetch(url)
        load_time = round(elapsed, 2)
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        flags.append("unreachable")
        notes.append(str(e)[:120])
        score = sum(FLAG_WEIGHTS[f] for f in flags)
        return {"verdict": "bad", "score": score, "flags": ";".join(flags),
                "load_time_s": "", "notes": "; ".join(notes), "found_email": ""}

    if status >= 400:
        flags.append("broken_status")
        notes.append(f"HTTP {status}")

    if not final_url.lower().startswith("https://"):
        flags.append("no_https")

    if load_time is not None and load_time > SLOW_THRESHOLD_S:
        flags.append("slow_load")
        notes.append(f"{load_time}s load time")

    if not re.search(r'<meta[^>]+name=["\']viewport["\']', body, re.I):
        flags.append("not_mobile_friendly")

    if re.search(r"<frameset|<frame\s|application/x-shockwave-flash|\.swf[\"']", body, re.I):
        flags.append("outdated_tech")

    if not re.search(r"<!doctype\s+html>", body, re.I):
        flags.append("no_doctype")

    if not re.search(r"<title>\s*\S+.*?</title>", body, re.I):
        flags.append("no_title")

    year_match = re.search(r"(?:copyright|©|\(c\))\D{0,10}(20\d{2})", body, re.I)
    if year_match:
        year = int(year_match.group(1))
        current_year = time.localtime().tm_year
        if current_year - year >= STALE_YEARS:
            flags.append("stale_copyright")
            notes.append(f"copyright year {year}")

    found_email = extract_email(body)

    score = sum(FLAG_WEIGHTS[f] for f in flags)
    verdict = "bad" if score >= 3 else "ok"

    if check_contact_page and verdict == "bad" and not found_email:
        found_email = find_contact_page_email(final_url)

    return {"verdict": verdict, "score": score, "flags": ";".join(flags),
            "load_time_s": load_time if load_time is not None else "",
            "notes": "; ".join(notes), "found_email": found_email}


EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
IGNORE_DOMAINS = ("sentry.io", "example.com", "wixpress.com", "godaddy.com", "schema.org",
                   "adobe.com", "w3.org", "google.com", "gstatic.com", "facebook.com",
                   "cloudflare.com", "wordpress.org", "wordpress.com")
BINARY_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".pdf", ".svg", ".webp", ".ico", ".bmp")


def looks_plausible(addr):
    local = addr.split("@")[0]
    if not re.match(r"^[a-zA-Z0-9](?:[a-zA-Z0-9._%+\-]*[a-zA-Z0-9])?$", local):
        return False
    if len(local) < 2:
        return False
    return True


def extract_email(body):
    """Pull a contact email the business itself published on its own page
    (mailto: links first, else a bare email pattern in the visible HTML).
    Never guesses/invents an address."""
    mailtos = re.findall(r'mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', body, re.I)
    for addr in mailtos:
        if not addr.lower().endswith(IGNORE_DOMAINS) and looks_plausible(addr):
            return addr
    for addr in EMAIL_RE.findall(body):
        if (not addr.lower().endswith(IGNORE_DOMAINS) and looks_plausible(addr)
                and not re.search(r"\.(png|jpg|jpeg|gif|svg|webp)$", addr, re.I)):
            return addr
    return ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input_csv")
    ap.add_argument("-o", "--output", default="analyzed.csv")
    args = ap.parse_args()

    with open(args.input_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []

    if "name" not in fieldnames:
        raise SystemExit("Input CSV must have a 'name' column")

    out_fields = list(fieldnames)
    for extra in ["verdict", "score", "flags", "load_time_s", "notes", "found_email"]:
        if extra not in out_fields:
            out_fields.append(extra)
    if "url" not in out_fields:
        out_fields.insert(1, "url")

    results = []
    bad_count = 0
    for i, row in enumerate(rows, 1):
        name = row.get("name", "").strip()
        url = row.get("url", "")
        print(f"[{i}/{len(rows)}] Checking {name}...", file=sys.stderr)
        analysis = analyze_one(name, url)
        row.update(analysis)
        if analysis["verdict"] == "bad":
            bad_count += 1
            human_flags = ", ".join(FLAG_LABELS.get(f, f) for f in analysis["flags"].split(";") if f)
            print(f"    -> BAD ({human_flags})", file=sys.stderr)
        results.append(row)
        time.sleep(0.3)  # be polite to target servers

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nDone: {bad_count}/{len(rows)} flagged as bad -> {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
