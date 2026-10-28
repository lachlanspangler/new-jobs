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
