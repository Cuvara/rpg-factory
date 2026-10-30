#!/usr/bin/env bash
# Engineering routing contract is frozen: every task scenario of tests/routing.test.sh, resolved on a
# throwaway stand-in workspace, must give the same lead / co-leads / legs / follow-ups / tech / ambiguous,
# touched modules and check ids as tests/fixtures/routing-golden.json (recorded before domain metadata).
# Added fields (e.g. routing.domain) are ignored by construction; anything else that moves is a FAIL.
#
# Usage: tests/routing-golden.test.sh [--update]   (--update rewrites the golden file; review the diff)
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GOLDEN="$ROOT/tests/fixtures/routing-golden.json"
TMP="$(mktemp_win)" || exit 1; trap 'rm -rf "$TMP"' EXIT
SW="$TMP/ws"
while IFS= read -r p; do
  git init -q "$SW/$p" && git -C "$SW/$p" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
done < <(jq -r '.repos | to_entries[] | select(.value.optional != true) | .value.path' "$ROOT/registry.json")
while IFS= read -r m; do mkdir -p "$SW/$(dirname "$m")"; touch "$SW/$m"; done < <(jq -r '.workspace.root_markers[]' "$ROOT/registry.json")
OUT="$TMP/routing.jsonl"; : > "$OUT"
RPG_FACTORY_WORKSPACE="$SW" ROUTING_GOLDEN_OUT="$OUT" bash "$ROOT/tests/routing.test.sh" --no-history > "$TMP/routing.log" 2>&1
# canonical: one object keyed by scenario name (sorted keys); a name used twice keeps both in order
# "absolute path (...)" scenarios depend on the host's path forms (C:/, /c/, /mnt/c/ exist only on Windows);
# tests/routing.test.sh asserts their lead on every platform, so they are kept out of the cross-platform golden
PLATFORM='with_entries(select(.key | startswith("absolute path (") | not))'
jq -S -s "reduce .[] as \$s ({}; .[\$s.name] += [\$s | del(.name)]) | $PLATFORM" "$OUT" > "$TMP/current.json"
n=$(jq 'length' "$TMP/current.json")
if [ "${1:-}" = "--update" ]; then cp "$TMP/current.json" "$GOLDEN"; echo "routing-golden: updated $n scenarios"; exit 0; fi
[ -f "$GOLDEN" ] || { echo "FAIL  no golden file $GOLDEN"; exit 1; }
if [ "$n" -lt 40 ]; then echo "FAIL  only $n scenarios recorded (expected >= 40)"; tail -5 "$TMP/routing.log"; exit 1; fi
jq -S "$PLATFORM" "$GOLDEN" > "$TMP/golden.json"
if diff -u "$TMP/golden.json" "$TMP/current.json" > "$TMP/diff.txt"; then
  echo "PASS  routing contract identical to the golden file ($n scenarios)"; echo "routing-golden: 1 passed, 0 failed"; exit 0
fi
echo "FAIL  routing contract changed:"; head -60 "$TMP/diff.txt" | sed 's/^/      /'
echo "routing-golden: 0 passed, 1 failed"; exit 1
