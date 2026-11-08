#!/usr/bin/env bash
# tests/run-all.sh -j N: the scheduler (sourced from run-all.sh, no checks run) on stand-in suites. With -j 3 the
# output is line for line the -j 1 output (times aside), the counts are equal, two slow suites overlap (event order,
# no wall clock), at most 3 suites run at once, a SLOW suite starts first, live-lane suites (runl, block) never
# overlap each other, a block's lines are counted, a run1 suite runs alone, suites get /dev/null as stdin, runp grades through its handler, and a bad -j exits 2.
# Killed workers cannot hang the queue; shared config classification permits only whole added branch/worktree sections.
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

cat > "$TMP/dead.sh" <<'PLAN'
. "$ROOT_UNDER_TEST/tests/run-all.sh" -j 3
die() { echo 'buffered before death'; kill -9 "$BASHPID"; }
run 'dead suite' die
run 'later suite' bash -c 'exit 0'
drain
echo "counts $pass $fail $skip"
[ "$pass" -eq 1 ] && [ "$fail" -eq 1 ] && [ "$skip" -eq 0 ]
PLAN
out=$(ROOT_UNDER_TEST="$ROOT" timeout 90 bash "$TMP/dead.sh" 2>&1); rc=$?
if [ "$rc" -eq 0 ] && grep -q '^FAIL  dead suite' <<<"$out" \
    && grep -q 'suite worker died without a result (pid [0-9]' <<<"$out" \
    && grep -q 'buffered before death' <<<"$out" && grep -q '^PASS  later suite' <<<"$out" \
    && grep -q '^counts 1 1 0$' <<<"$out"; then
  good 'dead worker fails with buffered output, later suites finish and counts are correct'
else no "dead worker recovery (rc=$rc; timeout=124)" "$out"; fi

# Source in a separate process: the scheduler initializes its own counters and EXIT trap.
cat > "$TMP/config.sh" <<'PLAN'
. "$ROOT_UNDER_TEST/tests/run-all.sh" -j 1
gitcfg_classify "$1" "$2"
PLAN
printf '[core]\n\tworktree = /original\n[branch "existing"]\n\tremote = origin\n' > "$TMP/before"
config_case() {
  local name=$1 want=$2 got
  got=$(ROOT_UNDER_TEST="$ROOT" bash "$TMP/config.sh" "$TMP/before" "$TMP/after")
  [ "$got" = "$want" ] && good "config: $name -> $want" || no "config: $name expected $want, got $got"
}
cp "$TMP/before" "$TMP/after"; config_case unchanged PASS
printf '[branch "other"]\n\tremote = origin\n' >> "$TMP/after"; config_case 'added branch section' WARN
cp "$TMP/before" "$TMP/after"; printf '[worktree]\n\tconfig = true\n' >> "$TMP/after"; config_case 'added worktree section' WARN
printf '[branch "other"]\n\tremote = origin\n' >> "$TMP/after"; config_case 'added both sections' WARN
sed 's@/original@/changed@' "$TMP/before" > "$TMP/after"; config_case 'changed core.worktree' FAIL
cp "$TMP/before" "$TMP/after"; printf '\tmerge = refs/heads/existing\n' >> "$TMP/after"; config_case 'key added inside existing branch' FAIL
head -2 "$TMP/before" > "$TMP/after"; config_case 'removed section' FAIL
cp "$TMP/before" "$TMP/after"; printf '[remote "other"]\n\turl = example\n' >> "$TMP/after"; config_case 'added unrelated section' FAIL
cp "$TMP/before" "$TMP/after"; printf '[branch "existing"]\n\tmerge = other\n' >> "$TMP/after"; config_case 'duplicate existing branch' FAIL
# A whole new section between old sections is allowed, but a key inserted before it is not.
{ head -2 "$TMP/before"; printf '[branch "middle"]\n\tremote = origin\n'; tail -2 "$TMP/before"; } > "$TMP/after"
config_case 'whole section inserted in middle' WARN
{ head -2 "$TMP/before"; printf '\tbare = false\n[branch "middle"]\n\tremote = origin\n'; tail -2 "$TMP/before"; } > "$TMP/after"
config_case 'core key inserted before new section' FAIL

