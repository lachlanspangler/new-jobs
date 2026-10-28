# Status — 2026-10-28

## What's built
The board now updates itself, with no laptop involved.
- **`.github/workflows/refresh.yml`** runs every 3 hours (`17 */3 * * *` UTC, 8 runs a day, ~7 minutes each) and on
  demand (**Actions → Refresh jobs → Run workflow**). It restores state, runs `fetch_jobs.py`, builds `docs/` plus a
  fresh `jobs.json` into a Pages artifact, saves state, and deploys with the official `upload-pages-artifact` +
  `deploy-pages` actions. Runs never overlap (`concurrency: refresh-jobs`); the refresh job times out at 30 minutes,
  the deploy at 10. Actions are pinned to commit SHAs, and Dependabot keeps them current.
- **No generated data in git:** `docs/jobs.json` and `seen.json` are untracked and gitignored. State (`seen.json` +
  the last deployed `jobs.json`) lives on the **`state` branch**: one parentless commit, replaced every run, so history
  never grows (ADR 0001).
- **Resilient runs:** a broken board is skipped and shown as a warning on the run, and its last good jobs stay on the
  site. If more than half the boards fail, or nothing comes back, the run goes red *before* writing anything: the
  live site and state stay as they were.
- **Memory:** `seen.json` keeps first- and last-seen dates. Postings gone from every board for 30+ days are pruned,
  and a pruned posting that returns counts as new. First real run: 19,449 → 16,601 entries (−2,879), 1.42 → 1.18 MB.
  `jobs.json` holds open postings only (12,168 roles today).
- **Unchanged:** the site's pages, job `key` formats and localStorage keys, so the apply tracker (`stats.html`) works
  exactly as before (verified: Apply → counted on the Applications page).
- `make check` is green: 23 unit tests (every parser, role filters, seen dates, pruning, carry-forward, the bad-run
  guard, step summary), a `state.sh` integration test against a local bare repo, and actionlint + shellcheck.

## What you need to do (once, in this order)
Order matters. Pushing `main` deletes `docs/jobs.json` from the branch, so the Pages source must already be
"GitHub Actions" or the current site loses its data.
1. **Push the bootstrapped state:** `git push origin state`. It holds `seen.json` with real last-seen dates rebuilt
   from history. If you skip this, the first run seeds from the live site instead: it works, with less accurate
   pruning dates.
2. **Switch Pages to Actions:** GitHub → **Settings → Pages → Build and deployment → Source: GitHub Actions**. The
   current site keeps serving until the first Actions deploy replaces it.
3. **Push main:** `git push origin main`.
4. **Start the first run:** **Actions → Refresh jobs → Run workflow** (branch `main`).

No other settings need to change. The workflow declares its own token permissions (`contents: write` for the state
branch, `pages: write` + `id-token: write` for the deploy, `actions: write` for the keepalive). The `github-pages`
environment is created automatically and allows `main`. If Settings → Actions → General restricts which actions can
run, allow GitHub-authored actions (`actions/*`).

## How to check it's working
- **Actions tab:** a green "Refresh jobs" run every ~3 hours. Each run's summary shows a table (live postings, target
  roles, new today, carried, pruned, seen before/after) and lists any boards it skipped.
- **The site:** the header shows "updated N m/h ago", which should never read more than ~3–4 h.
- **The `state` branch:** its single commit's message carries the time of the last successful run.
- **A red run** means most boards failed or nothing came back; the site is still the last good one. Open the run to
  see why. If the Actions tab says the workflow is *disabled* (GitHub does this after 60 days without repo activity;
  the workflow tries to prevent it), click **Enable workflow**.

## Known / next
- 5 board tokens in `companies.json` return 404 on every run: Old Mission, Amplitude, Postman, Shield AI, Wayve.
  Fix or remove them; until then their old `seen.json` entries are protected from pruning.
- If the repo ever goes private, Actions minutes stop being free: drop the cron to every 6 hours (ADR 0002).
