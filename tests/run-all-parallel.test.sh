#!/usr/bin/env bash
# tests/run-all.sh -j N: the scheduler (sourced from run-all.sh, no checks run) on stand-in suites. With -j 3 the
# output is line for line the -j 1 output (times aside), the counts are equal, two slow suites overlap (event order,
# no wall clock), at most 3 suites run at once, a SLOW suite starts first, live-lane suites (runl, block) never
# overlap each other, a block's lines are counted, a run1 suite runs alone, suites get /dev/null as stdin, runp grades through its handler, and a bad -j exits 2.
# Killed workers cannot hang the queue; shared config classification permits only whole added branch/worktree sections.
# A shared-config WARN is counted in the summary (copy removed; kept on FAIL); a passing suite's RETRY lines show under its PASS line.
# The suite registration inline check (suite_registration) fails an unregistered suite file under tests/ and a stale exemption.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
PLUGIN_SRC="$ROOT"   # ROOT is re-pointed at fixtures below
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
printf '#!/usr/bin/env bash\nprintf "a\\n" >> "$RUN_LOG"\n[ "${BREAK_SUITE:-0}" = 0 ] || { echo "a broke here"; exit 1; }\n' > "$TMP/repo/tests/a.sh"
cat > "$TMP/repo/tests/b.sh" <<'SUITE'
#!/usr/bin/env bash
# case-map: alpha scripts/alpha.py
# case-map: beta scripts/beta.py
printf 'b\n' >> "$RUN_LOG"
[ -z "${CASE_LOG:-}" ] || printf '%s\n' "$*" >> "$CASE_LOG"
[ "${BREAK_CASE:-0}" = 0 ]
SUITE
printf '#!/usr/bin/env bash\nprintf "never\\n" >> "$RUN_LOG"\n' > "$TMP/repo/tests/never.sh"
printf '#!/usr/bin/env bash\nprintf "live\\n" >> "$RUN_LOG"\n' > "$TMP/repo/tests/live.sh"
# hold: a suite that blocks while it runs (HOLD_SUITE_MARK appears, then it waits for HOLD_SUITE_MARK.release), so a test
# can observe the slot while a check is running
cat > "$TMP/repo/tests/hold.sh" <<'SUITE'
#!/usr/bin/env bash
printf 'hold\n' >> "$RUN_LOG"
touch "$HOLD_SUITE_MARK"; hold_until=$((SECONDS + 240))
while [ ! -f "$HOLD_SUITE_MARK.release" ]; do
  [ "$SECONDS" -lt "$hold_until" ] || { echo 'fixture suite hold timed out'; exit 1; }
  sleep 0.1
done
SUITE
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$1" >> "$RUN_LOG"\n' > "$TMP/repo/scripts/checks/x.sh"
# stand-ins for the three repo-wide enforcement scripts a --within run also runs (WITHIN_GUARDS); PP_BREACH=1 plants a
# portable-paths breach, RG_BREACH=1 a raw jq reader breach in the workspace readers guard
printf '#!/usr/bin/env bash\nprintf "english\\n" >> "$RUN_LOG"\n' > "$TMP/repo/scripts/checks/english-only.py"
printf '#!/usr/bin/env bash\nprintf "portable\\n" >> "$RUN_LOG"\n[ "${PP_BREACH:-0}" = 0 ] || { echo "planted portable-paths breach"; exit 1; }\n' > "$TMP/repo/scripts/checks/portable-paths.py"
printf '#!/usr/bin/env bash\nprintf "readers\\n" >> "$RUN_LOG"\n[ "${RG_BREACH:-0}" = 0 ] || { echo "planted raw jq reader breach"; exit 1; }\n' > "$TMP/repo/scripts/checks/workspace-readers.sh"
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
    args = sys.argv[2:]   # cases [--NAME VALUE | --NAME=VALUE]... FILE SUITE...: options in any order, never a suite
    while args and args[0].startswith('--'):
        args = args[1:] if '=' in args[0] else args[2:]
    for suite in args[1:]:   # like affected.py: one line per selected suite only
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
[ "${WITH_HOLD:-0}" = 0 ] || run hold bash tests/hold.sh
[ "${WITH_NEVER:-0}" = 0 ] || run never bash tests/never.sh
[ "${WITH_PARTIAL:-0}" = 0 ] || run partial bash tests/partial.sh
[ "${WITH_SKIP:-0}" = 0 ] || skp "tool check" "tool not on PATH"   # a skip for another reason than not affected
if [ "${WITH_GUARDS:-0}" != 0 ]; then   # the three enforcement lines, like run-all.sh's
  run "English-only enforcement (report available)" bash scripts/checks/english-only.py --enforce
  run "Portable-paths enforcement" bash scripts/checks/portable-paths.py --enforce
  run "Workspace readers guard (jq readers map paths, Python readers use the helper)" bash scripts/checks/workspace-readers.sh .
fi
# per-check durations: checks of known length, a failure and a runp skip (no tests/ path, so --list-suites never names them)
dskip_post() { _skp "dskip" "why"; }
if [ "${WITH_DUR:-0}" != 0 ]; then
  run d0 bash -c 'true'; run d3 bash -c 'sleep 3'; run d2 bash -c 'sleep 2'
  run dfail bash -c 'echo broke; exit 1'; runp dskip dskip_post bash -c 'true'
fi
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
# the `claude plugin validate` lines: gated by the pseudo key only for --workspace-only --base (no tests/ path: not listed)
if [ "${WITH_CLAUDE:-0}" != 0 ]; then ws_gate claude-plugin-validate && run1 cv bash -c 'printf "cv\n" >> "$RUN_LOG"'; fi
# workspace-list-end
[ "${CHANGE_INPUT:-0}" = 0 ] || echo changed >> tests/b.sh
[ -z "${CFG_CHANGE:-}" ] || git config rpgtest.during "$CFG_CHANGE"
drain
runall_finish
if [ -n "${CHECK_CFG:-}" ]; then
  if gitcfg_verify >/dev/null; then echo 'cfg unchanged'; else echo 'cfg changed'; rm -f "$GITCFG_COPY"; fi
fi
[ "${SLOWEST:-0}" = 0 ] || runall_slowest
runall_summary
echo "counts $pass $fail $skip"
# run-all.sh's own exit rule: every line after its last top-level summary call (the nothing-reached line, the status)
exit_rule=$(awk '{ sub(/\r$/, "") } /^runall_summary$/ { n = NR } { l[NR] = $0 } END { for (i = n + 1; n && i <= NR; i++) print l[i] }' "$ROOT_UNDER_TEST/tests/run-all.sh")
[ -n "$exit_rule" ] || { echo 'fixture: no exit rule after runall_summary in run-all.sh'; exit 99; }
eval "$exit_rule"
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
  && [ "$(find "$TMP/state/run-all/results" -type f -name '*.json' | wc -l)" -eq 1 ] \
  && good 'clean full PASS writes tree record and releases lock' || no 'full PASS record/lock' "$out"
out=$(cache_plan --reuse); rc=$?
[ "$rc" = 0 ] && grep -q '^reused full run at ' <<<"$out" && [ "$(wc -l < "$RUN_LOG")" -eq 2 ] \
  && [ "$(find "$TMP/state/run-all/results" -type f -name '*.json' | wc -l)" -eq 1 ] \
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
[ "$rc" = 0 ] && [ "$(tr '\n' ' ' <<<"$out")" = 'tests/a.sh tests/b.sh tests/hold.sh tests/never.sh tests/partial.sh scripts/checks/english-only.py scripts/checks/portable-paths.py scripts/checks/workspace-readers.sh scripts/checks/x.sh tests/live.sh tests/blockrun.sh tests/ws.sh ' ] \
  && [ ! -s "$RUN_LOG" ] && [ ! -d "$TMP/state/locks/run-all-full" ] \
  && good '--list-suites prints the run lines and gated scripts, runs nothing, no lock' || no "--list-suites (stand-in) rc=$rc log=$(cat "$RUN_LOG") lock=$(ls "$TMP/state/locks" 2>&1)" "$out"