# Persistence is tested in a disposable git repo with tiny suites; never run the real full suite.
mkdir -p "$TMP/repo/scripts/lib" "$TMP/repo/scripts/checks" "$TMP/repo/tests" "$TMP/repo/testlab" "$TMP/state"
cp "$ROOT/scripts/lib/fstate.py" "$TMP/repo/scripts/lib/"
printf '#!/usr/bin/env bash\nprintf "a\\n" >> "$RUN_LOG"\n[ "${BREAK_SUITE:-0}" = 0 ]\n' > "$TMP/repo/tests/a.sh"
printf '#!/usr/bin/env bash\nprintf "b\\n" >> "$RUN_LOG"\n' > "$TMP/repo/tests/b.sh"
printf '#!/usr/bin/env bash\nprintf "never\\n" >> "$RUN_LOG"\n' > "$TMP/repo/tests/never.sh"
printf '#!/usr/bin/env bash\nprintf "live\\n" >> "$RUN_LOG"\n' > "$TMP/repo/tests/live.sh"
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$1" >> "$RUN_LOG"\n' > "$TMP/repo/scripts/checks/x.sh"
cat > "$TMP/hashes.py" <<'PY'
import os, sys
if sys.argv[1] == 'hashes':
    for suite in sys.argv[2:]:
        print(suite, '-' if suite.endswith('never.sh') else os.environ.get('INPUT_HASH', 'a'*64))
elif sys.argv[1] == 'changed': print('tests/b.sh')
elif sys.argv[1] == 'select': sys.exit(0 if sys.argv[3] in os.environ.get('SELECT', 'tests/b.sh').split(',') else 1)
PY
cat > "$TMP/cache-plan.sh" <<'PLAN'
fixture=$1; shift
. "$ROOT_UNDER_TEST/tests/run-all.sh" "$@"
ROOT=$fixture; cd "$ROOT" || exit 1
runall_prepare; rc=$?
[ "$rc" = 10 ] && exit 0
[ "$rc" = 0 ] || exit "$rc"
[ -z "${HOLD_MARK:-}" ] || { touch "$HOLD_MARK"; while [ ! -f "$HOLD_MARK.release" ]; do sleep 0.1; done; }
run a bash tests/a.sh
run b bash tests/b.sh
[ "${WITH_NEVER:-0}" = 0 ] || run never bash tests/never.sh
# a live-lane suite, and a block and an inline check that run a script outside a run line (gated like a suite)
gated_block() { gated scripts/checks/x.sh && { bash scripts/checks/x.sh block && ok "gated block x" || bad "gated block x"; }; ok "block cheap"; }
if [ "${WITH_LIVE:-0}" != 0 ]; then
  runl live bash tests/live.sh
  block gated_block
  gated scripts/checks/x.sh && { bash scripts/checks/x.sh inline && ok "gated inline x" || bad "gated inline x"; }
fi
[ "${CHANGE_INPUT:-0}" = 0 ] || echo changed >> tests/b.sh
drain
runall_finish
echo "counts $pass $fail $skip"
[ "$pass" -gt 0 ] && [ "$fail" -eq 0 ]
PLAN
git -C "$TMP/repo" init -q
git -C "$TMP/repo" add .
git -C "$TMP/repo" -c user.name=test -c user.email=test@test commit -qm fixture
export ROOT_UNDER_TEST="$ROOT" RPG_FACTORY_STATE_DIR="$TMP/state" RUNALL_AFFECTED_PY="$TMP/hashes.py" RUN_LOG="$TMP/log"
cache_plan() { bash "$TMP/cache-plan.sh" "$TMP/repo" "$@"; }
reset_cache() { rm -rf "$TMP/state/run-all"; : > "$RUN_LOG"; }
reset_cache
out=$(cache_plan); rc=$?
tree=$(git -C "$TMP/repo" rev-parse 'HEAD^{tree}')
[ "$rc" = 0 ] && [ -f "$TMP/state/run-all/$tree.json" ] && [ ! -d "$TMP/state/locks/run-all-full" ] \
  && good 'clean full PASS writes tree record and releases lock' || no 'full PASS record/lock' "$out"
out=$(cache_plan --reuse); rc=$?
[ "$rc" = 0 ] && grep -q '^reused full run at ' <<<"$out" && [ "$(wc -l < "$RUN_LOG")" -eq 2 ] \
  && good '--reuse hits clean PASS tree without running suites' || no '--reuse clean hit' "$out"
# Restricted coverage cannot satisfy an unrestricted request.
python3 - "$TMP/state/run-all/$tree.json" <<'PY'
import json, sys
p=sys.argv[1]; r=json.load(open(p)); r['flags']['no_workspace']=True
with open(p,'w') as f: json.dump(r,f)
PY
out=$(cache_plan --reuse --no-reuse); rc=$?
[ "$rc" = 0 ] && ! grep -q '^reused full run' <<<"$out" && [ "$(wc -l < "$RUN_LOG")" -eq 4 ] \
  && good 'restricted full record cannot satisfy full workspace coverage' || no 'full coverage mismatch' "$out"
