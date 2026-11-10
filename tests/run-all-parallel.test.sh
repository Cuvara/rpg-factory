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

# a case subset keeps its SLOW slot at -j > 1: of two queued suites the SLOW one starts first although it was queued last
cat > "$TMP/subset-slow.sh" <<'PLAN'
. "$ROOT_UNDER_TEST/tests/run-all.sh" -j 2
SLOW="tests/zz-subset.sh"
CASE_SUITES=("tests/zz-subset.sh"); CASE_LISTS=("alpha")
export X
run first bash -c 'echo first >> "$X/start"; sleep 3' tests/zz-first.sh
run mid bash -c 'echo mid >> "$X/start"; sleep 0.5' tests/zz-mid.sh
run tail bash -c 'echo tail >> "$X/start"' tests/zz-tail.sh
run subset bash -c 'echo subset >> "$X/start"; echo "args $*" >> "$X/start"' tests/zz-subset.sh
drain
PLAN
X="$TMP/subset-slow"; rm -rf "$X"; mkdir -p "$X"
out=$(X="$X" ROOT_UNDER_TEST="$ROOT" timeout 90 bash "$TMP/subset-slow.sh" 2>&1); rc=$?
# first and mid start together at -j 2, so their order in the start file is free; subset must start before tail
[ "$rc" = 0 ] && [ "$(grep -vc '^args' "$X/start" | tr -d ' ')" = 4 ] \
  && [ "$(grep -v '^args' "$X/start" | head -n 2 | sort | tr '\n' ' ')" = 'first mid ' ] \
  && [ "$(grep -v '^args' "$X/start" | tail -n 2 | tr '\n' ' ')" = 'subset tail ' ] \
  && grep -q '^PASS  subset (cases alpha)' <<<"$out" && grep -qx 'args --case alpha' "$X/start" \
  && good "a case subset keeps its SLOW start slot at -j 2" || no "subset SLOW slot (rc=$rc): $(tr '\n' ' ' < "$X/start")" "$out"

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
cat > "$TMP/repo/tests/b.sh" <<'SUITE'
#!/usr/bin/env bash
printf 'b\n' >> "$RUN_LOG"
[ -z "${CASE_LOG:-}" ] || printf '%s\n' "$*" >> "$CASE_LOG"
[ "${BREAK_CASE:-0}" = 0 ]
SUITE
printf '#!/usr/bin/env bash\nprintf "never\\n" >> "$RUN_LOG"\n' > "$TMP/repo/tests/never.sh"
printf '#!/usr/bin/env bash\nprintf "live\\n" >> "$RUN_LOG"\n' > "$TMP/repo/tests/live.sh"
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$1" >> "$RUN_LOG"\n' > "$TMP/repo/scripts/checks/x.sh"
# partial: passes with a SKIP line (a tool missing), like orca-commands without orca
printf '#!/usr/bin/env bash
printf "partial\n" >> "$RUN_LOG"
echo "${PARTIAL_LINE:-SKIP  tool not on PATH}"
' > "$TMP/repo/tests/partial.sh"
for s in blockrun ws orphan; do printf '#!/usr/bin/env bash\nprintf "%s\\n" >> "$RUN_LOG"\n' "$s" > "$TMP/repo/tests/$s.sh"; done
cat > "$TMP/hashes.py" <<'PY'
import os, sys
if os.environ.get('AFF_CALLS') and sys.argv[1] in ('select', 'select-many', 'cases'):
    with open(os.environ['AFF_CALLS'], 'ab') as fh: fh.write((sys.argv[1] + '\n').encode())   # LF on Windows too
if sys.argv[1] == 'hashes':
    for suite in sys.argv[2:]:
        print(suite, '-' if suite.endswith('never.sh') else os.environ.get('INPUT_HASH', 'a'*64))
elif sys.argv[1] == 'changed':
    if os.environ.get('NO_BASE'): sys.exit(1)
    print('tests/b.sh')
elif sys.argv[1] == 'select': sys.exit(0 if sys.argv[3] in os.environ.get('SELECT', 'tests/b.sh').split(',') else 1)
elif sys.argv[1] == 'select-many':
    print('\n'.join(s for s in sys.argv[3:] if s in os.environ.get('SELECT', 'tests/b.sh').split(',')))
elif sys.argv[1] == 'cases':
    if os.environ.get('CASES_FAIL'): sys.exit(1)
    for suite in sys.argv[3:]:   # like affected.py: one line per selected suite only
        if suite in os.environ.get('SELECT', 'tests/b.sh').split(','):
            print(suite, os.environ.get('CASE_SELECT', 'ALL') if suite == 'tests/b.sh' else 'ALL')
PY
cat > "$TMP/cache-plan.sh" <<'PLAN'
fixture=$1; shift
. "$ROOT_UNDER_TEST/tests/run-all.sh" "$@"
ROOT=$fixture; cd "$ROOT" || exit 1
runall_prepare; rc=$?
[ "$rc" = 10 ] && exit 0
[ "$rc" = 0 ] || exit "$rc"
[ -z "${HOLD_MARK:-}" ] || {
  touch "$HOLD_MARK"; hold_until=$((SECONDS + 240))
  while [ ! -f "$HOLD_MARK.release" ]; do
    [ "$SECONDS" -lt "$hold_until" ] || { echo 'fixture hold timed out'; exit 1; }
    sleep 0.1
  done
}
if ! $workspace_only; then
run a bash tests/a.sh
run b bash tests/b.sh
[ "${WITH_NEVER:-0}" = 0 ] || run never bash tests/never.sh
[ "${WITH_PARTIAL:-0}" = 0 ] || run partial bash tests/partial.sh
$release && run1 safety bash tests/installed-safety.sh   # release-only, like run-all.sh's installed-safety line
fi
# workspace-list-begin
# a live-lane suite, and a block and an inline check that run a script outside a run line (gated like a suite)
gated_block() { gated scripts/checks/x.sh && { bash scripts/checks/x.sh block && ok "gated block x" || bad "gated block x"; }; ok "block cheap"; }
if [ "${WITH_LIVE:-0}" != 0 ]; then
  runl live bash tests/live.sh
  block gated_block
  gated scripts/checks/x.sh && { bash scripts/checks/x.sh inline && ok "gated inline x" || bad "gated inline x"; }
