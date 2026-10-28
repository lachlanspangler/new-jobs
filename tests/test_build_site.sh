#!/usr/bin/env bash
# build_site.sh must refuse to write over the repo, docs/, or anything outside it (it replaces the target dir).
set -euo pipefail
cd "$(dirname "$0")/.."
for bad in . ./ / docs docs/ ./docs .. ../elsewhere /tmp/x a/../docs; do
  if scripts/build_site.sh .state-test "$bad" >/dev/null 2>&1; then echo "FAIL: accepted '$bad'" >&2; exit 1; fi
done
if [ ! -f docs/index.html ] || [ -e .state-test ]; then echo "FAIL: touched the tree on refusal" >&2; exit 1; fi
echo "build_site.sh: refuses 11 unsafe targets OK"
