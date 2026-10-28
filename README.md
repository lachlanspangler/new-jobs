# new-jobs

A daily board of the newest **software & quant** roles across the biggest tech,
AI, quant, and hedge-fund employers — pulled from the public **Greenhouse**,
**Ashby**, and **Lever** APIs, filtered to the roles I care about, and shown on
a fast static site. Clicking **Apply** tallies your applications per company,
per role, and in total on a second page.

Live site: **https://lachlanspangler.github.io/new-jobs/**

## What it does

- Scans ~290 verified company boards (see `companies.json`) on Greenhouse, Ashby, Lever and Workday, plus
  openquant.co and Built In SF/NYC.
- Keeps target roles only: software / C++ / Python engineers, quant developer,
  quant researcher, quant, trade-desk operations, and adjacent SWE titles.
- Prioritizes **SF / Chicago / NYC** (★), flags roles first seen **today**, and
  shows location + salary (when the board exposes it).
- **Application tracker** (`stats.html`): clicking Apply records the role in
  your browser (localStorage) and tallies totals by company, by role, and
  overall. Export or clear anytime.

## How it updates

A GitHub Actions workflow (`.github/workflows/refresh.yml`) refreshes the board **every 3 hours** (at :17 past,
UTC) and redeploys the site. No laptop needed.

1. Restores the fetcher's state from the `state` branch: `seen.json` (first/last-seen date per posting) and the
   last deployed `jobs.json`.
2. Runs `fetch_jobs.py` over every board, then assembles `docs/` plus the fresh `jobs.json` into a Pages artifact.
3. Deploys it with the official Pages actions and saves the new state.

Generated data is never committed to `main`. The site ships as an artifact, and the `state` branch is a single commit
that's replaced each run, so the repo doesn't grow (`notes/adr/0001-data-out-of-git.md`).

- **A broken board never fails the run.** It's skipped, shown as a warning on the run, and its last good jobs stay on
  the site. If more than half the boards fail, or nothing comes back, the run stops before writing anything, so the
  live site and state stay as they were.
- **"New today"** means first seen on the current America/Chicago calendar day.
- **Old jobs are forgotten:** a posting gone from every board for 30+ days is pruned from `seen.json`. If it comes
  back, it counts as new. `jobs.json` only ever lists postings that are open now.
- **The apply tracker** (`stats.html`) lives in your browser's localStorage and isn't affected by any of this.

### Run it now, or check on it

- **Run now:** GitHub → **Actions** → **Refresh jobs** → **Run workflow**.
- **Check it's working:** the run list shows each run. Each run's summary has a table (live postings, target roles,
  new today, boards skipped, pruned). The board itself shows "updated N ago" next to the counts.
- Runs never overlap (a manual run queues behind a scheduled one), and each is capped at 30 minutes.

## Run it locally

```bash
python3 fetch_jobs.py            # refresh docs/jobs.json + seen.json (both gitignored)
python3 fetch_jobs.py --tag ai   # limit to a tag: ai / quant / hedge / tech (never prunes)
python3 -m http.server -d docs 8000   # open http://localhost:8000

make check   # unit tests + actionlint/shellcheck on the workflow and scripts
make site    # build the Pages artifact into _site/ exactly as CI does (state in .state/)
make serve   # serve _site/ on http://127.0.0.1:8611
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

## Draft outreach emails (Gmail)

`make_drafts.py` turns the contacts in `docs/recruiters.json` into personalized
**Gmail drafts** — it never sends. You review each in Gmail and hit send.

One-time setup: in Google Cloud Console, enable the **Gmail API**, create an
OAuth **Desktop app** client, and download it as `client_secret.json` here
(git-ignored). Then:

```bash
python3 make_drafts.py --dry-run     # preview who'd be drafted
python3 make_drafts.py --limit 20    # create up to 20 drafts (browser auth once)
```

- Uses the `gmail.compose` scope — create-drafts only; it can't send or read mail.
- Edit `email_template.txt` (placeholders `{first}`, `{company}`).
- Already-drafted addresses are tracked in `drafted.json` to avoid duplicates.
- Keep volume low and personalize — this is a review-then-send workflow, not a
  bulk sender.

## Notes

- Only employers on these three ATSes are covered; firms on custom career sites
  (some FAANG, and quant shops like Jane Street's own site, Citadel, Two Sigma)
  can't be pulled this way and are omitted.
- Salary coverage is partial — Ashby exposes it structured; Greenhouse/Lever
  only when it's in the posting.
