# Diary

Append-only, newest at the bottom. Decisions, surprises, numbers.

## 2026-10-28 — Auto-update kickoff
**Found:** no `.github/workflows`; the launchd job in `scripts/` was never loaded, so every "Refresh jobs" commit was by
hand (last 2026-10-12; main is 1 commit ahead of origin with it). Repo is **public** (so Actions minutes are free and
unlimited on standard runners) and Pages currently serves from the branch (`main` `/docs`).
**Ran `python3 fetch_jobs.py` once** (in a scratch copy, to keep the tree clean): 7 min 12 s wall time; 290 companies
→ 30,018 live postings → 11,859 target roles (1,986 "new today" — inflated because the last run was 16 days ago);
7 boards failed (Old Mission, Amplitude, Postman, Shield AI, Wayve: HTTP 404; Palantir, Zoox: read timeout).
Outputs: `docs/jobs.json` 4.8 MB, `seen.json` 1.2 MB.
**Memory question — real.** Committing those every 3 hours ≈ 8 × ~6 MB of churn a day; even compressed, that is
gigabytes of history a year, and every clone would carry it. So: data never goes to `main` (ADR 0001).
**Plan:** setup notes → fetcher hardening (state paths, last-seen dates, pruning, broken-board carry-forward, run guard)
with tests → workflow (schedule, button, concurrency, timeout, Pages deploy, state branch) + actionlint → untrack the
data → README → local verification with a screenshot → fresh code review.

## 2026-10-28 — Fetcher, workflow, state, verification
**Fetcher** (`fetch_jobs.py`, still stdlib only; parsers and filters unchanged): `seen.json` now stores
`key -> [first_seen, last_seen]`; postings gone from every board for 30+ days are pruned (full runs only; never for a
board that failed this run); a pruned posting that comes back gets a new first-seen date, so it shows as new. A board
that raises *anything* is skipped, logged as a warning annotation, and its rows from the last good `jobs.json` are
carried forward (without refreshing their last-seen). Built In now raises when its first page fails, instead of
quietly returning nothing. If more than half the boards fail, or no roles come back, the run exits 2 before writing
anything. CI paths (`--seen/--previous/--out`), atomic writes, and a run-summary table on the Actions run.
**Decided:** `TZ=America/Chicago` in CI so "new today" is the owner's day (ADR 0002). State on a one-commit `state`
branch rather than the Actions cache, which evicts after 7 idle days and would silently reset every first-seen date
(ADR 0001). Removed `scripts/update.sh` + the launchd plist: they committed the data to main, which is now gitignored,
and Actions replaces them. Action versions pinned to commit SHAs (checkout v7.0.1, setup-python v7.1.0,
upload-pages-artifact v5.0.0, deploy-pages v5.0.1), with Dependabot to keep them current.
**State bootstrap (numbers):** the old `seen.json` only had first-seen dates. I rebuilt last-seen from the 21
`docs/jobs.json` snapshots in git history, plus today's live run: 19,449 entries, 334 never in any snapshot
(last = first). Then a real CI-equivalent run (`make site`, 7 min 8 s):
- live postings 30,620 → **12,168 target roles** (2,016 first seen today: the last refresh was 16 days ago)
- **seen.json 19,449 → 16,601 entries** (−2,879 pruned: gone 30+ days; +31 new since the morning run),
  1.42 MB → 1.18 MB
- jobs.json 4.9 MB, open postings only
- 5 boards skipped (Old Mission, Amplitude, Postman, Shield AI, Wayve: HTTP 404, so their tokens are dead); 0
  carried, since they had no previous rows. Palantir and Zoox, which timed out in the morning, came back.
The result is on a local `state` branch (one parentless commit) for the owner to push, so CI starts from accurate
history instead of reseeding from the live site.
**Verified by use:** served `_site/` on 127.0.0.1:8611 with Playwright: 12,168 roles, 2,016 new today, the new-today
filter works, and clicking Apply recorded the job in `nj-apps` and showed it on `stats.html` (screenshots in
`notes/screenshots/`); no console errors. Found and fixed one small thing: "updated N ago" floored at "1h", so a
fresh deploy read "updated 1h ago". It now shows minutes.
**Noted, not changed (scope):** 5 dead board tokens in `companies.json`; those boards fail every run, so their old
seen entries are protected from pruning until they're fixed or removed.
