# new-jobs

A daily board of the newest **software & quant** roles across the biggest tech,
AI, quant, and hedge-fund employers — pulled from the public **Greenhouse**,
**Ashby**, and **Lever** APIs, filtered to the roles I care about, and shown on
a fast static site. Clicking **Apply** tallies your applications per company,
per role, and in total on a second page.

Live site: **https://lachlanspangler.github.io/new-jobs/**

## What it does

- Scans ~80 verified company boards (see `companies.json`) across three ATSes.
- Keeps target roles only: software / C++ / Python engineers, quant developer,
  quant researcher, quant, trade-desk operations, and adjacent SWE titles.
- Prioritizes **SF / Chicago / NYC** (★), flags roles first seen **today**, and
  shows location + salary (when the board exposes it).
- **Application tracker** (`stats.html`): clicking Apply records the role in
  your browser (localStorage) and tallies totals by company, by role, and
  overall. Export or clear anytime.

## How it's built

- `fetch_jobs.py` — stdlib-only fetcher; writes `docs/jobs.json` and tracks a
  first-seen date per posting in `seen.json` (powers "new today").
- `docs/` — static site (`index.html` jobs board, `stats.html` tracker). No
  backend; tallies live in the browser.
- Rebuilt daily via `scripts/update.sh` + a launchd job.

## Run it

```bash
python3 fetch_jobs.py            # refresh docs/jobs.json
python3 fetch_jobs.py --tag ai   # limit to a tag: ai / quant / hedge / tech
# serve locally:
python3 -m http.server -d docs 8000   # open http://localhost:8000
```

## Daily automation

```bash
cp scripts/com.lachlan.newjobs.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.lachlan.newjobs.plist   # runs 07:30 daily
```

## Add companies

Append to `companies.json` as `{ "name", "ats", "token", "tags" }`. Validate the
token returns a non-empty job list first:

- Greenhouse: `https://boards-api.greenhouse.io/v1/boards/<token>/jobs`
- Ashby: `https://api.ashbyhq.com/posting-api/job-board/<token>`
- Lever: `https://api.lever.co/v0/postings/<token>?mode=json`

## Recruiter contacts (Recruiters page)

`fetch_recruiters.py` pulls talent/HR contacts per company using an official API
with **your** key and writes `docs/recruiters.json`. Nothing is scraped or
guessed.

```bash
HUNTER_API_KEY=xxxx python3 fetch_recruiters.py            # preferred (real, scored emails)
HUNTER_API_KEY=xxxx python3 fetch_recruiters.py --tag quant --tag ai
APOLLO_API_KEY=xxxx python3 fetch_recruiters.py            # fallback (emails often locked)
```

- **Hunter.io** (Domain Search) is the higher-yield source: it returns real,
  deliverability-scored addresses for each company's `domain` (mapped in
  `companies.json`), with name, title, and LinkedIn. The page shows a
  confidence % and a ready-to-send email draft (mailto) per contact.
- Free tiers are limited (Hunter ~25–50 searches/mo), so run by `--tag` in
  batches. Keep outreach personalized and low-volume — cold-blasting a big list
  wrecks deliverability and can violate anti-spam law and platform terms.

## Notes

- Only employers on these three ATSes are covered; firms on custom career sites
  (some FAANG, and quant shops like Jane Street's own site, Citadel, Two Sigma)
  can't be pulled this way and are omitted.
- Salary coverage is partial — Ashby exposes it structured; Greenhouse/Lever
  only when it's in the posting.
