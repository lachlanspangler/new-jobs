# ADR 0002 — Every 3 hours, America/Chicago calendar days, polite fetching

**Status:** accepted (2026-10-28)

**Cadence:** `cron: "17 */3 * * *"`, 8 runs a day at :17 past the hour to avoid the top-of-hour load spike on
GitHub's scheduler (scheduled runs are often delayed there). One run takes ~7 minutes, so ~1 runner-hour a day. The
repo is public, so standard-runner minutes are free and unlimited; private would cost ~1,700 of the 2,000 free
minutes a month, so going private means dropping to every 6 hours. Each board is fetched once per run with the
existing pacing (0.25 s between boards, 0.1–0.2 s between pages), about 500 requests a run (~4,000 a day), spread over
hundreds of hosts and tenants: far below anything the public Greenhouse/Ashby/Lever posting APIs throttle.

**Time zone:** CI sets `TZ=America/Chicago`. "New today", `firstSeen`, the Workday/Built In relative dates
("Posted 3 days ago") and the 30-day prune clock all use the owner's calendar day, matching what the local launchd
job did. UTC would roll "today" over at 7 pm Chicago time.

**Overlap and hangs:** `concurrency: refresh-jobs` (no cancel-in-progress), so a manual run and a scheduled run queue
rather than race on the state branch. Job timeout 30 minutes (four times a normal run); the per-request timeouts
(15–20 s) bound any single board.

**Bad runs:** one failing board is skipped, logged as a warning annotation, and its last good jobs are carried
forward, but only jobs confirmed live within the last 30 days, so a board that stays broken doesn't keep closed
postings up forever. Outages that look like empty boards (a 200 with no job cards, a page without its data, an
unexpected payload) count as failures. The fetcher exits 2 *before writing*, naming every failed board, if more than
half the boards fail, if no roles come back, or if roles fall below half of the last run (a silent mass outage;
`--allow-drop` overrides it once if the drop is real). The workflow then goes red, the site keeps its last good
deploy and state is untouched: state is saved in a final job that runs only after a successful deploy, and only
from `main`.

**Schedule lapse:** GitHub disables schedules in public repos after 60 days without repository activity. The workflow
re-enables itself on every scheduled run, including red ones (a separate best-effort job holding the only
`actions: write` grant). If the Actions tab ever shows the workflow
disabled, click "Enable workflow".
