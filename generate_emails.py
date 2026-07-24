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
    "en": {
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
    },
    "nl": {
        "no_website": "Ik zag dat {company} nog geen website heeft",
        "unreachable": "Ik probeerde de website van {company} te bezoeken, maar die laadde niet",
        "broken_status": "Ik bezocht de website van {company} en er verschijnt momenteel een foutmelding",
        "no_https": "Ik bezocht de website van {company} en zag dat deze geen beveiligde HTTPS-verbinding gebruikt, wat browsers tegenwoordig als \"Niet beveiligd\" aanmerken",
        "not_mobile_friendly": "Ik bezocht de website van {company} op mijn telefoon en zag dat deze niet geoptimaliseerd is voor mobiel",
        "outdated_tech": "Ik bezocht de website van {company} en zag dat deze gebruikmaakt van behoorlijk verouderde technologie",
        "stale_copyright": "Ik bezocht de website van {company} en het lijkt erop dat deze al een tijdje niet is bijgewerkt",
        "slow_load": "Ik bezocht de website van {company} en het duurde behoorlijk lang voordat deze laadde",
        "no_doctype": "Ik bezocht de website van {company} en zag dat deze een verouderde paginastructuur gebruikt",
        "no_title": "Ik bezocht de website van {company} en zag dat er basisinformatie ontbreekt die zoekmachines nodig hebben",
        "default": "Ik heb even naar de website van {company} gekeken",
    },
}

SUBJECT_TEMPLATES = {
    "en": {
        "no_website": "Quick idea for {company}'s online presence",
        "default": "Quick note about {company}'s website",
    },
    "nl": {
        "no_website": "Snel ideetje voor de online aanwezigheid van {company}",
        "default": "Korte opmerking over de website van {company}",
    },
}

BODY_TEMPLATES = {
    "en": """Hi there,

{observation}, and thought I'd reach out.

A website is often the first impression a potential customer gets of {company}, and right now it might be costing you business without you realizing it. I help local businesses like yours get a modern, fast, mobile-friendly website that actually brings in customers.

If you're open to it, I'd be happy to put together a quick, no-obligation mockup of what an updated site could look like for {company}. No cost, no pressure either way.

Would you be open to a short call this week? And if you'd rather not hear from me again, just let me know and I won't follow up.

Best,
{from_name}{signature_extra}
""",
    "nl": """Hoi,

{observation}, en daarom wilde ik contact opnemen.

Een website is vaak de eerste indruk die een potentiële klant van {company} krijgt, en op dit moment kost dat je misschien klanten zonder dat je het doorhebt. Ik help lokale bedrijven zoals dat van jou aan een moderne, snelle en mobielvriendelijke website die daadwerkelijk klanten oplevert.

Als je daarvoor openstaat, maak ik graag gratis en vrijblijvend een korte mock-up van hoe een vernieuwde website voor {company} eruit zou kunnen zien. Geen kosten, geen verplichtingen.

Zou je deze week open staan voor een kort gesprek? Laat het me anders gerust weten als je liever niet meer bericht van me krijgt, dan neem ik geen contact meer op.

Met vriendelijke groet,
{from_name}{signature_extra}
""",
}


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:60]


def build_email(row, from_name, your_company, your_phone, portfolio_url, lang="en"):
    company = row["name"].strip()
    flags = [f for f in row.get("flags", "").split(";") if f]
    primary_flag = flags[0] if flags else "default"

    sentences = FLAG_SENTENCES.get(lang, FLAG_SENTENCES["en"])
    subjects = SUBJECT_TEMPLATES.get(lang, SUBJECT_TEMPLATES["en"])

    observation = sentences.get(primary_flag, sentences["default"]).format(company=company)
    subject = subjects.get(primary_flag, subjects["default"]).format(company=company)

    extra_lines = [line for line in (your_company, your_phone, portfolio_url) if line]
    signature_extra = ("\n" + "\n".join(extra_lines)) if extra_lines else ""

    body = BODY_TEMPLATES.get(lang, BODY_TEMPLATES["en"]).format(
        observation=observation, company=company, from_name=from_name,
        signature_extra=signature_extra,
    )
    return subject, body


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("analyzed_csv")
    ap.add_argument("--from-name", required=True)
    ap.add_argument("--your-company", required=True)
    ap.add_argument("--your-phone", default="")
    ap.add_argument("--portfolio-url", default="")
    ap.add_argument("--lang", default="en", choices=["en", "nl"])
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
            subject, body = build_email(row, args.from_name, args.your_company, args.your_phone, args.portfolio_url, args.lang)
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
