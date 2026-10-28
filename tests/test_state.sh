#!/usr/bin/env bash
# Integration test for scripts/state.sh against a throwaway local bare "origin" (no network, temp dirs only).
set -euo pipefail
STATE_SH="$(cd "$(dirname "$0")/.." && pwd)/scripts/state.sh"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

git init -q --bare "$T/origin.git"
git init -q "$T/work"
cd "$T/work"
git -c user.name=t -c user.email=t@t commit -q --allow-empty -m init
git remote add origin "$T/origin.git"
git push -q origin HEAD:refs/heads/main
mkdir site
echo '{"generated_at":"2026-10-27T00:00:00Z","jobs":[{"key":"k","firstSeen":"2026-10-01"}]}' >site/jobs.json

# 1. no state branch yet: bootstrap from the (here: file://) live site, no seen.json
SITE_URL="file://$T/work/site/" "$STATE_SH" restore st1 >/dev/null 2>&1
if [ ! -f st1/jobs.json ] || [ -f st1/seen.json ]; then fail "bootstrap should fetch jobs.json only"; fi

# 2. save, then restore round-trips both files
echo '{"a":["2026-10-01","2026-10-28"]}' >st1/seen.json
"$STATE_SH" save st1/seen.json site/jobs.json >/dev/null
"$STATE_SH" restore st2 >/dev/null
if ! cmp -s st1/seen.json st2/seen.json || ! cmp -s site/jobs.json st2/jobs.json; then fail "round trip"; fi

# 3. a second save replaces the state: still exactly one parentless commit (no history growth)
echo '{"b":["2026-10-02","2026-10-28"]}' >st1/seen.json
"$STATE_SH" save st1/seen.json site/jobs.json >/dev/null
[ "$(git --git-dir="$T/origin.git" rev-list --count state)" = 1 ] || fail "state branch grew history"
"$STATE_SH" restore st3 >/dev/null
grep -q '"b"' st3/seen.json || fail "restore after second save"

# 4. an unreachable remote is fatal (never bootstrap over good state because of a network blip)
git remote set-url origin "$T/missing.git"
if "$STATE_SH" restore st4 >/dev/null 2>&1; then fail "unreachable remote must fail"; fi
[ ! -e st4/jobs.json ] || fail "nothing restored on failure"

echo "state.sh: 4 checks OK"
