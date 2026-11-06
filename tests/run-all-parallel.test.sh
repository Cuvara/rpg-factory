#!/usr/bin/env bash
# tests/run-all.sh -j N: the scheduler (sourced from run-all.sh, no checks run) on stand-in suites. With -j 3 the
# output is line for line the -j 1 output (times aside), the counts are equal, two slow suites overlap (event order,
# no wall clock), at most 3 suites run at once, a SLOW suite starts first, live-lane suites (runl, block) never
# overlap each other, a block's lines are counted, a run1 suite runs alone, suites get /dev/null as stdin, runp grades through its handler, and a bad -j exits 2.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
good() { pass=$((pass + 1)); echo "PASS  $1"; }
no()  { fail=$((fail + 1)); echo "FAIL  $1"; [ -n "${2:-}" ] && echo "$2" | head -30 | sed 's/^/      /'; }

# a stand-in run-all: suites that sleep, fail, read stdin, and record how many suites were running at their start
cat > "$TMP/plan.sh" <<'PLAN'
X="$1"; J="$3"; shift   # J: the -j value
. "$ROOT_UNDER_TEST/tests/run-all.sh" "$@"
suite() { # name seconds rc [other]: marks itself running, records the running count and start/end events, sleeps,
  # at -j > 1 waits (60 s cap, so a serial scheduler fails instead of hanging) for suite <other> to start, unmarks
  local n i; echo "$1" >> "$X/order"; touch "$X/running.$1"; n=$(ls "$X" | grep -c '^running\.'); echo "$n" >> "$X/seen"
  echo "start $1" >> "$X/events"; sleep "$2"
  if [ -n "${4:-}" ] && [ "$J" -gt 1 ]; then
    i=$((SECONDS + 60)); until grep -qx "start $4" "$X/events" || [ "$SECONDS" -ge "$i" ]; do sleep 0.1; done
  fi
  echo "out of $1"; echo "end $1" >> "$X/events"; rm -f "$X/running.$1"; return "$3"
}
alone() { local n; n=$(ls "$X" | grep -c '^running\.'); echo "alone saw $n" >> "$X/alone"; echo "ran alone"; }
post() { if [ "$1" -eq 0 ] && grep -q 'out of p' <<<"$2"; then _ok "graded by runp handler"; else _bad "runp handler" "$2"; fi; }
live() { local n; touch "$X/live.$1"; n=$(ls "$X" | grep -c '^live\.'); echo "$n" >> "$X/liveseen"; sleep 0.5; rm -f "$X/live.$1"; }
blk() { ok "block line one"; skp "block skip" "why"; note "WARN  block note"; }
export -f suite alone live; export X J
SLOW="tests/zz-slow.sh"   # suite_of: the `bash -c` $0 below
run "slow a" bash -c 'suite a 1.5 0 b'
ok "inline after a"
run "slow b fails" bash -c 'suite b 1.5 3'
skp "skipped thing" "a reason"
run "slow c" bash -c 'suite c 1.5 0'
note "WARN  a note line"
run "slow d" bash -c 'suite d 1.5 0'
runl "live l1" bash -c 'live l1'
block blk
runl "live l2" bash -c 'live l2'
while IFS= read -r l; do run "stdin $l" bash -c 'x=$(cat); [ -z "$x" ]'; done < <(printf 'one\ntwo\n')
runp "p" post bash -c 'suite p 0.2 0'
run "slow z (listed in SLOW)" bash -c 'suite z 0.2 0' tests/zz-slow.sh
run1 "alone e" bash -c alone
bad "inline failure" "detail line"
run "quick f" bash -c 'suite f 0.2 0'
drain
echo "counts $pass $fail $skip"
PLAN

plan() { # jobs -> output with the [Ns] times removed
  local X="$TMP/x$1"; rm -rf "$X"; mkdir -p "$X"
  ROOT_UNDER_TEST="$ROOT" bash "$TMP/plan.sh" "$X" -j "$1" 2>&1 | sed -E 's/ \[[0-9]+s\]$//'
}
serial=$(plan 1); par=$(plan 3)
want="PASS  slow a
PASS  inline after a
FAIL  slow b fails
      out of b
SKIP  skipped thing (a reason)
PASS  slow c
WARN  a note line
PASS  slow d
PASS  live l1
PASS  block line one
SKIP  block skip (why)
WARN  block note
PASS  live l2
PASS  stdin one
PASS  stdin two
PASS  graded by runp handler
PASS  slow z (listed in SLOW)
PASS  alone e
FAIL  inline failure
      detail line
PASS  quick f
counts 13 2 2"
[ "$serial" = "$want" ] && good "-j 1: lines and counts as written" || no "-j 1 output" "$(diff <(echo "$want") <(echo "$serial"))"
[ "$par" = "$serial" ] && good "-j 3: same lines, same order, same counts as -j 1" || no "-j 3 output differs from -j 1" "$(diff <(echo "$serial") <(echo "$par"))"
max=$(sort -n "$TMP/x3/seen" | tail -1)
[ "$max" -ge 2 ] && [ "$max" -le 3 ] && good "-j 3: suites overlap, never more than 3 at once (max $max)" || no "-j 3 concurrency max=$max"
[ "$(sort -n "$TMP/x1/seen" | tail -1)" = 1 ] && good "-j 1: one suite at a time" || no "-j 1 ran suites concurrently"
o1=$(tr '\n' ' ' < "$TMP/x1/order"); o3=$(tr '\n' ' ' < "$TMP/x3/order")
[ "$o1" = "a b c d p z f " ] && [[ "$o3" == *z*p* ]] \
  && good "-j 3 starts a queued SLOW suite before an earlier one (p), -j 1 keeps the written order" || no "start order: -j 1 '$o1', -j 3 '$o3'"
[ "$(sort -n "$TMP/x3/liveseen" | tail -1)" = 1 ] && good "live-lane suites run one at a time" || no "live-lane overlap: $(cat "$TMP/x3/liveseen")"
[ "$(cat "$TMP/x3/alone")" = "alone saw 0" ] && good "run1 runs with no other suite running" || no "run1 not alone: $(cat "$TMP/x3/alone")"
# overlap by event order, not wall clock: at -j 3 a waits for b's start before it ends, so a scheduler that launches b
# only after a ends never writes "start b" before "end a"; at -j 1 a does not wait and every start follows the previous end
ev3=$(tr '\n' ' ' < "$TMP/x3/events"); ev1=$(tr '\n' ' ' < "$TMP/x1/events")
[[ "$ev3" == *"start b"*"end a"* ]] && good "-j 3: slow a and slow b overlap (b starts before a ends)" || no "-j 3: a and b did not overlap: $ev3"
[ "$ev1" = "start a end a start b end b start c end c start d end d start p end p start z end z start f end f " ] \
  && good "-j 1: each suite starts after the previous one ends" || no "-j 1 events: $ev1"
for j in 0 x ""; do
  out=$(bash "$ROOT/tests/run-all.sh" -j "$j" 2>&1); rc=$?
  [ $rc -eq 2 ] && grep -q 'needs a positive integer' <<<"$out" && good "-j '$j' is rejected (exit 2)" || no "-j '$j' (rc=$rc)" "$out"
done
grep -q '^\[ "\${BASH_SOURCE\[0\]}" != "\$0" \] && return 0' "$ROOT/tests/run-all.sh" \
  && good "sourcing run-all.sh stops after the scheduler" || no "run-all.sh has no source guard after the scheduler"

echo "run-all-parallel tests: $((pass + fail)) run, $pass passed, $fail failed"
[ "$fail" -eq 0 ] && [ "$pass" -gt 0 ]
