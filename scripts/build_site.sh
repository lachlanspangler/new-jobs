#!/usr/bin/env bash
# Assemble the Pages artifact exactly as CI does: the static site from docs/ plus a fresh jobs.json.
#   scripts/build_site.sh <state-dir> <site-dir> [fetch_jobs.py args...]
# <state-dir>/seen.json is read and updated; <state-dir>/jobs.json (last good data) feeds broken-board carry-forward.
# Paths are relative to the repo root. <site-dir> is replaced only after a successful build, and must be a dedicated
# output directory (never the repo, docs/, or anything outside the repo).
set -euo pipefail
state=${1:?state dir}; site=${2:?site dir}; shift 2
cd "$(dirname "$0")/.."
root=$(pwd -P)

case "$site" in
  "" | . | ./ | / | docs | docs/ | ./docs | ./docs/ | .. | ../* | /* | *..*)
    echo "build_site: refusing to write the site to '$site' (use a dedicated directory like _site)" >&2; exit 64 ;;
esac

mkdir -p "$state"
tmp=$(mktemp -d "$root/.site-build.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
cp -R docs/. "$tmp/"
rm -f "$tmp/jobs.json" "$tmp/.nojekyll" # never ship a stale local jobs.json; .nojekyll is moot for Actions deploys
prev=()
[ -f "$state/jobs.json" ] && prev=(--previous "$state/jobs.json")
python3 fetch_jobs.py --seen "$state/seen.json" ${prev[@]+"${prev[@]}"} --out "$tmp/jobs.json" "$@"

rm -rf "$site"
mv "$tmp" "$site"
trap - EXIT
