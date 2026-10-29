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

## 2026-10-28 — Fresh code review: findings and fixes
A fresh reviewer (given the code and the requirements, not my conclusions) verified the pinned SHAs against their
tags, confirmed the owner's setup order is safe, and found:
1. **A board that fails forever kept its jobs on the site forever** (carried rows never aged). Fixed: carry only rows
   confirmed live within the 30-day window; warn once a board has failed past that.
2. **Outages that look like empty boards** (Built In serving a 200 challenge page from datacenter IPs, openquant
   without `__NEXT_DATA__`, a non-list Lever payload) silently dropped jobs. Fixed: they raise, so they count as
   failures. Added a mass-outage guard: abort if roles fall under 50% of the last run (`--allow-drop`, exposed as a
   "Run workflow" checkbox).
3. **State was saved before the deploy, and from any branch.** Fixed: three jobs, refresh → deploy → save-state;
   save-state runs only after a successful deploy; everything is gated to `main`.
4. **A red run didn't name the failed boards.** Fixed: the abort path annotates each failure first.
5. **`build_site.sh` would `rm -rf` any target**, including `.` or `docs`. Fixed: unsafe targets are refused (11
   tested), and the build goes to a temp dir that's swapped in only on success.
Hardening: the fetch job is now read-only (`contents: read`, `persist-credentials: false`, since the fetcher parses
untrusted remote data), and `contents: write` exists only in save-state. The keepalive moved to its own job holding
the only `actions: write` grant; it runs even after a red refresh. First-run seeding converts `generated_at` to local
time. A corrupt state file now stops with an explanation.
**Not fixed (low risk, in STATUS):** no per-board time budget; local `--tag` runs overwrite `docs/jobs.json` (as
before); failures are keyed by `ats:token`.
29 unit tests + 2 shell test suites + actionlint/shellcheck green. Re-verified the hardened `build_site.sh` with a
small real run (`--tag hedge`: 341 roles).

## 2026-10-28 — Review sign-off
The reviewer re-checked all three fix commits and **signed off** (5/5 bugs fixed; new action pins verified). Its
non-blocking follow-ups are done too: `build_site.sh`'s guard was a denylist that still accepted `.git`, `scripts`,
`docs//` and `Docs` (the same folder as `docs` on case-insensitive macOS). It's now an **allowlist** (only a top-level
`_site`, `_site-*` or `_site_*`), tested against 20 unsafe targets. Also: a carried row without a key can't crash;
STATUS and ADR 0002 note that going private would need the token for the anonymous state restore (it fails safely
until then). Accepted as is: if save-state fails after a good deploy, the site is one run ahead of its state (worst
case a few jobs show "new" for a second day).

## 2026-10-29 — Synced with GitHub
The remote had two web edits to the README title ("[no longer used, I switched to job-finder]", then back to "new-jobs"); merged both, so local main is now 0 behind / 17+ ahead of origin and will fast-forward. The owner's first push attempt ran `! cd … && git push` in Terminal, where zsh's `!` inverts the exit status, so nothing was pushed.