fi
# workspace readers: a run line inside a block (like sgl-determinism, wire-parity) and one given RPG_FACTORY_WORKSPACE
blk_run() { run blockrun bash tests/blockrun.sh; }
if [ "${WITH_WS:-0}" != 0 ]; then
  block blk_run
  run ws env RPG_FACTORY_WORKSPACE=/ws bash tests/ws.sh
fi
# workspace-list-end
[ "${CHANGE_INPUT:-0}" = 0 ] || echo changed >> tests/b.sh
[ -z "${CFG_CHANGE:-}" ] || git config rpgtest.during "$CFG_CHANGE"
drain
runall_finish
if [ -n "${CHECK_CFG:-}" ]; then
  if gitcfg_verify >/dev/null; then echo 'cfg unchanged'; else echo 'cfg changed'; rm -f "$GITCFG_COPY"; fi
fi
echo "counts $pass $fail $skip"
[ "$pass" -gt 0 ] && [ "$fail" -eq 0 ]
PLAN
git -C "$TMP/repo" init -q
git -C "$TMP/repo" add .
git -C "$TMP/repo" -c user.name=test -c user.email=test@test commit -qm fixture
export ROOT_UNDER_TEST="$ROOT" RPG_FACTORY_STATE_DIR="$TMP/state" RUNALL_AFFECTED_PY="$TMP/hashes.py" RUN_LOG="$TMP/log"
export RPG_FACTORY_TEST_SLOTS=2   # fixtures have their own persistent state and deterministic cap
export RUNALL_SUITES_FROM="$TMP/cache-plan.sh"   # --only-suites accepts the stand-in plan's run lines
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
# an existing file no run line runs would be accepted and never run: exit 2 naming each such name, nothing runs
: > "$RUN_LOG"
out=$(cache_plan --only-suites tests/orphan.sh,tests/a.sh,scripts/lib/fstate.py 2>&1); rc=$?
[ "$rc" = 2 ] && grep -q "unknown suite 'tests/orphan.sh'" <<<"$out" && grep -q "unknown suite 'scripts/lib/fstate.py'" <<<"$out" \
  && ! grep -q "'tests/a.sh'" <<<"$out" && [ ! -s "$RUN_LOG" ] \
  && good '--only-suites rejects every existing file without a run line (exit 2, each named)' || no 'orphan suite' "$out"
out=$(cache_plan --only-suites=tests/a.sh,tests/blockrun.sh,scripts/checks/x.sh,tests/live.sh); rc=$?
[ "$rc" = 0 ] && good '--only-suites accepts run lines, block run lines and gated scripts (also --only-suites=L)' || no 'accepted names' "$out"
# Workspace-only selects the guarded checks without running fixtures or taking the full-run lock.
reset_cache
out=$(WITH_LIVE=1 WITH_WS=1 cache_plan --workspace-only --no-reuse); rc=$?
log=$(sort "$RUN_LOG" | tr '\n' ' ')
[ "$rc" = 0 ] && [ "$log" = 'block blockrun inline live ws ' ] && [ ! -d "$TMP/state/locks/run-all-full" ] \
  && good '--workspace-only runs only workspace checks without the full-run lock' || no "workspace-only (rc=$rc, log=$log)" "$out"
out=$(bash "$ROOT/tests/run-all.sh" --workspace-only --list-suites); rc=$?
[ "$rc" = 0 ] && [ "$(tr '\n' ' ' <<<"$out")" = 'scripts/checks/x.sh tests/live.sh tests/blockrun.sh tests/ws.sh ' ] \
  && good '--list-suites honours --workspace-only' || no "workspace-only list (rc=$rc)" "$out"
for arg in -h --help unknown --unknown; do
  reset_cache
  out=$(cache_plan "$arg" 2>"$TMP/arg.err"); rc=$?
  case "$arg" in -h|--help) expected=0; header=$out ;; *) expected=2; header=$(cat "$TMP/arg.err") ;; esac
  [ "$rc" = "$expected" ] && grep -q '^# Usage: tests/run-all.sh' <<<"$header" && [ ! -s "$RUN_LOG" ] && [ ! -d "$TMP/state/locks/run-all-full" ] \
    && good "$arg prints usage and runs nothing (exit $expected)" || no "$arg argument (rc=$rc)" "$out $header"
done
for arg in --no-workspace --release; do
  out=$(cache_plan --workspace-only "$arg" 2>&1); rc=$?
  [ "$rc" = 2 ] && grep -q 'conflicts' <<<"$out" && [ ! -s "$RUN_LOG" ] \
    && good "--workspace-only conflicts with $arg" || no "workspace-only conflict $arg (rc=$rc)" "$out"
