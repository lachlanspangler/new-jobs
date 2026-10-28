#!/usr/bin/env bash
# Assemble the Pages artifact exactly as CI does: the static site from docs/ plus a fresh jobs.json.
#   scripts/build_site.sh <state-dir> <site-dir> [fetch_jobs.py args...]
# <state-dir>/seen.json is read and updated; <state-dir>/jobs.json (last good data) feeds broken-board carry-forward.
set -euo pipefail
state=${1:?state dir}; site=${2:?site dir}; shift 2
cd "$(dirname "$0")/.."
rm -rf "$site"
mkdir -p "$site" "$state"
cp -R docs/. "$site/"
rm -f "$site/jobs.json" "$site/.nojekyll"   # never ship a stale local jobs.json; .nojekyll is moot for Actions deploys
prev=()
[ -f "$state/jobs.json" ] && prev=(--previous "$state/jobs.json")
python3 fetch_jobs.py --seen "$state/seen.json" ${prev[@]+"${prev[@]}"} --out "$site/jobs.json" "$@"
