#!/usr/bin/env python3
"""
generate_emails.py — Turn flagged "bad website" companies into personalized
outreach drafts (text files you review/send yourself, or feed to your own
mail client / CRM / mail-merge tool).

Usage:
    python generate_emails.py analyzed.csv --from-name "Your Name" \
        --your-company "Acme Web Studio" --your-phone "555-123-4567" \
        --portfolio-url "https://acmewebstudio.com" -o emails/

Notes:
- This script does NOT send anything. It only writes .txt files.
- Recipient email addresses are NOT guessed or scraped here on purpose —
  find real contact addresses yourself (company site, LinkedIn, a phone
  call) and put them in the CSV's `email` column, or fill them in before
  you send. Emailing addresses you invented (e.g. info@domain guesses)
  to companies that never gave you that address is exactly the kind of
  cold-email pattern that gets flagged as spam / can violate anti-spam law.
- Keep your list small and personalized rather than mass-blasting; a
  95%-templated email to a real prospect converts far better than a
  1000-recipient blast, and is much less likely to get you blacklisted.
"""
import argparse
import csv
import os
import re
import sys

FLAG_SENTENCES = {
    "no_website": "I noticed {company} doesn't have a website yet",
    "unreachable": "I tried to visit {company}'s website and it wouldn't load",
    "broken_status": "I visited {company}'s website and it's currently showing an error page",
    "no_https": "I visited {company}'s website and noticed it isn't using a secure HTTPS connection, which browsers now flag as \"Not Secure\"",
    "not_mobile_friendly": "I visited {company}'s website on my phone and noticed it isn't optimized for mobile",
    "outdated_tech": "I visited {company}'s website and noticed it's built on some fairly outdated technology",
    "stale_copyright": "I visited {company}'s website and it looks like it hasn't been updated in a while",
    "slow_load": "I visited {company}'s website and it took quite a while to load",
    "no_doctype": "I visited {company}'s website and noticed it uses an outdated page structure",
    "no_title": "I visited {company}'s website and noticed it's missing basic page info search engines look for",
    "default": "I took a look at {company}'s website",
}

SUBJECT_TEMPLATES = {
    "no_website": "Quick idea for {company}'s online presence",
    "default": "Quick note about {company}'s website",
}


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:60]


def build_email(row, from_name, your_company, your_phone, portfolio_url):
    company = row["name"].strip()
    flags = [f for f in row.get("flags", "").split(";") if f]
    primary_flag = flags[0] if flags else "default"

    observation = FLAG_SENTENCES.get(primary_flag, FLAG_SENTENCES["default"]).format(company=company)
    subject = SUBJECT_TEMPLATES.get(primary_flag, SUBJECT_TEMPLATES["default"]).format(company=company)

    body = f"""Hi there,

{observation}, and thought I'd reach out.

A website is often the first impression a potential customer gets of {company} — and right now it might be costing you business without you realizing it. I help local businesses like yours get a modern, fast, mobile-friendly website that actually brings in customers.

If you're open to it, I'd be happy to put together a quick, no-obligation mockup of what an updated site could look like for {company} — no cost, no pressure either way.

Would you be open to a short call this week?

Best,
{from_name}
{your_company}
{your_phone}
{portfolio_url}

---
If you'd rather not hear from me again, just reply and let me know and I won't follow up.
"""
    return subject, body


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("analyzed_csv")
    ap.add_argument("--from-name", required=True)
    ap.add_argument("--your-company", required=True)
    ap.add_argument("--your-phone", default="")
    ap.add_argument("--portfolio-url", default="")
    ap.add_argument("-o", "--outdir", default="emails")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    with open(args.analyzed_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    bad_rows = [r for r in rows if r.get("verdict") == "bad"]
    if not bad_rows:
        print("No rows with verdict=bad found. Run analyze_websites.py first.", file=sys.stderr)
        return

    master_path = os.path.join(args.outdir, "_master.csv")
    with open(master_path, "w", newline="", encoding="utf-8") as mf:
        writer = csv.writer(mf)
        writer.writerow(["company", "email", "url", "subject", "file"])
        for row in bad_rows:
            company = row["name"].strip()
            subject, body = build_email(row, args.from_name, args.your_company, args.your_phone, args.portfolio_url)
            fname = f"{slugify(company)}.txt"
            fpath = os.path.join(args.outdir, fname)
            with open(fpath, "w", encoding="utf-8") as ef:
                ef.write(f"Subject: {subject}\n\n{body}")
            email = row.get("email", "") or row.get("found_email", "")
            writer.writerow([company, email, row.get("url", ""), subject, fname])

    print(f"Wrote {len(bad_rows)} email drafts to {args.outdir}/", file=sys.stderr)
    print(f"Fill in verified recipient addresses in {master_path} before sending.", file=sys.stderr)


if __name__ == "__main__":
    main()
