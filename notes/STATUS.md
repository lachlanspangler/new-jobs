# Status — 2026-10-29: live

The setup below is **done** (2026-10-29): state and main pushed, Pages source = GitHub Actions, first run green
(12,198 roles deployed). It now runs on its schedule; nothing more is needed from you.

## What's built
The board now updates itself, with no laptop involved.
- **`.github/workflows/refresh.yml`** runs every 3 hours (`17 */3 * * *` UTC, 8 runs a day, ~7 minutes each) and on
  demand (**Actions → Refresh jobs → Run workflow**). Three jobs: **refresh** (restores state, runs
  `fetch_jobs.py`, builds `docs/` plus a fresh `jobs.json` into a Pages artifact) → **deploy** (official
  `upload-pages-artifact` + `deploy-pages`) → **save-state** (only after a successful deploy, only from `main`). Runs
  never overlap (`concurrency: refresh-jobs`); the jobs time out at 30, 10 and 5 minutes. Actions are pinned to commit SHAs, and Dependabot keeps them current.
- **No generated data in git:** `docs/jobs.json` and `seen.json` are untracked and gitignored. State (`seen.json` +
  the last deployed `jobs.json`) lives on the **`state` branch**: one parentless commit, replaced every run, so history
  never grows (ADR 0001).
- **Resilient runs:** a broken board is skipped and shown as a warning on the run, and its last good jobs stay on the
  site (for up to 30 days, so a board that stays broken doesn't show closed jobs forever). Outages that look like an
  empty board count as failures. If more than half the boards fail, nothing comes back, or roles fall under half of
  the last run, the run goes red *before* writing anything and names the failed boards. The live site and state stay
  as they were.
- **Memory:** `seen.json` keeps first- and last-seen dates. Postings gone from every board for 30+ days are pruned,
  and a pruned posting that returns counts as new. First real run: 19,449 → 16,601 entries (−2,879), 1.42 → 1.18 MB.
  `jobs.json` holds open postings only (12,168 roles today).
- **Unchanged:** the site's pages, job `key` formats and localStorage keys, so the apply tracker (`stats.html`) works
  exactly as before (verified: Apply → counted on the Applications page).
- `make check` is green: 29 unit tests (every parser and its outage cases, role filters, seen dates, pruning, a
  pruned job coming back, carry-forward and its 30-day limit, the bad-run guards, step summary), a `state.sh`
  integration test against a local bare repo, a `build_site.sh` safety test, and actionlint + shellcheck.
- A fresh code reviewer found 5 bugs and 8 smaller issues; all fixed except three low-risk ones listed under Known (see DIARY).

## Guest mode and reset (2026-10-29)
- **`?guest` on any page** (e.g. https://lachlanspangler.github.io/new-jobs/?guest) shows the board with a completely
  empty tracker: no applications, dismissed jobs or pipeline statuses. The Companies and Recruiters pages derive from
  those, so they're empty too. Guest data lives in the tab's sessionStorage, never in localStorage. It stays guest on
  every page (internal links carry `?guest`) and shows an orange "guest" pill. The pill or the normal link takes you
  back to the real data, untouched.
- **Reset everything** on the Applications page clears every `nj-*` store, now and in future, behind an inline
  confirm that lists what will go and offers a full backup download first. A guest reset clears only the guest
  session.
- All storage now goes through `docs/store.js`. Browser tests (`make e2e`, part of `make check`) prove the real
  data is byte-for-byte identical before and after a guest session that applies, dismisses and sets a status; a
  guest reset leaves the real data alone; and reset offers the export, then clears every store and only this
  site's. Deliberately broken versions (guest writing to localStorage; reset skipping a store) make the tests fail.
- To ship: `git push origin main`. The next run (or **Run workflow**) deploys it.

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

No other settings need to change. The workflow declares its own least-privilege token permissions per job: the fetch
job is read-only, `pages: write` + `id-token: write` for the deploy, `contents: write` only in the final save-state
job, and `actions: write` only for the keepalive. The `github-pages`
environment is created automatically and allows `main`. If Settings → Actions → General restricts which actions can
run, allow GitHub-authored actions (`actions/*`).

## How to check it's working
- **Actions tab:** a green "Refresh jobs" run every ~3 hours. Each run's summary shows a table (live postings, target
  roles, new today, carried, pruned, seen before/after) and lists any boards it skipped.
- **The site:** the header shows "updated N m/h ago", which should never read more than ~3–4 h.
- **The `state` branch:** its single commit's message carries the time of the last successful run.
- **A red run** means most boards failed, nothing came back, or roles fell under half of the last run. The site and
  state are still the last good ones. Open the run: it names every failed board. If a big drop is real (e.g. you
  removed many companies), use **Run workflow** with **"Accept a run with under half of last run's roles"** ticked,
  once. If the Actions tab says the workflow is *disabled* (GitHub does this after 60 days without repo activity;
  the workflow tries to prevent it), click **Enable workflow**.

## Known / next
- Don't push the `state` branch by hand while a run is in progress: the run's save would overwrite it.
- 5 board tokens in `companies.json` return 404 on every run: Old Mission, Amplitude, Postman, Shield AI, Wayve.
  Fix or remove them; until then their old `seen.json` entries are protected from pruning.
- If the repo ever goes private: Actions minutes stop being free, so drop the cron to every 6 hours; and the restore
  step reads `state` anonymously, so give the refresh job the token. Until then every run fails safely at restore
  (ADR 0002).
- Not fixed from review, low risk: (a) no per-board time budget; enough slow boards could push a run past 30 minutes.
  Nothing is written then, so it's only a wasted run. (b) A local `--tag` run overwrites `docs/jobs.json` with the
  subset (local only, as before). (c) Failures are keyed by `ats:token`, so two companies sharing a token would count
  as one (none do).
