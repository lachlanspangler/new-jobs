# ADR 0001 — Generated data never lands in main; state lives on a one-commit `state` branch

**Status:** accepted (2026-10-28)

## Context
The board refreshes every 3 hours. Each run produces `docs/jobs.json` (~4.8 MB) and `seen.json` (~1.2 MB). Committing
them each run, as the old launchd script did, adds ~6 MB of churn eight times a day. Even with git's compression that
is gigabytes of history a year, carried by every clone. The fetcher also needs state to survive between runs:
first/last-seen dates (for "new today" and pruning) and the last good data (so a broken board keeps its jobs).

## Decision
1. **Deploy with the official Pages actions** (`upload-pages-artifact` + `deploy-pages`). The artifact is `docs/` plus a
   freshly generated `jobs.json`, assembled by `scripts/build_site.sh`. `docs/jobs.json` and `seen.json` are untracked
   and gitignored. Pages' source switches from "Deploy from a branch" to "GitHub Actions".
2. **State lives on a `state` branch holding exactly one parentless commit** (`seen.json` + the last deployed
   `jobs.json`), written with `git mktree`/`commit-tree` and force-pushed each run by a final `save-state` job that
   runs only after the deploy succeeds (`scripts/state.sh`). The fetch job itself is read-only. History never
   grows; old blobs become unreachable and GitHub garbage-collects them. Nobody needs to check it out.
3. **First run with no state branch** seeds from the live site's `jobs.json` (its `firstSeen` per job), so existing
   roles don't all show up as "new today" once. Failing to *reach* the remote is fatal rather than a reason to
   bootstrap, so a network blip can never overwrite good state with a reseeded copy.

## Alternatives considered
- **Actions cache** (with restore-keys fallback): free and simple, but entries are evicted after 7 days without
  access, are immutable (a new key per run), and are invisible outside Actions. Losing it silently resets every
  "first seen" date. Rejected as the primary store.
- **Artifacts from the previous run**: needs the API to find the last successful run's artifact and has 90-day
  retention; more moving parts than a branch.
- **Commit `seen.json` only to main**: 1.2 MB per run is still ~3 GB/year of history.
- **A separate data repo**: more setup for the owner (a second repo and a token) for no gain over a branch.

## Consequences
- The deployed `jobs.json` is reachable only on the live site, which is the only place anything reads it.
- `stats.html`'s tracker is untouched: same origin and paths, same job `key` formats, same localStorage keys.
- The owner flips one setting (Pages source → GitHub Actions) and optionally pushes the bootstrapped `state` branch.
