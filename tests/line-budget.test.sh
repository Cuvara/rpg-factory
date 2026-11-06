#!/usr/bin/env bash
# Line budget for the scripts that were split to stay readable: scripts/lib/gitguard.py, scripts/lib/context.py and
# scripts/run-checks.py must each stay under 500 lines (FAIL names the file and its count). The suite proves its own
# check first: a temp copy padded to exactly 500 lines must FAIL and one padded to 499 lines must PASS.
# Usage: tests/line-budget.test.sh [--root DIR] [--no-self-test]   (standalone; own temp dir; no network)
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUDGET=500
FILES=(scripts/lib/gitguard.py scripts/lib/context.py scripts/run-checks.py)
self_test=true
while [ $# -gt 0 ]; do
  case "$1" in
    --root) ROOT="$2"; shift 2 ;;
    --no-self-test) self_test=false; shift ;;
    *) echo "usage: tests/line-budget.test.sh [--root DIR] [--no-self-test]" >&2; exit 2 ;;
  esac
done
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; [ -n "${2:-}" ] && printf '%s\n' "$2" | sed 's/^/      /'; return 0; }
# lines FILE: physical lines, a last line without a newline included
lines() { awk 'END { print NR }' "$1"; }

if $self_test; then
  echo "-- self-test (padded temp copies)"
  TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
  # pad N: a stand-in root whose run-checks.py has exactly N lines, the other files 1 line
  pad() {
    local r="$TMP/r$1"; mkdir -p "$r/scripts/lib"
    printf 'x = 1\n' > "$r/scripts/lib/gitguard.py"; printf 'x = 1\n' > "$r/scripts/lib/context.py"
    awk -v n="$1" 'BEGIN { for (i = 1; i <= n; i++) print "# line " i }' > "$r/scripts/run-checks.py"
    echo "$r"
  }
  r=$(pad 500); out=$(bash "$SELF" --root "$r" --no-self-test 2>&1); rc=$?
  if [ "$rc" -ne 0 ] && grep -qE "^FAIL  scripts/run-checks.py: 500 lines" <<<"$out"; then
    ok "self-test: run-checks.py at 500 lines FAILs (file and count named)"
  else no "self-test: run-checks.py at 500 lines must FAIL" "rc=$rc out: $out"; fi
  r=$(pad 499); out=$(bash "$SELF" --root "$r" --no-self-test 2>&1); rc=$?
  if [ "$rc" -eq 0 ] && grep -qE "^PASS  scripts/run-checks.py: 499 lines" <<<"$out"; then
    ok "self-test: run-checks.py at 499 lines PASSes"
  else no "self-test: run-checks.py at 499 lines must PASS" "rc=$rc out: $out"; fi
  r=$(pad 499); printf 'tail without newline' >> "$r/scripts/run-checks.py"
  out=$(bash "$SELF" --root "$r" --no-self-test 2>&1); rc=$?
  if [ "$rc" -ne 0 ] && grep -qE "^FAIL  scripts/run-checks.py: 500 lines" <<<"$out"; then
    ok "self-test: a last line without a newline counts"
  else no "self-test: a last line without a newline counts" "rc=$rc out: $out"; fi
  r=$(pad 1); rm "$r/scripts/lib/context.py"; out=$(bash "$SELF" --root "$r" --no-self-test 2>&1); rc=$?
  if [ "$rc" -ne 0 ] && grep -qE "^FAIL  scripts/lib/context.py: missing" <<<"$out"; then
    ok "self-test: a missing file FAILs"
  else no "self-test: a missing file FAILs" "rc=$rc out: $out"; fi
  echo "-- budget ($ROOT)"
fi

for f in "${FILES[@]}"; do
  if [ ! -f "$ROOT/$f" ]; then no "$f: missing (line budget $BUDGET)"; continue; fi
  n=$(lines "$ROOT/$f")
  if [ "$n" -lt "$BUDGET" ]; then ok "$f: $n lines (budget: under $BUDGET)"
  else no "$f: $n lines (budget: under $BUDGET; move a cohesive part into scripts/lib/)"; fi
done

echo "line-budget: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
