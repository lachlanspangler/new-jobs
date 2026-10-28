#!/usr/bin/env bash
# Keep the fetcher's state between CI runs on a `state` branch holding ONE parentless commit, force-pushed each run,
# so the repo's history never grows (ADR 0001).
#
#   scripts/state.sh restore <dir>             -> <dir>/seen.json, <dir>/jobs.json (last good site data)
#   scripts/state.sh save <seen.json> <jobs.json>
#
# Restore with no state branch yet (first run) seeds from the live site's jobs.json instead, so "new today" doesn't
# light up for every existing role. A failure to *reach* the remote is fatal: bootstrapping then would overwrite good
# state with a reseeded copy.
set -euo pipefail

BRANCH="${STATE_BRANCH:-state}"
SITE_URL="${SITE_URL:-https://lachlanspangler.github.io/new-jobs/}"

restore() {
  local dir=$1 rc=0
  mkdir -p "$dir"
  git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null || rc=$?
  if [ "$rc" -eq 0 ]; then
    git fetch --quiet --depth=1 origin "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
    git show "origin/$BRANCH:seen.json" >"$dir/seen.json"
    git show "origin/$BRANCH:jobs.json" >"$dir/jobs.json"
    echo "restored state from '$BRANCH': $(git log -1 --format=%s "origin/$BRANCH")"
  elif [ "$rc" -eq 2 ]; then
    echo "::warning::no '$BRANCH' branch yet; bootstrapping from the live site"
    if curl -fsSL --retry 3 --max-time 60 "${SITE_URL}jobs.json" -o "$dir/jobs.json"; then
      echo "seeded from ${SITE_URL}jobs.json"
    else
      rm -f "$dir/jobs.json"
      echo "::warning::live site unreachable too; starting with empty state (every role will look new once)"
    fi
  else
    echo "::error::could not reach origin to read '$BRANCH' (git ls-remote exit $rc)"
    exit 1
  fi
}

save() {
  local seen=$1 jobs=$2 seen_blob jobs_blob tree commit
  seen_blob=$(git hash-object -w "$seen")
  jobs_blob=$(git hash-object -w "$jobs")
  tree=$(printf '100644 blob %s\tjobs.json\n100644 blob %s\tseen.json\n' "$jobs_blob" "$seen_blob" | git mktree)
  commit=$(GIT_AUTHOR_NAME="github-actions[bot]" GIT_AUTHOR_EMAIL="41898282+github-actions[bot]@users.noreply.github.com" \
    GIT_COMMITTER_NAME="github-actions[bot]" GIT_COMMITTER_EMAIL="41898282+github-actions[bot]@users.noreply.github.com" \
    git commit-tree "$tree" -m "state $(date -u +%Y-%m-%dT%H:%MZ)")
  git push --force --quiet origin "$commit:refs/heads/$BRANCH"
  echo "saved state to '$BRANCH' ($commit)"
}

case "${1:-}" in
  restore) restore "${2:?dir}" ;;
  save) save "${2:?seen.json}" "${3:?jobs.json}" ;;
  *) echo "usage: $0 restore <dir> | save <seen.json> <jobs.json>" >&2; exit 64 ;;
esac