done
# --list-suites: the plan's run lines and gated scripts in order, nothing else; runs no check and takes no lock
: > "$RUN_LOG"
out=$(bash "$ROOT/tests/run-all.sh" --list-suites); rc=$?
[ "$rc" = 0 ] && [ "$(tr '\n' ' ' <<<"$out")" = 'tests/a.sh tests/b.sh tests/never.sh tests/partial.sh scripts/checks/x.sh tests/live.sh tests/blockrun.sh tests/ws.sh ' ] \
  && [ ! -s "$RUN_LOG" ] && [ ! -d "$TMP/state/locks/run-all-full" ] \
  && good '--list-suites prints the run lines and gated scripts, runs nothing, no lock' || no "--list-suites (stand-in) rc=$rc log=$(cat "$RUN_LOG") lock=$(ls "$TMP/state/locks" 2>&1)" "$out"
out=$(bash "$ROOT/tests/run-all.sh" --list-suites --release); rc=$?
[ "$rc" = 0 ] && [ "$(tr '
' ' ' <<<"$out")" = 'tests/a.sh tests/b.sh tests/never.sh tests/partial.sh tests/installed-safety.sh scripts/checks/x.sh tests/live.sh tests/blockrun.sh tests/ws.sh ' ]   && good '--list-suites --release also lists the release-only suite' || no "--list-suites --release (stand-in) rc=$rc" "$out"
out=$(cache_plan --only-suites tests/a.sh,tests/installed-safety.sh 2>&1); rc=$?
[ "$rc" = 2 ] && grep -q "release-only suite 'tests/installed-safety.sh' runs only with --release" <<<"$out"   && ! grep -q "'tests/a.sh'" <<<"$out" && ! grep -q 'unknown suite' <<<"$out"   && good '--only-suites rejects a release-only suite without --release (exit 2, named)' || no "release-only --only-suites (rc=$rc)" "$out"
real=$(env -u RUNALL_SUITES_FROM bash "$ROOT/tests/run-all.sh" --list-suites); rc=$?
miss=""; for s in tests/git-guard.test.sh tests/run-all-parallel.test.sh scripts/checks/sgl-determinism.py scripts/checks/wire-parity.sh \
    scripts/checks/netcode-headless.sh scripts/factory-context.sh tests/routing.test.sh testlab/tests/test_lab.py; do
  grep -qx "$s" <<<"$real" || miss+=" $s"; done
for s in tests/handoff-e2e.test.sh tests/orca-wait.test.sh scripts/lib/resolve.jq tests/run-all.sh tests/installed-safety.sh; do grep -qx "$s" <<<"$real" && miss+=" !$s"; done
rel=$(env -u RUNALL_SUITES_FROM bash "$ROOT/tests/run-all.sh" --list-suites --release)
[ "$(grep -vx 'tests/installed-safety.sh' <<<"$rel")" = "$real" ] && grep -qx tests/installed-safety.sh <<<"$rel" || miss+=" release:installed-safety"
[ "$rc" = 0 ] && [ -z "$miss" ] && [ "$(sort <<<"$real" | uniq -d)" = "" ] \
  && good "--list-suites on run-all.sh: suites and gated scripts, no orphan or syntax-check path ($(wc -l <<<"$real") names)" \
  || no "--list-suites (run-all.sh) wrong:$miss" "$real"
out=$(env -u RUNALL_SUITES_FROM bash "$ROOT/tests/run-all.sh" --only-suites tests/handoff-e2e.test.sh,tests/git-guard.test.sh,tests/orca-wait.test.sh 2>&1); rc=$?
[ "$rc" = 2 ] && grep -q "unknown suite 'tests/handoff-e2e.test.sh'" <<<"$out" && grep -q "unknown suite 'tests/orca-wait.test.sh'" <<<"$out" \
  && ! grep -q "'tests/git-guard.test.sh'" <<<"$out" && ! grep -q '^PASS ' <<<"$out" \
  && good 'run-all.sh --only-suites rejects suites it has no run line for, before any check' || no 'run-all.sh orphan suites' "$out"
reset_cache
out=$(cache_plan --affected --only-suites tests/a.sh); rc=$?
[ "$rc" = 0 ] && [ "$(tr '\n' ' ' < "$RUN_LOG")" = 'a b ' ] \
  && good '--affected and --only-suites form a deduplicated union' || no 'affected union' "$out"
# A subset is shown in results and passed as one comma-separated argument, in serial and parallel runs. It must
# never poison full-suite reuse, but a previously verified full suite can satisfy the same subset request.
for j in 1 3; do
  reset_cache; : > "$TMP/case-args"
  out=$(CASE_LOG="$TMP/case-args" CASE_SELECT=alpha,beta cache_plan --affected -j "$j"); rc=$?
  published=$(find "$TMP/state/run-all/suites" -type f 2>/dev/null | wc -l | tr -d ' ')
  [ "$rc" = 0 ] && [ "$(cat "$TMP/case-args")" = '--case alpha,beta' ] \
    && grep -q '^PASS  b (cases alpha,beta)' <<<"$out" && [ "$published" = 0 ] \
    && good "case subset is passed and named, never published as full suite PASS (-j $j)" || no "case subset (-j $j)" "$out"
  out=$(CASE_SELECT=alpha,beta BREAK_CASE=1 cache_plan --affected -j "$j"); rc=$?
  [ "$rc" = 1 ] && grep -q '^FAIL  b (cases alpha,beta)' <<<"$out" \
    && good "failed subset names its cases (-j $j)" || no "failed case subset (-j $j)" "$out"
  reset_cache; : > "$TMP/case-args"
  out=$(CASE_LOG="$TMP/case-args" CASE_SELECT=alpha,beta cache_plan --affected --only-suites tests/b.sh -j "$j"); rc=$?
  [ "$rc" = 0 ] && [ "$(wc -l < "$TMP/case-args")" -eq 1 ] && [ -z "$(cat "$TMP/case-args")" ] \
    && ! grep -q '(cases ' <<<"$out" && [ "$(find "$TMP/state/run-all/suites" -type f | wc -l)" -eq 1 ] \
    && good "explicit --only-suites overrides subset, publishes full suite PASS (-j $j)" || no "explicit case override (-j $j)" "$out"
  out=$(CASE_SELECT=alpha,beta cache_plan --affected -j "$j"); rc=$?
  [ "$rc" = 0 ] && grep -q 'reused tests/b.sh inputs ' <<<"$out" && [ "$(wc -l < "$RUN_LOG")" -eq 1 ] \
    && good "full-suite PASS can satisfy a case subset (-j $j)" || no "subset reuses full suite (-j $j)" "$out"
  reset_cache; : > "$TMP/case-args"
  out=$(CASE_LOG="$TMP/case-args" CASE_SELECT=ALL cache_plan --affected -j "$j"); rc=$?
  [ "$rc" = 0 ] && [ -z "$(cat "$TMP/case-args")" ] && ! grep -q '(cases ' <<<"$out" \
    && [ "$(find "$TMP/state/run-all/suites" -type f | wc -l)" -eq 1 ] \
    && good "case map ALL runs and records the full suite (-j $j)" || no "case map ALL (-j $j)" "$out"
done
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
# a suite that passed with SKIP lines (a missing tool) records no PASS: it runs again once the tool may be there
for j in 1 3; do
  reset_cache
  WITH_PARTIAL=1 cache_plan -j "$j" --only-suites tests/partial.sh,tests/a.sh >/dev/null
  out=$(WITH_PARTIAL=1 cache_plan -j "$j" --only-suites tests/partial.sh,tests/a.sh); rc=$?
  [ "$rc" = 0 ] && [ "$(sort "$RUN_LOG" | tr '
' ' ')" = 'a partial partial ' ] && grep -q 'reused tests/a.sh' <<<"$out"     && ! grep -q 'reused tests/partial.sh' <<<"$out"     && good "suite output with SKIP / not on PATH is never reused, a clean suite is (-j $j)" || no "partial suite reuse (-j $j): $(tr '
' ' ' < "$RUN_LOG")" "$out"
done
# Only result lines mark a partial pass: a PASS case whose name says NOT_AVAILABLE (ui-catalog, assetgen, pipeline) is
# reused like any clean suite; a NOT_AVAILABLE result line is not.
partial_line_case() { # want(reused|run) line
  local j
  for j in 1 3; do
    reset_cache
    PARTIAL_LINE=$2 WITH_PARTIAL=1 cache_plan -j "$j" --only-suites tests/partial.sh >/dev/null
    out=$(PARTIAL_LINE=$2 WITH_PARTIAL=1 cache_plan -j "$j" --only-suites tests/partial.sh); rc=$?
    if [ "$1" = reused ]; then
      [ "$rc" = 0 ] && grep -q 'reused tests/partial.sh' <<<"$out" && [ "$(cat "$RUN_LOG")" = partial ]         && good "suite output '$2' is a clean pass, reused (-j $j)" || no "clean pass not reused: '$2' (-j $j)" "$out"
    else
      [ "$rc" = 0 ] && ! grep -q 'reused tests/partial.sh' <<<"$out" && [ "$(tr '
' ' ' < "$RUN_LOG")" = 'partial partial ' ]         && good "suite output '$2' is a partial pass, never reused (-j $j)" || no "partial pass reused: '$2' (-j $j)" "$out"
    fi
  done
}
partial_line_case reused 'PASS  orca missing: NOT_AVAILABLE, cleanup stays CLEAN'
partial_line_case reused 'ok  probe prints tool not on PATH as NOT_AVAILABLE'
partial_line_case run 'NOT_AVAILABLE  unity: not on PATH'
partial_line_case run '  SKIP: Windows-form TMPDIR parser pass'
# --affected without a base and --only-suites: the message names what runs, and only that runs
reset_cache
out=$(NO_BASE=1 cache_plan --affected --only-suites tests/a.sh); rc=$?
[ "$rc" = 0 ] && grep -q 'no base, running only --only-suites tests/a.sh' <<<"$out" && ! grep -q 'running everything' <<<"$out"   && [ "$(cat "$RUN_LOG")" = a ] && good '--affected without a base and --only-suites says it runs only the listed suites' || no 'no-base message' "$out"
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
# the holder records its Windows PID where the runtime has one (MSYS/Cygwin /proc/<pid>/winpid), and no file elsewhere
HL="$TMP/state/locks/run-all-full"; hpid=$(cat "$HL/pid" 2>/dev/null)
if [ -r "/proc/$hpid/winpid" ]; then
  [ -n "$hpid" ] && [ "$(cat "$HL/winpid" 2>/dev/null)" = "$(cat "/proc/$hpid/winpid")" ]     && good 'full-run lock records the holder Windows PID' || no 'winpid recorded' "pid=$hpid winpid=$(cat "$HL/winpid" 2>&1)"
else
  [ -n "$hpid" ] && [ ! -e "$HL/winpid" ] && good 'full-run lock records no Windows PID without /proc/<pid>/winpid'     || no 'no winpid file' "pid=$hpid $(ls "$HL" 2>&1)"
fi
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
# The shared-config snapshot is taken once the lock is held: another session's config change while this run waits
# for the lock is not this run's; a change during its own run still is.
rm -f "$TMP/held" "$TMP/held.release"
HOLD_MARK="$TMP/held" cache_plan --no-reuse > "$TMP/holder.out" 2>&1 & holder=$!
for ((i=0; i<200; i++)); do [ ! -f "$TMP/held" ] || break; sleep 0.1; done
CHECK_CFG=1 cache_plan --no-reuse > "$TMP/waiter.out" 2>&1 & waiter=$!
for ((i=0; i<100; i++)); do grep -q 'waiting for full run ' "$TMP/waiter.out" && break; sleep 0.1; done
git -C "$TMP/repo" config rpgtest.wait other-session
touch "$TMP/held.release"; wait "$holder"; hrc=$?; wait "$waiter"; wrc=$?
[ "$hrc" = 0 ] && [ "$wrc" = 0 ] && grep -q 'waiting for full run ' "$TMP/waiter.out" && grep -qx 'cfg unchanged' "$TMP/waiter.out"   && good 'config changed by another session while waiting for the lock is not attributed to the waiting run'   || no "snapshot after lock (holder $hrc, waiter $wrc)" "$(cat "$TMP/waiter.out")"
out=$(CHECK_CFG=1 CFG_CHANGE=mine cache_plan --no-reuse); rc=$?
[ "$rc" = 0 ] && grep -qx 'cfg changed' <<<"$out" && good 'config changed during the run itself is still detected' || no 'config change during run' "$out"
git -C "$TMP/repo" config --remove-section rpgtest
mkdir -p "$TMP/state/locks/run-all-full"
printf '99999999\n' > "$TMP/state/locks/run-all-full/pid"
printf 'old checkout\n' > "$TMP/state/locks/run-all-full/checkout"
out=$(cache_plan --no-reuse); rc=$?
[ "$rc" = 0 ] && grep -q 'taking over stale full-run lock' <<<"$out" && [ ! -d "$TMP/state/locks/run-all-full" ] \
  && good 'dead PID lock is taken over and released' || no 'stale takeover' "$out"
# A holder from another MSYS/Cygwin runtime: its MSYS pid is dead here but its Windows PID is alive (stand-in
# tasklist.exe), so the lock is kept; once the Windows PID is gone as well, it is taken over.
L0="$TMP/state/locks/run-all-full"; mkdir -p "$TMP/winbin" "$L0"
cat > "$TMP/winbin/tasklist.exe" <<'STUB'
#!/usr/bin/env bash
[ "$*" = "//FI PID eq ${LIVE_WINPID:-none} //NH" ] && { echo "bash.exe   $LIVE_WINPID Console   1   11,184 K"; exit 0; }
echo 'INFO: No tasks are running which match the specified criteria.'
STUB
chmod +x "$TMP/winbin/tasklist.exe"
WINBIN="$TMP/winbin"; if command -v cygpath >/dev/null 2>&1; then WINBIN=$(cygpath -u "$WINBIN"); fi  # C:/ splits PATH
printf '99999999
' > "$L0/pid"; printf '4242
' > "$L0/winpid"
out=$(PATH="$WINBIN:$PATH" LIVE_WINPID=4242 timeout 60 bash "$TMP/cache-plan.sh" "$TMP/repo" --no-reuse --no-wait); rc=$?
[ "$rc" = 3 ] && ! grep -q 'taking over stale full-run lock' <<<"$out" && [ "$(cat "$L0/winpid" 2>/dev/null)" = 4242 ]   && good 'lock with a dead MSYS pid and a live Windows PID is not taken over' || no "live winpid (rc=$rc)" "$out"
mkdir -p "$L0"; printf '99999999
' > "$L0/pid"; printf '4242
' > "$L0/winpid"
out=$(PATH="$WINBIN:$PATH" LIVE_WINPID=1 timeout 60 bash "$TMP/cache-plan.sh" "$TMP/repo" --no-reuse --no-wait); rc=$?
[ "$rc" = 0 ] && grep -q 'taking over stale full-run lock' <<<"$out" && [ ! -d "$L0" ]   && good 'lock whose MSYS pid and Windows PID are both dead is taken over' || no "dead winpid (rc=$rc)" "$out"
# A takeover that died inside its reclaim guard: before it removed the pid files (dead holder in reclaim/pid), and after
# (lock holds only an old reclaim dir without pid). Neither wedges the lock, and --no-wait does not exit 3 for ever.
L="$TMP/state/locks/run-all-full"
mkdir -p "$L/reclaim"; printf '99999999
' > "$L/pid"; printf '99999998
' > "$L/reclaim/pid"
out=$(timeout 60 bash "$TMP/cache-plan.sh" "$TMP/repo" --no-reuse --no-wait); rc=$?
[ "$rc" = 0 ] && grep -q 'removing stale reclaim guard' <<<"$out" && grep -q 'taking over stale full-run lock' <<<"$out" && [ ! -d "$L" ]   && good 'reclaim guard of a dead takeover is removed, lock taken over' || no "dead reclaim holder (rc=$rc)" "$out"
mkdir -p "$L/reclaim"; touch -d '-1 minute' "$L/reclaim" "$L"
out=$(timeout 60 bash "$TMP/cache-plan.sh" "$TMP/repo" --no-reuse); rc=$?
[ "$rc" = 0 ] && grep -q 'removing stale reclaim guard of the full-run lock (no pid)' <<<"$out" && [ ! -d "$L" ]   && good 'old reclaim guard without a pid in a pid-less lock is removed, lock taken over' || no "old pid-less reclaim (rc=$rc)" "$out"
# Three-way takeover race: this run judged the lock stale and takes the reclaim guard, but meanwhile another takeover
# removed the stale lock and a new holder created a fresh one (pid not yet written) that the guard now sits in. The run
# re-checks under the guard and leaves the new holder's lock alone (stale lock with a dead pid, and one without a pid).
cat > "$TMP/race-plan.sh" <<'PLAN'
fixture=$1; shift
. "$ROOT_UNDER_TEST/tests/run-all.sh" "$@"
ROOT=$fixture; cd "$ROOT" || exit 1
eval "orig_lock_still_stale () $(declare -f lock_still_stale | tail -n +2)"
lock_still_stale() { # the other takeover and the new holder act between this run's checks and its re-check
  if [ ! -f "$LOCK.raced" ]; then
    touch "$LOCK.raced"; mv "$LOCK" "$LOCK.old"; mkdir "$LOCK"; mv "$LOCK.old/reclaim" "$LOCK/"; rm -rf "$LOCK.old"
  fi
  orig_lock_still_stale "$@"
}
runall_prepare; rc=$?
echo "prepare rc=$rc"
PLAN
for kind in pid nopid; do
  rm -rf "$L" "$L.raced"; mkdir -p "$L"
  if [ "$kind" = pid ]; then printf '99999999
' > "$L/pid"; else touch -d '-1 minute' "$L"; fi
  out=$(timeout 60 bash "$TMP/race-plan.sh" "$TMP/repo" --no-reuse --no-wait 2>&1); rc=$?
  [ -f "$L.raced" ] && grep -q 'prepare rc=3' <<<"$out" && ! grep -q 'taking over stale full-run lock' <<<"$out"     && [ -d "$L" ] && [ ! -e "$L/reclaim" ]     && good "takeover race ($kind): the new holder's fresh lock is kept, this run waits" || no "takeover race ($kind)" "$out"
done
rm -rf "$L" "$L.raced"
# Targeted runs share two machine-wide slots by default. Two held runs can start together; the third queues
# exactly once and cannot run a suite until a holder releases its slot. All holds are bounded by the fixture.
slot_wait_for() { # file [pattern]: wait for an observable checkpoint, not a fixed timing assumption
  local i
  for ((i=0; i<300; i++)); do
    if [ -n "${2:-}" ]; then grep -q "$2" "$1" 2>/dev/null && return 0
    else [ -f "$1" ] && return 0; fi
    sleep 0.1
  done
  return 1
}
SL="$TMP/state/locks/run-all-slots"
reset_cache
HOLD_MARK="$TMP/slot-held-1" cache_plan --only-suites tests/a.sh --no-reuse > "$TMP/slot-holder-1.out" 2>&1 & sh1=$!
slot_wait_for "$SL/1/checkout" repo
HOLD_MARK="$TMP/slot-held-2" cache_plan --affected --no-reuse > "$TMP/slot-holder-2.out" 2>&1 & sh2=$!
slot_wait_for "$SL/2/checkout" repo
slot_wait_for "$TMP/slot-held-1"; slot_wait_for "$TMP/slot-held-2"
[ -d "$SL/1" ] && [ -d "$SL/2" ] && [ -f "$TMP/slot-held-1" ] && [ -f "$TMP/slot-held-2" ] \
  && good 'default cap admits two targeted runs concurrently' || no 'default test slot cap' "$(cat "$TMP/slot-holder-1.out" "$TMP/slot-holder-2.out")"
spid=$(cat "$SL/1/pid" 2>/dev/null)
if [ -r "/proc/$spid/winpid" ]; then
  [ "$(cat "$SL/1/winpid" 2>/dev/null)" = "$(cat "/proc/$spid/winpid")" ] \
    && good 'targeted slot records the holder Windows PID' || no 'slot winpid metadata'
else
  [ -n "$spid" ] && [ ! -e "$SL/1/winpid" ] && good 'targeted slot records shell PID without a Windows runtime' || no 'slot pid metadata'
fi
out=$(cache_plan --only-suites tests/a.sh --no-reuse --no-wait); rc=$?
[ "$rc" = 3 ] && grep -q 'run-all: waiting for a test slot (2 in use:' <<<"$out" && [ ! -s "$RUN_LOG" ] \
  && good '--no-wait exits 3 when all targeted test slots are busy, before checks' || no 'targeted no-wait' "$out"
cache_plan --only-suites tests/a.sh --no-reuse > "$TMP/slot-waiter.out" 2>&1 & sw=$!
slot_wait_for "$TMP/slot-waiter.out" 'waiting for a test slot'
kill -0 "$sw" 2>/dev/null && [ ! -s "$RUN_LOG" ] && grep -q "$spid in " "$TMP/slot-waiter.out" \
  && good 'third targeted run queues and names its holders and checkouts' || no 'targeted wait message' "$(cat "$TMP/slot-waiter.out")"
touch "$TMP/slot-held-1.release"; wait "$sh1"; sr1=$?; wait "$sw"; srw=$?
touch "$TMP/slot-held-2.release"; wait "$sh2"; sr2=$?
[ "$sr1 $sr2 $srw" = '0 0 0' ] && [ "$(grep -c 'waiting for a test slot' "$TMP/slot-waiter.out")" -eq 1 ] \
  && [ "$(sort "$RUN_LOG" | tr '\n' ' ')" = 'a a b ' ] && [ -z "$(ls -A "$SL")" ] \
  && good 'waiting targeted run continues after release, announces once, all slots released' || no 'targeted slot handoff' "$(cat "$TMP/slot-waiter.out")"
# An environment cap of one blocks even with the default second slot free; zero disables slot admission entirely.
mkdir -p "$SL/1"; printf '%s\n' "$$" > "$SL/1/pid"; printf 'another checkout\n' > "$SL/1/checkout"
out=$(RPG_FACTORY_TEST_SLOTS=1 cache_plan --affected --no-reuse --no-wait); rc=$?
[ "$rc" = 3 ] && grep -q '(1 in use:' <<<"$out" && [ ! -d "$SL/2" ] \
  && good 'RPG_FACTORY_TEST_SLOTS=1 enforces a single machine-wide slot' || no 'environment slot cap' "$out"
out=$(RPG_FACTORY_TEST_SLOTS=0 cache_plan --affected --no-reuse --no-wait); rc=$?
[ "$rc" = 0 ] && ! grep -q 'waiting for a test slot' <<<"$out" && [ "$(cat "$SL/1/pid")" = "$$" ] \
  && good 'RPG_FACTORY_TEST_SLOTS=0 disables admission without touching other holders' || no 'disabled slots' "$out"
rm -rf "$SL/1"
out=$(RPG_FACTORY_TEST_SLOTS=bad cache_plan --affected --no-reuse 2>&1); rc=$?
[ "$rc" = 2 ] && grep -q 'RPG_FACTORY_TEST_SLOTS needs a non-negative integer' <<<"$out" \
  && good 'invalid slot cap exits 2 before checks' || no 'invalid slot cap' "$out"
mkdir -p "$SL/1"; printf '99999999\n' > "$SL/1/pid"
out=$(RPG_FACTORY_TEST_SLOTS=1 cache_plan --affected --no-reuse --no-wait); rc=$?
[ "$rc" = 0 ] && grep -q 'taking over stale test slot 1 (99999999)' <<<"$out" && [ ! -d "$SL/1" ] \
  && good 'dead targeted slot is reclaimed under guard and released' || no 'stale test slot' "$out"
mkdir -p "$SL/1/reclaim"; printf '99999999\n' > "$SL/1/pid"; printf '99999998\n' > "$SL/1/reclaim/pid"
out=$(RPG_FACTORY_TEST_SLOTS=1 cache_plan --affected --no-reuse --no-wait); rc=$?
[ "$rc" = 0 ] && grep -q 'removing stale reclaim guard of test slot 1' <<<"$out" && [ ! -d "$SL/1" ] \
  && good 'dead reclaim guard cannot wedge targeted slots' || no 'stale slot reclaim guard' "$out"
mkdir -p "$SL/1"; printf '99999999\n' > "$SL/1/pid"; printf '4242\n' > "$SL/1/winpid"
out=$(PATH="$WINBIN:$PATH" LIVE_WINPID=4242 RPG_FACTORY_TEST_SLOTS=1 cache_plan --affected --no-reuse --no-wait); rc=$?
[ "$rc" = 3 ] && ! grep -q 'taking over stale test slot' <<<"$out" && [ -d "$SL/1" ] \
  && good 'live Windows PID prevents targeted slot takeover across runtimes' || no 'live slot winpid' "$out"
rm -rf "$SL/1"
out=$(BREAK_SUITE=1 cache_plan --only-suites tests/a.sh --no-reuse); rc=$?
[ "$rc" = 1 ] && [ -z "$(ls -A "$SL")" ] && good 'targeted slot released after a failing suite' || no 'slot release on failure' "$out"
# Signals must release the acquired slot too. Start bash directly to capture the sourced-runner process PID.
HOLD_MARK="$TMP/slot-signal" bash "$TMP/cache-plan.sh" "$TMP/repo" --only-suites tests/a.sh --no-reuse > "$TMP/slot-signal.out" 2>&1 & ss=$!
slot_wait_for "$TMP/slot-signal"
kill -TERM "$ss"; wait "$ss"; rc=$?
[ "$rc" = 143 ] && [ -z "$(ls -A "$SL")" ] \
  && good 'targeted slot released on TERM' || no "slot release on TERM ($rc)" "$(cat "$TMP/slot-signal.out")"
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
# --affected asks affected.py once (`cases`: the selected suites and their cases), at -j 1 and -j 3 alike
for j in 1 3; do
  reset_cache; : > "$TMP/aff-calls"
  out=$(AFF_CALLS="$TMP/aff-calls" SELECT=tests/b.sh,tests/live.sh,scripts/checks/x.sh WITH_LIVE=1 cache_plan --no-reuse -j "$j" --affected); rc=$?
  calls=$(tr '\n' ' ' < "$TMP/aff-calls"); log=$(sort "$RUN_LOG" | tr '\n' ' ')
  [ "$rc" = 0 ] && [ "$calls" = 'cases ' ] && [ "$log" = 'b block inline live ' ] && grep -qx 'counts 5 0 1' <<<"$out" \
    && good "--affected calls affected.py once, with cases (-j $j)" || no "--affected affected.py calls (-j $j): '$calls' log '$log'" "$out"
done
# a failed `cases` call falls back to asking affected.py per suite (select), and the selection stays the same
reset_cache; : > "$TMP/aff-calls"
out=$(AFF_CALLS="$TMP/aff-calls" CASES_FAIL=1 cache_plan --no-reuse --affected); rc=$?
calls=$(tr '\n' ' ' < "$TMP/aff-calls"); log=$(sort "$RUN_LOG" | tr '\n' ' ')
[ "$rc" = 0 ] && [[ "$calls" == 'cases select '* ]] && [ "$log" = 'b ' ] \
  && good "--affected falls back to per-suite select when the cases call fails" || no "--affected cases fallback: '$calls' log '$log'" "$out"
# Workspace readers are never reused or published: a run line inside a block, a runl suite and a run line given
# RPG_FACTORY_WORKSPACE run again on the second run (even over a planted PASS record), while the fixture suite a is reused.
ws_suites=tests/a.sh,tests/live.sh,tests/blockrun.sh,tests/ws.sh
plant() { local s k; for s in tests/live.sh tests/blockrun.sh tests/ws.sh; do
  k=$(printf '%s' "$s" | sha1sum); k=${k%% *}; mkdir -p "$TMP/state/run-all/suites/$k"; printf 'PASS\n' > "$TMP/state/run-all/suites/$k/$(printf 'a%.0s' {1..64})"; done; }
for j in 1 3; do
  reset_cache
  out1=$(WITH_LIVE=1 WITH_WS=1 cache_plan -j "$j" --only-suites "$ws_suites"); rc1=$?
  published=$(find "$TMP/state/run-all/suites" -type f 2>/dev/null | wc -l | tr -d ' ')
  plant; : > "$RUN_LOG"
  out=$(WITH_LIVE=1 WITH_WS=1 cache_plan -j "$j" --only-suites "$ws_suites"); rc=$?
  log=$(sort "$RUN_LOG" | tr '\n' ' ')
  [ "$rc1" = 0 ] && [ "$published" = 1 ] && [ "$rc" = 0 ] && [ "$log" = 'blockrun live ws ' ] \
    && grep -q '^PASS  a (reused tests/a.sh inputs ' <<<"$out" && [ "$(grep -c 'reused' <<<"$out")" = 1 ] \
    && good "workspace readers (block run line, runl, RPG_FACTORY_WORKSPACE) never reused, fixture suite reused (-j $j)" \
    || no "workspace reader reuse (-j $j): published=$published log '$log'" "$out1"$'\n----\n'"$out"
done
# Every exit removes the shared-config copy (gitcfg_snapshot's mktemp, in $TMPDIR): --list-suites, an unknown suite
# (exit 2), a --reuse hit (exit 0 before any check) and --no-wait (exit 3)
CT="$TMP/cfgtmp"; mkdir -p "$CT"; reset_cache
TMPDIR="$CT" bash "$ROOT/tests/run-all.sh" --list-suites >/dev/null; r1=$?
TMPDIR="$CT" bash "$ROOT/tests/run-all.sh" --only-suites tests/unknown.sh >/dev/null 2>&1; r2=$?
args=""   # every argument-validation exit (exit 2), before the snapshot
for a in '--only-suites' '--only-suites=' '-j 0' '--jobs x' '--only-suites tests/installed-safety.sh'; do
  # shellcheck disable=SC2086
  TMPDIR="$CT" bash "$ROOT/tests/run-all.sh" $a >/dev/null 2>&1; args+="$? "
done
cache_plan >/dev/null; TMPDIR="$CT" cache_plan --reuse >/dev/null; r3=$?
mkdir -p "$TMP/state/locks/run-all-full"; printf '%s
' "$$" > "$TMP/state/locks/run-all-full/pid"
TMPDIR="$CT" cache_plan --no-reuse --no-wait >/dev/null; r4=$?; rm -rf "$TMP/state/locks/run-all-full"
left=$(ls -A "$CT")
[ "$r1 $r2 $r3 $r4" = '0 2 0 3' ] && [ "$args" = '2 2 2 2 2 ' ] && [ -z "$left" ]   && good 'early exits (--list-suites, unknown suite, bad arguments, release-only suite, --reuse hit, --no-wait) leave no git-config copy'   || no "early-exit temp files (rc $r1 $r2 $r3 $r4, arguments $args)" "$left"
# Unit-level WindowsApps shim: only the sourced runner process changes PATH.
mkdir -p "$TMP/WindowsApps" "$TMP/real-python"
printf '#!/usr/bin/env bash
exit 0
' > "$TMP/real-python/python.exe"; chmod +x "$TMP/real-python/python.exe"
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$REAL_PY_DIR"\n' > "$TMP/WindowsApps/python3"
chmod +x "$TMP/WindowsApps/python3"
cat > "$TMP/python-path.sh" <<'PLAN'
. "$ROOT_UNDER_TEST/tests/run-all.sh" -j 1
unset -f python3; unset RUNALL_REAL_PYTHON   # an outer run-all on an alias machine exports its python3 function
PATH="$(path_entry "$FAKE_ALIAS"):$PATH"; before=$PATH
python_path_fast
[ "$PATH" = "$(path_entry "$REAL_PY_DIR"):$before" ] && echo 'path prepended'
[ "$(type -t python3)" = function ] && [ "$RUNALL_REAL_PYTHON" = "$(path_entry "$REAL_PY_DIR")/python.exe" ] && echo 'alias bypassed'
PLAN
out=$(FAKE_ALIAS="$TMP/WindowsApps" REAL_PY_DIR="$TMP/real-python" bash "$TMP/python-path.sh"); rc=$?
[ "$rc" = 0 ] && grep -q 'using real Python directory' <<<"$out" && grep -q 'path prepended' <<<"$out" \
  && grep -q 'alias bypassed' <<<"$out" \
  && good 'WindowsApps shim prepends real interpreter directory and calls python.exe directly, in runner only' || no 'WindowsApps path' "$out"
unset RPG_FACTORY_STATE_DIR RUNALL_AFFECTED_PY RUN_LOG ROOT_UNDER_TEST

echo "run-all-parallel tests: $((pass + fail)) run, $pass passed, $fail failed"
[ "$fail" -eq 0 ] && [ "$pass" -gt 0 ]