echo dirty > "$TMP/repo/untracked"
out=$(cache_plan --reuse --no-reuse); rc=$?
[ "$rc" = 0 ] && ! grep -q '^reused full run' <<<"$out" && [ "$(wc -l < "$RUN_LOG")" -eq 6 ] \
  && good '--reuse misses a dirty tree' || no '--reuse dirty miss' "$out"
rm "$TMP/repo/untracked"
python3 - "$TMP/state/run-all/$tree.json" <<'PY'
import json, sys
p=sys.argv[1]; r=json.load(open(p)); r['counts']['fail']=1
with open(p,'w') as f: json.dump(r,f)
PY
out=$(cache_plan --reuse --no-reuse); rc=$?
[ "$rc" = 0 ] && ! grep -q '^reused full run' <<<"$out" && [ "$(wc -l < "$RUN_LOG")" -eq 8 ] \
  && good '--reuse misses a failed tree record' || no '--reuse failed record' "$out"
reset_cache
out=$(cache_plan --only-suites tests/a.sh); rc=$?
[ "$rc" = 0 ] && [ "$(cat "$RUN_LOG")" = a ] && [ ! -f "$TMP/state/run-all/$tree.json" ] \
  && good '--only-suites selects exactly the requested suite, no tree record' || no '--only-suites selection' "$out"
out=$(cache_plan --only-suites tests/unknown.sh 2>&1); rc=$?
[ "$rc" = 2 ] && grep -q "unknown suite 'tests/unknown.sh'" <<<"$out" \
  && good '--only-suites rejects unknown name with exit 2' || no 'unknown suite' "$out"
reset_cache
out=$(cache_plan --affected --only-suites tests/a.sh); rc=$?
[ "$rc" = 0 ] && [ "$(tr '\n' ' ' < "$RUN_LOG")" = 'a b ' ] \
  && good '--affected and --only-suites form a deduplicated union' || no 'affected union' "$out"
reset_cache
cache_plan --only-suites tests/a.sh >/dev/null
out=$(cache_plan --only-suites tests/a.sh -j 3); rc=$?
[ "$rc" = 0 ] && grep -q 'reused tests/a.sh inputs ' <<<"$out" && [ "$(wc -l < "$RUN_LOG")" -eq 1 ] \
  && good 'suite PASS reused with parallel output and unchanged inputs' || no 'suite reuse hit' "$out"
out=$(INPUT_HASH=$(printf 'b%.0s' {1..64}) cache_plan --only-suites tests/a.sh); rc=$?
[ "$rc" = 0 ] && ! grep -q reused <<<"$out" && [ "$(wc -l < "$RUN_LOG")" -eq 2 ] \
  && good 'suite input hash change misses reuse' || no 'suite hash miss' "$out"
out=$(cache_plan --only-suites tests/a.sh --no-reuse); rc=$?
[ "$rc" = 0 ] && ! grep -q reused <<<"$out" && [ "$(wc -l < "$RUN_LOG")" -eq 3 ] \
  && good '--no-reuse forces suites to execute' || no '--no-reuse' "$out"
reset_cache
WITH_NEVER=1 cache_plan --only-suites tests/never.sh >/dev/null
out=$(WITH_NEVER=1 cache_plan --only-suites tests/never.sh); rc=$?
[ "$rc" = 0 ] && ! grep -q reused <<<"$out" && [ "$(wc -l < "$RUN_LOG")" -eq 2 ] \
  && good 'hash - never reuses a suite' || no 'never reuse marker' "$out"
reset_cache
out=$(BREAK_SUITE=1 cache_plan); rc=$?
[ "$rc" = 1 ] && [ ! -d "$TMP/state/locks/run-all-full" ] \
  && [ "$(find "$TMP/state/run-all/suites" -type f | wc -l)" -eq 1 ] \
  && good 'FAIL writes no suite PASS record and full-run lock is released' || no 'FAIL cache and lock' "$out"
record=$(python3 - "$TMP/state/run-all/$tree.json" <<'PY'
import json, sys
r=json.load(open(sys.argv[1]))
print(r['counts']['fail'], len(r['failed_checks']), r['failed_checks'][0].split()[0])
PY
)
[ "$record" = '1 1 a' ] && good 'failed full-run record includes counts and failed check names' || no 'failed record details' "$record"
reset_cache
out=$(CHANGE_INPUT=1 cache_plan --only-suites tests/a.sh); rc=$?
[ "$rc" = 0 ] && [ ! -d "$TMP/state/run-all/suites" ] \
  && good 'changed inputs prevent suite PASS publication' || no 'input mutation' "$out"