out=$(bash "$ROOT/tests/run-all.sh" --list-suites --release); rc=$?
[ "$rc" = 0 ] && [ "$(tr '
' ' ' <<<"$out")" = 'tests/a.sh tests/b.sh tests/hold.sh tests/never.sh tests/partial.sh scripts/checks/english-only.py scripts/checks/portable-paths.py scripts/checks/workspace-readers.sh tests/installed-safety.sh scripts/checks/x.sh tests/live.sh tests/blockrun.sh tests/ws.sh ' ]   && good '--list-suites --release also lists the release-only suite' || no "--list-suites --release (stand-in) rc=$rc" "$out"
out=$(cache_plan --only-suites tests/a.sh,tests/installed-safety.sh 2>&1); rc=$?
[ "$rc" = 2 ] && grep -q "release-only suite 'tests/installed-safety.sh' runs only with --release" <<<"$out"   && ! grep -q "'tests/a.sh'" <<<"$out" && ! grep -q 'unknown suite' <<<"$out"   && good '--only-suites rejects a release-only suite without --release (exit 2, named)' || no "release-only --only-suites (rc=$rc)" "$out"
real=$(env -u RUNALL_SUITES_FROM bash "$ROOT/tests/run-all.sh" --list-suites); rc=$?
miss=""; for s in tests/git-guard.test.sh tests/run-all-parallel.test.sh scripts/checks/sgl-determinism.py scripts/checks/wire-parity.sh \
    scripts/checks/netcode-headless.sh scripts/checks/english-only.py scripts/checks/portable-paths.py scripts/checks/workspace-readers.sh scripts/factory-context.sh tests/routing.test.sh testlab/tests/test_lab.py \
    tests/workflow.test.sh tests/handoff-e2e.test.sh tests/artifact-quality.test.sh tests/asset-manifest.test.sh tests/domains-foundation.test.sh; do
  grep -qx "$s" <<<"$real" || miss+=" $s"; done
for s in tests/orca-wait.test.sh scripts/lib/resolve.jq tests/run-all.sh tests/installed-safety.sh; do grep -qx "$s" <<<"$real" && miss+=" !$s"; done
rel=$(env -u RUNALL_SUITES_FROM bash "$ROOT/tests/run-all.sh" --list-suites --release)
[ "$(grep -vx 'tests/installed-safety.sh' <<<"$rel")" = "$real" ] && grep -qx tests/installed-safety.sh <<<"$rel" || miss+=" release:installed-safety"
[ "$rc" = 0 ] && [ -z "$miss" ] && [ "$(sort <<<"$real" | uniq -d)" = "" ] \
  && good "--list-suites on run-all.sh: suites and gated scripts, no orphan or syntax-check path ($(wc -l <<<"$real") names)" \
  || no "--list-suites (run-all.sh) wrong:$miss" "$real"
out=$(env -u RUNALL_SUITES_FROM bash "$ROOT/tests/run-all.sh" --only-suites tests/git-guard.test.sh,tests/orca-wait.test.sh 2>&1); rc=$?
[ "$rc" = 2 ] && grep -q "unknown suite 'tests/orca-wait.test.sh'" <<<"$out" \
  && ! grep -q "'tests/git-guard.test.sh'" <<<"$out" && ! grep -q '^PASS ' <<<"$out" \
  && good 'run-all.sh --only-suites rejects suites it has no run line for, before any check' || no 'run-all.sh orphan suites' "$out"
# suite registration (inline check): every suite file under tests/ has a run line or a SUITE_EXEMPT entry; an exemption for a
# missing or registered file fails. suite_registration runs against a temp tree with a stand-in run-all file.
mkdir -p "$TMP/reg/tests"
printf '%s\n' 'run "a" env -u TMPDIR tests/a.test.sh' 'if [ -f tests/b.test.sh ]; then run "b" tests/b.test.sh; fi' > "$TMP/reg/plan.sh"
for s in a b exempt zz-unregistered; do printf '#!/usr/bin/env bash\n' > "$TMP/reg/tests/$s.test.sh"; done
cat > "$TMP/reg-check.sh" <<'PLAN'
. "$ROOT_UNDER_TEST/tests/run-all.sh" -j 1
cd "$REG" || exit 1
echo '== unregistered'; SUITE_EXEMPT="tests/exempt.test.sh"; suite_registration "$REG/plan.sh"
rm -f tests/zz-unregistered.test.sh
echo '== clean'; suite_registration "$REG/plan.sh"
echo '== bad exemptions'; SUITE_EXEMPT="tests/exempt.test.sh tests/a.test.sh tests/gone.test.sh"; suite_registration "$REG/plan.sh"
PLAN
out=$(ROOT_UNDER_TEST="$ROOT" REG="$TMP/reg" env -u RUNALL_SUITES_FROM bash "$TMP/reg-check.sh" 2>&1); rc=$?
sect() { sed -n "/^== $1\$/,/^== /{/^== /d;p;}" <<<"$out"; }
s1=$(sect unregistered); s2=$(sect clean); s3=$(sect 'bad exemptions')
[ "$rc" = 0 ] && [ "$(grep -c '^FAIL' <<<"$s1")" = 1 ] \
  && grep -qx 'FAIL  suite registration: tests/zz-unregistered.test.sh has no run line in tests/run-all.sh and no SUITE_EXEMPT entry' <<<"$s1" \
  && ! grep -q '^PASS' <<<"$s1" && ! grep -q 'exempt.test.sh\|tests/a.test.sh\|tests/b.test.sh' <<<"$s1" \
  && good 'suite registration fails an unregistered suite file under tests/ by name and passes run lines and exemptions' \
  || no "suite registration: unregistered file (rc=$rc)" "$out"
[ "$rc" = 0 ] && grep -qx 'PASS  suite registration: 3 tests/\*.test.sh files each have a run line or a SUITE_EXEMPT entry' <<<"$s2" \
  && ! grep -q '^FAIL' <<<"$s2" && good 'suite registration passes when every suite has a run line or an exemption' \
  || no "suite registration: clean tree (rc=$rc)" "$out"
[ "$rc" = 0 ] && [ "$(grep -c '^FAIL' <<<"$s3")" = 2 ] && ! grep -q '^PASS' <<<"$s3" \
  && grep -qx 'FAIL  suite registration: SUITE_EXEMPT entry tests/a.test.sh also has a run line in tests/run-all.sh (drop the exemption)' <<<"$s3" \
  && grep -qx 'FAIL  suite registration: SUITE_EXEMPT entry tests/gone.test.sh does not exist' <<<"$s3" \
  && good 'suite registration fails an exemption that is registered or names no file' \
  || no "suite registration: bad exemptions (rc=$rc)" "$out"
# a listed suite that is absent from the tree (a run line behind `if [ -f ... ]`) is not listed for run-all's own
# run lines and is rejected by --only-suites; a stand-in list (RUNALL_SUITES_FROM) keeps every name it lists
printf '%s\n' 'run "present" tests/git-guard.test.sh' 'if [ -f tests/zz-absent.test.sh ]; then run "absent" tests/zz-absent.test.sh; fi' \
  'run "also absent" env -u TMPDIR tests/zz-ghost.test.sh' > "$TMP/absent-plan.sh"
cat > "$TMP/absent-list.sh" <<'PLAN'
. "$ROOT_UNDER_TEST/tests/run-all.sh" -j 1
echo "real: $(list_suites "$PLAN_FILE" | tr '\n' ' ')"
RUNALL_SUITES_FROM="$PLAN_FILE"; echo "standin: $(list_suites "$PLAN_FILE" | tr '\n' ' ')"
PLAN
out=$(ROOT_UNDER_TEST="$ROOT" PLAN_FILE="$TMP/absent-plan.sh" env -u RUNALL_SUITES_FROM bash "$TMP/absent-list.sh" 2>&1); rc=$?
[ "$rc" = 0 ] && grep -qx 'real: tests/git-guard.test.sh ' <<<"$out" \
  && grep -qx 'standin: tests/git-guard.test.sh tests/zz-absent.test.sh tests/zz-ghost.test.sh ' <<<"$out" \
  && good 'list_suites leaves an absent suite out of run-all'"'"'s own list and keeps it in a stand-in list' || no "absent suite listing (rc=$rc)" "$out"
if [ ! -e "$ROOT/tests/plan-paths.test.sh" ]; then
  # the real wiring: tests/plan-paths.test.sh has a guarded run line and no file until task checks-lows lands
  grep -q 'tests/plan-paths.test.sh' "$ROOT/tests/run-all.sh" && ! grep -qx 'tests/plan-paths.test.sh' <<<"$real" \
    && out=$(env -u RUNALL_SUITES_FROM bash "$ROOT/tests/run-all.sh" --only-suites tests/plan-paths.test.sh 2>&1); rc=$?
  [ "$rc" = 2 ] && grep -q "unknown suite 'tests/plan-paths.test.sh'" <<<"$out" \
    && good 'an absent plan-paths suite is neither listed nor accepted by --only-suites' || no "absent plan-paths suite (rc=$rc)" "$out"
else
  grep -qx 'tests/plan-paths.test.sh' <<<"$real" && good 'the present plan-paths suite is listed' || no 'plan-paths suite present but not listed' "$real"
fi
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
  # --only-cases gives the one --only-suites suite a subset (CI passes scripts/ci-plan.py's planned cases): the same
  # --case argument and result name as an affected subset, and no suite PASS record
  reset_cache; : > "$TMP/case-args"
  out=$(CASE_LOG="$TMP/case-args" cache_plan --only-suites tests/b.sh --only-cases alpha,beta -j "$j"); rc=$?
  [ "$rc" = 0 ] && [ "$(cat "$TMP/case-args")" = '--case alpha,beta' ] && [ "$(cat "$RUN_LOG")" = b ] \
    && grep -q '^PASS  b (cases alpha,beta)' <<<"$out" && [ -z "$(find "$TMP/state/run-all/suites" -type f 2>/dev/null)" ] \
    && good "--only-cases subset reaches the suite as --case, named, no suite PASS record (-j $j)" || no "--only-cases subset (-j $j)" "$out"
  for arg in '--only-cases ALL' '--only-cases='; do
    reset_cache; : > "$TMP/case-args"
    # shellcheck disable=SC2086   # the option and its value are two words, or one with =
    out=$(CASE_LOG="$TMP/case-args" cache_plan --only-suites tests/b.sh $arg -j "$j"); rc=$?
    [ "$rc" = 0 ] && [ "$(wc -l < "$TMP/case-args" | tr -d ' ')" = 1 ] && [ -z "$(cat "$TMP/case-args")" ] \
      && ! grep -q '(cases ' <<<"$out" && [ "$(find "$TMP/state/run-all/suites" -type f | wc -l | tr -d ' ')" = 1 ] \
      && good "'$arg' runs every case and records the full suite (-j $j)" || no "'$arg' (-j $j)" "$out"
  done
done
# --only-cases misuse exits 2 with a message naming the problem, before any suite runs or a lock is taken
only_cases_misuse() { # message args...
  local want=$1; shift
  reset_cache
  out=$(cache_plan "$@" 2>&1); rc=$?
  [ "$rc" = 2 ] && grep -q "^run-all: .*$want" <<<"$out" && [ ! -s "$RUN_LOG" ] && ! grep -q '^PASS ' <<<"$out" \
    && [ ! -d "$TMP/state/locks/run-all-full" ] \
    && good "--only-cases misuse exits 2: $*" || no "--only-cases misuse (rc=$rc): $*" "$out"
}
only_cases_misuse '--only-cases needs --only-suites' --only-cases alpha
only_cases_misuse "exactly one --only-suites name, got 'tests/a.sh,tests/b.sh'" --only-suites tests/a.sh,tests/b.sh --only-cases alpha
only_cases_misuse "suite 'tests/a.sh' has no case map" --only-suites tests/a.sh --only-cases alpha
only_cases_misuse "unknown case(s) 'gamma' in 'tests/b.sh'" --only-suites tests/b.sh --only-cases alpha,gamma
only_cases_misuse '--only-cases conflicts with --release' --only-suites tests/b.sh --only-cases alpha --release
only_cases_misuse '--inline-only conflicts with --only-cases' --inline-only --only-cases alpha
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
inspection=$(bash "$ROOT/tests/run-all.sh" --last-result --checkout "$TMP/repo"); irc=$?
[ "$irc" = 1 ] && grep -q "^running: full run pid $hpid .* args --no-reuse$" <<<"$inspection" \
  && [ "$(cat "$HL/args" 2>/dev/null)" = '--no-reuse' ] && [ -n "$(cat "$HL/record" 2>/dev/null)" ] \
  && good 'printer shows the live full-run lock and its arguments before a result exists' || no 'running full-run inspection' "$inspection"
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
printf 'old arguments\n' > "$TMP/state/locks/run-all-full/args"
printf '/old/result.json\n' > "$TMP/state/locks/run-all-full/record"
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
out=$(cache_plan --only-suites tests/a.sh --no-reuse -j 1 --no-wait); rc=$?
[ "$rc" = 3 ] && grep -q 'run-all: waiting for a test slot (2 in use:' <<<"$out" && [ ! -s "$RUN_LOG" ] \
  && good '--no-wait exits 3 when all targeted test slots are busy, before checks' || no 'targeted no-wait' "$out"
cache_plan --only-suites tests/a.sh --no-reuse -j 1 > "$TMP/slot-waiter.out" 2>&1 & sw=$!
slot_wait_for "$TMP/slot-waiter.out" 'waiting for a test slot'
kill -0 "$sw" 2>/dev/null && [ ! -s "$RUN_LOG" ] && grep -q "$spid in " "$TMP/slot-waiter.out" \
  && good 'third targeted run queues and names its holders and checkouts' || no 'targeted wait message' "$(cat "$TMP/slot-waiter.out")"
sleep 1; queued_until=$(date -u +%FT%TZ)   # one second into the wait: a start taken before the wait is earlier
touch "$TMP/slot-held-1.release"; wait "$sh1"; sr1=$?; wait "$sw"; srw=$?
waiter_start=$(python3 -B - "$TMP/state/run-all/results" <<'PY'
import glob, json, os, sys
for path in glob.glob(os.path.join(sys.argv[1], '*', '*.json')):
    with open(path, encoding='utf-8') as f:
        r = json.load(f)
    if '-j' in r['args']:
        print(r['started'] + ' ' + os.path.basename(path).split('-')[0])
PY
)
read -r waiter_started waiter_stamp <<<"${waiter_start%$'\r'}"
[ -n "$waiter_started" ] && [[ ! "$waiter_started" < "$queued_until" ]] && [ "$waiter_stamp" = "${waiter_started//[-:]/}" ] \
  && good 'a queued run records its start at slot admission, not before its wait' \
  || no 'queued run start time' "started '$waiter_started' file '$waiter_stamp' queued until $queued_until"
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
printf 'old arguments\n' > "$SL/1/args"; printf '/old/result.json\n' > "$SL/1/record"
printf 'check=old\n' > "$SL/1/progress"; printf 'check=old\n' > "$SL/1/progress.tmp.99999999"   # a dead holder's progress goes with its slot
out=$(RPG_FACTORY_TEST_SLOTS=1 cache_plan --affected --no-reuse --no-wait 2>"$TMP/slot-takeover.err"); rc=$?
[ "$rc" = 0 ] && ! grep -q 'taking over stale test slot' <<<"$out" && grep -q 'taking over stale test slot 1 (99999999)' "$TMP/slot-takeover.err" && [ ! -d "$SL/1" ] \
  && good 'dead targeted slot is reclaimed under guard and released; the takeover message is on stderr, not stdout' || no 'stale test slot' "$out $(cat "$TMP/slot-takeover.err")"
mkdir -p "$SL/1/reclaim"; printf '99999999\n' > "$SL/1/pid"; printf '99999998\n' > "$SL/1/reclaim/pid"
out=$(RPG_FACTORY_TEST_SLOTS=1 cache_plan --affected --no-reuse --no-wait); rc=$?
[ "$rc" = 0 ] && grep -q 'removing stale reclaim guard of test slot 1' <<<"$out" && [ ! -d "$SL/1" ] \
  && good 'dead reclaim guard cannot wedge targeted slots' || no 'stale slot reclaim guard' "$out"
mkdir -p "$SL/1"; printf '99999999\n' > "$SL/1/pid"; printf '4242\n' > "$SL/1/winpid"
out=$(PATH="$WINBIN:$PATH" LIVE_WINPID=4242 RPG_FACTORY_TEST_SLOTS=1 cache_plan --affected --no-reuse --no-wait 2>&1); rc=$?
[ "$rc" = 3 ] && ! grep -q 'taking over stale test slot' <<<"$out" && [ -d "$SL/1" ] \
  && good 'live Windows PID prevents targeted slot takeover across runtimes' || no 'live slot winpid' "$out"
rm -rf "$SL/1"
# netcode-headless.sh prune_evidence orders same-second evidence directories by numeric pid: pid 10 is newer than pid 9.
# Only the function is run (extracted from the check), against a temp evidence root.
EV="$TMP/evidence-prune"; mkdir -p "$EV"
for n in 20260101T000000-9 20260101T000000-10 20260101T000000-100 20260101T000001-1 20251231T235959-99999; do mkdir -p "$EV/$n"; done
sed -n '/^prune_evidence() {/,/^}/p' "$PLUGIN_SRC/scripts/checks/netcode-headless.sh" > "$TMP/prune-evidence.sh"
out=$(RPG_FACTORY_NETCODE_EVIDENCE_KEEP=3 bash -c '. "$1"; prune_evidence "$2" 20260101T000001-1' _ "$TMP/prune-evidence.sh" "$EV" 2>&1); rc=$?
left=$(ls "$EV" | LC_ALL=C sort | tr '\n' ' ')
[ "$rc" = 0 ] && [ "$left" = '20260101T000000-10 20260101T000000-100 20260101T000001-1 ' ] \
  && grep -q 'pruned 2 old' <<<"$out" \
  && good 'netcode evidence prune keeps the newest by full timestamp, then numeric pid (pid 100 and 10 over 9)' || no "evidence prune order (rc=$rc left='$left')" "$out"
out=$(BREAK_SUITE=1 cache_plan --only-suites tests/a.sh --no-reuse); rc=$?
[ "$rc" = 1 ] && [ -z "$(ls -A "$SL")" ] && good 'targeted slot released after a failing suite' || no 'slot release on failure' "$out"
# Signals must release the acquired slot too. Start bash directly to capture the sourced-runner process PID.
HOLD_MARK="$TMP/slot-signal" bash "$TMP/cache-plan.sh" "$TMP/repo" --only-suites tests/a.sh --no-reuse > "$TMP/slot-signal.out" 2>&1 & ss=$!
slot_wait_for "$TMP/slot-signal"
kill -TERM "$ss"; wait "$ss"; rc=$?
[ "$rc" = 143 ] && [ -z "$(ls -A "$SL")" ] \
  && good 'targeted slot released on TERM' || no "slot release on TERM ($rc)" "$(cat "$TMP/slot-signal.out")"
# Results survive lost terminals, preserve original arguments and describe failures independently of PASS reuse.
last_result() { bash "$ROOT/tests/run-all.sh" --last-result --checkout "$TMP/repo"; }
for broken in 0 1; do
  reset_cache
  out=$(BREAK_SUITE=$broken cache_plan --only-suites tests/a.sh,tests/b.sh --no-reuse); rc=$?
  printed=$(last_result); prc=$?
  record=$(sed -n 's/^result: //p' <<<"$printed")
  checked=$(python3 -B - "$record" "$TMP/repo" "$broken" "$out" <<'PY'
import datetime, hashlib, json, os, re, subprocess, sys
path, checkout, broken, output = sys.argv[1:]
broken = int(broken)
with open(path, encoding='utf-8') as f:
    r = json.load(f)
assert r['schema'] == 'rpg-factory.run-all-result/1'
assert r['checkout'] == checkout
assert r['args'] == ['--only-suites', 'tests/a.sh,tests/b.sh', '--no-reuse']
assert r['exit'] == broken and type(r['exit']) is int
assert r['counts'] == {'pass': 2-broken, 'fail': broken, 'skip': 0, 'warn': 0, 'not_affected': 0}
# a timed suite keeps its wall time in the name, as run-all prints it ('a [1s]')
assert len(r['failed']) == broken and all(re.fullmatch(r'a \[[0-9]+s\]', name) for name in r['failed'])
if broken:   # the failure's output survives the run: its last lines, next to the unchanged failed list
    [out] = r['failed_output']
    assert sorted(out) == ['name', 'tail'] and out['name'] == r['failed'][0]
    assert 'a broke here' in out['tail'].split('\n')
else:
    assert r['failed_output'] == []
assert r['summary'] in output.splitlines()
start, end = (datetime.datetime.fromisoformat(r[k].replace('Z', '+00:00')) for k in ('started', 'ended'))
assert start <= end and r['started'].endswith('Z') and r['ended'].endswith('Z')
assert r['head'] == subprocess.check_output(['git', '-C', checkout, 'rev-parse', 'HEAD'], text=True).strip()
assert type(r['pid']) is int and r['pid'] > 0
assert r['winpid'] is None or type(r['winpid']) is int and r['winpid'] > 0
key = hashlib.sha256(checkout.encode()).hexdigest()[:16]
assert os.path.dirname(path).replace('\\', '/').endswith('/run-all/results/' + key)
assert re.fullmatch(r'\d{8}T\d{6}Z-\d+\.json', os.path.basename(path))
assert os.path.basename(path) == start.strftime('%Y%m%dT%H%M%SZ') + f"-{r['pid']}.json"
sys.stdout.buffer.write(b'record valid\n')
PY
  ); crc=$?
  [ "$rc" = "$broken" ] && [ "$prc" = 0 ] && [ "$crc" = 0 ] && [ "$checked" = 'record valid' ] \
    && grep -qx "exit: $broken" <<<"$printed" && grep -q '^started: .*Z$' <<<"$printed" \
    && grep -q '^ended: .*Z$' <<<"$printed" && grep -qx 'args: --only-suites tests/a.sh,tests/b.sh --no-reuse' <<<"$printed" \
    && { [ "$broken" = 0 ] || [ "$(grep -A1 -E '^FAILED a \[[0-9]+s\]$' <<<"$printed")" = "$(grep -E '^FAILED a \[[0-9]+s\]$' <<<"$printed")"$'\n''      a broke here' ]; } \
    && good "persistent result has every field, exact counts and failures; printer reads it (exit $broken)" \
    || no "result record (run $rc, printer $prc, validation $crc)" "$out"$'\n'"$printed"
done
# The default checkout works when the runner is sourced by the stand-in too.
out=$(cache_plan --last-result); rc=$?
[ "$rc" = 0 ] && [ "$out" = "$printed" ] \
  && good '--last-result defaults to the current checkout and runs no check' || no 'default checkout printer' "$out"
# The record path is the very last output line (after the summary), for a passing and a failing run alike, so a caller
# that keeps only the tail of the output can find the FAIL blocks: the file exists under the state dir and holds them.
for broken in 1 0; do
  reset_cache
  out=$(BREAK_SUITE=$broken cache_plan --only-suites tests/a.sh --no-reuse); rc=$?
  last=$(tail -n 1 <<<"${out//$'\r'/}")
  rec=${last#run-all: result record }; rec=${rec%% (FAIL blocks: tests/run-all.sh --last-result)}
  sum_n=$(grep -n '^run-all: [0-9]* checks, ' <<<"${out//$'\r'/}" | tail -n 1 | cut -d: -f1)
  total_n=$(wc -l <<<"${out//$'\r'/}" | tr -d ' ')
  held=$(python3 -B - "$rec" "$broken" <<'PY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as f:
    r = json.load(f)
broken = int(sys.argv[2])
if broken:
    [o] = r['failed_output']
    assert o['name'].startswith('a [') and 'a broke here' in o['tail'].split('\n')
else:
    assert r['failed'] == [] and r['failed_output'] == []
sys.stdout.buffer.write(b'held\n')
PY
  ); hrc=$?
  [ "$rc" = "$broken" ] && [ "$last" != "$rec" ] && [ "$(grep -c '^run-all: result record ' <<<"${out//$'\r'/}")" = 1 ] \
    && [ -n "$sum_n" ] && [ "$sum_n" -lt "$total_n" ] && [[ "$rec" == "$TMP/state/run-all/results/"* ]] && [ -f "$rec" ] \
    && [ "$hrc" = 0 ] && [ "$held" = held ] && grep -qx "result: $rec" <<<"$(last_result)" \
    && good "the last output line names the result record, after the summary, holding the FAIL blocks (exit $broken)" \
    || no "record path line (run $rc, record check $hrc, summary line $sum_n of $total_n)" "$out"
done
# An interrupted run prints it too, once the record is written.
reset_cache
HOLD_MARK="$TMP/record-line-term" bash "$TMP/cache-plan.sh" "$TMP/repo" --only-suites tests/a.sh --no-reuse > "$TMP/record-line-term.out" 2>&1 & rt=$!
slot_wait_for "$TMP/record-line-term"
kill -TERM "$rt"; wait "$rt"; rc=$?
last=$(tail -n 1 "$TMP/record-line-term.out" | tr -d '\r'); rec=${last#run-all: result record }; rec=${rec%% (FAIL blocks: tests/run-all.sh --last-result)}
[ "$rc" = 143 ] && [ "$last" != "$rec" ] && [ -f "$rec" ] && grep -qx 'exit: 143' <<<"$(last_result)" \
  && good 'an interrupted run (TERM) prints its result record path as the last line' || no "record path line after TERM (rc $rc)" "$(cat "$TMP/record-line-term.out")"
for ((i=0; i<300; i++)); do [ -z "$(ls -A "$SL")" ] && break; sleep 0.1; done
# Inspection is read-only, including when no record exists or a caller supplies parallel-job flags.
before=$(find "$TMP/state" -type f -exec sha256sum {} \; | sort)
out=$(bash "$ROOT/tests/run-all.sh" --last-result --checkout "$TMP/unknown-checkout" -j 2); rc=$?
after=$(find "$TMP/state" -type f -exec sha256sum {} \; | sort)
[ "$rc" = 1 ] && grep -q 'no result record for checkout ' <<<"$out" && [ "$before" = "$after" ] \
  && good '--last-result for an unknown checkout exits 1 without changing persistent state' || no 'unknown checkout result' "$out"
out=$(bash "$ROOT/tests/run-all.sh" --checkout "$TMP/repo" 2>&1); rc=$?
[ "$rc" = 2 ] && grep -q -- '--checkout requires --last-result' <<<"$out" \
  && good '--checkout requires the read-only printer' || no '--checkout without printer' "$out"
for broken in 0 1; do
  reset_cache
  mark="$TMP/duplicate-$broken"
  HOLD_MARK="$mark" BREAK_SUITE=$broken cache_plan --only-suites tests/a.sh --no-reuse > "$TMP/duplicate-holder.out" 2>&1 & dh=$!
  slot_wait_for "$mark"
  dp=$(cat "$SL/1/pid" 2>/dev/null); ds=$(cat "$SL/1/started" 2>/dev/null); dr=$(cat "$SL/1/record" 2>/dev/null)
  [ "$(cat "$SL/1/args" 2>/dev/null)" = '--only-suites tests/a.sh --no-reuse' ] && [[ "$dr" == "$TMP/state/run-all/results/"* ]] \
    && good 'slot publishes normalized arguments and its absolute result path' || no 'slot arguments and record metadata'
  out=$(cache_plan --no-wait --only-suites tests/a.sh --no-reuse); rc=$?
  [ "$rc" = 4 ] && grep -q "same run already holds test slot 1 (pid $dp, winpid .*started $ds, args " <<<"$out" \
    && grep -q -- '--last-result' <<<"$out" && [ ! -s "$RUN_LOG" ] && [ ! -d "$SL/2" ] && [ ! -f "$dr" ] \
    && good 'same checkout and arguments exit 4 naming the holder, without a suite or another slot' || no "duplicate run (rc $rc)" "$out"
  running=$(last_result); rrc=$?
  [ "$rrc" = 1 ] && grep -q "^running: slot 1 pid $dp .*started $ds args --only-suites tests/a.sh --no-reuse$" <<<"$running" \
    && good 'read-only inspection shows a live matching slot before its first result exists' || no 'running slot inspection' "$running"
  cache_plan --attach --only-suites tests/a.sh --no-reuse --no-wait > "$TMP/attached.out" 2>&1 & da=$!
  slot_wait_for "$TMP/attached.out" 'run-all: attaching to test slot 1'
  kill -0 "$da" 2>/dev/null && [ ! -s "$RUN_LOG" ] && [ ! -d "$SL/2" ] \
    && good '--attach waits on the original owner without taking another slot or starting a suite' || no 'attach wait' "$(cat "$TMP/attached.out")"
  touch "$mark.release"; wait "$dh"; hrc=$?; wait "$da"; arc=$?
  nr=$(find "$TMP/state/run-all/results" -name '*.json' -type f | wc -l | tr -d ' ')
  [ "$hrc" = "$broken" ] && [ "$arc" = "$broken" ] && [ "$nr" = 1 ] && [ "$(cat "$RUN_LOG")" = a ] \
    && grep -q '^result: ' "$TMP/attached.out" && grep -qx "exit: $broken" "$TMP/attached.out" && [ -z "$(ls -A "$SL")" ] \
    && good "--attach prints the holder's only result and returns its exit status ($broken)" \
    || no "attached result (holder $hrc, attached $arc, records $nr)" "$(cat "$TMP/attached.out")"
done
# While a run holds a slot it keeps a progress file in the slot directory (UTC time, the check running or last finished,
# its result, the counts so far); the file goes with the slot. tests/a.sh passes (or fails) first, then tests/hold.sh runs.
for broken in 0 1; do
  reset_cache
  mark="$TMP/progress-held-$broken"
  HOLD_SUITE_MARK="$mark" WITH_HOLD=1 BREAK_SUITE=$broken cache_plan --only-suites tests/a.sh,tests/hold.sh --no-reuse -j 1 > "$TMP/progress.out" 2>&1 & pg=$!
  slot_wait_for "$mark"
  prog=$(tr -d '\r' < "$SL/1/progress" 2>/dev/null)
  keys=$(cut -d= -f1 <<<"$prog" | tr '\n' ' ')
  [ "$keys" = 'updated check result passed failed ' ] && grep -qx 'check=hold' <<<"$prog" && grep -qx 'result=running' <<<"$prog" \
    && grep -qx "passed=$((1 - broken))" <<<"$prog" && grep -qx "failed=$broken" <<<"$prog" \
    && grep -Eqx 'updated=[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z' <<<"$prog" && [ -z "$(ls "$SL/1" | grep 'progress\.tmp')" ] \
    && good "a held slot has a progress file: the running check, its result and the counts so far (failing first suite: $broken)" \
    || no "slot progress file (broken $broken)" "$prog"
  touch "$mark.release"; wait "$pg"; prc=$?
  for ((i=0; i<300; i++)); do [ -d "$SL/1" ] || break; sleep 0.1; done
  [ "$prc" = "$broken" ] && [ -z "$(ls -A "$SL")" ] \
    && good 'the progress file is gone once the slot is released' || no "slot progress cleanup (rc $prc)" "$(ls -A "$SL/1" 2>/dev/null)"
done
# A newer result wins over an older failure. Neither the printer nor a run writes into the checkout.
out=$(cache_plan --only-suites tests/a.sh,tests/b.sh --no-reuse); rc=$?
printed=$(last_result); prc=$?
[ "$rc $prc" = '0 0' ] && grep -qx 'exit: 0' <<<"$printed" && ! grep -q '^FAILED ' <<<"$printed" \
  && [ -z "$(git -C "$TMP/repo" status --porcelain)" ] \
  && good 'printer selects the newest result for the checkout; fixture checkout stays clean' || no 'newest result and checkout pollution' "$printed"
# Background a held run in a subshell, let that launching shell return, then release the orphaned run.
reset_cache
(
  HOLD_MARK="$TMP/detached" bash "$TMP/cache-plan.sh" "$TMP/repo" --only-suites tests/a.sh --no-reuse \
    > "$TMP/detached.out" 2>&1 < /dev/null &
  printf '%s\n' "$!" > "$TMP/detached.pid"
)
launcher_rc=$?
slot_wait_for "$TMP/detached"
dr=$(cat "$SL/1/record" 2>/dev/null)
touch "$TMP/detached.release"
slot_wait_for "$dr"
printed=$(last_result); prc=$?
[ "$launcher_rc $prc" = '0 0' ] && [ -f "$dr" ] && grep -qx "result: $dr" <<<"$printed" \
  && grep -qx 'exit: 0' <<<"$printed" && [ "$(cat "$RUN_LOG")" = a ] \
  && good 'a run whose launching subshell already exited still writes its result' || no 'detached run result' "$printed"
# A record is published before its slot is removed; wait for cleanup before resetting shared fixture state.
for ((i=0; i<300; i++)); do [ -d "$SL/1" ] || break; sleep 0.1; done
# Identical arguments in another checkout retain the ordinary second-slot behaviour.
reset_cache
cp -R "$TMP/repo" "$TMP/other-repo"
HOLD_MARK="$TMP/checkout-one" cache_plan --only-suites tests/a.sh --no-reuse > "$TMP/checkout-one.out" 2>&1 & co1=$!
slot_wait_for "$TMP/checkout-one"
HOLD_MARK="$TMP/checkout-two" bash "$TMP/cache-plan.sh" "$TMP/other-repo" --only-suites tests/a.sh --no-reuse > "$TMP/checkout-two.out" 2>&1 & co2=$!
slot_wait_for "$TMP/checkout-two"
[ "$(cat "$SL/1/checkout" 2>/dev/null)" = "$TMP/repo" ] && [ "$(cat "$SL/2/checkout" 2>/dev/null)" = "$TMP/other-repo" ] \
  && good 'same arguments in another checkout take the second slot' || no 'other checkout slot' "$(cat "$TMP/checkout-two.out")"
touch "$TMP/checkout-one.release" "$TMP/checkout-two.release"
wait "$co1"; c1=$?; wait "$co2"; c2=$?
out=$(bash "$ROOT/tests/run-all.sh" --last-result --checkout "$TMP/other-repo"); rc=$?
[ "$c1 $c2 $rc" = '0 0 0' ] && grep -qx 'exit: 0' <<<"$out" && [ "$(wc -l < "$RUN_LOG")" -eq 2 ] \
  && [ -z "$(git -C "$TMP/other-repo" status --porcelain)" ] \
  && good 'each checkout publishes its own result and runs its own suite' || no 'checkout-isolated results' "$out"
# HUP exits 129, publishes partial counts and releases its slot just like TERM.
reset_cache
HOLD_MARK="$TMP/slot-hup" bash "$TMP/cache-plan.sh" "$TMP/repo" --only-suites tests/a.sh --no-reuse > "$TMP/slot-hup.out" 2>&1 & hs=$!
slot_wait_for "$TMP/slot-hup"
kill -HUP "$hs"; wait "$hs"; hrc=$?
printed=$(last_result); prc=$?
[ "$hrc $prc" = '129 0' ] && grep -qx 'exit: 129' <<<"$printed" && [ -z "$(ls -A "$SL")" ] \
  && good 'HUP publishes an interrupted result and releases its targeted slot' || no 'HUP result and cleanup' "$printed"
# Zero slots still records the run, retaining the original flags omitted only from duplicate matching.
reset_cache
out=$(RPG_FACTORY_TEST_SLOTS=0 cache_plan --only-suites tests/a.sh --no-reuse --no-wait --attach); rc=$?
printed=$(last_result); prc=$?
[ "$rc $prc" = '0 0' ] && grep -qx 'args: --only-suites tests/a.sh --no-reuse --no-wait --attach' <<<"$printed" \
  && [ -z "$(ls -A "$SL")" ] && grep -q '^run-all: 2 checks, 1 passed, 0 failed, 1 skipped (1 not affected by the change)$' <<<"$printed" \
  && good 'disabled slot cap still publishes counts and all original arguments' || no 'result without slot admission' "$printed"
# Seed old records without running suites repeatedly: writing the next real result keeps exactly the newest 20.
record=$(sed -n 's/^result: //p' <<<"$printed")
python3 -B - "$record" <<'PY'
import json, os, sys
directory = os.path.dirname(sys.argv[1])
with open(sys.argv[1], encoding='utf-8') as f:
    r = json.load(f)
for i in range(25):
    path = os.path.join(directory, f'20000101T000000Z-{i}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(r, f)
    os.utime(path, (i+1, i+1))
PY
out=$(cache_plan --only-suites tests/a.sh --no-reuse); rc=$?
printed=$(last_result); prc=$?
nr=$(find "${record%/*}" -type f -name '*.json' | wc -l | tr -d ' ')
[ "$rc $prc" = '0 0' ] && [ "$nr" = 20 ] && [ ! -e "${record%/*}/20000101T000000Z-0.json" ] \
  && grep -qx 'args: --only-suites tests/a.sh --no-reuse' <<<"$printed" \
  && good 'result writes prune old records to the newest 20 per checkout' || no "result retention ($nr files)" "$printed"
# A failed record write is silent and leaves the holder's result untouched; attachment reports the missing record.
reset_cache; mkdir -p "$TMP/state/run-all"; : > "$TMP/state/run-all/results"
HOLD_MARK="$TMP/result-unwritable" cache_plan --only-suites tests/a.sh --no-reuse > "$TMP/result-unwritable.out" 2>&1 & uh=$!
slot_wait_for "$TMP/result-unwritable"
cache_plan --only-suites tests/a.sh --no-reuse --attach > "$TMP/result-missing.out" 2>&1 & ua=$!
slot_wait_for "$TMP/result-missing.out" 'run-all: attaching to'
touch "$TMP/result-unwritable.release"; wait "$uh"; urc=$?; wait "$ua"; arc=$?
[ "$urc $arc" = '0 5' ] && grep -q 'no result record available' "$TMP/result-missing.out" \
  && ! grep -Eqi 'traceback|error|result' "$TMP/result-unwritable.out" && [ -z "$(ls -A "$SL")" ] \
  && good 'record errors do not change output or exit; attachment with no record exits 5' \
  || no "record write failure (holder $urc, attached $arc)" "$(cat "$TMP/result-unwritable.out" "$TMP/result-missing.out")"
# A holder killed without its EXIT trap (SIGKILL) keeps its owner file and writes no record: an attached run notices
# the dead holder, ends with exit 5 and says there is no record, without starting a suite.
reset_cache
HOLD_MARK="$TMP/killed-holder" bash "$TMP/cache-plan.sh" "$TMP/repo" --only-suites tests/a.sh --no-reuse > "$TMP/killed-holder.out" 2>&1 & kh=$!
slot_wait_for "$TMP/killed-holder"
cache_plan --only-suites tests/a.sh --no-reuse --attach > "$TMP/killed-attach.out" 2>&1 & ka=$!
slot_wait_for "$TMP/killed-attach.out" 'run-all: attaching to test slot 1'
kill -KILL "$kh"; wait "$kh" 2>/dev/null
for ((i=0; i<300; i++)); do kill -0 "$ka" 2>/dev/null || break; sleep 0.1; done
if kill -0 "$ka" 2>/dev/null; then
  kill "$ka" 2>/dev/null; wait "$ka" 2>/dev/null
  no '--attach to a killed holder ends' "$(cat "$TMP/killed-attach.out")"
else
  wait "$ka"; arc=$?
  [ "$arc" = 5 ] && grep -q 'no result record available' "$TMP/killed-attach.out" && [ -f "$SL/1/owner" ] \
    && [ ! -s "$RUN_LOG" ] && [ ! -d "$SL/2" ] \
    && good '--attach to a holder killed without its EXIT trap ends with exit 5 and no record' \
    || no "attach to killed holder (rc $arc)" "$(cat "$TMP/killed-attach.out")"
fi
rm -rf "$SL/1"
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
# --inline-only: --affected with an empty changed list. No suite and no gated script runs (each counts as not
# affected, affected.py is never asked), the inline checks still print, and it is a targeted run (no full-run record).
for j in 1 3; do
  reset_cache; : > "$TMP/aff-calls"
  out=$(AFF_CALLS="$TMP/aff-calls" NO_BASE=1 SELECT=tests/b.sh,tests/live.sh,scripts/checks/x.sh WITH_LIVE=1 WITH_WS=1 cache_plan --no-reuse -j "$j" --inline-only); rc=$?
  calls=$(tr '\n' ' ' < "$TMP/aff-calls"); log=$(cat "$RUN_LOG")
  [ "$rc" = 0 ] && [ -z "$log" ] && [ -z "$calls" ] && grep -q '^inline-only mode' <<<"$out" && ! grep -q 'no base' <<<"$out" \
    && grep -q '^PASS  block cheap' <<<"$out" && grep -qx 'counts 1 0 7' <<<"$out" && ! grep -q '^PASS  a\b' <<<"$out" \
    && [ ! -f "$TMP/state/run-all/$tree.json" ] && [ ! -d "$TMP/state/locks/run-all-full" ] && [ -z "$(ls -A "$SL")" ] \
    && good "--inline-only runs no suite, counts every suite and gated script as not affected, prints inline checks (-j $j)" \
    || no "--inline-only (-j $j): rc $rc log '$log' calls '$calls'" "$out"
done
conflicts_ok=true
for a in '--affected' '--base main' '--only-suites tests/a.sh' '--only-suites=tests/a.sh' '--release' '--workspace-only' '--list-suites' '--base main --affected'; do
  for order in 'before' 'after'; do
    # shellcheck disable=SC2086
    if [ "$order" = before ]; then out=$(cache_plan --inline-only $a 2>&1); rc=$?; else out=$(cache_plan $a --inline-only 2>&1); rc=$?; fi
    [ "$rc" = 2 ] && grep -q 'run-all: --inline-only conflicts with ' <<<"$out" && ! grep -q '^PASS' <<<"$out" || { conflicts_ok=false; no "--inline-only $a ($order) exits 2 (rc $rc)" "$out"; }
  done
done
$conflicts_ok && good '--inline-only conflicts with --affected, --base, --only-suites, --release, --workspace-only and --list-suites (exit 2, either order)'
mkdir -p "$SL/1"; printf '%s\n' "$$" > "$SL/1/pid"; printf 'another checkout\n' > "$SL/1/checkout"
out=$(RPG_FACTORY_TEST_SLOTS=1 cache_plan --inline-only --no-reuse --no-wait); rc=$?
[ "$rc" = 3 ] && grep -q 'run-all: waiting for a test slot (1 in use:' <<<"$out" && [ ! -d "$TMP/state/locks/run-all-full" ] \
  && good '--inline-only takes a test slot (busy slot: exit 3 with --no-wait) and no full-run lock' || no '--inline-only test slot' "$out"
rm -rf "$SL/1"
# Exit rule of an affected run with a base: a change that reaches no check (0 passed, 0 failed, every skip not affected)
# exits 6 (NOT_RUN: no evidence, never a pass) and says so in two lines after the summary; the result record's exit is 6
# and it writes no suite PASS record. A skip for another reason, a run without a base and --only-suites alone keep the
# old rule (0 passes exit 1); a run that reaches a suite exits on it.
NONE_LINE='run-all: nothing the change reaches: no check ran (not affected: 2)'
NOTRUN_LINE='run-all: exit 6 = NOT_RUN: no evidence; run without --base (or with --only-suites) for a verdict'
none_after_summary() { # out: the nothing-reached line appears once, after the summary line, the NOT_RUN line right after it
  local s n r
  s=$(grep -n '^run-all: [0-9]* checks, ' <<<"$1" | tail -1 | cut -d: -f1)
  n=$(grep -nxF "$NONE_LINE" <<<"$1" | cut -d: -f1)
  r=$(grep -nxF "$NOTRUN_LINE" <<<"$1" | cut -d: -f1)
  [ -n "$s" ] && [ -n "$n" ] && [ -n "$r" ] && [ "$(grep -cxF "$NONE_LINE" <<<"$1")" = 1 ] \
    && [ "$(grep -cxF "$NOTRUN_LINE" <<<"$1")" = 1 ] && [ "$n" -gt "$s" ] && [ "$r" = $((n + 1)) ]
}
no_suite_record() { [ "$(find "$TMP/state/run-all/suites" -type f 2>/dev/null | wc -l | tr -d ' ')" = 0 ]; }
for j in 1 3; do
  reset_cache
  out=$(SELECT=none cache_plan --no-reuse -j "$j" --affected --base main); rc=$?
  printed=$(last_result)
  [ "$rc" = 6 ] && [ -z "$(cat "$RUN_LOG")" ] && grep -qx 'counts 0 0 2' <<<"$out" && none_after_summary "$out" \
    && grep -qx 'run-all: 2 checks, 0 passed, 0 failed, 2 skipped (2 not affected by the change)' <<<"$out" && no_suite_record \
    && grep -qx 'exit: 6' <<<"$printed" \
    && good "--affected --base reaching no check exits 6 (NOT_RUN, record exit 6), nothing-reached and NOT_RUN lines after the summary (-j $j)" \
    || no "--affected reaching nothing (-j $j): rc $rc log '$(cat "$RUN_LOG")'" "$out"$'\n'"$printed"
  reset_cache
  out=$(WITH_SKIP=1 SELECT=none cache_plan --no-reuse -j "$j" --affected --base main); rc=$?
  [ "$rc" = 1 ] && grep -qx 'counts 0 0 3' <<<"$out" && grep -q '^SKIP  tool check (tool not on PATH)' <<<"$out" \
    && ! grep -q 'nothing the change reaches' <<<"$out" && no_suite_record \
    && good "--affected reaching no check with a skip for another reason still exits 1, no nothing-reached line (-j $j)" \
    || no "--affected reaching nothing plus a tool skip (-j $j): rc $rc" "$out"
  reset_cache
  out=$(cache_plan --no-reuse -j "$j" --affected --base main); rc=$?
  [ "$rc" = 0 ] && [ "$(cat "$RUN_LOG")" = b ] && grep -qx 'counts 1 0 1' <<<"$out" && ! grep -q 'nothing the change reaches' <<<"$out" \
    && good "--affected --base reaching a passing suite exits 0 without the nothing-reached line (-j $j)" \
    || no "--affected reaching a passing suite (-j $j): rc $rc" "$out"
  reset_cache
  out=$(BREAK_CASE=1 cache_plan --no-reuse -j "$j" --affected --base main); rc=$?
  [ "$rc" = 1 ] && grep -qx 'counts 0 1 1' <<<"$out" && ! grep -q 'nothing the change reaches' <<<"$out" && no_suite_record \
    && good "--affected --base reaching a failing suite exits 1 without the nothing-reached line (-j $j)" \
    || no "--affected reaching a failing suite (-j $j): rc $rc" "$out"
  # tests/never.sh is a listed suite whose run line is off (no WITH_NEVER): nothing runs, a and b are not affected
  reset_cache
  out=$(NO_BASE=1 cache_plan --no-reuse -j "$j" --affected --only-suites tests/never.sh); rc=$?
  [ "$rc" = 1 ] && [ -z "$(cat "$RUN_LOG")" ] && grep -qx 'counts 0 0 2' <<<"$out" && grep -q 'no base, running only --only-suites tests/never.sh' <<<"$out" \
    && ! grep -q 'nothing the change reaches' <<<"$out" \
    && good "--affected without a base and nothing passing keeps exit 1, no nothing-reached line (-j $j)" \
    || no "--affected no base, nothing passing (-j $j): rc $rc log '$(cat "$RUN_LOG")'" "$out"
  reset_cache
  out=$(cache_plan --no-reuse -j "$j" --only-suites tests/never.sh); rc=$?
  [ "$rc" = 1 ] && [ -z "$(cat "$RUN_LOG")" ] && grep -qx 'counts 0 0 2' <<<"$out" && ! grep -q 'nothing the change reaches' <<<"$out" \
    && good "--only-suites alone with nothing passing keeps exit 1, no nothing-reached line (-j $j)" \
    || no "--only-suites nothing passing (-j $j): rc $rc log '$(cat "$RUN_LOG")'" "$out"
done
# --within (task QA's scoped selection, with --affected --base): only the named suites and gated scripts run. A named suite
# the change reaches gets only its affected cases (as --affected passes them), one the change does not reach still runs
# with every case, what the change selects outside the list is left to CI (counted as not affected, named in one line
# before the checks). Same lines and counts at -j 1 and -j 3; affected.py is asked once.
for j in 1 3; do
  reset_cache; : > "$TMP/case-args"; : > "$TMP/aff-calls"
  out=$(AFF_CALLS="$TMP/aff-calls" CASE_LOG="$TMP/case-args" SELECT=tests/b.sh CASE_SELECT=alpha cache_plan --no-reuse -j "$j" --affected --base main --within tests/b.sh,tests/a.sh); rc=$?
  log=$(sort "$RUN_LOG" | tr '\n' ' '); calls=$(tr '\n' ' ' < "$TMP/aff-calls")
  first=$(grep -nE '^(PASS|SKIP|FAIL)' <<<"$out" | head -1 | cut -d: -f1); left=$(grep -nx 'left to CI: 0 suites' <<<"$out" | cut -d: -f1)
  [ "$rc" = 0 ] && [ "$log" = 'a b ' ] && [ "$(cat "$TMP/case-args")" = '--case alpha' ] && grep -q '^PASS  b (cases alpha)' <<<"$out" \
    && [ "$calls" = 'cases ' ] && grep -qx 'counts 2 0 0' <<<"$out" && [ -n "$left" ] && [ "$left" -lt "$first" ] \
    && good "--within: the reached named suite gets only its affected cases, the unreached named suite runs, one cases call, left-to-CI line first (-j $j)" \
    || no "--within cases (-j $j): rc $rc log '$log' calls '$calls' cases '$(cat "$TMP/case-args")'" "$out"
  reset_cache; : > "$TMP/case-args"
  out=$(CASE_LOG="$TMP/case-args" SELECT=tests/a.sh CASE_SELECT=alpha cache_plan --no-reuse -j "$j" --affected --base main --within tests/b.sh); rc=$?
  log=$(sort "$RUN_LOG" | tr '\n' ' ')
  [ "$rc" = 0 ] && [ "$log" = 'b ' ] && [ "$(wc -l < "$TMP/case-args" | tr -d ' ')" = 1 ] && [ -z "$(cat "$TMP/case-args")" ] && ! grep -q '(cases ' <<<"$out" \
    && grep -qx 'left to CI: 1 suites (tests/a.sh)' <<<"$out" && grep -qx 'counts 1 0 1' <<<"$out" \
    && good "--within: a named suite the change does not reach still runs, with every case; the selected one outside the list is left to CI (-j $j)" \
    || no "--within unreached (-j $j): rc $rc log '$log'" "$out"
  reset_cache
  out=$(WITH_NEVER=1 SELECT=tests/b.sh,tests/a.sh,tests/never.sh cache_plan --no-reuse -j "$j" --affected --base main --within tests/b.sh); rc=$?
  log=$(sort "$RUN_LOG" | tr '\n' ' ')
  [ "$rc" = 0 ] && [ "$log" = 'b ' ] && grep -qx 'left to CI: 2 suites (tests/a.sh, tests/never.sh)' <<<"$out" && grep -qx 'counts 1 0 2' <<<"$out" \
    && grep -q '(2 not affected by the change)' <<<"$out" \
    && good "--within: every selected suite outside the list is named and counted as not affected, none runs (-j $j)" \
    || no "--within left to CI (-j $j): rc $rc log '$log'" "$out"
  reset_cache
  out=$(NO_BASE=1 cache_plan --no-reuse -j "$j" --affected --base main --within tests/a.sh); rc=$?
  log=$(sort "$RUN_LOG" | tr '\n' ' ')
  [ "$rc" = 0 ] && [ "$log" = 'a ' ] && grep -qx 'affected mode: no base, running only --within tests/a.sh' <<<"$out" \
    && grep -q '^left to CI: no base' <<<"$out" && grep -qx 'counts 1 0 1' <<<"$out" \
    && good "--within without a base runs only the named suites and says so (-j $j)" || no "--within no base (-j $j): rc $rc log '$log'" "$out"
  # a gated script named in the list runs (block and inline), a live-lane suite the list does not name does not
  reset_cache
  out=$(WITH_LIVE=1 SELECT=tests/live.sh cache_plan --no-reuse -j "$j" --affected --base main --within=scripts/checks/x.sh); rc=$?
  log=$(sort "$RUN_LOG" | tr '\n' ' ')
  [ "$rc" = 0 ] && [ "$log" = 'block inline ' ] && grep -qx 'left to CI: 1 suites (tests/live.sh)' <<<"$out" && grep -qx 'counts 3 0 3' <<<"$out" \
    && good "--within=L runs a named gated script, leaves a selected live-lane suite to CI (-j $j)" || no "--within gated (-j $j): rc $rc log '$log'" "$out"
  # the repo-wide enforcement lines (WITHIN_GUARDS) also run under --within when the change reaches them, they are not
  # reported as left to CI, and a breach fails the run; unreached, or without a base, they do not run
  guards=scripts/checks/english-only.py,scripts/checks/portable-paths.py,scripts/checks/workspace-readers.sh
  reset_cache
  out=$(WITH_GUARDS=1 SELECT=$guards cache_plan --no-reuse -j "$j" --affected --base main --within tests/a.sh); rc=$?
  log=$(sort "$RUN_LOG" | tr '\n' ' ')
  [ "$rc" = 0 ] && [ "$log" = 'a english portable readers ' ] && grep -qx 'left to CI: 0 suites' <<<"$out" && grep -qx 'counts 4 0 1' <<<"$out" \
    && grep -q '^PASS  English-only enforcement' <<<"$out" && grep -q '^PASS  Portable-paths enforcement' <<<"$out" \
    && grep -q '^PASS  Workspace readers guard' <<<"$out" \
    && good "--within of an unrelated suite also runs all three enforcement lines the change reaches, not listed as left to CI (-j $j)" \
    || no "--within guards run (-j $j): rc $rc log '$log'" "$out"
  reset_cache
  out=$(PP_BREACH=1 WITH_GUARDS=1 SELECT=$guards cache_plan --no-reuse -j "$j" --affected --base main --within tests/a.sh); rc=$?
  log=$(sort "$RUN_LOG" | tr '\n' ' ')
  [ "$rc" != 0 ] && [ "$log" = 'a english portable readers ' ] && grep -q '^FAIL  Portable-paths enforcement' <<<"$out" \
    && grep -q '^PASS  English-only enforcement' <<<"$out" && grep -qx 'counts 3 1 1' <<<"$out" \
    && good "--within fails (FAIL line, rc != 0) on a planted portable-paths breach (-j $j)" \
    || no "--within guards breach (-j $j): rc $rc log '$log'" "$out"
  reset_cache
  out=$(RG_BREACH=1 WITH_GUARDS=1 SELECT=$guards cache_plan --no-reuse -j "$j" --affected --base main --within tests/a.sh); rc=$?
  log=$(sort "$RUN_LOG" | tr '\n' ' ')
  [ "$rc" != 0 ] && [ "$log" = 'a english portable readers ' ] && grep -q '^FAIL  Workspace readers guard' <<<"$out" \
    && grep -q '^PASS  English-only enforcement' <<<"$out" && grep -q '^PASS  Portable-paths enforcement' <<<"$out" \
    && grep -qx 'counts 3 1 1' <<<"$out" \
    && good "--within fails (FAIL line, rc != 0) on a planted raw jq reader breach in the workspace readers guard (-j $j)" \
    || no "--within readers breach (-j $j): rc $rc log '$log'" "$out"
  reset_cache
  out=$(WITH_GUARDS=1 SELECT=tests/b.sh cache_plan --no-reuse -j "$j" --affected --base main --within tests/a.sh); rc=$?
  log=$(sort "$RUN_LOG" | tr '\n' ' ')
  [ "$rc" = 0 ] && [ "$log" = 'a ' ] && grep -qx 'counts 1 0 4' <<<"$out" \
    && good "--within: an enforcement line the change does not reach does not run (-j $j)" || no "--within guards unreached (-j $j): rc $rc log '$log'" "$out"
  reset_cache
  out=$(NO_BASE=1 WITH_GUARDS=1 SELECT=$guards cache_plan --no-reuse -j "$j" --affected --base main --within tests/a.sh); rc=$?
  log=$(sort "$RUN_LOG" | tr '\n' ' ')
  [ "$rc" = 0 ] && [ "$log" = 'a ' ] && grep -qx 'counts 1 0 4' <<<"$out" \
    && good "--within without a base runs no enforcement line, only the named suites (-j $j)" || no "--within guards no base (-j $j): rc $rc log '$log'" "$out"
done
within_misuse() { # message args...
  local want=$1; shift
  reset_cache
  out=$(cache_plan "$@" 2>&1); rc=$?
  [ "$rc" = 2 ] && grep -q "^run-all: .*$want" <<<"$out" && [ ! -s "$RUN_LOG" ] && ! grep -q '^PASS ' <<<"$out" \
    && [ ! -d "$TMP/state/locks/run-all-full" ] && [ -z "$(ls -A "$SL" 2>/dev/null)" ] \
    && good "--within misuse exits 2: $*" || no "--within misuse (rc=$rc): $*" "$out"
}
for a in '--only-suites tests/a.sh' '--only-suites=tests/a.sh' '--only-cases alpha' '--inline-only' '--release' '--workspace-only' '--list-suites'; do
  # shellcheck disable=SC2086   # the option and its value are two words, or one with =
  within_misuse '--within conflicts with ' --within tests/a.sh --affected $a
  # shellcheck disable=SC2086
  within_misuse '--within conflicts with ' $a --affected --within tests/a.sh
done
within_misuse '--within requires --affected' --within tests/a.sh
within_misuse '--within requires --affected' --base main --within tests/a.sh
within_misuse '--within needs a list' --affected --within=
within_misuse '--within needs a list' --affected --within
within_misuse "unknown suite 'tests/unknown.sh'" --affected --base main --within tests/a.sh,tests/unknown.sh
within_misuse "unknown suite 'tests/orphan.sh'" --affected --base main --within tests/orphan.sh
within_misuse "release-only suite 'tests/installed-safety.sh' runs only with --release" --affected --base main --within tests/installed-safety.sh
out=$(cache_plan --help); rc=$?
[ "$rc" = 0 ] && grep -q -- '--within L' <<<"$out" && grep -q -- '--workspace-only \[--base REF\]' <<<"$out" && grep -q 'slowest' <<<"$out" \
  && good 'the usage text documents --within, --workspace-only --base and the slowest-checks lines' || no 'usage text for the new flags' "$out"
# --workspace-only --base: only the workspace checks the change reaches run (each gated like a suite; the `claude plugin
# validate` lines by the key claude-plugin-validate), the rest counts as not affected; no test slot. Without --base, or when
# no base is found, every workspace check runs.
ws_case() { # name want-log want-counts args... (the stand-in selection comes from the caller's SELECT / NO_BASE)
  local name=$1 wlog=$2 wcounts=$3 j; shift 3
  for j in 1 3; do
    reset_cache
    out=$(WITH_LIVE=1 WITH_WS=1 WITH_CLAUDE=1 cache_plan --no-reuse -j "$j" "$@"); rc=$?
    log=$(sort "$RUN_LOG" | tr '\n' ' ')
    [ "$rc" = 0 ] && [ "$log" = "$wlog" ] && grep -qx "counts $wcounts" <<<"$out" && [ ! -d "$TMP/state/locks/run-all-full" ] \
      && [ -z "$(ls -A "$SL" 2>/dev/null)" ] && good "workspace-only --base: $name (-j $j)" || no "workspace-only --base: $name (-j $j): rc $rc log '$log'" "$out"
  done
}
SELECT=none ws_case 'a change reaching no workspace input (docs only) runs none of the checks' '' '1 0 6' --workspace-only --base main
SELECT=tests/live.sh,tests/ws.sh ws_case 'only the reached checks run (routing-like inputs)' 'live ws ' '3 0 4' --workspace-only --base main
SELECT=claude-plugin-validate ws_case 'the claude validator runs on its own key' 'cv ' '2 0 5' --workspace-only --base main
SELECT=tests/live.sh,tests/blockrun.sh,tests/ws.sh,scripts/checks/x.sh,claude-plugin-validate ws_case 'a change reaching everything runs everything' 'block blockrun cv inline live ws ' '7 0 0' --workspace-only --base main
SELECT=none ws_case 'without --base every workspace check runs' 'block blockrun cv inline live ws ' '7 0 0' --workspace-only
SELECT=none NO_BASE=1 ws_case 'no base found: every workspace check runs' 'block blockrun cv inline live ws ' '7 0 0' --workspace-only --base main
reset_cache
out=$(WITH_LIVE=1 WITH_WS=1 WITH_CLAUDE=1 SELECT=none cache_plan --no-reuse --workspace-only --release --base main 2>&1); rc=$?
[ "$rc" = 2 ] && grep -q 'conflicts with --no-workspace and --release' <<<"$out" && [ ! -s "$RUN_LOG" ] \
  && good '--workspace-only --base still conflicts with --release' || no '--workspace-only --base --release' "$out"
# a scoped workspace run takes no test slot: it runs with the only slot held by another run
reset_cache; mkdir -p "$SL/1"; printf '%s\n' "$$" > "$SL/1/pid"; printf 'another checkout\n' > "$SL/1/checkout"
out=$(RPG_FACTORY_TEST_SLOTS=1 WITH_LIVE=1 SELECT=tests/live.sh cache_plan --no-reuse --no-wait --workspace-only --base main); rc=$?
[ "$rc" = 0 ] && [ "$(sort "$RUN_LOG" | tr '\n' ' ')" = 'live ' ] && ! grep -q 'waiting for a test slot' <<<"$out" \
  && good '--workspace-only --base takes no test slot (the only slot is held by another run)' || no '--workspace-only --base admission' "$out"
rm -rf "$SL/1"
# per-check durations: the result record lists one {name, seconds, status} per check in run order (-j 1 and -j 3 alike;
# a block is one entry, the lines inside it are not), and the summary tail names the slowest checks, longest first
for j in 1 3; do
  reset_cache
  out=$(WITH_DUR=1 WITH_LIVE=1 SLOWEST=1 cache_plan --no-reuse -j "$j"); rc=$?
  rec=$(ls -t "$TMP/state/run-all/results"/*/*.json 2>/dev/null | head -1)
  checked=$(python3 -B - "$rec" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], encoding='utf-8'))
d = r['durations']
assert all(sorted(x) == ['name', 'seconds', 'status'] and type(x['seconds']) is int and x['seconds'] >= 0 for x in d), d
names = [x['name'] for x in d]
assert names == ['a', 'b', 'd0', 'd3', 'd2', 'dfail', 'dskip', 'live', 'block gated_block'], names
by = {x['name']: x for x in d}
assert [x['status'] for x in d] == ['pass'] * 5 + ['fail', 'skip', 'pass', 'pass'], d
assert by['d3']['seconds'] >= 3 and by['d2']['seconds'] >= 2, by   # sleeps are lower bounds; a loaded host only adds
print('durations valid')
PY
  ); crc=$?
  tail_lines=$(grep -A5 '^slowest checks:$' <<<"$out" | tail -n +2 | sed -E -n 's/^  ([0-9]+)s  .*/\1/p')   # the five seconds, as printed
  [ "$rc" = 1 ] && [ "$crc" = 0 ] && [ "$checked" = 'durations valid' ] \
    && [ "$(wc -l <<<"$tail_lines" | tr -d ' ')" = 5 ] && [ "$tail_lines" = "$(sort -nr <<<"$tail_lines")" ] \
    && good "result record holds per-check durations in run order, the summary names the slowest first (-j $j)" \
    || no "durations (-j $j): rc $rc record check $crc '$checked'" "$out"
done
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
early_records=$(find "$TMP/state/run-all/results" -type f -name '*.json' 2>/dev/null | wc -l | tr -d ' ')
cache_plan >/dev/null; TMPDIR="$CT" cache_plan --reuse >/dev/null; r3=$?
mkdir -p "$TMP/state/locks/run-all-full"; printf '%s
' "$$" > "$TMP/state/locks/run-all-full/pid"
TMPDIR="$CT" cache_plan --no-reuse --no-wait >/dev/null; r4=$?; rm -rf "$TMP/state/locks/run-all-full"
left=$(ls -A "$CT")
[ "$early_records" = 0 ] && [ "$(find "$TMP/state/run-all/results" -type f -name '*.json' | wc -l)" -eq 1 ] \
  && good 'usage errors, list, reuse hits and no-wait exits publish no result record' || no 'early-exit result records'
[ "$r1 $r2 $r3 $r4" = '0 2 0 3' ] && [ "$args" = '2 2 2 2 2 ' ] && [ -z "$left" ]   && good 'early exits (--list-suites, unknown suite, bad arguments, release-only suite, --reuse hit, --no-wait) leave no git-config copy'   || no "early-exit temp files (rc $r1 $r2 $r3 $r4, arguments $args)" "$left"
# A shared-config WARN is counted, the copy is removed on WARN and kept on FAIL, and a passing suite's RETRY lines are
# shown under its PASS line. End to end: the stand-in plan sources the real scheduler and ends with the real tail of
# tests/run-all.sh (shared-config verdict, summary line, exit status), in a throwaway repo (never the real shared config).
tail_src=$(sed -n '/^# ---- the shared git config (common dir) must be byte-identical/,$p' "$ROOT/tests/run-all.sh")
{ cat <<'PLAN'
fixture=$1; shift
. "$ROOT_UNDER_TEST/tests/run-all.sh" "$@"
ROOT=$fixture; cd "$ROOT" || exit 1
runall_prepare; rc=$?
[ "$rc" = 0 ] || exit "$rc"
run w bash tests/w.sh
run r bash tests/r.sh
drain
[ -z "$QD" ] || rm -rf "$QD"
PLAN
  printf '%s\n' "$tail_src"; } > "$TMP/warn-plan.sh"
WF="$TMP/warnrepo"; CT2="$TMP/warntmp"
warn_fixture() { # a fresh repo per case: a second [branch "x"] section in the same config would be a FAIL
  rm -rf "$WF"; mkdir -p "$WF/scripts/lib" "$WF/tests" "$WF/testlab"
  cp "$ROOT/scripts/lib/fstate.py" "$WF/scripts/lib/"
  cat > "$WF/tests/w.sh" <<'SUITE'
#!/usr/bin/env bash
cfg="$(git rev-parse --path-format=absolute --git-common-dir)/config"
case "${CFG_MODE:-}" in
  warn) printf '[branch "x"]\n\tremote = origin\n' >> "$cfg" ;;
  fail) git config rpgtest.during changed ;;
esac
[ -z "${RETRY_LINES:-}" ] || printf 'RETRY git status: empty guard output (first try rc=7)\nRETRY second\n'
echo "w done"
SUITE
  printf '#!/usr/bin/env bash\necho "r done"\n' > "$WF/tests/r.sh"
  git -C "$WF" init -q
}
wrun() { # jobs [VAR=value...]: sets out, rc and leaves the temp dir listing in $left
  local j=$1; shift
  warn_fixture; reset_cache; rm -rf "$CT2"; mkdir -p "$CT2"
  out=$(env "$@" TMPDIR="$CT2" ROOT_UNDER_TEST="$ROOT" RUNALL_SUITES_FROM="$TMP/warn-plan.sh" \
    bash "$TMP/warn-plan.sh" "$WF" -j "$j" --only-suites tests/w.sh,tests/r.sh 2>&1); rc=$?
  left=$(ls -A "$CT2")
}
if [ -n "$tail_src" ] && grep -q 'gitcfg_verify' <<<"$tail_src" && grep -qx 'runall_summary' <<<"$tail_src"; then
  for j in 1 2; do
    wrun "$j" CFG_MODE=warn
    [ "$rc" = 0 ] && grep -q "^WARN  shared git config: only other sessions' branch/worktree sections were added" <<<"$out" \
      && grep -q '^      +\[branch "x"\]' <<<"$out" \
      && grep -q '^run-all: 2 checks, 2 passed, 0 failed, 0 skipped, 1 warned' <<<"$out" \
      && ! grep -q '^FAIL' <<<"$out" && [ -z "$left" ] \
      && good "shared-config WARN is counted in the summary, exit 0, the config copy is removed (-j $j)" \
      || no "config WARN (-j $j, rc=$rc, left='$left')" "$out"
  done
  wrun 1
  [ "$rc" = 0 ] && grep -q '^PASS  shared git config unchanged during the run' <<<"$out" \
    && grep -q '^run-all: 3 checks, 3 passed, 0 failed, 0 skipped' <<<"$out" && ! grep -q 'warned' <<<"$out" \
    && ! grep -q '^WARN' <<<"$out" && [ -z "$left" ] \
    && good "an unchanged shared config adds no warned count and leaves no copy" || no "unchanged config (rc=$rc, left='$left')" "$out"
  wrun 1 CFG_MODE=fail
  copy=$(sed -n 's/.*(copy from before the run: \(.*\))$/\1/p' <<<"$out")
  [ "$rc" = 1 ] && grep -q '^FAIL  shared git config changed during the run' <<<"$out" && ! grep -q 'warned' <<<"$out" \
    && [ -n "$copy" ] && [ -f "$copy" ] && [ -n "$left" ] \
    && good "a shared-config FAIL keeps the copy its message names and exits 1" || no "config FAIL (rc=$rc, copy='$copy', left='$left')" "$out"
  rm -rf "$CT2"
  # RETRY lines of a passing suite: under its PASS line, in order, no failure, the suite PASS records still published
  want_retry='PASS  w
      RETRY git status: empty guard output (first try rc=7)
      RETRY second
PASS  r'
  for j in 1 2; do
    wrun "$j" RETRY_LINES=1
    got=$(sed -E 's/ \[[0-9]+s\]$//' <<<"$out" | grep -A3 '^PASS  w$')
    published=$(find "$TMP/state/run-all/suites" -type f 2>/dev/null | wc -l | tr -d ' ')
    [ "$rc" = 0 ] && [ "$got" = "$want_retry" ] && grep -q '^run-all: 3 checks, 3 passed, 0 failed, 0 skipped' <<<"$out" \
      && ! grep -q '^FAIL' <<<"$out" && [ "$published" = 2 ] \
      && good "RETRY lines of a passing suite are shown under its PASS line, not counted, records published (-j $j)" \
      || no "RETRY lines (-j $j, rc=$rc, published=$published)" "$got"$'\n----\n'"$out"
  done
  wrun 1
  ! grep -q 'RETRY' <<<"$out" && good "no RETRY line is shown when the suite printed none" || no "stray RETRY line" "$out"
else no "the tail of tests/run-all.sh (shared-config verdict, summary) was not found for the stand-in plan" "$tail_src"; fi
# gitcfg_snapshot: a copy that cannot be filled (cp fails) is removed at once and not recorded; the hash still is
GC="$TMP/gc-repo"; GT="$TMP/gc-tmp"; mkdir -p "$GT"; git init -q "$GC" 2>/dev/null
cat > "$TMP/gc-snap.sh" <<'PLAN'
. "$ROOT_UNDER_TEST/scripts/lib/gitcfg-guard.sh"
cp() { return 1; }
gitcfg_snapshot "$GC_REPO"
echo "copy=[${GITCFG_COPY:-}] file=[${GITCFG_FILE:+set}] hash=[${GITCFG_HASH:+set}]"
gitcfg_verify >/dev/null && echo "verify=ok"
PLAN
out=$(ROOT_UNDER_TEST="$ROOT" GC_REPO="$GC" TMPDIR="$GT" bash "$TMP/gc-snap.sh" 2>&1); rc=$?
left=$(find "$GT" -type f 2>/dev/null | wc -l | tr -d ' ')
[ "$rc" = 0 ] && grep -qx 'copy=\[\] file=\[set\] hash=\[set\]' <<<"$out" && grep -qx 'verify=ok' <<<"$out" && [ "$left" = 0 ] \
  && good 'gitcfg_snapshot removes a config copy that could not be filled, keeps the hash, leaves no temp file' \
  || no "gitcfg_snapshot with a failing cp (rc=$rc, temp files left=$left)" "$out"
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
