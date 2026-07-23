# Website Outreach Toolkit

Find local businesses with bad/outdated websites and generate personalized
outreach emails offering to redesign their site. Three stages, run in order.
No pip installs required — everything uses only the Python standard library.

## 1. Find companies

Either bring your own list (CSV with at least `name` and `url` columns —
see `companies_sample.csv`), or search OpenStreetMap for free:

```bash
python find_companies.py "plumbers" "Tulsa, OK" -o companies.csv
```

This geocodes the location (Nominatim) and pulls matching businesses from
OpenStreetMap (Overpass API) — no API key needed. Coverage varies by area;
if you get few/no results, try a bigger `--radius` or a broader niche word,
or just build the CSV by hand from Google Maps results.

## 2. Analyze their websites

```bash
python analyze_websites.py companies.csv -o analyzed.csv
```

Fetches each site and flags: no website, unreachable, HTTP errors, no
HTTPS, not mobile-friendly (no responsive viewport tag), outdated tech
(frames/Flash), stale copyright year, slow load time, missing doctype/title.
Each company gets a `verdict` (`bad` or `ok`), a `score`, and a `flags` list.

## 3. Generate outreach emails

```bash
python generate_emails.py analyzed.csv \
    --from-name "Your Name" \
    --your-company "Your Studio" \
    --your-phone "555-123-4567" \
    --portfolio-url "https://yourstudio.com" \
    -o emails/
```

Writes one personalized `.txt` draft per flagged company (subject + body,
referencing the *specific* issue found on their site) plus `emails/_master.csv`
listing them all. **This step does not send anything.**

## 4. Sending

The `email` column in `_master.csv` is intentionally left blank — go find
each company's real published contact address (their site, a phone call,
LinkedIn) rather than guessing `info@domain.com`. Emailing addresses you
invented, or blasting hundreds of strangers with an identical template, is
what gets outreach flagged as spam and can run afoul of anti-spam law
(CAN-SPAM in the US requires your real postal address and an opt-out in
every commercial email — both are already included in the template).

If you'd like, tell Claude which companies from `_master.csv` you want to
reach out to and it can create the messages as **drafts** in your connected
Gmail account for you to personally review and send — it won't send bulk
email on your behalf automatically.

## Ethics/legal notes

- Keep lists small and genuinely personalized — better reply rates, lower
  spam risk, than a mass blast.
- Some jurisdictions (e.g. EU/UK under PECR/GDPR) restrict unsolicited B2C
  commercial email more than B2B — check rules for your target region.
- Always honor opt-out replies immediately.