git -C "$TMP/repo" checkout -- tests/b.sh
# Hold the first full run until the test explicitly releases it.
reset_cache
HOLD_MARK="$TMP/held" cache_plan --no-reuse > "$TMP/holder.out" 2>&1 & holder=$!
for ((i=0; i<200; i++)); do [ ! -f "$TMP/held" ] || break; sleep 0.1; done
out=$(cache_plan --no-wait --no-reuse); rc=$?
[ "$rc" = 3 ] && grep -q 'waiting for full run ' <<<"$out" \
  && good '--no-wait exits 3 while a full run holds the lock' || no '--no-wait contention' "$out"
cache_plan --no-reuse > "$TMP/waiter.out" 2>&1 & waiter=$!
for ((i=0; i<100; i++)); do grep -q 'waiting for full run ' "$TMP/waiter.out" && break; sleep 0.1; done
kill -0 "$waiter" 2>/dev/null && grep -q 'waiting for full run ' "$TMP/waiter.out" \
  && good 'second full run waits for the first' || no 'lock wait' "$(cat "$TMP/waiter.out")"
touch "$TMP/held.release"; wait "$holder"; hrc=$?; wait "$waiter"; wrc=$?
[ "$hrc" = 0 ] && [ "$wrc" = 0 ] && [ ! -d "$TMP/state/locks/run-all-full" ] \
  && good 'waiting full run continues and releases its own lock' || no 'lock handoff' "$(cat "$TMP/holder.out" "$TMP/waiter.out")"
mkdir -p "$TMP/state/locks/run-all-full"
printf '99999999\n' > "$TMP/state/locks/run-all-full/pid"
printf 'old checkout\n' > "$TMP/state/locks/run-all-full/checkout"
out=$(cache_plan --no-reuse); rc=$?
[ "$rc" = 0 ] && grep -q 'taking over stale full-run lock' <<<"$out" && [ ! -d "$TMP/state/locks/run-all-full" ] \
  && good 'dead PID lock is taken over and released' || no 'stale takeover' "$out"
# With --affected / --only-suites, a live-lane suite and gated script checks (in a block or inline) run only when
# listed or affected and count as not affected otherwise, with the same counts at -j 1 and -j 3; a full run runs them.
live_case() { # name want-log want-counts args...
  local name=$1 wlog=$2 wcounts=$3 j log; shift 3
  for j in 1 3; do
    reset_cache
    out=$(WITH_LIVE=1 cache_plan --no-reuse -j "$j" "$@"); rc=$?
    log=$(sort "$RUN_LOG" | tr '\n' ' ')
    [ "$rc" = 0 ] && [ "$log" = "$wlog" ] && grep -qx "counts $wcounts" <<<"$out" \
      && good "live/gated: $name (-j $j)" || no "live/gated: $name (-j $j): log '$log'" "$out"
  done
}
live_case '--only-suites without them skips them' 'a ' '2 0 4' --only-suites tests/a.sh
live_case '--only-suites listing them runs them' 'a block inline live ' '5 0 1' --only-suites tests/a.sh,tests/live.sh,scripts/checks/x.sh
SELECT=tests/b.sh,tests/live.sh,scripts/checks/x.sh live_case '--affected selecting them runs them' 'b block inline live ' '5 0 1' --affected
live_case '--affected not selecting them skips them' 'b ' '2 0 4' --affected
live_case 'a full run runs them' 'a b block inline live ' '6 0 0'
# Unit-level WindowsApps shim: only the sourced runner process changes PATH.
mkdir -p "$TMP/WindowsApps" "$TMP/real-python"
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$REAL_PY_DIR"\n' > "$TMP/WindowsApps/python3"
chmod +x "$TMP/WindowsApps/python3"
cat > "$TMP/python-path.sh" <<'PLAN'
. "$ROOT_UNDER_TEST/tests/run-all.sh" -j 1
PATH="$(path_entry "$FAKE_ALIAS"):$PATH"; before=$PATH
python_path_fast
[ "$PATH" = "$(path_entry "$REAL_PY_DIR"):$before" ] && echo 'path prepended'
PLAN
out=$(FAKE_ALIAS="$TMP/WindowsApps" REAL_PY_DIR="$TMP/real-python" bash "$TMP/python-path.sh"); rc=$?
[ "$rc" = 0 ] && grep -q 'using real Python directory' <<<"$out" && grep -q 'path prepended' <<<"$out" \
  && good 'WindowsApps shim prepends real interpreter directory in runner only' || no 'WindowsApps path' "$out"
unset RPG_FACTORY_STATE_DIR RUNALL_AFFECTED_PY RUN_LOG ROOT_UNDER_TEST

echo "run-all-parallel tests: $((pass + fail)) run, $pass passed, $fail failed"
[ "$fail" -eq 0 ] && [ "$pass" -gt 0 ]
