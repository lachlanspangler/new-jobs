#!/usr/bin/env bash
# Daily refresh: fetch the newest roles, commit the static data, publish.
set -uo pipefail
REPO="/Users/spanglew/new-jobs"
cd "$REPO" || { echo "repo not found"; exit 1; }

/usr/bin/python3 fetch_jobs.py

if [ -n "$(git status --porcelain docs/jobs.json seen.json)" ]; then
  git add docs/jobs.json seen.json
  git commit -q -m "Refresh job listings ($(date '+%Y-%m-%d'))"
  git push -q origin main || echo "push failed — run 'git push' manually (launchd may lack cached credentials)"
else
  echo "no listing changes"
fi
