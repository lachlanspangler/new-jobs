# CLAUDE.md — new-jobs

A static job board of new software / quant roles, pulled from public ATS APIs (Greenhouse, Ashby, Lever, Workday)
plus openquant.co and Built In SF/NYC. Live at https://lachlanspangler.github.io/new-jobs/.

Start every session with `notes/STATUS.md`, then the last entries of `notes/DIARY.md` (append-only, newest at the
bottom). Don't stop to ask the owner what you can decide: pick the sensible default, write why in the diary, keep
going. Big decisions get an ADR in `notes/adr/NNNN-title.md`.

## How it runs
- `.github/workflows/refresh.yml` runs `fetch_jobs.py` every 3 hours (and on the "Run workflow" button), then deploys
  `docs/` + the fresh `jobs.json` with the official Pages actions. Generated data is **never committed to main**.
- State that must survive between runs (`seen.json` first/last-seen dates, last `jobs.json` for broken-board
  carry-forward) lives on the `state` branch as a single force-pushed commit (ADR 0001).
- `docs/` is the static site; `stats.html` tracks applications in the browser's localStorage (keys `nj-apps`,
  `nj-dismissed`, `nj-status`) — never change job `key` formats or those storage keys.

## Commands
| | |
|---|---|
| `make check` | unit tests + actionlint on the workflow + compile check |
| `make fetch` | run the fetcher locally (writes gitignored `docs/jobs.json`, `seen.json`) |
| `make site` | assemble the Pages artifact into `_site/` exactly as CI does |
| `make serve` | serve `_site/` on http://127.0.0.1:8611 |

## Rules
- `fetch_jobs.py` stays standard-library only (no pip install in CI).
- One broken board never fails a run: skip it, log it, keep its last good jobs.
- Be polite to the ATS APIs: keep the pacing, never raise the cadence above every 3 hours without an ADR.
- Never commit secrets (`token.json`, `client_secret.json` are gitignored) or generated data (`docs/jobs.json`,
  `seen.json`).
- Commit locally; the owner pushes.
- `notes/` is outside `docs/`, so Pages never serves it.
