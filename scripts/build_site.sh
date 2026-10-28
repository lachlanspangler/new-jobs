#!/usr/bin/env bash
# Assemble the Pages artifact exactly as CI does: the static site from docs/ plus a fresh jobs.json.
#   scripts/build_site.sh <state-dir> <site-dir> [fetch_jobs.py args...]
# <state-dir>/seen.json is read and updated; <state-dir>/jobs.json (last good data) feeds broken-board carry-forward.
# Paths are relative to the repo root. <site-dir> is replaced only after a successful build, so it must be a dedicated
# top-level output directory named _site or _site-*/_site_* (an allowlist: nothing else can ever be deleted).
set -euo pipefail
state=${1:?state dir}; site=${2:?site dir}; shift 2
cd "$(dirname "$0")/.."
root=$(pwd -P)

site=${site%/}
case "$site" in
  _site | _site-* | _site_*) ;;
  *) echo "build_site: refusing to write the site to '$site' (use _site or _site-<name>)" >&2; exit 64 ;;
esac
case "$site" in */*) echo "build_site: '$site' must be a top-level directory" >&2; exit 64 ;; esac

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
