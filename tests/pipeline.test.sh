#!/usr/bin/env bash
# factory-pipeline.py on a throwaway workspace (a server repo and a Unity client project): tiers, plan validation
# (ownership, cycles, cross-model review, the no-worktree rule for Unity projects, exclusive resources), dispatch
# commands for Orca and the Agent fallback, verdicts and the READY_FOR_PR gate. Never touches the real workspace.
# case-map: dogfood tests/dogfood.sh tests/dogfood/*
# case-map: model-routing docs/registry.schema.json docs/schemas/kinds/* docs/schemas/pipeline-subplan.schema.json scripts/check-registry.sh
# case-map: recorded-implementer docs/registry.schema.json docs/schemas/kinds/* docs/schemas/pipeline-subplan.schema.json scripts/check-registry.sh
# case-map: model-policy docs/schemas/pipeline-subplan.schema.json
# case-map: subplan docs/schemas/pipeline-subplan.schema.json
# case-map: status docs/schemas/pipeline-status.schema.json
# case-map: cleanup docs/schemas/pipeline-status.schema.json
# case-map: settled-workers docs/schemas/pipeline-status.schema.json
# Measured with sys.monitoring and an audit hook over a full run: factory-pipeline.py, registry.json, the plan schema,
# model_policy.py, orca_cmd.py and plan_paths.py run in every case, and pipeline_route.py and fstate.py in 17 of 20, so
# they have no map: ALL is the safe fallback for them (and for any file not listed).
set -uo pipefail
CASES='validate subplan dispatch model-policy child-dispatch tier verdict-gate cleanup settled-workers orca-first review-findings tier-plugin status owned-case dogfood recorded-implementer cleanup-merged gate-merge model-routing multiwave qa-tiers tier-xs cli-selftest'
usage() {
  printf '%s\n' 'Usage: pipeline.test.sh [--case NAMES | --only NAMES] [--list-cases] [-h|--help]' \
    'NAMES is a comma-separated list; selectors may be repeated. No selector runs every case.' \
    'Prerequisite cases run automatically; dependencies are documented beside case_deps below.' \
    'Independent units (the dependency chain, status, recorded-implementer, ...) run as parallel child runs; PIPELINE_TEST_UNITS'     'sets how many at once (default 4). PIPELINE_TEST_TIMES=1 prints section wall times; PIPELINE_TEST_JOBS sets the'     'background case limit (default 4); PIPELINE_TEST_MATCH=check compares the bash matcher with grep -E.'
}
SELECTED=; list_cases=0
# one selector value (the argument of --case/--only) is validated as it is parsed, before the commas become spaces: an
# empty or whitespace-only value and an empty name inside the list (leading, trailing or doubled comma, `tier,,status`,
# `,tier`, `tier,`, `tier, ,status`) are usage errors, never silently dropped and never "run everything"
add_selector() {
  local compact="${1//[[:space:]]/}"
  case "$compact" in
    ''|,*|*,|*,,*) printf 'Empty case name in selector: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  SELECTED+=" ${1//,/ }"
}
while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --list-cases) list_cases=1; shift ;;
    --case|--only)
      [ "$#" -ge 2 ] || { usage >&2; exit 2; }
      add_selector "$2"; shift 2 ;;
    --case=*|--only=*) add_selector "${1#*=}"; shift ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done
# Validate before sourcing helpers or creating any fixture (also with --list-cases).
unique_selected=
for selected in $SELECTED; do
  [[ " $CASES " == *" $selected "* ]] || { printf 'Unknown case: %s\n' "$selected" >&2; exit 2; }
  [[ " $unique_selected " == *" $selected "* ]] || unique_selected+=" $selected"
done
SELECTED="$unique_selected"
if [ "$list_cases" = 1 ]; then printf '%s\n' $CASES; exit 0; fi
[ -n "$SELECTED" ] || SELECTED="$CASES"
case_deps() {
  case "$1" in
    subplan) echo validate ;;                      # OK/TOOL plans
    dispatch) echo subplan ;;                      # EX/SPC plans and reg-nowt
    model-policy) echo dispatch ;;                 # existing demo-gw worktree and subplans
    child-dispatch) echo dispatch ;;               # WT and SPC; removes demo-gw afterwards
    verdict-gate) echo child-dispatch ;;           # demo-gw must have been removed
    cleanup) echo verdict-gate ;;                  # integrated SG/G candidate and its verdicts
    settled-workers) echo cleanup ;;              # G and persisted dispatch specs
    orca-first) echo settled-workers ;;            # fake Orca and integration children to remove
    review-findings) echo orca-first tier ;;       # integration branches of the chain above, and the ctx helper of tier
  esac
}
# Expand to a fixed point so even the last requested case brings all of its setup.
pending="$SELECTED"
while [ -n "$pending" ]; do
  next_pending=
  for selected in $pending; do
    for dependency in $(case_deps "$selected"); do
      if [[ " $SELECTED " != *" $dependency "* ]]; then SELECTED+=" $dependency"; next_pending+=" $dependency"; fi
    done
  done
  pending="$next_pending"
done
has_case() { [[ " $SELECTED " == *" $1 "* ]]; }
case_start() { CASE_START="$EPOCHREALTIME"; }
case_end() {
  if [ "${PIPELINE_TEST_TIMES:-0}" = 1 ]; then
    local now="$EPOCHREALTIME" elapsed
    elapsed=$(( ${now/./} - ${CASE_START/./} ))
    printf 'TIME  %s %d.%03ds\n' "$1" "$((elapsed / 1000000))" "$((elapsed / 1000 % 1000))"
  fi
}
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
P="$ROOT/scripts/factory-pipeline.py"
# Units: groups of cases that need no state of any other unit. With more than one unit selected the suite re-runs
# itself once per unit (up to PIPELINE_TEST_UNITS at once, default 4), then prints the outputs in this order and
# adds the counts; a child (PIPELINE_TEST_UNIT set) runs its own cases inline. The chain is the longest unit, first.
UNITS='chain status recorded-implementer dogfood cleanup-merged gate-merge owned-case tier-plugin model-routing multiwave qa-tiers tier-xs cli-selftest'
unit_cases() {
  case "$1" in
    chain) echo 'validate subplan dispatch model-policy child-dispatch tier verdict-gate cleanup settled-workers orca-first review-findings' ;;
    *) echo "$1" ;;
  esac
}
if [ -z "${PIPELINE_TEST_UNIT:-}" ]; then
  chosen=()
  for u in $UNITS; do
    mine=
    for c in $(unit_cases "$u"); do has_case "$c" && mine+="${mine:+,}$c"; done
    [ -z "$mine" ] || chosen+=("$u=$mine")
  done
  # selection only (cli-selftest): print what would run, run nothing and build no fixture
  if [ "${PIPELINE_SELFTEST_CHILD:-}" = select ]; then
    printf 'selected:%s
units:%s
' "${SELECTED# }" "${chosen[*]}"; exit 0
  fi
  if [ "${#chosen[@]}" -gt 1 ]; then
    OUTD="$(mktemp_win)" || exit 1; trap 'wait; rm -rf "$OUTD"' EXIT
    running=0
    for entry in "${chosen[@]}"; do
      [ "$running" -lt "${PIPELINE_TEST_UNITS:-4}" ] || { wait -n; running=$((running - 1)); }
      ( PIPELINE_TEST_UNIT="${entry%%=*}" bash "${BASH_SOURCE[0]}" --case "${entry#*=}" > "$OUTD/${entry%%=*}.out" 2>&1
        echo "$?" > "$OUTD/${entry%%=*}.rc" ) &
      running=$((running + 1))
    done
    wait
    run=0; passed=0; failed=0; reused_total=0; bad=0
    for entry in "${chosen[@]}"; do
      u="${entry%%=*}"
      grep -vE '^(pipeline tests: |capture once: )' "$OUTD/$u.out"
      sum=$(grep -E '^pipeline tests: [0-9]+ run, [0-9]+ passed, [0-9]+ failed' "$OUTD/$u.out" | tail -n 1)
      if [[ $sum =~ ^pipeline\ tests:\ ([0-9]+)\ run,\ ([0-9]+)\ passed,\ ([0-9]+)\ failed ]]; then
        run=$((run + BASH_REMATCH[1])); passed=$((passed + BASH_REMATCH[2])); failed=$((failed + BASH_REMATCH[3]))
      else bad=1; echo "FAIL  unit $u printed no summary"; fi
      [ "$(cat "$OUTD/$u.rc" 2>/dev/null)" = 0 ] || bad=1
      if [[ $(grep -E '^capture once: ' "$OUTD/$u.out") =~ ^capture\ once:\ ([0-9]+) ]]; then reused_total=$((reused_total + BASH_REMATCH[1])); fi
    done
    [ "$reused_total" = 0 ] || echo "capture once: $reused_total assertion(s) reused the output of the identical command before them"
    echo "pipeline tests: $run run, $passed passed, $failed failed"
    [ "$run" -gt 0 ] && [ "$failed" -eq 0 ] && [ "$bad" = 0 ]
    exit
  fi
fi
# The case selection itself (its own unit: it needs no fixture). --help exits 0, an unknown argument, an unknown case or
# an empty selector exits 2 before any run, --list-cases lists every case, and the selection itself (the case list and the
# units, printed by PIPELINE_SELFTEST_CHILD=select without running any) is deduplicated and narrow: no child suite run.
if [ "${SELECTED// /}" = cli-selftest ]; then
  self="${BASH_SOURCE[0]}"; spass=0; sfail=0
  sok() { spass=$((spass + 1)); echo "PASS  $1"; }
  sno() { sfail=$((sfail + 1)); echo "FAIL  $1"; }
  bash "$self" --help >/dev/null 2>&1 && sok "--help exits 0" || sno "--help did not exit 0"
  bash "$self" --no-such-option >/dev/null 2>&1; rc=$?
  [ "$rc" -eq 2 ] && sok "unknown argument exits 2" || sno "unknown argument exited $rc, want 2"
  bash "$self" --case no-such-case >/dev/null 2>&1; rc=$?
  [ "$rc" -eq 2 ] && sok "unknown case exits 2" || sno "unknown case exited $rc, want 2"
  for sel in ',' '' ' , '; do
    bash "$self" --case "$sel" >/dev/null 2>&1; rc=$?
    [ "$rc" -eq 2 ] && sok "empty selector '$sel' exits 2 and runs nothing" || sno "empty selector '$sel' exited $rc, want 2"
  done
  # an empty name inside a list or among repeated selectors is a usage error too, before any run: the selection (child mode
  # select, which would print "selected:...") must not even be reached
  for args in '--case|tier,,status' '--case|tier|--case|,' '--case|,tier' '--case|tier,' '--only=tier,' '--case|tier, ,status' '--case=,tier' '--case|tier|--only|'; do
    IFS='|' read -ra eargs <<<"$args"
    out=$(PIPELINE_TEST_UNIT= PIPELINE_SELFTEST_CHILD=select bash "$self" "${eargs[@]}" 2>&1); rc=$?
    if [ "$rc" -eq 2 ] && ! grep -q '^selected:' <<<"$out"; then sok "empty case name in '${args//|/ }' exits 2 and runs nothing"
    else sno "empty case name in '${args//|/ }' rc=$rc, want 2: $(head -c 200 <<<"$out")"; fi
  done
  listed=$(bash "$self" --list-cases 2>&1); rc=$?
  want=$(printf '%s
' $CASES)
  [ "$rc" -eq 0 ] && [ "$listed" = "$want" ] && sok "--list-cases exits 0 and lists the $(wc -w <<<"$CASES") cases" || sno "--list-cases rc=$rc, listed: $(head -c 200 <<<"$listed")"
  # --help prints the usage and runs nothing: no fixture (TMPDIR stays empty), no case, no summary line
  helpdir=$(mktemp -d "${TMPDIR:-/tmp}/pt-help.XXXXXX") && helpout=$(TMPDIR="$helpdir" bash "$self" --help 2>&1); rc=$?
  if [ "$rc" -eq 0 ] && grep -q '^Usage: pipeline.test.sh' <<<"$helpout" && ! grep -qE '^(PASS|FAIL|-- |pipeline tests: )' <<<"$helpout"      && [ -z "$(ls -A "$helpdir")" ]; then sok "--help prints the usage only: no fixture, no case run"
  else sno "--help rc=$rc, fixture dir: $(ls -A "$helpdir" | head -c 100), output: $(head -c 200 <<<"$helpout")"; fi
  rm -rf "$helpdir"
  # the selection (PIPELINE_SELFTEST_CHILD=select prints it and exits before any unit runs): one case runs once, a repeated
  # or comma-listed duplicate selector selects it once, a dependent case brings its prerequisites in order, and a
  # one-case selection is one unit, not the full run
  sel() { PIPELINE_TEST_UNIT= PIPELINE_SELFTEST_CHILD=select bash "$self" "$@" 2>&1; }
  for form in comma repeated; do
    if [ "$form" = comma ]; then args=(--case cli-selftest,cli-selftest)
    else args=(--case cli-selftest --only cli-selftest); fi
    duplicate=$(sel "${args[@]}"); rc=$?
    if [ "$rc" -eq 0 ] && [ "$duplicate" = $'selected:cli-selftest
units:cli-selftest=cli-selftest' ]; then sok "$form duplicate selector selects cli-selftest once"
    else sno "$form duplicate selector rc=$rc, selection: $(head -c 200 <<<"$duplicate")"; fi
  done
  one=$(sel --case tier); rc=$?
  if [ "$rc" -eq 0 ] && [ "$one" = $'selected:tier
units:chain=tier' ]; then sok "--case tier selects one case in one unit, not the full run"
  else sno "--case tier rc=$rc, selection: $(head -c 200 <<<"$one")"; fi
  # a comma list of non-empty names still selects each of them (whitespace around a comma is fine)
  for list in 'tier,status' 'tier, status'; do
    two=$(sel --case "$list"); rc=$?
    if [ "$rc" -eq 0 ] && [ "$two" = $'selected:tier status
units:chain=tier status=status' ]; then sok "--case '$list' selects both cases in their units"
    else sno "--case '$list' rc=$rc, selection: $(head -c 200 <<<"$two")"; fi
  done
  dep=$(sel --case subplan --only subplan); rc=$?
  if [ "$rc" -eq 0 ] && [ "$dep" = $'selected:subplan validate
units:chain=validate,subplan' ]; then sok "--case subplan brings its prerequisite validate once"
  else sno "--case subplan rc=$rc, selection: $(head -c 200 <<<"$dep")"; fi
  all=$(sel); rc=$?
  if [ "$rc" -eq 0 ] && [ "$(sed -n 's/^selected://p' <<<"$all")" = "$CASES" ]; then sok "no selector selects every case"
  else sno "no selector rc=$rc, selection: $(head -c 200 <<<"$all")"; fi
  total=$((spass + sfail)); echo "pipeline tests: $total run, $spass passed, $sfail failed"
  [ "$sfail" -eq 0 ]; exit
fi
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'wait; rm -rf "$TMP"' EXIT
export RPG_FACTORY_AGENTS=claude,codex
export RPG_FACTORY_STATE_DIR="$TMP/state" TMPDIR="$TMP" RPG_FACTORY_WORKSPACE="$TMP/ws"
# hermetic inside an Orca terminal: no ORCA_* variable, so the default runner is print and --runner agent is allowed
# (the Orca-first cases below set them on purpose)
for v in $(compgen -e | grep '^ORCA_'); do unset "$v"; done
# no real process listing either: cleanup and status read RPG_FACTORY_PROCESS_TABLE (a JSON list; the cases that name
# processes point it at their own fixture)
echo '[]' > "$TMP/proc-none.json"; export RPG_FACTORY_PROCESS_TABLE="$TMP/proc-none.json"
WS="$TMP/ws"; S="$WS/rpg-mmo-server"; C="$WS/IndieRPGMMOAdventure"; T="$TMP/tool"
pass=0; fail=0
# Capture once: consecutive assertions on one command (same arguments, directory, PATH and env prefix, no other
# top-level command in between) share one run of factory-pipeline.py. The DEBUG trap (top level only: functions and
# subshells do not inherit it) drops the capture before every other command - git, a verdict, a file edit, a plan.
# verdict, agents and a dispatch without --runner print always run (they write state). PIPELINE_TEST_REUSE=0 runs every assertion's command;
# PIPELINE_TEST_REUSE=check also re-runs each reused command and fails the case when its output or exit code differs.
REUSE="${PIPELINE_TEST_REUSE:-1}"; MEMO_KEY=; MEMO_ENV=(); MEMO_OUT=; MEMO_RC=0; MEMO_SPEC=; MEMO_SRC=; reused=0
memo_trap() {
  local c="$BASH_COMMAND" names=()
  while [[ $c =~ ^([A-Za-z_][A-Za-z_0-9]*)=(\"[^\"]*\"|\'[^\']*\'|[^ ]*)\ +(.*)$ ]]; do
    names+=("${BASH_REMATCH[1]}"); c="${BASH_REMATCH[3]}"
  done
  case "${c%% *}" in expect|refute|expect_spec|refute_spec|opath|oref|inorca|st_phase|agree|for) MEMO_ENV=("${names[@]}") ;; *) MEMO_KEY= ;; esac
}
[ "$REUSE" = 0 ] || trap memo_trap DEBUG
# pp <args...>: OUT and RC of `factory-pipeline.py <args>` (stdout and stderr), reused per the capture-once rule
pp() {
  local IFS=$'\x1f' key n env=
  for n in "${MEMO_ENV[@]}"; do env+="$n=${!n-}$IFS"; done
  key="$PWD$IFS$PATH$IFS${ORCA_WORKTREE_ID-}$IFS$env$IFS$*"
  if [ "$REUSE" != 0 ] && [ "$key" = "$MEMO_KEY" ] && [[ "$IFS$*$IFS" != *"${IFS}verdict$IFS"* && "$IFS$*$IFS" != *"${IFS}agents$IFS"* ]]      && { [[ "$IFS$*$IFS" != *"${IFS}dispatch$IFS"* ]] || [[ "$IFS$*$IFS" == *"${IFS}--runner${IFS}print$IFS"* ]]; }; then
    OUT="$MEMO_OUT"; RC="$MEMO_RC"; reused=$((reused + 1))
    if [ "$REUSE" = check ]; then
      local fresh rc; fresh=$(python3 -B "$P" "$@" 2>&1); rc=$?
      [ "$fresh" = "$OUT" ] && [ "$rc" = "$RC" ] || { fail=$((fail + 1)); echo "FAIL  capture once: a rerun of '$*' differs"; }
    fi
    return
  fi
  python3 -B "$P" "$@" > "$TMP/pp.out" 2>&1; RC=$?; OUT=$(<"$TMP/pp.out")  # no subshell: a fork costs most on Windows
  MEMO_KEY="$key"; MEMO_OUT="$OUT"; MEMO_RC="$RC"; MEMO_SPEC=; MEMO_SRC=
}
# pp_spec <args...>: pp, then SPEC and SRC: the persisted Orca spec the one-line prompt names (and the read's exit code).
# Only the last line that carries the prompt (`--prompt ` or `--spec ` with `Read your task spec at`) is split: OUT also
# holds stderr, and a quote character in a stderr line must not break the parse.
pp_spec() {
  pp "$@"
  if [ -z "$MEMO_SRC" ] || [ "$REUSE" = check ]; then
    MEMO_SPEC=$(python3 -c 'import pathlib,shlex,sys
lines=[l for l in sys.argv[1].splitlines() if ("--prompt " in l or "--spec " in l) and "Read your task spec at " in l]
args=shlex.split(lines[-1]); flag="--prompt" if "--prompt" in args else "--spec"
prompt=args[args.index(flag)+1]
assert prompt.startswith("Read your task spec at ") and prompt.endswith(" and follow it.")
print(pathlib.Path(prompt[len("Read your task spec at "):-len(" and follow it.")]).read_text(encoding="utf-8"))' "$OUT" 2>&1); MEMO_SRC=$?
  fi
  SPEC="$MEMO_SPEC"; SRC="$MEMO_SRC"
}
# has_ere <text> <ere>: grep -qE on the text without a process (bash regex per line; a fork costs most on Windows).
# PIPELINE_TEST_MATCH=check also runs grep and fails on any difference between the two.
CR=$'\r'
has_ere() {
  local line found=1
  while IFS= read -r line; do line=${line%"$CR"}; [[ $line =~ $2 ]] && { found=0; break; }; done <<<"$1"
  if [ "${PIPELINE_TEST_MATCH:-}" = check ]; then
    local g=1; grep -qE -- "$2" <<<"$1" && g=0
    [ "$g" = "$found" ] || { fail=$((fail + 1)); echo "FAIL  matcher differs from grep -E for '$2' (bash $found, grep $g)"; }
  fi
  return "$found"
}
# expect <name> <rc> <grep-regex|-> <args...>: exit code and (optionally) a line of the combined output
expect() {
  local name="$1" want="$2" pat="$3"; shift 3
  local out rc; pp "$@"; out="$OUT"; rc="$RC"
  if [ "$rc" = "$want" ] && { [ "$pat" = - ] || has_ere "$out" "$pat"; }; then pass=$((pass + 1)); echo "PASS  $name"
  else fail=$((fail + 1)); echo "FAIL  $name (rc=$rc, want $want, pattern '$pat')"; sed 's/^/      /' <<<"$out" | head -30; fi
}
# refute <name> <grep-regex> <args...>: the output must NOT contain the pattern (exit code ignored)
refute() {
  local name="$1" pat="$2"; shift 2
  local out; pp "$@"; out="$OUT"
  if has_ere "$out" "$pat"; then fail=$((fail + 1)); echo "FAIL  $name (found '$pat')"; sed 's/^/      /' <<<"$out" | head -20
  else pass=$((pass + 1)); echo "PASS  $name"; fi
}
# Match a rule in the persisted Orca spec, rather than the one-line launch prompt.
expect_spec() {
  local name="$1" pat="$2"; shift 2
  local rc spec
  pp_spec "$@"; rc="$RC"; spec="$SPEC"
  if [ "$rc" = 0 ] && has_ere "$spec" "$pat"; then pass=$((pass + 1)); echo "PASS  $name"
  else fail=$((fail + 1)); echo "FAIL  $name (rc=$rc, pattern '$pat')"; head -20 <<<"$spec"; fi
}
# refute_spec <name> <grep-regex> <args...>: the persisted Orca spec must NOT contain the pattern (exit 0, spec read)
refute_spec() {
  local name="$1" pat="$2"; shift 2
  local rc spec src
  pp_spec "$@"; rc="$RC"; spec="$SPEC"; src="$SRC"
  if [ "$rc" = 0 ] && [ "$src" = 0 ] && [ -n "$spec" ] && ! has_ere "$spec" "$pat"; then pass=$((pass + 1)); echo "PASS  $name"
  else fail=$((fail + 1)); echo "FAIL  $name (rc=$rc, spec rc=$src, found or no spec '$pat')"; head -20 <<<"$spec"; fi
}
gi() { local d="$1"; shift; git -C "$d" -c user.email=t@t -c user.name=t "$@"; }
plan() { printf '%s\n' "$2" > "$TMP/$1.json"; echo "$TMP/$1.json"; }

for d in "$S" "$C" "$T"; do mkdir -p "$d"; git init -q -b develop "$d"; done
mkdir -p "$C/ProjectSettings" "$T/ProjectSettings"; echo "m_EditorVersion: 6000.0.0f1" > "$C/ProjectSettings/ProjectVersion.txt"
cp "$C/ProjectSettings/ProjectVersion.txt" "$T/ProjectSettings/"
for d in "$S" "$C"; do echo base > "$d/README.md"; gi "$d" add -A; gi "$d" commit -qm base; done
cp -R "$S" "$TMP/base-server"
HEAD='"schema":"rpg-factory.pipeline-plan/1","id":"demo","title":"Demo change","topic":"feat/core/demo","deliver":"pr"'

# Independent case groups (model routing, multi-wave currency, QA tiers): every case has its own directories and state
# dir, so they run in the background, at most $PIPELINE_TEST_JOBS at once, while the linear scenario runs; each
# section prints its results at its place, in the original order.
ROUTING_CASES="model-composition kind-lead kind-plan kind-docs kind-policy kind-design kind-code kind-test kind-fix kind-refactor kind-generated overrides-and-qa availability-claude availability-codex marks-and-empty orca-no-auth orca-system-auth orca-account-auth orca-malformed orca-offline validation followup-validation followup-legacy followup-preview dispatch-claude dispatch-codex status-claude status-codex registry-defaults planned-warning subtask-kind no-probe kinds-single-list enum-copy-original enum-copy-subplan enum-copy-registry"
MULTIWAVE_CASES="covered direct post-review outside-owner invalid-review missing-review evil-merge task-qa integration-qa report implementer override legacy-implementer serial-covered serial-missing-qa subtask-covered subtask-legacy subtask-direct subtask-post-review subtask-missing-review subtask-evil-merge subtask-same-task subtask-sibling-covered subtask-sibling-pre-start subtask-sibling-unknown-start subtask-sibling-post-review subtask-sibling-outside subtask-sibling-missing subtask-sibling-unpaired subtask-sibling-fingerprint repo-path"
cat > "$TMP/routing-cases.py" <<'ROUTING'
import importlib.util, json, os, pathlib, sys
from unittest.mock import patch
root, tmp, case = sys.argv[1:]
sys.path.insert(0, root + '/scripts/lib')
import pipeline_route as r
pipe = json.loads(pathlib.Path(root + '/registry.json').read_text())['pipeline']
both = {a: {'available': True} for a in pipe['agents']}
if case.startswith('kind-'):
    kind = case[len('kind-'):]
    assert kind in r.KINDS
    assert r.route(pipe, {'kind': kind}, both)[0] == pipe['agent_routing'][kind]
if case == 'overrides-and-qa':
    assert r.route(pipe, {'kind': 'code', 'implementer': 'claude'}, both)[0] == 'claude'
    assert r.warnings(pipe, [{'kind': 'code', 'implementer': 'claude'}])
    assert not r.warnings(pipe, [{'kind': 'code', 'implementer': 'claude', 'reason': 'special expertise'}])
    assert r.warnings(pipe, [{'kind': 'code'}] * 3)
    assert r.roles(pipe, {'kind': 'code'}, both)['qa'][0] == 'claude'
    assert r.roles(pipe, {'kind': 'docs'}, both)['qa'][0] == 'codex'
plan = {'id': 'routing-unit'}
for sole in ('claude', 'codex'):
    if case != 'availability-' + sole:
        continue
    with patch.dict(os.environ, {'RPG_FACTORY_AGENTS': sole}):
        avail = r.available(pipe, plan)
        for kind in r.KINDS:
            roles = r.roles(pipe, {'kind': kind}, avail)
            assert all(agent == sole for agent, why in roles.values()), roles
            assert 'SAME_MODEL (fallback:' in roles['review'][1]
    bindir = pathlib.Path(tmp) / ('only-' + sole)
    bindir.mkdir(exist_ok=True)
    binary = bindir / (pipe['agents'][sole]['bin'] + ('.exe' if os.name == 'nt' else ''))
    binary.write_text('fixture')
    binary.chmod(0o755)
    with patch.dict(os.environ, {'PATH': str(bindir), 'PATHEXT': '.EXE;.CMD'}, clear=True):
        avail = r.available(pipe, plan)
        assert all(a == sole for a, why in r.roles(pipe, {'kind': 'code'}, avail).values())
if case == 'marks-and-empty':
    with patch.dict(os.environ, {'RPG_FACTORY_AGENTS': 'claude,codex'}):
        r.mark(plan, 'codex', '401 revoked token')
        assert r.route(pipe, {'kind': 'code'}, r.available(pipe, plan)) == ('claude', 'fallback: codex unavailable')
        r.mark(plan, 'codex')
        assert r.available(pipe, plan)['codex']['available']
    with patch.dict(os.environ, {'RPG_FACTORY_AGENTS': ''}):
        assert 'WARNING' in r.route(pipe, {'kind': 'code'}, r.available(pipe, plan))[1]
import subprocess
for label, payload, down in (
    ('no-auth', json.dumps({'result': {'codex': {'accounts': [], 'systemDefault': {'hasAuth': False}}}}), True),
    ('system-auth', json.dumps({'result': {'codex': {'accounts': [], 'systemDefault': {'hasAuth': True}}}}), False),
    ('account-auth', json.dumps({'result': {'codex': {'accounts': [{}], 'systemDefault': {'hasAuth': False}}}}), False),
    ('malformed', '{"result":null}', False),
):
    if case != 'orca-' + label:
        continue
    with patch.dict(os.environ, {'ORCA_WORKTREE_ID': 'fixture', 'PATH': 'orca-' + label,
                                'RPG_FACTORY_STATE_DIR': tmp + '/account-state'}, clear=True), \
         patch('pipeline_route.shutil.which', return_value='/fake'), \
         patch('pipeline_route.subprocess.run', return_value=subprocess.CompletedProcess([], 0, payload)):
        avail = r.available(pipe, {'id': 'account-' + label})
        assert avail['claude']['available']
        assert avail['codex']['available'] != down
if case == 'orca-offline':
    with patch.dict(os.environ, {'ORCA_WORKTREE_ID': 'fixture', 'PATH': 'orca-offline',
                                'RPG_FACTORY_STATE_DIR': tmp + '/account-state'}, clear=True), \
         patch('pipeline_route.shutil.which', return_value='/fake'), \
         patch('pipeline_route.subprocess.run', side_effect=OSError('offline')):
        assert all(a['available'] for a in r.available(pipe, {'id': 'account-offline'}).values())
spec = importlib.util.spec_from_file_location('routing_pipeline', root + '/scripts/factory-pipeline.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
reg = json.loads(pathlib.Path(root + '/registry.json').read_text())
plan = {'schema': m.SCHEMA, 'id': 'route-validation', 'title': 'test', 'topic': 'test',
        'repos': {'plugin': {'path': root}},
        'tasks': [{'id': 't', 'repo': 'plugin', 'kind': 'code', 'implementer': 'claude',
                   'objective': 'x', 'paths': ['scripts/'], 'acceptance': ['x']}]}
if case == 'followup-validation':
    plan['tasks'][0].pop('kind')
    plan['tasks'][0]['implementer'] = 'claude' if r.route(pipe, {}, both)[0] == 'codex' else 'codex'
    assert any('default routing without reason' in w for w in m.validate(plan, reg)['warnings'])
    sub = {'schema': m.SUBPLAN_SCHEMA, 'plan': 'p', 'task': 't', 'subtasks': [
           {'id': 's', 'objective': 'x', 'paths': ['scripts/x'], 'implementer': plan['tasks'][0]['implementer']}]}
    assert any('default routing without reason' in w for w in m.validate_subplan(sub, plan, reg)['warnings'])
    custom = dict(pipe, agent_routing={})
    other = next(agent for agent in pipe['agents'] if agent != pipe['default_implementer'])
    assert r.warnings(custom, [{'implementer': other}])
    assert r.warnings(custom, [{'kind': 'code', 'implementer': other}]) == [
        '?: implementer overrides default routing without reason']
    assert not r.warnings(custom, [{'implementer': other, 'reason': 'expertise'}])
    plan['tasks'][0]['kind'] = 'outside-schema'
    assert m.validate(plan, reg)['errors']
if case == 'followup-legacy':
    with patch.object(m, 'verdict_dir', return_value=tmp + '/legacy-followup'), \
         patch.object(m, 'scope_fingerprint', return_value='current'), \
         patch.object(m, 'repo_info', return_value={'path': root}):
        directory = pathlib.Path(m.verdict_dir(plan))
        directory.mkdir(exist_ok=True)
        legacy = {'task': 't', 'subtask': 'a', 'phase': 'review', 'sha': 'abc',
                  'state': 'FAIL', 'by': 'codex', 'fingerprint': 'current'}
        (directory / 't__sub-a__review.json').write_text(json.dumps(legacy))
        (directory / 't@a__review__b__review.json').write_text(json.dumps(dict(legacy, subtask='a__review__b', state='PASS')))
        assert m.subtask_failures(plan, reg, 't', 'abc')
        current = directory / 't@a__review.json'
        current.write_text(json.dumps(dict(legacy, state='PASS', fingerprint='stale')))
        assert m.subtask_failures(plan, reg, 't', 'abc')
        current.write_text(json.dumps(dict(legacy, state='PASS')))
        assert not m.subtask_failures(plan, reg, 't', 'abc')
        current.rename(directory / 't@a__review__0123456789ab__codex.json')
        assert not m.subtask_failures(plan, reg, 't', 'abc')
if case == 'model-composition':
    policy = m.model_policy.load(reg)
    task = plan['tasks'][0]
    task.pop('implementer', None)
    task.update(kind='code', grade='heavy')
    sub = {'task': task['id'], 'subtasks': [{'id': 's', 'kind': 'code', 'grade': 'light'}]}
    for agents in ('claude,codex', 'claude', 'codex'):
        with patch.dict(os.environ, {'RPG_FACTORY_AGENTS': agents}):
            errors = []
            row = m.plan_models(plan, reg, errors)['tasks'][task['id']]
            subrow = m.subplan_models(sub, plan, reg, errors)['subtasks']['s']
            roles = r.roles(pipe, task, r.available(pipe, plan))
            for phase, role in (('implement', 'heavy'), ('review', 'heavy'), ('qa', 'qa')):
                agent = roles[phase][0]
                assert row[phase] == dict(m.model_policy.resolve(policy, agent, role), agent=agent, role=role), row
            for phase, role in (('implement', 'light'), ('review', 'review')):
                agent = roles[phase][0]
                assert subrow[phase] == dict(m.model_policy.resolve(policy, agent, role), agent=agent, role=role), subrow
            assert not errors, errors
if case == 'validation':
    assert any('without reason' in w for w in m.validate(plan, reg)['warnings'])
    plan['tasks'][0]['reason'] = 'expertise'
    assert not m.validate(plan, reg)['warnings']
    sub = {'schema': m.SUBPLAN_SCHEMA, 'plan': 'p', 'task': 't', 'subtasks': [
           {'id': 's', 'objective': 'x', 'paths': ['scripts/x'], 'implementer': 'gpt'}]}
    assert any('implementer `gpt` is not' in e for e in m.validate_subplan(sub, plan, reg)['errors'])
    sub['subtasks'][0].update(implementer='claude', kind='code')
    assert any('without reason' in w for w in m.validate_subplan(sub, plan, reg)['warnings'])
    sub['subtasks'][0]['reason'] = 'expertise'
    assert not m.validate_subplan(sub, plan, reg)['warnings']
import subprocess
project = pathlib.Path(tmp) / ('routing-project-' + case)
(project / 'ProjectSettings').mkdir(parents=True, exist_ok=True)
(project / 'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.0.0f1')
plan['repos']['plugin']['path'] = str(project)
plan['repos']['plugin']['base'] = 'main'
planfile = pathlib.Path(tmp) / ('routing-command-plan-' + case + '.json')
plan['tasks'][0].pop('implementer', None)
planfile.write_text(json.dumps(plan))
if case == 'followup-preview':
    state = tmp + '/preview-state'
    env = dict(os.environ, RPG_FACTORY_AGENTS='claude,codex', RPG_FACTORY_STATE_DIR=state)
    for runner in ('print', 'orca', 'agent'):
        for phase in ('implement', 'review'):
            args = [sys.executable, '-B', root + '/scripts/factory-pipeline.py', 'dispatch', str(planfile),
                    '--task', 't', '--phase', phase, '--runner', runner]
            if phase == 'review':
                args += ['--sha', 'abc1234']
            if runner == 'agent':
                args += ['--orca-unavailable', 'fixture']
            result = subprocess.run(args, capture_output=True, text=True, env=env)
            assert result.returncode == 0, result.stderr
            records = list(pathlib.Path(state).rglob('*.model.json'))
            assert bool(records) == (runner != 'print'), records
            if runner != 'print':
                role = 'implementer' if phase == 'implement' else 'reviewer'
                assert any('__' + role in record.name for record in records), records
                for record in records:
                    record.unlink()
    for reason in (None, 'revoked'):
        args = [sys.executable, '-B', root + '/scripts/factory-pipeline.py', 'agents', str(planfile), '--down', 'codex']
        if reason:
            args += ['--reason', reason]
        result = subprocess.run(args, capture_output=True, text=True, env=env)
        assert result.returncode == 0, result.stderr
        assert result.stdout.count('MODEL_UNAVAILABLE') == 1, result.stdout
        assert ('MODEL_UNAVAILABLE: revoked' if reason else 'MODEL_UNAVAILABLE') in result.stdout
for sole in ('claude', 'codex'):
    if case != 'dispatch-' + sole and case != 'status-' + sole:
        continue
    # own state per case: an implement dispatch records its model, which later review/QA dispatches pair against
    env = dict(os.environ, RPG_FACTORY_AGENTS=sole, RPG_FACTORY_STATE_DIR=tmp + '/state-' + case)
    if case == 'status-' + sole:
        result = subprocess.run([sys.executable, '-B', root + '/scripts/factory-pipeline.py', 'status', str(planfile), '--json'], capture_output=True, text=True, encoding='utf-8', env=env)
        models = json.loads(result.stdout)['models']['t']
        assert all(x['agent'] == sole and x['why'] for x in models.values()), models
        assert 'SAME_MODEL (fallback:' in models['review']['why']
        continue
    for phase in ('lead', 'implement', 'review', 'qa'):
        args = [sys.executable, '-B', root + '/scripts/factory-pipeline.py', 'dispatch', str(planfile),
                '--task', 't', '--phase', phase, '--runner', 'print']
        if phase == 'lead':
            args += ['--agent', 'codex' if sole == 'claude' else 'claude']
        if phase in ('review', 'qa'):
            args += ['--sha', 'abc1234']
        result = subprocess.run(args, capture_output=True, text=True, env=env)
        assert result.returncode == 0, result.stderr
        assert '# agent: ' + sole in result.stdout, result.stdout
        assert 'model: ' + phase + ' -> ' + sole in result.stderr, result.stderr
        if phase == 'lead':
            assert 'the task lead is ' + sole in result.stderr and 'always' not in result.stderr
            if sole == 'codex':
                assert 'fallback: claude unavailable' in result.stderr
if case == 'registry-defaults':
    custom = dict(pipe, available_agents=['claude'], agent_routing=dict(pipe['agent_routing'], default='codex'))
    with patch.dict(os.environ, {'RPG_FACTORY_AGENTS': 'claude,codex'}):
        avail = r.available(custom, {'id': 'candidate-set'})
        assert not avail['codex']['available']
        assert avail['codex']['why'] == 'not in pipeline.available_agents'
    assert r.route(custom, {}, both) == ('codex', 'agent_routing.default')
if case == 'planned-warning':
    assert not r.warnings(pipe, [{'kind': k} for k in ('code', 'docs', 'test')])
if case == 'subtask-kind':
    sub = {'schema': m.SUBPLAN_SCHEMA, 'plan': 'p', 'task': 't', 'subtasks': [
           {'id': 's', 'objective': 'x', 'paths': ['scripts/x']}]}
    assert 'subtask s: missing implementer (or kind)' in m.validate_subplan(sub, plan, reg)['errors']
    sub['subtasks'][0]['kind'] = 'code'
    assert not m.validate_subplan(sub, plan, reg)['errors']
if case == 'no-probe':
    import shutil
    orig_run, orig_which, started = subprocess.run, shutil.which, []
    def spy(args, *k, **kw):
        if isinstance(args, (list, tuple)) and list(args[:1]) == ['orca']:
            started.append(args)
            return subprocess.CompletedProcess(args, 0, '{}')
        return orig_run(args, *k, **kw)
    env = {k: v for k, v in os.environ.items() if k != 'RPG_FACTORY_AGENTS'}
    env['ORCA_WORKTREE_ID'] = 'fixture'
    sub = {'schema': m.SUBPLAN_SCHEMA, 'plan': 'p', 'task': 't', 'subtasks': [
           {'id': 's', 'objective': 'x', 'paths': ['scripts/x'], 'kind': 'code'}]}
    with patch.dict(os.environ, env, clear=True), patch('subprocess.run', spy), \
         patch('shutil.which', lambda n, *a, **k: '/fake' if n == 'orca' else orig_which(n, *a, **k)):
        m.validate(plan, reg)
        m.validate_subplan(sub, plan, reg)
        assert not started, started
        r.available(pipe, {'id': 'probe-control'})
        assert started, 'control: available() starts the orca account probe'
    with patch.dict(os.environ, {'RPG_FACTORY_AGENTS': 'claude,codex'}), \
         patch('pipeline_route.fstate.read_json', side_effect=AssertionError('marks read')):
        r.available(pipe, None)  # the planner: no per-run marks
        try:
            r.available(pipe, {'id': 'marks-control'})
            raise RuntimeError('control: a plan reads its marks')
        except AssertionError as e:
            assert 'marks read' in str(e)
if case == 'kinds-single-list':
    import re
    kinds = list(r.KINDS)
    assert set(kinds) == set(pipe['agent_routing']) - {'default'}, pipe['agent_routing']
    def find(node, key, out):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == key:
                    out.append(v)
                find(v, key, out)
        elif isinstance(node, list):
            for v in node:
                find(v, key, out)
        return out
    for name in ('pipeline-plan', 'pipeline-subplan'):
        schema = json.loads(pathlib.Path(root + '/docs/schemas/' + name + '.schema.json').read_text(encoding='utf-8'))
        found = [v['enum'] for v in find(schema, 'kind', []) if isinstance(v, dict) and 'enum' in v]
        assert found and all(e == kinds for e in found), (name, found)
    schema = json.loads(pathlib.Path(root + '/docs/registry.schema.json').read_text(encoding='utf-8'))
    found = [v['propertyNames']['enum'] for v in find(schema, 'agent_routing', []) if isinstance(v, dict) and 'propertyNames' in v]
    assert found and all(e == kinds + ['default'] for e in found), found
    text = pathlib.Path(root + '/scripts/check-registry.sh').read_text(encoding='utf-8')
    assert '--argjson pipeline_kinds "$pipeline_kinds"' in text
if case in ('enum-copy-original', 'enum-copy-subplan', 'enum-copy-registry'):
    import shutil
    sys.path.insert(0, root + '/scripts/lib')
    from shells import find_bash
    bash = find_bash()
    assert bash, 'Git Bash is required for enum-copy registry checks'
    copied = pathlib.Path(tmp) / case
    for name in ('registry.json', 'docs/registry.schema.json', 'docs/schemas/pipeline-plan.schema.json',
                 'docs/schemas/pipeline-subplan.schema.json', 'scripts/check-registry.sh', 'scripts/lib/compat.sh'):
        dest = copied / name; dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pathlib.Path(root) / name, dest)
    shutil.copytree(pathlib.Path(root) / 'docs/schemas/kinds', copied / 'docs/schemas/kinds')
    shutil.copytree(pathlib.Path(root) / 'scripts/checks', copied / 'scripts/checks')
    changed = None
    if case == 'enum-copy-subplan':
        changed = 'docs/schemas/pipeline-subplan.schema.json'
        keys = ('properties', 'subtasks', 'items', 'properties', 'kind', 'enum')
    elif case == 'enum-copy-registry':
        changed = 'docs/registry.schema.json'
        keys = ('properties', 'pipeline', 'properties', 'agent_routing', 'propertyNames', 'enum')
    if changed:
        doc = json.loads((copied / changed).read_text())
        value = doc
        for key in keys:
            value = value[key]
        value.append('drift')
        (copied / changed).write_text(json.dumps(doc))
    result = subprocess.run([bash, str(copied / 'scripts/check-registry.sh'), '--structure-only'],
                            capture_output=True, text=True, env=dict(os.environ, CLAUDE_PLUGIN_ROOT=str(copied)))
    if changed:
        assert result.returncode != 0, result.stdout
        assert ('pipeline kind enum: ' + changed + ' differs from docs/schemas/pipeline-plan.schema.json') in result.stdout, (result.stdout, result.stderr)
    else:
        assert result.returncode == 0, (result.stdout, result.stderr)
print('routing assertions passed')
ROUTING
cat > "$TMP/multiwave.py" <<'MULTIWAVE'
import copy, importlib.util, json, os, pathlib, shutil, subprocess, sys
root, tmp, case = sys.argv[1:]
spec = importlib.util.spec_from_file_location('multiwave_pipeline', root + '/scripts/factory-pipeline.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
reg = json.loads(pathlib.Path(root + '/registry.json').read_text())
work = pathlib.Path(tmp) / ('multiwave-' + case); work.mkdir()
repo = work / 'repo'
variant = 'serial' if case.startswith('serial-') else 'subtask' if case.startswith('subtask-') else 'base'
shutil.copytree(pathlib.Path(tmp) / 'templates' / variant, repo, ignore=shutil.ignore_patterns('*.lock'))
os.environ['RPG_FACTORY_STATE_DIR'] = str(work / 'state')
def git(*args):
    r = subprocess.run(['git', '-C', str(repo), '-c', 'user.name=test', '-c', 'user.email=t@t', *args],
                       capture_output=True, text=True)
    assert r.returncode == 0, (args, r.stderr)
    return r.stdout.strip()
def commit(text, filename='shared.txt'):
    (repo / filename).write_text(text)
    git('add', filename); git('commit', '-qm', text)
    return git('rev-parse', 'HEAD')
base = git('rev-parse', 'HEAD')
git('switch', '--no-track', '-c', 'topic')
plan = {'schema': m.SCHEMA, 'id': 'multiwave-' + case, 'title': 'test', 'topic': 'topic',
        'repos': {'fixture': {'path': str(repo), 'base': 'main'}},
        'tasks': [{'id': 'a', 'repo': 'fixture', 'kind': 'code', 'objective': 'first',
                   'paths': ['shared.txt'], 'acceptance': ['reviewed']},
                  {'id': 'b', 'repo': 'fixture', 'kind': 'code', 'objective': 'second',
                   'paths': ['shared.txt'], 'acceptance': ['reviewed'], 'deps': ['a']}]}
pf = work / 'plan.json'; plan['_path'] = str(pf)
if case.startswith('subtask-'):
    plan['tasks'][0]['paths'] = ['.']  # task owns the directory, subtask owns only shared.txt
    plan['tasks'][1]['paths'] = ['shared.txt', 'outside.txt']
def save():
    pf.write_text(json.dumps(plan))
save()
if case == 'repo-path':
    workspace = work / 'workspace'; workspace.mkdir()
    for marker in reg['workspace']['root_markers']:
        (workspace / marker).mkdir(parents=True, exist_ok=True)
    os.environ[reg['workspace']['root_env']] = str(workspace)
    for value in ('$' + reg['workspace']['root_env'] + '/repo', '${' + reg['workspace']['root_env'] + '}/repo'):
        plan['repos']['fixture']['path'] = value
        assert m.repo_info(plan, reg, 'fixture')['path'] == str(workspace / 'repo')
    plan['repos']['fixture']['path'] = str(repo)
    assert m.repo_info(plan, reg, 'fixture')['path'] == str(repo)
    plan['repos']['fixture']['path'] = 'repo'
    assert m.repo_info(plan, reg, 'fixture')['path'] == str(repo)
    print(case + ' assertions passed')
    sys.exit(0)

def pipeline_cli(*args):
    if os.environ.get('PIPELINE_TEST_CLI') == 'process':
        return subprocess.run([sys.executable, '-B', root + '/scripts/factory-pipeline.py', *args],
                              capture_output=True, text=True)
    import contextlib, io
    out, err = io.StringIO(), io.StringIO()
    argv = sys.argv
    try:
        sys.argv = [root + '/scripts/factory-pipeline.py', *args]
        m.pr._cache.clear()  # availability probes belong to one CLI invocation
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rc = m.main()
            except SystemExit as exc:
                rc = exc.code
    finally:
        sys.argv = argv
    return subprocess.CompletedProcess(args, rc, out.getvalue(), err.getvalue())

def cli(*args, rc=0):
    r = pipeline_cli(*args)
    assert r.returncode == rc, (args, r.stdout, r.stderr)
    return r
def verdict(task, phase, sha, by='claude', extra=()):
    return cli('verdict', str(pf), '--task', task, '--phase', phase, '--sha', sha,
               '--by', by, '--state', 'PASS', *extra)
def record(task, phase):
    return m.verdict_of(plan, reg, task, phase)[0]
def stale_a(expected):
    g = m.gate(plan, reg)
    blockers = [b for b in g['blockers'] if b.startswith('a: review is STALE')]
    row = m.task_status(plan, reg, plan['tasks'][0], 2)[0]
    stale = [n for n in row['notes'] if n.startswith('review at') and 'STALE' in n]
    assert bool(blockers) == expected, g
    assert bool(stale) == expected, row
    if expected:
        assert 'shared.txt' in blockers[0] and 'shared.txt' in stale[0]
    return g, row
if case.startswith('serial-'):
    a = commit('a')
    verdict('a', 'review', a); verdict('a', 'qa', a)
    b = commit('b')
    verdict('b', 'review', b)
    if case != 'serial-missing-qa':
        verdict('b', 'qa', b)
    verdict('integration:fixture', 'qa', b)
    g, row = stale_a(case == 'serial-missing-qa')
    if case == 'serial-covered':
        assert g['state'] == 'READY_FOR_PR', g
        assert row['phase'] == 'qa', row
    else:
        assert any(x.startswith('a: QA is STALE') for x in g['blockers']), g
    print(case + ' assertions passed')
    sys.exit(0)
git('switch', '--no-track', '-c', 'topic-a')
a = commit('a')
if case.startswith('subtask-'):
    m.pr.record(plan, 'a', 's', 'implementer', {'agent': 'claude', 'paths': ['shared.txt']})
    m.pr.record(plan, 'a', None, 'implementer', {'agent': 'codex'})  # the task-level implement dispatch the explicit --implementer codex below matches
    verdict('a', 'review', a, by='codex', extra=('--subtask', 's'))
    if case == 'subtask-legacy':
        folder = pathlib.Path(m.verdict_dir(plan)) / 'a'; folder.mkdir()
        (folder / 'subplan-old.json').write_text(json.dumps({'task': 'a', 'subtasks': [{'id': 's', 'paths': ['shared.txt']}]}))
        m.pr.record(plan, 'a', 's', 'implementer', {'agent': 'claude'})
        for filename in pathlib.Path(m.verdict_dir(plan)).glob('a@s__review*.json'):
            doc = json.loads(filename.read_text()); doc.pop('paths', None); filename.write_text(json.dumps(doc))
    verdict('a', 'review', a, extra=('--implementer', 'codex'))
else:
    verdict('a', 'review', a)
verdict('a', 'qa', a)
if case.startswith('subtask-sibling-'):
    if case == 'subtask-sibling-pre-start':
        commit('unreviewed edit before sibling starts')
    start = git('rev-parse', 'HEAD')
    sibling = commit('sibling edit')
    sibling_paths = ['outside.txt'] if case == 'subtask-sibling-outside' else ['shared.txt']
    m.pr.record(plan, 'a', 'later', 'implementer', {'agent': 'claude', 'paths': sibling_paths, **({} if case == 'subtask-sibling-unknown-start' else {'start': start})})
    if case != 'subtask-sibling-missing':
        by = 'claude' if case == 'subtask-sibling-unpaired' else 'codex'
        verdict('a', 'review', sibling, by=by, extra=('--subtask', 'later'))
    if case == 'subtask-sibling-fingerprint':
        for filename in pathlib.Path(m.verdict_dir(plan)).glob('a@later__review*.json'):
            doc = json.loads(filename.read_text()); doc['fingerprint'] = 'invalid'
            filename.write_text(json.dumps(doc))
    if case == 'subtask-sibling-post-review':
        commit('unreviewed sibling edit')
    git('switch', 'topic'); git('merge', '--no-ff', '-m', 'merge sibling work', 'topic-a')
    head = git('rev-parse', 'HEAD')
    verdict('a', 'review', head, extra=('--implementer', 'codex'))
    verdict('a', 'qa', head)
    verdict('b', 'review', head); verdict('b', 'qa', head)
    verdict('integration:fixture', 'qa', head)
    g = m.gate(plan, reg)
    stale = [x for x in g['blockers'] if 'subtask s recorded' in x and 'stale subtask review:' in x]
    assert not stale, g
    if stale:
        assert 'shared.txt' in stale[0], stale
        if case == 'subtask-sibling-unknown-start':
            assert 'unknown legacy starts receive no credit' in stale[0], stale
    else:
        assert g['state'] == 'READY_FOR_PR', g
    print(case + ' assertions passed')
    sys.exit(0)
if case == 'task-qa':
    row = m.task_status(plan, reg, plan['tasks'][0], 2)[0]
    assert row['qa']['task'] == 'a' and row['qa']['sha'] == a, row
    assert not any('STALE' in n for n in row['notes']), row
elif case in ('report', 'implementer', 'override', 'legacy-implementer'):
    if case == 'report':
        r = cli('verdict', str(pf), '--task', 'a', '--phase', 'qa', '--sha', a, '--by', 'claude',
                '--state', 'PASS', '--report', 'free text is not a file', rc=2)
        assert '--report must name an existing file' in r.stderr and '--note' in r.stderr
        verdict('a', 'qa', a, extra=('--note', 'free text'))
        assert record('a', 'qa')['note'] == 'free text'
        report = work / 'report.md'; report.write_text('evidence')
        verdict('a', 'qa', a, extra=('--report', str(report)))
        assert pathlib.Path(record('a', 'qa')['report']).is_file()
    else:
        m.pr.record(plan, 'a', 's1', 'implementer', {'agent': 'claude'})
        m.pr.record(plan, 'a', 's2', 'implementer', {'agent': 'claude'})
        extra = ('--implementer', 'codex') if case == 'override' else ()
        if extra:
            m.pr.record(plan, 'a', None, 'implementer', {'agent': 'codex'})  # a task-level implement dispatch: the explicit declaration is recorded, not contradicting
        if extra:
            pathlib.Path(m.verdict_file(plan, 'a', 'review')).unlink()  # exercise a fresh explicit declaration, not review preservation
        verdict('a', 'review', a, by='codex', extra=extra)
        rv = record('a', 'review')
        assert rv['implementer'] == ('codex' if extra else 'claude'), rv
        assert rv['implementer_source'] == ('explicit' if extra else 'subtask implementers'), rv
        assert rv['implementers'] == {'s1': 'claude', 's2': 'claude'}, rv
        if case == 'legacy-implementer':
            del rv['implementer']
            m.fstate.write_json(m.verdict_file(plan, 'a', 'review'), rv)
        git('switch', 'topic'); git('merge', '--no-ff', '-m', 'merge a', 'topic-a')
        g = m.gate(plan, reg)
        pair_errors = [b for b in g['blockers'] if b.startswith('a: reviewed by')]
        assert bool(pair_errors) == bool(extra), g
        if extra:
            assert 'cross-model review needs claude' in pair_errors[0]
else:
    git('switch', 'topic'); git('merge', '--no-ff', '-m', 'merge a', 'topic-a')
    verdict('integration:fixture', 'qa', git('rev-parse', 'HEAD'))
    if case == 'integration-qa':
        row = m.task_status(plan, reg, plan['tasks'][0], 2)[0]
        assert not any('STALE' in n for n in row['notes']), row
        plan['tasks'][1]['objective'] = 'updated later wave'; save()
        row = m.task_status(plan, reg, plan['tasks'][0], 2)[0]
        assert row['qa']['task'] == 'a', row
        s = m.status(plan, reg)
        assert any('integration QA' in n and 'STALE' in n for r in s['tasks'] for n in r['notes']), s
        assert all(sum('integration QA' in n and 'STALE' in n for n in r['notes']) == 1 for r in s['tasks']), s
        assert not any(n.startswith('qa verdict is STALE') for r in s['tasks'] for n in r['notes']), s
    else:
        git('switch', '--no-track', '-c', 'topic-b')
        b = commit('b')
        if case.startswith('subtask-'):
            b = commit('outside later wave', 'outside.txt')
        verdict('b', 'review', b)
        if case in ('post-review', 'subtask-post-review'):
            commit('unreviewed b')
        if case == 'outside-owner':
            plan['tasks'][1]['paths'] = ['other.txt']; save()
            verdict('b', 'review', b)
        git('switch', 'topic'); git('merge', '--no-ff', '-m', 'merge b', 'topic-b')
        if case in ('direct', 'subtask-direct'):
            commit('unreviewed topic')
        if case == 'subtask-same-task':
            commit('later first-task edit')
            verdict('a', 'review', git('rev-parse', 'HEAD'), extra=('--implementer', 'codex'))
        if case == 'invalid-review':
            plan['tasks'][1]['objective'] = 'review fingerprint changed'; save()
        if case in ('missing-review', 'subtask-missing-review'):
            pathlib.Path(m.verdict_file(plan, 'b', 'review')).unlink()
        if case in ('evil-merge', 'subtask-evil-merge'):
            # A merge commit can introduce content absent from either parent.
            git('switch', '--no-track', '-c', 'evil-side')
            commit('side', 'other.txt')
            git('switch', 'topic')
            git('merge', '--no-ff', '--no-commit', 'evil-side')
            (repo / 'shared.txt').write_text('evil resolution')
            git('add', 'shared.txt'); git('commit', '-qm', 'evil merge')
        head = git('rev-parse', 'HEAD')
        verdict('integration:fixture', 'qa', head)
        if case.startswith('subtask-'):
            g = m.gate(plan, reg)
            stale = [x for x in g['blockers'] if 'stale subtask review:' in x]
            assert not stale, g
            if stale:
                assert 'shared.txt' in stale[0] and 'outside.txt' not in stale[0], stale
            if case in ('subtask-covered', 'subtask-legacy'):
                assert g['state'] == 'READY_FOR_PR', g
            print(case + ' assertions passed')
            sys.exit(0)
        g, row = stale_a(case != 'covered')
        if case == 'covered':
            assert g['state'] == 'READY_FOR_PR', g
            assert row['phase'] == 'qa', row
            # Branch removal must not change currency.
            git('branch', '-d', 'topic-a')
            assert not stale_a(False)[0]['blockers']
print(case + ' assertions passed')
MULTIWAVE
cat > "$TMP/qa-tiers.py" <<'QA_TIERS'
import argparse, contextlib, importlib.util, io, json, os, pathlib, re, subprocess, sys
root, tmp = sys.argv[1:]
spec = importlib.util.spec_from_file_location('qa_pipeline', root + '/scripts/factory-pipeline.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
reg = json.loads(pathlib.Path(root + '/registry.json').read_text())
work = pathlib.Path(tmp) / 'qa-tiers'; work.mkdir()
repo = work / 'repo'; repo.mkdir()
os.environ['RPG_FACTORY_STATE_DIR'] = str(work / 'state')
def git(*args):
    p = subprocess.run(['git', '-C', str(repo), '-c', 'user.name=test', '-c', 'user.email=t@t', *args], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()
git('init', '-q', '-b', 'main')
(repo / 'code.py').write_text('base')
# stand-in run-all: --list-suites prints the suites it runs (tests/dogfood.sh, installed-safety.sh, orca-wait not among them)
(repo / 'tests').mkdir()
(repo / 'tests' / 'run-all.sh').write_text('case "$1" in --list-suites) printf "tests/pipeline.test.sh\\ntests/routing-properties.test.py\\ntests/routing.test.sh\\n"; exit 0 ;; esac\n'
                                          'echo full > "$(dirname "$0")/../full-run"; exit 1\n', newline='\n')
git('add', '.'); git('commit', '-qm', 'base')
base = git('rev-parse', 'HEAD'); git('switch', '--no-track', '-c', 'topic')
(repo / 'code.py').write_text('change'); git('commit', '-qam', 'change'); first = git('rev-parse', 'HEAD')
task = {'id': 'a', 'repo': 'fixture', 'kind': 'code', 'objective': 'test', 'paths': ['code.py', 'fix.py'],
        'checks': ['bash tests/pipeline.test.sh', 'env -u TMPDIR tests/pipeline.test.sh',
                   'tests/run-all.sh -j 4', 'tests/run-all.sh --affected --only-suites tests/pipeline.test.sh',
                   'python3 -B scripts/build-registry.py --check', 'tests/dogfood.sh',
                   'python3 -B tests/routing-properties.test.py', 'env -u TMPDIR python3 -B tests/routing-properties.test.py',
                   'tests/run-all.sh --affected --only-suites tests/installed-safety.sh'],
        'acceptance': ['full run-all 0 failed']}
plan = {'schema': m.SCHEMA, 'id': 'qa-tiers', 'title': 'QA', 'topic': 'topic', 'tier': 'M',
        'repos': {'fixture': {'path': str(repo), 'base': 'main'}}, 'tasks': [task]}
pf = work / 'plan.json'
def save(): pf.write_text(json.dumps(plan))
save()
git('worktree', 'add', '-q', '-b', 'topic-a', str(work / 'task'), 'topic')
warnings = m.validate(plan, reg)['warnings']
assert len([w for w in warnings if 'full runs belong to integration QA' in w]) == 2, warnings
safe = dict(task, checks=['tests/run-all.sh --affected'], acceptance=['run-all.sh --affected 0 failed',
                                                                      'tests/run-all.sh --only-suites tests/x.sh 0 failed'])
# a suite or test command in checks warns (implementers run syntax checks only); the scoped run-all tier command does not
assert any('implementers run syntax checks only' in w for w in m.task_qa_warnings(dict(safe, checks=['bash tests/pipeline.test.sh'])))
assert any('implementers run syntax checks only' in w for w in m.task_qa_warnings(dict(safe, checks=['dotnet test Game.Tests.csproj'])))
assert any('implementers run syntax checks only' in w for w in m.task_qa_warnings(dict(safe, checks=['tests/run-all.sh --affected && bash tests/pipeline.test.sh'])))
assert not m.task_qa_warnings(dict(safe, acceptance=['a'], checks=['tests/run-all.sh --affected --only-suites tests/x.sh -j 2']))
assert not m.task_qa_warnings(dict(safe, acceptance=['a'], checks=['tests/run-all.sh --only-suites=tests/x.sh,tests/y.sh -j 2']))
assert any('implementers run syntax checks only' in w for w in
           m.task_qa_warnings(dict(safe, checks=['tests/run-all.sh --affected --only-suites tests/x.sh && bash tests/y.sh'])))
assert not m.task_qa_warnings(dict(safe, acceptance=['a']))
# a run-all re-verify drops the run-all commands and suites (failed suites plus --affected replace them), keeps any other command
retry_task = dict(task, checks=['tests/run-all.sh --affected --only-suites tests/x.sh', 'env -u TMPDIR bash tests/x.sh --case a',
                                'python3 -B scripts/build-registry.py --check'])
assert m.retry_checks(retry_task, {'tests/x.sh'}) == ['python3 -B scripts/build-registry.py --check'], m.retry_checks(retry_task, {'tests/x.sh'})
assert m.retry_checks(retry_task) == ['env -u TMPDIR bash tests/x.sh --case a', 'python3 -B scripts/build-registry.py --check']
for text in ['full suite 0 failed', 'the whole suite passes', 'all suites 0 failed', 'entire test suite green']:
    assert m.pr.qa_warnings(dict(safe, acceptance=[text])), text
assert not any('acceptance' in w for w in m.pr.qa_warnings(dict(safe, acceptance=['git-guard suite same case count'])))
# without run-all --list-suites nothing is folded: every check stays an extra command, no full run is started
assert m.pr.qa_checks([task], None)[0] == [] and '[a] tests/dogfood.sh' in m.pr.qa_checks([task], None)[1]
old = work / 'old'; (old / 'tests').mkdir(parents=True)
(old / 'tests' / 'run-all.sh').write_text('echo full > "$(dirname "$0")/../full-run"\n', newline='\n')
assert m.runall_suites(str(old)) is None and not (old / 'full-run').exists()
(old / 'tests' / 'run-all.sh').write_text('[ "$1" = --list-suites ] && exit 2\n', newline='\n')
assert m.runall_suites(str(old)) is None
listed = {'tests/pipeline.test.sh', 'tests/routing-properties.test.py', 'tests/routing.test.sh'}
assert m.runall_suites(str(repo)) == listed
assert m.runall_suites(str(work / 'none')) is False  # no tests/run-all.sh: a product repo
# --list-suites starts Git Bash through find_bash (never a bare "bash": the System32 WSL launcher on Windows)
real_find_bash = m.find_bash
m.find_bash = lambda: str(work / 'no-such-bash')
assert m.runall_suites(str(repo)) is None
m.find_bash = real_find_bash
# registry pipeline.qa_tiers picks the tier command; a missing key falls back to task: affected, integration: ci+workspace
assert reg['pipeline']['qa_tiers']['task'] == 'affected' and reg['pipeline']['qa_tiers']['integration'] == 'ci+workspace'
assert m.tier_command('affected', 'main', []) == 'tests/run-all.sh --affected --base main -j 2'
lone = [dict(task, checks=['bash tests/pipeline.test.sh'])]
assert m.tier_command('full', 'main', ['tests/x.sh']) == 'tests/run-all.sh --reuse -j 4'
# task QA never gets a full run: without a base only the check suites, with no suites the lead must give a base
for level in ('affected', 'full'):
    assert m.tier_command(level, '', ['tests/x.sh'], task=True) == 'tests/run-all.sh --only-suites tests/x.sh -j 2'
    assert m.tier_command(level, None, [], task=True).startswith('NONE: the review base is missing')
    assert '--reuse' not in m.tier_command(level, None, [], task=True)
assert 'QA tier command:\ntests/run-all.sh --only-suites tests/pipeline.test.sh -j 2' in m.qa_body('x', lone, runall=listed)
assert 'QA tier command:\ntests/run-all.sh --affected --base main --only-suites tests/pipeline.test.sh -j 2' in \
    m.qa_body('x', lone, base='main', runall=listed)
assert 'QA tier command:\ntests/run-all.sh --affected --base main --only-suites tests/pipeline.test.sh -j 2' in \
    m.qa_body('x', lone, base='main', runall=listed, tiers={'task': 'full'})
assert 'QA tier command:\ntests/run-all.sh --workspace-only' in m.qa_body('x', lone, integration=True, runall=listed, tiers={})
assert 'gh pr checks' not in m.qa_body('x', lone, integration=True, runall=listed, tiers={})
assert 'QA tier command:\ntests/run-all.sh --reuse -j 4' in m.qa_body('x', lone, integration=True, runall=listed, tiers={'integration': 'full'})
assert 'CI runs the affected suites and ci-ok must be green before merging' in m.qa_body('x', lone, integration=True, runall=listed)
assert ('Task QA: never a full tests/run-all.sh run; CI runs the affected suites per change and ci-ok must be green '
        'before merging') in m.qa_body('x', lone, base='main', runall=listed)
handoff = io.StringIO()
with contextlib.redirect_stdout(handoff):
    m.emit_lead_handoff(reg, 'claude', 'prompt', {'new': True, 'repo': 'path:' + str(repo),
                        'parent': str(work / 'integration'), 'base': 'main'}, 'topic-task',
                        {'model': 'model', 'effort': 'high'})
commands = handoff.getvalue().splitlines()
assert len(commands) == 3 and 'worktree add --no-track -b topic-task' in commands[0]
assert commands[1].startswith('orca worktree set ') and '--parent-worktree' in commands[1]
assert commands[2].startswith('orca agent launch ') and 'path:' in commands[2]
assert 'worktree create' not in handoff.getvalue()
# without a known suite list, an --only-suites suite path runs as run-all runs it (TMPDIR unset), attributed to its task
unknown = 'tests/run-all.sh --only-suites tests/session-state.test.sh,tests/r.test.py'
assert m.pr.qa_checks([dict(task, checks=[unknown])], None)[1] == ['[a] env -u TMPDIR bash tests/session-state.test.sh',
                                                                  '[a] env -u TMPDIR python3 -B tests/r.test.py']
# with the list known, an entry run-all does not list makes the whole check DO NOT RUN (run-all would reject it)
assert m.pr.qa_checks([dict(task, checks=[unknown])], listed) == ([], ['[a] ' + m.pr.DO_NOT_RUN + unknown], False)
# r11 review: an --only-suites entry that is run-all itself never becomes a runnable command (a full run), known list
# or not, and neither does a sibling entry of the same check; nor a non-suite path when the list is unknown
for check in ('tests/run-all.sh --only-suites tests/run-all.sh', 'tests/run-all.sh --only-suites=./tests/run-all.sh',
              'tests/run-all.sh --affected --only-suites tests/routing.test.sh,tests/run-all.sh',
              'tests/run-all.sh --only-suites scripts/x.sh', 'tests/run-all.sh --only-suites tests/x'):
    for known in (listed, None):
        got = m.pr.qa_checks([dict(task, checks=[check])], known)
        assert got == ([], ['[a] ' + m.pr.DO_NOT_RUN + check], False), (check, known, got)
# r11 review: only an exact --only-suites token with a list, or --only-suites=LIST, scopes a check; any other flag
# word run-all ignores or misreads (a flag taken as a value) leaves a full run: DO NOT RUN, and validate warns
for check in ('tests/run-all.sh --only-suitesXYZ', 'tests/run-all.sh --only-suitesXYZ tests/routing.test.sh',
              'tests/run-all.sh --only-suites', 'tests/run-all.sh --only-suites=', 'tests/run-all.sh --only-suites=,',
              'tests/run-all.sh --only-suites --affected', 'tests/run-all.sh --base --affected',
              'tests/run-all.sh -j --affected', 'tests/run-all.sh --affected=1', 'tests/run-all.sh --affectedX',
              'tests/run-all.sh --affected --bogus', 'tests/run-all.sh --affected --release',
              'tests/run-all.sh --affected --list-suites'):
    for known in (listed, None):
        got = m.pr.qa_checks([dict(task, checks=[check])], known)
        assert got == ([], ['[a] ' + m.pr.DO_NOT_RUN + check], False), (check, known, got)
for check in ('tests/run-all.sh --only-suitesXYZ', 'tests/run-all.sh --only-suites=', 'tests/run-all.sh --base --affected',
              'tests/run-all.sh --affected=1', 'true && tests/run-all.sh --only-suitesXYZ tests/x.sh'):
    assert m.pr.full_run(check), check
for check in ('tests/run-all.sh --only-suites tests/x.sh', 'tests/run-all.sh --only-suites=tests/x.sh -j 2',
              'tests/run-all.sh --base main --affected --jobs=2 --no-reuse'):
    assert not m.pr.full_run(check), check
assert m.pr.qa_checks([dict(task, checks=['tests/run-all.sh --no-wait --reuse --no-reuse -j2 --jobs 2 --no-workspace '
                                          '--no-claude --base main --only-suites tests/routing.test.sh'])],
                      listed) == (['tests/routing.test.sh'], [], False)
# a repo without tests/run-all.sh keeps the previous body: the task checks and the run-checks.py fast tier
old_body = ('Candidate SHA: x. First check `git rev-parse HEAD` equals it; otherwise report NOT_INDEPENDENT.\n'
            'Read-only unless a check writes its own build output. Check each acceptance criterion against the tree, '
            'run the checks (run-checks.py fast tier for registry repos), regressions, edge and failure cases. A Unity '
            'test run waits for the `unity-test` resource; never a second Editor.\n'
            'Report: templates/pipeline/qa-report.md, ending `VERDICT: PASS|FAIL|NOT_RUN|BLOCKED`.\nAcceptance:\n'
            '- [s] tests pass\nChecks:\n- [s] dotnet test x\n- [s] tests/run-all.sh -j 4')
srv = {'id': 's', 'checks': ['dotnet test x', 'tests/run-all.sh -j 4'], 'acceptance': ['tests pass']}
for kw in ({'base': 'main'}, {'integration': True}, {'base': 'main', 'failed_suites': ['tests/x.sh']}):
    assert m.qa_body('x', [srv], runall=False, **kw) == old_body + ('\nPreviously failed suites:\n- tests/x.sh' if kw.get('failed_suites') else ''), kw
assert m.pr.small_task({'tier': 'M'}, dict(task, paths=['docs/a.md', 'skills/foo/']))
assert not m.pr.small_task({'tier': 'M'}, task)
# tier S prose is .md anywhere, changelog.d/ and skills/ directories: a schema or JSON under docs/ is a machine input
for paths in (['docs/schemas/pipeline-plan.schema.json'], ['docs/registry.schema.json'], ['docs/a.md', 'docs/x.json'],
              ['skills/foo/run.py'], ['docs/plans/']):
    assert not m.pr.small_task({'tier': 'M'}, dict(task, paths=paths)), paths
assert m.pr.small_task({'tier': 'M'}, dict(task, paths=['changelog.d/x.md', 'changelog.d/', 'skills/foo', 'x/y.md']))
# task QA folds only a plain scoped run-all: an optional `env -u TMPDIR` / `bash` prefix, then plain flag tokens with
# --affected or --only-suites among them; the suites it names join the one tier command
for plain in ('tests/run-all.sh --affected', './tests/run-all.sh --affected --base plugin-flow-2 -j 2',
              'bash tests/run-all.sh --only-suites=tests/routing.test.sh', '  env -u TMPDIR tests/run-all.sh --affected\t'):
    assert m.pr.qa_checks([dict(task, checks=[plain])], listed) == (
        ['tests/routing.test.sh'] if 'routing' in plain else [], [], False), repr(plain)
assert m.pr.qa_checks([dict(task, checks=['env -u TMPDIR bash tests/run-all.sh --only-suites tests/routing.test.sh'])],
                      listed) == (['tests/routing.test.sh'], [], False)
# every other check that mentions run-all is DO NOT RUN: full, compound, wrapped, adjacent operators, redirections,
# quotes, escapes, comments, other env prefixes and newlines (no shell parsing decides whether a full run hides)
dnr = [
    # full runs (no scoped flag)
    'tests/run-all.sh', 'tests/run-all.sh -j 4', 'tests/run-all.sh --reuse -j 4', 'env -u TMPDIR X=1 tests/run-all.sh -j 4',
    'tests/run-all.sh # --affected', 'echo tests/run-all.sh',
    # compound, scoped or not
    'tests/run-all.sh --only-suites tests/pipeline.test.sh && python3 -B scripts/build-registry.py --check',
    'tests/run-all.sh --affected || true', 'tests/run-all.sh --affected; echo done', 'tests/run-all.sh --affected | tail -1',
    '(tests/run-all.sh --affected)', 'echo $(tests/run-all.sh --affected)', 'tests/run-all.sh --affected > out.txt',
    'tests/run-all.sh --affected\npython3 -B scripts/build-registry.py --check',
    'tests/run-all.sh --affected\r\npython3 -B scripts/build-registry.py --check',
    'tests/run-all.sh -j 4 && python3 -B scripts/build-registry.py --check', 'tests/run-all.sh --affected\ntests/run-all.sh',
    # wrapped
    "bash -c 'tests/run-all.sh -j 4' > out.txt", 'bash -c "tests/run-all.sh -j 4"', "bash -c 'tests/run-all.sh'",
    "bash -c 'tests/run-all.sh --affected -j 2'", 'sh tests/run-all.sh', 'sh ./tests/run-all.sh -j 4',
    'env -u TMPDIR sh tests/run-all.sh --reuse', 'env tests/run-all.sh --affected', 'env -u HOME tests/run-all.sh --affected',
    # operators and redirections without spaces
    'tests/run-all.sh>qa.log', 'tests/run-all.sh>>qa.log', 'tests/run-all.sh 2>&1', 'tests/run-all.sh&>qa.log',
    'tests/run-all.sh|tee qa.log', 'tests/run-all.sh 2>&1|tee qa.log', 'true;tests/run-all.sh', 'true&&tests/run-all.sh -j 4',
    'tests/run-all.sh --affected;tests/run-all.sh', '(tests/run-all.sh)', 'tests/run-all.sh>--affected',
    'bash -c "tests/run-all.sh">qa.log', 'echo $(tests/run-all.sh)', 'X="tests/run-all.sh -j 4" true',
    'tests/run-all.sh "unbalanced', 'tests/run-all.sh --affected>qa.log', 'tests/run-all.sh --affected 2>&1|tee qa.log',
    'tests/run-all.sh --only-suites=tests/x.sh;true', 'tests/run-all.sh --affected&>qa.log',
    'bash -c "tests/run-all.sh --affected">qa.log', 'tests/run-all.sh --affected `true`', 'tests/run-all.sh --affected $X',
    # comments
    'tests/run-all.sh --affected # scoped', 'tests/run-all.sh --affected # scoped\ntests/run-all.sh',
    'tests/run-all.sh --affected #c\r\ntests/run-all.sh -j 4', 'tests/run-all.sh --affected;#x\ntests/run-all.sh',
    'true # c\n\ntests/run-all.sh', 'bash -c "true # c\ntests/run-all.sh"', 'echo "#"; tests/run-all.sh',
    'echo \\# x; tests/run-all.sh', 'tests/run-all.sh \\', 'tests/run-all.sh --affected # tests/run-all.sh',
    'echo a#b; tests/run-all.sh --affected',
    # escaped spaces and operators (the r10 review repro first), quoted or escaped names
    'echo x\\ #literal; tests/run-all.sh', 'echo x\\ #literal\ntests/run-all.sh', 'tests/run-all.sh --affected\\ ;tests/run-all.sh',
    'tests/run-all.sh\\;true', 'tests/run-all.sh --affected \\&\\& tests/run-all.sh', 'tests/run-all.sh --affected \\| true',
    'tests/run-all.sh --affected \\> qa.log', 'tests/run-all.sh "--affected"', "tests/run-all.sh '--only-suites=tests/x.sh'",
    'tests/run-a"ll".sh -j 4', "tests/run-a'll'.sh", 'tests/run-all\\.sh', 'tests/run-al\\l.sh --affected',
]
for check in dnr:
    assert m.pr.qa_checks([dict(task, checks=[check])], listed) == ([], ['[a] ' + m.pr.DO_NOT_RUN + check], False), repr(check)
assert m.pr.DO_NOT_RUN.startswith('DO NOT RUN') and 'NOT_RUN' in m.pr.DO_NOT_RUN
# a check without run-all stays a plain extra command (compound commands are never split)
for other in ('bash tests/pipeline.test.sh && true', 'bash tests/run-all-parallel.test.sh', 'echo run-all'):
    assert m.pr.qa_checks([dict(task, checks=[other])], listed) == ([], ['[a] ' + other], False), other
# validate still warns on a full run inside a compound check; a scoped one is fine
assert m.pr.qa_warnings(dict(safe, checks=['tests/run-all.sh -j 4 && python3 -B scripts/build-registry.py --check']))
assert m.pr.qa_warnings(dict(safe, checks=['tests/run-all.sh --affected && tests/run-all.sh -j 4']))
assert not m.task_qa_warnings(dict(safe, checks=['tests/run-all.sh --affected && python3 -B scripts/build-registry.py --check']))
for wrapped in ("bash -c 'tests/run-all.sh -j 4'", 'bash -c "tests/run-all.sh"', "bash -c 'true && tests/run-all.sh'",
                'tests/run-all.sh --affected\ntests/run-all.sh -j 4', 'echo x\\ #literal; tests/run-all.sh',
                'echo x\\;#literal\ntests/run-all.sh', 'tests/run-all.sh # --affected'):
    assert m.pr.full_run(wrapped), repr(wrapped)
for scoped in ("bash -c 'tests/run-all.sh --affected -j 2'", 'tests/run-all.sh --affected # tests/run-all.sh',
               'echo a#b; tests/run-all.sh --affected', 'tests/run-all.sh --affected 2>&1|tee qa.log'):
    assert not m.pr.full_run(scoped), scoped
# re-QA: a failed suite already among the extra checks (any invocation form) runs once, under its first form
for form in ('tests/dogfood.sh', 'bash tests/dogfood.sh', 'env -u TMPDIR tests/dogfood.sh'):
    assert m.pr.qa_checks([dict(task, checks=[form])], listed, ['tests/dogfood.sh']) == ([], ['[a] ' + form], False), form
assert m.pr.qa_checks([dict(task, checks=['tests/dogfood.sh', 'bash tests/dogfood.sh',
                                          'tests/run-all.sh --only-suites tests/dogfood.sh'])], None,
                      ['tests/dogfood.sh', 'tests/x.sh']) == ([], ['[a] env -u TMPDIR bash tests/dogfood.sh',
                                                                   '[a] env -u TMPDIR bash tests/x.sh'], False)
# the same with run-all's list known: the --only-suites check names a suite run-all does not list, so DO NOT RUN
dog = 'tests/run-all.sh --only-suites tests/dogfood.sh'
assert m.pr.qa_checks([dict(task, checks=['tests/dogfood.sh', 'bash tests/dogfood.sh', dog])], listed,
                      ['tests/dogfood.sh', 'tests/x.sh']) == ([], ['[a] tests/dogfood.sh', '[a] ' + m.pr.DO_NOT_RUN + dog,
                                                                   '[a] env -u TMPDIR bash tests/x.sh'], False)
# the same suite with and without `env -u TMPDIR`: the env form wins, in the first form's place, task ids merged
assert m.pr.qa_checks([dict(task, checks=['tests/x.sh', 'python3 -B scripts/y.py', 'env -u TMPDIR tests/x.sh'])],
                      listed) == ([], ['[a] env -u TMPDIR tests/x.sh', '[a] python3 -B scripts/y.py'], False)
envs = [dict(task, id='a', checks=['bash tests/x.sh']), dict(task, id='b', checks=['env -u TMPDIR bash tests/x.sh', 'tests/x.sh'])]
assert m.pr.qa_checks(envs, listed)[1] == ['[a, b] env -u TMPDIR bash tests/x.sh']
two = [dict(task, id='a', checks=['tests/dogfood.sh']), dict(task, id='b', checks=['bash tests/dogfood.sh'])]
assert m.pr.qa_checks(two, listed, ['tests/dogfood.sh'])[1] == ['[a, b] tests/dogfood.sh']
# release-only suites stay extras, also against the REAL `tests/run-all.sh --list-suites` of this checkout
runall_text = pathlib.Path(root, 'tests', 'run-all.sh').read_text(encoding='utf-8')
assert set(re.search(r'^RELEASE_ONLY="([^"]*)"', runall_text, re.M)[1].split()) == m.pr.RELEASE_ONLY
real = m.runall_suites(root)
assert real and 'tests/pipeline.test.sh' in real, real
for check in ('tests/installed-safety.sh', 'env -u TMPDIR tests/installed-safety.sh', 'tests/dogfood.sh'):
    got = m.pr.qa_checks([dict(task, checks=[check, 'bash tests/pipeline.test.sh'])], real, ['tests/installed-safety.sh'])
    assert got[0] == ['tests/pipeline.test.sh'], (check, got)
    assert any('installed-safety.sh' in x for x in got[1]) or 'installed-safety' not in check, (check, got)
    assert any('dogfood.sh' in x for x in got[1]) or 'dogfood' not in check, (check, got)
    assert len([x for x in got[1] if 'installed-safety.sh' in x]) == 1, (check, got)
# run-all rejects a release-only or unlisted --only-suites entry without --release: that check is DO NOT RUN
check = 'tests/run-all.sh --affected --only-suites tests/installed-safety.sh,tests/dogfood.sh'
got = m.pr.qa_checks([dict(task, checks=[check, 'bash tests/pipeline.test.sh'])], real, ['tests/installed-safety.sh'])
assert got == (['tests/pipeline.test.sh'], ['[a] ' + m.pr.DO_NOT_RUN + check,
                                           '[a] env -u TMPDIR bash tests/installed-safety.sh'], False), got
# a recorded failed suite that is run-all itself (any spelling) or no suite path is DO NOT RUN, never a runnable extra
for bad in ('tests/run-all.sh', './tests/run-all.sh', 'tests/run-a"ll".sh', 'docs/x.md', 'tests/../x.sh'):
    for runall in (real, None):
        got = m.pr.qa_checks([dict(task, checks=['bash tests/pipeline.test.sh'])], runall, [bad])
        assert got[1][-1] == '[a] ' + m.pr.DO_NOT_RUN_FAILED + bad, (bad, got)
        assert not any(e.startswith('[a] env') and 'run-all' in e for e in got[1]), (bad, got)
assert not m.pr.failed_suite_ok('tests/run-all.sh') and m.pr.failed_suite_ok('tests/orca-wait.test.sh')

def pipeline_cli(*args):
    if os.environ.get('PIPELINE_TEST_CLI') == 'process':
        return subprocess.run([sys.executable, '-B', root + '/scripts/factory-pipeline.py', *args],
                              capture_output=True, text=True)
    import contextlib, io
    out, err = io.StringIO(), io.StringIO()
    argv = sys.argv
    try:
        sys.argv = [root + '/scripts/factory-pipeline.py', *args]
        m.pr._cache.clear()  # availability probes belong to one CLI invocation
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rc = m.main()
            except SystemExit as exc:
                rc = exc.code
    finally:
        sys.argv = argv
    return subprocess.CompletedProcess(args, rc, out.getvalue(), err.getvalue())

def cli(*args):
    p = pipeline_cli(*args)
    assert p.returncode == 0, (args, p.stdout, p.stderr)
    return p.stdout
def cli_fail(*args):
    p = pipeline_cli(*args)
    assert p.returncode != 0 and '--failed-suites' in p.stderr, (args, p.stdout, p.stderr)
def dispatch(phase, sha, tid='a'):
    return cli('dispatch', str(pf), '--task', tid, '--phase', phase, '--sha', sha, '--runner', 'print')
verify = dispatch('verify', first)
assert '# agent: claude' in verify and verify.index('Review the whole diff') < verify.index('QA tier command:')
TASK_QA = ('Task QA: never a full tests/run-all.sh run; CI runs the affected suites per change and ci-ok must be green '
           'before merging')
assert TASK_QA in verify, verify
assert 'blocking finding' in verify and 'run no tests' in verify
implementation = cli('dispatch', str(pf), '--task', 'a', '--phase', 'implement', '--runner', 'print')
assert 'Run no test suites; only a syntax check' in implementation and 'bash tests/pipeline.test.sh' not in implementation
out = dispatch('qa', first)
assert TASK_QA in out, out
assert 'Affected cases: not computed (tests/affected.py missing)' in out, out
assert 'tier command already passes these cases' not in out, out
affected = work / 'task' / 'tests' / 'affected.py'
affected.write_text('import pathlib, sys\nassert sys.argv[1] == "cases"\n'
                    'assert pathlib.Path(sys.argv[2]).read_text().splitlines() == ["code.py"]\n'
                    'print("tests/pipeline.test.sh\\tdispatch,qa-tiers")\n'
                    'print("tests/routing.test.sh\\tselection")\n', encoding='utf-8')
case_out = dispatch('qa', first)
assert ('Affected cases (tests/affected.py cases):\ntests/pipeline.test.sh ALL\n'
        'tests/routing-properties.test.py ALL\ntests/routing.test.sh --case selection') in case_out, case_out
assert 'tier command already passes these cases' in case_out, case_out
bad_out = dispatch('qa', 'bad-sha')
assert 'Affected cases: not computed (git diff failed)' in bad_out and 'tier command already passes these cases' not in bad_out, bad_out
affected.unlink()
command = ('tests/run-all.sh --affected --base main --only-suites '
           'tests/pipeline.test.sh,tests/routing-properties.test.py -j 2')
assert out.count(command) == 1, out
assert 'never a full tests/run-all.sh run' in out and 'A full run-all check was dropped' not in out
# the full run-all check is marked DO NOT RUN, in its place among the extras, never folded or runnable
extras = ('Extra commands:\n[a] ' + m.pr.DO_NOT_RUN + 'tests/run-all.sh -j 4\n'
          '[a] python3 -B scripts/build-registry.py --check\n[a] tests/dogfood.sh\n'
          '[a] ' + m.pr.DO_NOT_RUN + 'tests/run-all.sh --affected --only-suites tests/installed-safety.sh')
assert out.count('tests/run-all.sh -j 4') == 1 and extras in out, out
assert 'routing-properties.test.py' not in out.split('Extra commands:')[1], out
assert not (work / 'task' / 'full-run').exists() and not (repo / 'full-run').exists()
assert 'Run no suites; only a minimal repro when needed' in dispatch('review', first)
out = dispatch('qa', first, 'integration:fixture')
assert 'tests/run-all.sh --workspace-only' in out and 'gh pr checks' not in out and 'tests/run-all.sh --reuse -j 4' not in out and extras in out, out
# a product repo without tests/run-all.sh: task and integration QA keep its checks and the run-checks.py fast tier
srv_repo = work / 'srv'; srv_repo.mkdir()
def sgit(*args):
    p = subprocess.run(['git', '-C', str(srv_repo), '-c', 'user.name=test', '-c', 'user.email=t@t', *args],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()
sgit('init', '-q', '-b', 'main'); (srv_repo / 'srv.cs').write_text('base'); sgit('add', '.'); sgit('commit', '-qm', 'base')
sgit('switch', '--no-track', '-c', 'topic'); (srv_repo / 'srv.cs').write_text('change'); sgit('commit', '-qam', 'change')
srv_sha = sgit('rev-parse', 'HEAD')
sgit('worktree', 'add', '-q', '-b', 'topic-s', str(work / 'srv-task'), 'topic')
srv_plan = {'schema': m.SCHEMA, 'id': 'qa-srv', 'title': 'QA', 'topic': 'topic', 'tier': 'M',
            'repos': {'srv': {'path': str(srv_repo), 'base': 'main'}},
            'tasks': [{'id': 's', 'repo': 'srv', 'kind': 'code', 'objective': 'test', 'paths': ['srv.cs'],
                       'checks': ['dotnet test x'], 'acceptance': ['tests pass']}]}
srv_pf = work / 'srv-plan.json'; srv_pf.write_text(json.dumps(srv_plan))
for tid in ('s', 'integration:srv'):
    out = cli('dispatch', str(srv_pf), '--task', tid, '--phase', 'qa', '--sha', srv_sha, '--runner', 'print')
    assert 'run the checks (run-checks.py fast tier for registry repos)' in out and 'Checks:\n- [s] dotnet test x' in out, out
    assert 'QA tier command' not in out and 'tests/run-all.sh' not in out, out
# a verify whose review FAILs ran no tests: no QA record, so the next verify keeps the original base and checks
(srv_repo / 'srv.cs').write_text('fix1'); sgit('commit', '-qam', 'fix1'); srv_fix1 = sgit('rev-parse', 'HEAD')
cli('verdict', str(srv_pf), '--task', 's', '--phase', 'verify', '--sha', srv_sha, '--by', 'codex', '--state', 'FAIL',
    '--failed-at', 'review')
assert not os.path.exists(m.verdict_file(srv_plan, 's', 'qa')), 'a review-only FAIL wrote a QA record'
assert json.loads(open(m.verdict_file(srv_plan, 's', 'review')).read())['state'] == 'FAIL'
out = cli('dispatch', str(srv_pf), '--task', 's', '--phase', 'verify', '--sha', srv_fix1, '--runner', 'print')
assert 'git diff main...' + srv_fix1 in out and 'fix delta' not in out, out
assert 'Checks:\n- [s] dotnet test x' in out, out
# a QA FAIL without --failed-suites (a product test failed): the re-verify keeps the task's check commands
cli('verdict', str(srv_pf), '--task', 's', '--phase', 'verify', '--sha', srv_fix1, '--by', 'codex', '--state', 'FAIL',
    '--failed-at', 'qa')
qa_rec = json.loads(open(m.verdict_file(srv_plan, 's', 'qa')).read())
assert qa_rec['state'] == 'FAIL' and qa_rec['sha'] == srv_fix1, qa_rec
assert json.loads(open(m.verdict_file(srv_plan, 's', 'review')).read())['state'] == 'PASS'  # QA ran after a review PASS
(srv_repo / 'srv.cs').write_text('fix2'); sgit('commit', '-qam', 'fix2'); srv_fix2 = sgit('rev-parse', 'HEAD')
out = cli('dispatch', str(srv_pf), '--task', 's', '--phase', 'verify', '--sha', srv_fix2, '--runner', 'print')
assert 'git diff ' + srv_fix1 + '...' + srv_fix2 in out and 'fix delta since previous candidate' in out, out
assert 'Checks:\n- [s] dotnet test x' in out, out
lean = m.qa_body(first,[dict(task, checks=['bash tests/pipeline.test.sh'])], base='main',
                 runall={'tests/pipeline.test.sh'})
assert 'Extra commands' not in lean and '--only-suites tests/pipeline.test.sh -j 2' in lean, lean
# --failed-suites refusals: a PASS, a review verdict, a name neither run-all lists nor a (tests|testlab|scripts)/ suite
cli_fail('verdict', str(pf), '--task', 'a', '--phase', 'qa', '--sha', first, '--by', 'claude', '--state', 'PASS',
         '--failed-suites', 'tests/routing.test.sh')
cli_fail('verdict', str(pf), '--task', 'a', '--phase', 'review', '--sha', first, '--by', 'claude', '--state', 'FAIL',
         '--failed-suites', 'tests/routing.test.sh')
for bad in ('docs/x.md', 'tests/../x.sh', 'tests/x.txt', 'tools/lab.sh,tests/routing.test.sh', 'tests/routing.test.sh,../x.sh',
            'tests/run-all.sh', 'tests/routing.test.sh,tests/run-all.sh', './tests/run-all.sh'):
    cli_fail('verdict', str(pf), '--task', 'a', '--phase', 'qa', '--sha', first, '--by', 'claude', '--state', 'FAIL',
             '--failed-suites', bad)
p = subprocess.run([sys.executable, '-B', root + '/scripts/factory-pipeline.py', 'verdict', str(pf), '--task', 'a',
                    '--phase', 'qa', '--sha', first, '--by', 'claude', '--state', 'FAIL', '--failed-suites',
                    'tests/run-all.sh'], capture_output=True, text=True)
assert p.returncode == 2 and 'never names tests/run-all.sh' in p.stderr, (p.returncode, p.stderr)
# suites run-all lists outside tests/ (testlab/tests/test_lab.py, scripts/check-registry.sh) are accepted
for good in ('scripts/check-registry.sh', 'testlab/tests/test_lab.py'):
    cli('verdict', str(pf), '--task', 'a', '--phase', 'qa', '--sha', first, '--by', 'claude', '--state', 'FAIL',
        '--failed-suites', good)
# any other name the checkout's `run-all --list-suites` prints is accepted too
runall_src = (repo / 'tests' / 'run-all.sh').read_text()
(repo / 'tests' / 'run-all.sh').write_text(runall_src.replace('routing.test.sh\\n', 'routing.test.sh\\ntools/lab.sh\\n'),
                                          newline='\n')
assert 'tools/lab.sh' in (repo / 'tests' / 'run-all.sh').read_text()
cli('verdict', str(pf), '--task', 'a', '--phase', 'qa', '--sha', first, '--by', 'claude', '--state', 'FAIL',
    '--failed-suites', 'tools/lab.sh')
(repo / 'tests' / 'run-all.sh').write_text(runall_src, newline='\n')
cli('verdict', str(pf), '--task', 'a', '--phase', 'qa', '--sha', first, '--by', 'claude', '--state', 'FAIL',
    '--failed-suites', 'tests/routing.test.sh,tests/routing.test.sh,tests/orca-wait.test.sh')
(repo / 'fix.py').write_text('fix'); git('add', 'fix.py'); git('commit', '-qm', 'fix'); second = git('rev-parse', 'HEAD')
affected.write_text('import pathlib, sys\nassert pathlib.Path(sys.argv[2]).read_text().splitlines() == ["fix.py"]\n'
                    'print("tests/routing.test.sh\\tselection")\n', encoding='utf-8')
verify_again = dispatch('verify', second)
assert 'git diff ' + first + '...' + second in verify_again
assert '--base ' + first + ' --only-suites tests/routing.test.sh' in verify_again
assert 'tests/orca-wait.test.sh' in verify_again and 'tests/pipeline.test.sh' not in verify_again.split('QA tier command:')[1]
out = dispatch('qa', second)
assert ('--base ' + first + ' --only-suites tests/pipeline.test.sh,tests/routing-properties.test.py,'
        'tests/routing.test.sh -j 2') in out, out
assert 'tests/routing.test.sh ALL' in out and 'not computed' not in out, out
affected.unlink()
# a failed suite run-all does not run (exit 2 under --only-suites) is an extra command instead
assert 'orca-wait' not in out.split('QA tier command:\n')[1].split('\n')[0], out
assert '[a] env -u TMPDIR bash tests/orca-wait.test.sh' in out.split('Extra commands:')[1], out
cli('verdict', str(pf), '--task', 'a', '--phase', 'qa', '--sha', first, '--by', 'claude', '--state', 'FAIL')
assert '--base main ' in dispatch('qa', second)
def verdict(tid, phase, by, note=None):
    args = ['verdict', str(pf), '--task', tid, '--phase', phase, '--sha', second, '--by', by, '--state', 'PASS']
    if note: args += ['--note', note]
    cli(*args)
# implementer codex: a QA session by any model passes as before (codex = the one-model fallback); a QA verdict
# recorded as the lead's own tier S run passes only for a tier S task
task['implementer'] = 'codex'
for tier, by, note, allowed in [('S', 'codex', 'tier S: lead ran task suites', True),
                                ('S', 'claude', 'tier S: lead ran task suites', True),
                                ('M', 'codex', 'tier S: lead ran task suites', False),
                                ('M', 'claude', 'tier S: lead ran task suites', False),
                                ('S', 'codex', None, True), ('M', 'codex', None, True), ('M', 'claude', None, True)]:
    plan['tier'] = tier; save()
    verdict('a', 'review', 'claude'); verdict('a', 'qa', by, note); verdict('integration:fixture', 'qa', 'claude')
    result = m.gate(plan, reg, run_checks=False)
    blocked = any('tier S lead QA, but the task is not tier S' in b for b in result['blockers'])
    assert blocked != allowed, (tier, by, note, result)
    if allowed: assert not result['blockers'], result
plan['tier'] = 'S'; save()
assert 'no separate QA session' in dispatch('qa', second)
print('QA tier command, dedup, extras, warnings, review, integration, re-QA and S/M gate assertions passed')
QA_TIERS
# tier XS: a prose-only change within registry pipeline.tiers.XS; the run lead edits and commits on plan.topic, one
# cross-model review, the lead's own QA, gate. One section per acceptance: tier, validate, dispatch, gate.
cat > "$TMP/tier-xs.py" <<'TIER_XS'
import contextlib, importlib.util, io, json, os, pathlib, subprocess, sys
root, tmp, section = sys.argv[1:]
spec = importlib.util.spec_from_file_location('xs_pipeline', root + '/scripts/factory-pipeline.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
reg = json.loads(pathlib.Path(root + '/registry.json').read_text())
rule = reg['pipeline']['tiers']['XS']
assert rule['max_files'] == 3 and rule['max_changed_lines'] == 40 and rule['prose_only'] is True, rule
work = pathlib.Path(tmp) / ('tier-xs-' + section); work.mkdir()
repo = work / 'repo'; repo.mkdir()
os.environ['RPG_FACTORY_STATE_DIR'] = str(work / 'state')
os.environ['RPG_FACTORY_AGENTS'] = 'claude,codex'
def git(*args):
    p = subprocess.run(['git', '-C', str(repo), '-c', 'user.name=test', '-c', 'user.email=t@t', *args], capture_output=True, text=True)
    assert p.returncode == 0, (args, p.stderr)
    return p.stdout.strip()
def write(rel, lines):
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(''.join(f'line {i}\n' for i in range(lines)), newline='\n')
git('init', '-q', '-b', 'main')
write('docs/guide.md', 10); write('code.py', 1); write('changelog.d/README.md', 1)
git('add', '.'); git('commit', '-qm', 'base')
topic = 'feat/docs/xs'
git('switch', '-q', '--no-track', '-c', topic)
task = {'id': 'doc', 'repo': 'fixture', 'objective': 'o', 'paths': ['docs/guide.md', 'changelog.d/'], 'acceptance': ['a']}
plan = {'schema': m.SCHEMA, 'id': 'xs-' + section, 'title': 'XS', 'topic': topic, 'tier': 'XS',
        'repos': {'fixture': {'path': str(repo), 'base': 'main'}}, 'tasks': [task]}
pf = work / 'plan.json'
def save(): pf.write_text(json.dumps(plan))
save()
def cli(*args, rc=0):
    out, err = io.StringIO(), io.StringIO()
    argv = sys.argv
    try:
        sys.argv = [root + '/scripts/factory-pipeline.py', *[str(x) for x in args]]
        m.pr._cache.clear()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                got = m.main()
            except SystemExit as exc:
                got = exc.code
    finally:
        sys.argv = argv
    assert (got or 0) == rc, (args, got, out.getvalue(), err.getvalue())
    return out.getvalue() + err.getvalue()
def tier(*paths):
    return cli('tier', '--plan', pf, '--repo', 'fixture', '--paths', *paths)
def errors(**change):
    p = json.loads(json.dumps(plan)); p['tasks'][0].update(change.pop('task', {})); p.update(change)
    p['_path'] = str(pf)
    return m.validate(p, reg)['errors']

if section == 'tier':
    write('docs/guide.md', 12)  # 2 changed lines, uncommitted
    out = tier('docs/guide.md')
    assert out.startswith('Tier: XS ') and '2 changed line(s)' in out and 'above XS' not in out, out
    assert '"tier": "XS"' in cli('tier', '--json', '--plan', pf, '--repo', 'fixture', '--paths', 'docs/guide.md', 'changelog.d/x.md')
    # one path that is not prose is never XS: the S rule takes it
    out = tier('docs/guide.md', 'code.py')
    assert not out.startswith('Tier: XS') and 'above XS: not prose: code.py' in out, out
    out = tier('docs/schema.json')
    assert out.startswith('Tier: S ') and 'not prose: docs/schema.json' in out, out
    # an oversize change is never XS: changed lines (untracked files count whole) and files above the thresholds
    write('docs/big.md', 45)
    out = tier('docs/big.md')
    assert out.startswith('Tier: S ') and 'above XS: 45 changed lines > 40' in out, out
    out = tier('a.md', 'b.md', 'c.md', 'd.md')
    assert out.startswith('Tier: S ') and '4 files > 3' in out, out
    assert m.pr.above_xs(rule, ['a.md', 'skills/x/'], 40) == []
    assert m.pr.above_xs(rule, ['a.md'], 41) == ['41 changed lines > 40']
    print('tier: XS printed only for prose within the thresholds')

if section == 'validate':
    assert errors() == [], errors()
    lead = reg['pipeline']['lead_agent']; pair = reg['pipeline']['review_pairing'][lead]
    out = cli('validate', pf)
    assert f'grade light (tier XS of the owned paths): implement {lead} ' in out and f', review {pair} ' in out, out
    assert any('not prose: code.py' in e for e in errors(task={'paths': ['docs/guide.md', 'code.py']})), 'non-prose'
    # a task-level tier XS is held to the same rule
    assert any('not prose: code.py' in e for e in errors(tier='M', task={'tier': 'XS', 'paths': ['code.py']}))
    assert any('4 files > 3' in e for e in errors(task={'paths': ['a.md', 'b.md', 'c.md', 'd.md']})), 'oversize'
    two = dict(task, id='more', paths=['other.md'])
    assert any('exactly one task, this one has 2' in e for e in errors(tasks=[task, two])), 'multi-task'
    assert any('tier must be XS, S, M or L' in e for e in errors(tier='XL'))
    # XS grades light, and the run lead's model (pipeline.lead_agent) is its implementer: the review is the pair
    assert m.TIER_GRADE['XS'] == 'light'
    p = dict(plan, _path=str(pf))
    assert m.implementer_of(reg['pipeline'], p, task)[0] == reg['pipeline']['lead_agent']
    # contracts: false and generated: false hold for validate as for tier: a prose path the routing snapshot names as a
    # contract end or a generated path is above XS (the fixture repo has none, so its snapshot is stubbed)
    real = m.task_context
    try:
        m.task_context = lambda pl, rg, t: ({'repos': [{'repo': 'fixture', 'touched': ['docs'], 'files': [],
                                              'contracts': [{'id': 'wire'}], 'generated_hits': ['docs/guide.md']}]}, None)
        why = errors()
        assert any('contract wire' in e and 'generated path docs/guide.md' in e for e in why), why
        assert errors(tier='M') == [], 'contracts and generated paths only bar tier XS'
    finally:
        m.task_context = real
    print('validate: XS one-task prose plan only, no contract or generated path')

if section in ('dispatch', 'gate'):
    out = cli('dispatch', pf, '--task', 'doc', '--phase', 'lead', '--runner', 'print')
    assert 'Tier XS: task doc starts no task lead, task worktree or implement session' in out, out
    assert '--task doc --phase review --sha <sha>' in out and 'tier XS: lead ran task suites' in out, out
    assert 'git add -- docs/guide.md changelog.d/' in out and 'gate ' in out and '# agent' not in out, out
    assert 'worktree add' not in out and len(git('worktree', 'list').splitlines()) == 1, out
    assert 'tier XS' in cli('dispatch', pf, '--task', 'doc', '--phase', 'implement', '--runner', 'print', rc=2)
    write('docs/guide.md', 13); git('add', '--', 'docs/guide.md'); git('commit', '-qm', 'docs: guide')
    sha = git('rev-parse', 'HEAD')
    out = cli('dispatch', pf, '--task', 'doc', '--phase', 'review', '--sha', sha, '--runner', 'print')
    lead = reg['pipeline']['lead_agent']; pair = reg['pipeline']['review_pairing'][lead]
    assert f'Review worker ({pair}) for code written by {lead}' in out, out
    assert f'Tier XS: the run lead committed it on {topic}' in out and 'no worktree of' not in out, out
    assert f"(tier XS: the run lead's checkout of {topic})" in out and "task lead's worktree" not in out, out
    if section == 'dispatch':
        print('dispatch: lead prints the run lead steps, review reads the topic checkout')
    else:
        def verdicts(at):
            cli('verdict', pf, '--task', 'doc', '--phase', 'review', '--sha', at, '--by', pair, '--state', 'PASS')
            cli('verdict', pf, '--task', 'doc', '--phase', 'qa', '--sha', at, '--by', lead, '--state', 'PASS',
                '--note', 'tier XS: lead ran task suites')
        verdicts(sha)
        out = cli('gate', pf, '--no-run-checks')
        assert out.startswith('Gate: READY_FOR_PR') and 'tier XS lead ran task suites' in out, out
        # a committed path the routing snapshot names as a contract end or generated path blocks it (stubbed snapshot)
        real = m.task_context
        try:
            m.task_context = lambda pl, rg, t: ({'repos': [{'repo': 'fixture', 'touched': ['docs'], 'files': [],
                                                  'contracts': [], 'generated_hits': ['docs/guide.md']}]}, None)
            out = cli('gate', pf, '--no-run-checks', rc=1)
            assert 'BLOCKER doc: tier XS, but the committed diff is above XS: generated path docs/guide.md' in out, out
        finally:
            m.task_context = real
        # an oversize committed diff blocks the gate, so does a path that is not prose
        write('docs/guide.md', 60); git('commit', '-qam', 'docs: more'); big = git('rev-parse', 'HEAD')
        verdicts(big)
        out = cli('gate', pf, '--no-run-checks', rc=1)
        assert 'BLOCKER doc: tier XS, but the committed diff is above XS: 50 changed lines > 40' in out, out
        git('reset', '-q', '--hard', sha)
        write('code.py', 2); git('commit', '-qam', 'fix: code'); code = git('rev-parse', 'HEAD')
        verdicts(code)
        out = cli('gate', pf, '--no-run-checks', rc=1)
        assert 'above XS: not prose: code.py' in out, out
        # a 'tier XS' lead QA counts only for a tier-XS task
        git('reset', '-q', '--hard', sha)
        plan['tier'] = 'S'; save(); verdicts(sha)
        cli('verdict', pf, '--task', 'integration:fixture', '--phase', 'qa', '--sha', sha, '--by', pair, '--state', 'PASS')
        out = cli('gate', pf, '--no-run-checks', rc=1)
        assert 'QA recorded as tier XS lead QA, but the task is not tier XS' in out, out
        print('gate: READY_FOR_PR for XS with review PASS and lead QA; oversize or non-prose diff blocks')

if section == 'status':
    # status follows the XS flow like the gate: the run lead's edit and commit on plan.topic, its review dispatch, its
    # own QA after the review PASS, and that QA at the topic HEAD as the integration QA
    lead = reg['pipeline']['lead_agent']; pair = reg['pipeline']['review_pairing'][lead]
    def st():
        o = json.loads(cli('status', '--json', pf))
        return o, o['tasks'][0]
    o, r = st()
    assert r['phase'] == 'pending' and '--task doc --phase lead' in r['next'] and r['branch'] == topic, r
    write('docs/guide.md', 13)
    o, r = st()
    assert r['phase'] == 'implementing' and any('tier XS: the run lead edits the owned paths' in n for n in r['notes']), r
    assert not any('implementation worker' in n for n in r['notes']), r
    git('add', '--', 'docs/guide.md'); git('commit', '-qm', 'docs: guide'); sha = git('rev-parse', 'HEAD')
    o, r = st()
    assert r['phase'] == 'candidate' and f'--task doc --phase review --sha {sha}' in r['next'], r
    assert '--phase verify' not in r['next'], r
    cli('verdict', pf, '--task', 'doc', '--phase', 'review', '--sha', sha, '--by', pair, '--state', 'PASS')
    o, r = st()
    # after the review PASS: the run lead's own QA record, never an integration QA session, and no gate yet
    assert r['phase'] == 'integrated', r
    assert (f'--task doc --phase qa --sha {sha} --state PASS --by {lead}' in r['next']
            and 'tier XS: lead ran task suites' in r['next'] and 'integration:' not in r['next']), r
    assert any('tier XS: the run lead runs the task tier command' in n and 'the task checks' in n for n in r['notes']), r
    assert not any(' gate ' in c for c in o['next']), o['next']
    cli('verdict', pf, '--task', 'doc', '--phase', 'qa', '--sha', sha, '--by', lead, '--state', 'PASS',
        '--note', 'tier XS: lead ran task suites')
    o, r = st()
    # the lead QA at the topic HEAD counts as the integration QA: status says the gate is ready, as the gate does
    assert r['phase'] == 'qa' and r['next'] is None, r
    assert not any('the gate needs it' in n for n in r['notes']), r
    assert any(' gate ' in c for c in o['next']), o['next']
    assert cli('gate', pf, '--no-run-checks').startswith('Gate: READY_FOR_PR')
    # a reviewed fix after the QA: the lead QA is not at the new HEAD, so status asks for it again at that HEAD
    write('docs/guide.md', 14); git('commit', '-qam', 'docs: fix'); fix = git('rev-parse', 'HEAD')
    o, r = st()
    assert r['phase'] == 'candidate' and f'--phase review --sha {fix}' in r['next'], r
    cli('verdict', pf, '--task', 'doc', '--phase', 'review', '--sha', fix, '--by', pair, '--state', 'PASS')
    o, r = st()
    assert r['phase'] == 'integrated' and f'--phase qa --sha {fix} ' in r['next'], r
    assert not any(' gate ' in c for c in o['next']), o['next']
    print('status: XS steps match the gate: review dispatch, lead QA record, gate ready at the topic HEAD')
TIER_XS
if has_case multiwave; then
python3 -B - "$TMP" <<'TEMPLATES'
import pathlib, shutil, subprocess, sys
folder = pathlib.Path(sys.argv[1]) / 'templates'; folder.mkdir()
base = folder / 'base'; base.mkdir()
# No auto maintenance: a detached `git maintenance run --auto` after a commit holds .git/objects/maintenance.lock,
# which vanished mid-copytree on Linux CI (templates/serial missing). Lock files are never copied either.
def git(repo, *args):
    subprocess.run(['git', '-C', str(repo), '-c', 'user.name=test', '-c', 'user.email=t@t', '-c', 'maintenance.auto=false',
                    '-c', 'gc.auto=0', *args], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
def copy(src, dst):
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns('*.lock'))
git(base, 'init', '-q', '-b', 'main')
(base / 'shared.txt').write_text('base')
git(base, 'add', '.'); git(base, 'commit', '-qm', 'base')
sub = folder / 'subtask'; copy(base, sub)
(sub / 'outside.txt').write_text('outside base'); git(sub, 'add', '.'); git(sub, 'commit', '-qm', 'outside base')
serial = folder / 'serial'; copy(base, serial)
(serial / 'ProjectSettings').mkdir()
(serial / 'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.0.0f1')
git(serial, 'add', '.'); git(serial, 'commit', '-qm', 'Unity marker')
TEMPLATES
fi
BG="$TMP/bg"; mkdir -p "$BG"
# bg_case <id> <command...>: run one case, output in $BG/<id>.out, exit code in $BG/<id>.rc
bg_case() {
  local id="$1" begin="$EPOCHREALTIME" rc now elapsed; shift
  "$@" > "$BG/$id.out" 2>&1; rc=$?
  now="$EPOCHREALTIME"; elapsed=$(( ${now/./} - ${begin/./} ))
  printf '%d.%03d' "$((elapsed / 1000000))" "$((elapsed / 1000 % 1000))" > "$BG/$id.time"
  echo "$rc" > "$BG/$id.rc"
}
(
  running=0
  next() {
    [ "$running" -lt "${PIPELINE_TEST_JOBS:-4}" ] || { wait -n; running=$((running - 1)); }
    bg_case "$@" & running=$((running + 1))
  }
  if has_case model-routing; then
  for c in $ROUTING_CASES; do next "routing-$c" env RPG_FACTORY_STATE_DIR="$TMP/state-routing-$c" python3 -B "$TMP/routing-cases.py" "$ROOT" "$TMP" "$c"; done
  fi
  if has_case multiwave; then
  for c in $MULTIWAVE_CASES; do next "multiwave-$c" python3 -B "$TMP/multiwave.py" "$ROOT" "$TMP" "$c"; done
  fi
  if has_case qa-tiers; then next qa-tiers python3 -B "$TMP/qa-tiers.py" "$ROOT" "$TMP"; fi
  if has_case tier-xs; then
  for c in tier validate dispatch gate status; do next "tier-xs-$c" python3 -B "$TMP/tier-xs.py" "$ROOT" "$TMP" "$c"; done
  fi
  wait
) &
BG_PID=$!
# bg_report <name> <id>: PASS when the background case exited 0, else FAIL with its output
bg_report() {
  [ -z "$BG_PID" ] || { wait "$BG_PID"; BG_PID=; }
  if [ "${PIPELINE_TEST_TIMES:-0}" = 1 ]; then printf 'TIME  %s %ss\n' "$2" "$(cat "$BG/$2.time")"; fi
  if [ "$(cat "$BG/$2.rc" 2>/dev/null)" = 0 ]; then pass=$((pass + 1)); echo "PASS  $1"
  else fail=$((fail + 1)); echo "FAIL  $1"; cat "$BG/$2.out" 2>/dev/null; fi
}

if has_case validate; then
case_start
echo "-- validate"
OK=$(plan ok "{$HEAD,\"tasks\":[
 {\"id\":\"gw\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend/gateway/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"c1\",\"repo\":\"client\",\"objective\":\"o\",\"paths\":[\"Assets/A/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"c2\",\"repo\":\"client\",\"objective\":\"o\",\"paths\":[\"Assets/B/\"],\"acceptance\":[\"a\"],\"implementer\":\"codex\"}]}")
expect "valid plan: OK, waves printed" 0 "^OK$" validate "$OK"
X=$(plan x "{$(sed 's/"id":"demo"/"id":"_planner"/' <<<"$HEAD"),\"tasks\":[{\"id\":\"a\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend/gateway/\"],\"acceptance\":[\"a\"]}]}")
expect "plan id _planner is reserved for the planner's specs" 1 "ERROR plan id ._planner. is reserved" validate "$X"
expect "two tasks of a Unity project never share a wave" 0 "^Wave 2: c2$" validate "$OK"
expect "the Unity project is named as no-worktree" 0 "No worktree .*: client" validate "$OK"
X=$(plan overlap "{$HEAD,\"tasks\":[
 {\"id\":\"a\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"b\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend/gateway/x.go\"],\"acceptance\":[\"a\"]}]}")
expect "overlapping owned paths are an error" 1 "ERROR tasks a and b own overlapping paths" validate "$X"
X=$(plan overlap-dep "{$HEAD,\"tasks\":[
 {\"id\":\"a\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"b\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend/gateway/x.go\"],\"acceptance\":[\"a\"],\"deps\":[\"a\"]}]}")
expect "overlap ordered by a dependency is fine" 0 "^Wave 2: b$" validate "$X"
X=$(plan cycle "{$HEAD,\"tasks\":[
 {\"id\":\"a\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"x/\"],\"acceptance\":[\"a\"],\"deps\":[\"b\"]},
 {\"id\":\"b\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"y/\"],\"acceptance\":[\"a\"],\"deps\":[\"a\"]}]}")
expect "dependency cycle is an error" 1 "ERROR dependency cycle among a, b" validate "$X"
X=$(plan same "{$HEAD,\"tasks\":[{\"id\":\"a\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"x/\"],\"acceptance\":[\"a\"],\"implementer\":\"codex\",\"reviewer\":\"codex\"}]}")
expect "reviewer of the implementer's model is an error" 1 "cross-model review needs the pair \(claude\)" validate "$X"
X=$(plan wt "{$HEAD,\"tasks\":[{\"id\":\"a\",\"repo\":\"client\",\"objective\":\"o\",\"paths\":[\"Assets/\"],\"acceptance\":[\"a\"],\"worktree\":true}]}")
expect "worktree: true in a Unity project is an error" 1 "takes no worktree" validate "$X"
X=$(plan res "{$HEAD,\"tasks\":[
 {\"id\":\"a\",\"repo\":\"client\",\"objective\":\"o\",\"paths\":[\"Assets/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"n\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"x/\"],\"acceptance\":[\"a\"],\"resources\":[\"unity-test\"]}]}")
expect "two Unity test users in one wave: queue warning" 0 "WARN  wave 1: a, n share .unity-test." validate "$X"
X=$(plan unknown "{$HEAD,\"tasks\":[{\"id\":\"a\",\"repo\":\"nope\",\"objective\":\"o\",\"paths\":[\"x/\"],\"acceptance\":[\"a\"]}]}")
expect "unknown repo is an error" 1 "neither a registry repo nor in plan.repos" validate "$X"
TOOL=$(plan tool "{$HEAD,\"repos\":{\"tool\":{\"path\":\"tool\",\"base\":\"develop\"}},\"tasks\":[{\"id\":\"t\",\"repo\":\"tool\",\"objective\":\"o\",\"paths\":[\"x/\"],\"acceptance\":[\"a\"]}]}")
expect "unregistered repo with ProjectVersion.txt is a no-worktree repo" 0 "No worktree .*: tool" validate "$TOOL"
# known_failing: [{check, reason}], checks that already fail at the task base
KFT='"tasks":[{"id":"a","repo":"server","objective":"o","paths":["backend/gateway/"],"acceptance":["a"]}]'
X=$(plan kf-ok "{$HEAD,\"known_failing\":[{\"check\":\"tests/foo.test.sh\",\"reason\":\"fails on base\"}],$KFT}")
expect "known_failing: a good plan validates and warns" 0 "^WARN  known failing at base: tests/foo.test.sh - fails on base$" validate "$X"
refute "known_failing: the warning is no error" "^ERROR|INVALID" validate "$X"
X=$(plan kf-str "{$HEAD,\"known_failing\":\"x\",$KFT}")
expect "known_failing: a string is rejected" 1 "known_failing must be an array of \{check, reason\} objects" validate "$X"
for bad in '[{"check":"a"}]' '["a"]' '[{"check":"","reason":"r"}]'; do
  X=$(plan kf-bad "{$HEAD,\"known_failing\":$bad,$KFT}")
  expect "known_failing $bad: rejected" 1 "known_failing\[0\]: needs non-empty string check and reason" validate "$X"
done
X=$(plan kf-key "{$HEAD,\"known_failing\":[{\"check\":\"a\",\"reason\":\"r\",\"x\":1}],$KFT}")
expect "known_failing: an unknown key is rejected" 1 "known_failing\[0\]: unknown key x" validate "$X"
# the schema carries the same shape: items need check and reason, nothing else
if python3 -B - "$ROOT" <<'PY'
import json, pathlib, sys
kf = json.loads(pathlib.Path(sys.argv[1], 'docs/schemas/pipeline-plan.schema.json').read_text(encoding='utf-8'))['properties']['known_failing']
item = kf['items']
assert kf['type'] == 'array' and item['type'] == 'object', kf
assert item['required'] == ['check', 'reason'] and item['additionalProperties'] is False, item
assert all(item['properties'][k]['type'] == 'string' and item['properties'][k]['minLength'] == 1 for k in ('check', 'reason')), item
PY
then pass=$((pass + 1)); echo "PASS  schema: known_failing items require a non-empty check and reason, no other key"
else fail=$((fail + 1)); echo "FAIL  schema: known_failing shape"; fi

case_end validate
fi

if has_case subplan; then
case_start
echo "-- subplan validate"
# subplan <name> <task> <subtasks JSON> [plan file]: a subplan of the plan $OK, or of the named plan file in $TMP
# (named relative to the subplan file)
subplan() { printf '{"schema":"rpg-factory.pipeline-subplan/1","plan":"%s","task":"%s","subtasks":%s}\n' "${4:-ok.json}" "$2" "$3" > "$TMP/sub-$1.json"; echo "$TMP/sub-$1.json"; }
SP=$(subplan ok gw '[
 {"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude","reviewer":"codex"},
 {"id":"s2","objective":"o","paths":["backend/gateway/b.go"],"implementer":"codex","acceptance":["a"],"checks":["c"]},
 {"id":"s3","objective":"o","paths":["backend/gateway/a/x.go"],"implementer":"claude","deps":["s1","s2"]}]')
expect "valid subplan: OK" 0 "^OK$" subplan validate "$SP"
expect "valid subplan: parallel subtasks share wave 1" 0 "^Wave 1: s1, s2$" subplan validate "$SP"
expect "valid subplan: overlap ordered by deps runs in wave 2" 0 "^Wave 2: s3$" subplan validate "$SP"
expect "valid subplan --json: waves and no errors" 0 '"errors": \[\]' subplan validate "$SP" --json
X=$(subplan overlap gw '[
 {"id":"s1","objective":"o","paths":["backend/gateway/"],"implementer":"claude"},
 {"id":"s2","objective":"o","paths":["backend/gateway/x.go"],"implementer":"codex"}]')
expect "overlapping subtask paths are an error" 1 "ERROR subtasks s1 and s2 own overlapping paths \(backend/gateway/ ~ backend/gateway/x.go\)" subplan validate "$X"
X=$(subplan outside gw '[{"id":"s1","objective":"o","paths":["backend/gatewayx/a.go"],"implementer":"claude"}]')
expect "subtask path outside the task's owned paths is an error" 1 "ERROR subtask s1: path backend/gatewayx/a.go is outside the owned paths of task gw" subplan validate "$X"
X=$(subplan wider gw '[{"id":"s1","objective":"o","paths":["backend/"],"implementer":"claude"}]')
expect "subtask path wider than the owned path is an error" 1 "path backend/ is outside the owned paths" subplan validate "$X"
X=$(subplan same gw '[{"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"codex","reviewer":"codex"}]')
expect "same-model reviewer is an error" 1 "ERROR subtask s1: reviewer .codex. is the implementer's model; cross-model review needs the pair \(claude\)" subplan validate "$X"
X=$(subplan noimpl gw '[{"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"gpt"}]')
expect "implementer that is no pipeline agent is an error" 1 "implementer .gpt. is not a pipeline agent" subplan validate "$X"
X=$(subplan cycle gw '[
 {"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude","deps":["s2"]},
 {"id":"s2","objective":"o","paths":["backend/gateway/b/"],"implementer":"claude","deps":["s1"]}]')
expect "subtask dependency cycle is an error" 1 "ERROR dependency cycle among s1, s2" subplan validate "$X"
X=$(subplan unkdep gw '[{"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude","deps":["zz"]}]')
expect "unknown subtask dependency is an error" 1 "ERROR subtask s1: unknown dependency zz" subplan validate "$X"
X=$(subplan unktask nope '[{"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude"}]')
expect "unknown task is an error" 1 "ERROR unknown task nope: plan demo has gw, c1, c2" subplan validate "$X"
X=$(subplan other gw '[{"id":"s1","task":"c1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude"}]')
expect "a subtask of another task is an error" 1 "ERROR subtask s1: belongs to task c1, not gw" subplan validate "$X"
EX=$(plan ex "{$HEAD,\"tasks\":[{\"id\":\"gw\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend/\"],\"exclusions\":[\"backend/shared/proto/\"],\"acceptance\":[\"a\"]}]}")
X=$(subplan excl gw '[{"id":"s1","objective":"o","paths":["backend/shared/proto/wire.proto"],"implementer":"claude"}]')
expect "--plan overrides the subplan's plan: a path inside a task exclusion is an error" 1 "path backend/shared/proto/wire.proto overlaps an exclusion of task gw" subplan validate "$X" --plan "$EX"
expect "without --plan the subplan's own plan applies: that path is outside gw" 1 "path backend/shared/proto/wire.proto is outside the owned paths" subplan validate "$X"
printf '{"schema":"rpg-factory.pipeline-subplan/1","task":"gw","subtasks":[]}\n' > "$TMP/sub-noplan.json"
expect "a subplan without plan and --plan is a usage error" 2 "names no .plan. and no --plan" subplan validate "$TMP/sub-noplan.json"
expect "a missing subplan file is a usage error" 2 "cannot read subplan" subplan validate "$TMP/sub-missing.json"
if python3 - "$ROOT" "$TMP" <<'PY'
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("lint", sys.argv[1] + "/scripts/checks/artifact-lint.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
schema = json.load(open(sys.argv[1] + "/docs/schemas/pipeline-subplan.schema.json", encoding="utf-8"))
assert schema["properties"]["schema"]["const"] == "rpg-factory.pipeline-subplan/1"
for name in ("ok", "same", "cycle", "excl"):
    value = json.load(open(f"{sys.argv[2]}/sub-{name}.json", encoding="utf-8"))
    errors = m.schema_errors(value, schema, schema)
    assert not errors, (name, errors)
bad = json.load(open(f"{sys.argv[2]}/sub-ok.json", encoding="utf-8"))
bad["subtasks"][0]["owner"] = "x"
del bad["subtasks"][1]["implementer"]
assert m.schema_errors(bad, schema, schema), "an unknown field and a missing implementer must fail the schema"
PY
then pass=$((pass + 1)); echo "PASS  pipeline-subplan.schema.json is valid JSON and matches the test subplans"
else fail=$((fail + 1)); echo "FAIL  pipeline-subplan.schema.json"; fi
# path safety: owned paths are compared by spelling, so absolute and `..` paths never reach containment or overlap
X=$(subplan escape gw '[{"id":"s1","objective":"o","paths":["backend/gateway/../../outside.cs"],"implementer":"claude"}]')
expect "a subtask path leaving the task with .. is an error" 1 "ERROR subtask s1: path backend/gateway/../../outside.cs has a .\.\.. segment" subplan validate "$X"
X=$(subplan abs gw '[{"id":"s1","objective":"o","paths":["/etc/passwd"],"implementer":"claude"},{"id":"s2","objective":"o","paths":["C:/x/backend/gateway/a.go"],"implementer":"codex"}]')
expect "an absolute subtask path is an error" 1 "ERROR subtask s1: path /etc/passwd is absolute" subplan validate "$X"
expect "a drive-letter subtask path is an error" 1 "ERROR subtask s2: path C:/x/backend/gateway/a.go is absolute" subplan validate "$X"
X=$(subplan exbypass gw '[{"id":"s1","objective":"o","paths":["backend/x/../shared/proto/wire.proto"],"implementer":"claude"}]')
expect "a .. path cannot bypass a task exclusion" 1 "ERROR subtask s1: path backend/x/../shared/proto/wire.proto has a" subplan validate "$X" --plan "$EX"
refute "a .. path is not reported OK" "^OK$" subplan validate "$X" --plan "$EX"
X=$(subplan ovbypass gw '[{"id":"s1","objective":"o","paths":["backend/gateway/b.go"],"implementer":"claude"},{"id":"s2","objective":"o","paths":["backend/gateway/a/../b.go"],"implementer":"codex"}]')
expect "a .. path cannot hide an overlap" 1 "ERROR subtask s2: path backend/gateway/a/../b.go has a" subplan validate "$X"
X=$(subplan dot gw '[{"id":"s1","objective":"o","paths":["backend/gateway/b.go"],"implementer":"claude"},{"id":"s2","objective":"o","paths":["backend//gateway/./b.go"],"implementer":"codex"}]')
expect "./ and // segments are normalized before the overlap check" 1 "ERROR subtasks s1 and s2 own overlapping paths" subplan validate "$X"
X=$(plan dotdot "{$HEAD,\"tasks\":[{\"id\":\"a\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend/../x/\"],\"exclusions\":[\"/abs/\"],\"acceptance\":[\"a\"]}]}")
expect "plan validate rejects a .. owned path" 1 "ERROR task a: path backend/../x/ has a" validate "$X"
expect "plan validate rejects an absolute exclusion" 1 "ERROR task a: exclusion /abs/ is absolute" validate "$X"
expect "dispatch --paths rejects a .. path" 2 "--paths backend/gateway/../../outside.cs has a" dispatch "$OK" --task gw --phase implement --paths backend/gateway/../../outside.cs
expect "dispatch --paths rejects an absolute path" 2 "--paths C:/etc/x is absolute" dispatch "$OK" --task gw --phase implement --paths C:/etc/x
# malformed subtasks are errors, never silently dropped
X=$(subplan null gw '[null]')
expect "a null subtask is an error" 1 "ERROR subtask #1: must be an object, got null" subplan validate "$X"
refute "a null subtask is not OK" "^OK$" subplan validate "$X"
X=$(subplan mixed gw '[{"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude"},"s2",3]')
expect "a string subtask is an error" 1 'ERROR subtask #2: must be an object, got "s2"' subplan validate "$X"
expect "a number subtask is an error" 1 "ERROR subtask #3: must be an object, got 3" subplan validate "$X"
X=$(subplan types gw '[{"id":"s1","objective":"o","paths":"backend/gateway/a/","implementer":"claude","deps":"s2"},{"id":["s2"],"objective":"o","paths":[1],"implementer":"codex"}]')
expect "paths that are not a list is an error" 1 'ERROR subtask s1: .paths. must be a list of strings, got "backend/gateway/a/"' subplan validate "$X"
expect "deps that are not a list is an error" 1 "ERROR subtask s1: .deps. must be a list of strings" subplan validate "$X"
expect "a non-string id is an error" 1 "ERROR subtask #2: .id. must be a string" subplan validate "$X"
expect "a non-string path is an error" 1 "ERROR subtask #2: .paths. must be a list of strings, got \[1\]" subplan validate "$X"
printf '{"schema":"rpg-factory.pipeline-subplan/1","plan":"ok.json","task":"gw","subtasks":{"id":"s1"}}\n' > "$TMP/sub-obj.json"
expect "subtasks that are not a list is an error" 1 "ERROR .subtasks. must be a non-empty list of objects" subplan validate "$TMP/sub-obj.json"
# one id rule (the schemas' pattern) for subplan validate, dispatch and verdict; unknown keys are errors (additionalProperties)
X=$(subplan badid gw '[{"id":"ui/settings","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude"},{"id":"fix ui","objective":"o","paths":["backend/gateway/b/"],"implementer":"claude"}]')
expect "a subtask id with / is an error" 1 'ERROR subtask "ui/settings": id is not an id' subplan validate "$X"
expect "a subtask id with a space is an error" 1 'ERROR subtask "fix ui": id is not an id' subplan validate "$X"
refute "a malformed subtask id is never OK" "^OK$" subplan validate "$X"
expect "dispatch refuses the subplan with a malformed id" 1 "subplan is invalid.*id is not an id" dispatch "$OK" --task gw --phase implement --subplan "$X" --subtask ui/settings
expect "verdict refuses the same id (one rule)" 2 "--subtask is the id of a subtask of a plan task \(letters, digits" verdict "$OK" --task gw --phase review --sha abc1234 --by codex --state PASS --subtask ui/settings
X=$(subplan keys gw '[{"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude","owner":"me"}]')
expect "an unknown subtask key is an error" 1 "ERROR subtask s1: unknown key .owner." subplan validate "$X"
printf '{"schema":"rpg-factory.pipeline-subplan/1","plan":"ok.json","task":"gw","extra":1,"subtasks":[{"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude"}]}\n' > "$TMP/sub-top.json"
expect "an unknown subplan key is an error" 1 "ERROR unknown key .extra." subplan validate "$TMP/sub-top.json"
X=$(plan badtid "{$HEAD,\"tasks\":[{\"id\":\"a/b\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"x/\"],\"acceptance\":[\"a\"]}]}")
expect "plan validate: a task id with / is an error (same rule)" 1 'ERROR task id "a/b" is not an id' validate "$X"
X=$(plan intclash "{$HEAD,\"tasks\":[{\"id\":\"integration_server\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"x/\"],\"acceptance\":[\"a\"]}]}")
expect "plan validate: task integration_<repo> would share the integration QA's verdict file" 1 "ERROR task id .integration_server. is reserved: the integration QA of repo server" validate "$X"
# a no-worktree repo runs its subtasks one after another: the registry flag and the Unity marker
X=$(subplan par gw '[{"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude"},{"id":"s2","objective":"o","paths":["backend/gateway/b/"],"implementer":"codex"}]')
expect "disjoint subtasks of a worktree repo share a wave" 0 "^Wave 1: s1, s2$" subplan validate "$X"
python3 -c 'import json,sys; r=json.load(open(sys.argv[1],encoding="utf-8")); r["repos"]["server"]["worktrees"]=False; r["repos"]["server"]["worktrees_reason"]="test flag"; json.dump(r,open(sys.argv[2],"w",encoding="utf-8"))' "$ROOT/registry.json" "$TMP/reg-nowt.json"
expect "registry worktrees=false: disjoint subtasks run one per wave" 0 "^Wave 2: s2$" --registry "$TMP/reg-nowt.json" subplan validate "$X"
expect "registry worktrees=false: the reason is printed" 0 "One subtask at a time \(no worktree: test flag\)" --registry "$TMP/reg-nowt.json" subplan validate "$X"
refute "registry worktrees=false: never two subtasks in one wave" "^Wave 1: s1, s2$" --registry "$TMP/reg-nowt.json" subplan validate "$X"
X=$(subplan marker t '[{"id":"s1","objective":"o","paths":["x/a/"],"implementer":"claude"},{"id":"s2","objective":"o","paths":["x/b/"],"implementer":"codex"}]')
expect "Unity marker (unregistered repo): disjoint subtasks run one per wave" 0 "^Wave 2: s2$" subplan validate "$X" --plan "$TOOL"
expect "Unity marker: the marker is named" 0 "One subtask at a time \(no worktree: ProjectSettings/ProjectVersion.txt present" subplan validate "$X" --plan "$TOOL"
expect "Unity marker --json: the serial reason is reported" 0 '"serial": "ProjectSettings' subplan validate "$X" --plan "$TOOL" --json
# placement: shared (default) or child (an Orca child of the task worktree, with a reason); never child without worktrees
SPC=$(subplan child gw '[
 {"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude","placement":"shared"},
 {"id":"s2","objective":"o","paths":["backend/gateway/b.go"],"implementer":"codex","placement":"child","reason":"runs the full suite","checks":["c"]}]')
expect "placement shared and child (with a reason): OK" 0 "^OK$" subplan validate "$SPC"
X=$(subplan child-noreason gw '[{"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude","placement":"child"}]')
expect "placement child without a reason is an error" 1 "ERROR subtask s1: placement child needs a .reason." subplan validate "$X"
X=$(subplan child-bad gw '[{"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude","placement":"top"}]')
expect "an unknown placement is an error" 1 "ERROR subtask s1: placement .top. is not one of shared, child" subplan validate "$X"
X=$(subplan child-unity t '[{"id":"s1","objective":"o","paths":["x/a/"],"implementer":"claude","placement":"child","reason":"r"}]')
expect "placement child in a Unity project is an error" 1 "ERROR subtask s1: placement child in repo .tool., which takes no worktree" subplan validate "$X" --plan "$TOOL"
expect "placement child with registry worktrees=false is an error" 1 "placement child in repo .server., which takes no worktree \(test flag\)" --registry "$TMP/reg-nowt.json" subplan validate "$SPC"
if python3 - "$ROOT" "$SPC" <<'PY'
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("lint", sys.argv[1] + "/scripts/checks/artifact-lint.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
schema = json.load(open(sys.argv[1] + "/docs/schemas/pipeline-subplan.schema.json", encoding="utf-8"))
value = json.load(open(sys.argv[2], encoding="utf-8"))
assert not m.schema_errors(value, schema, schema)
value["subtasks"][0]["placement"] = "top"
assert m.schema_errors(value, schema, schema), "an unknown placement must fail the schema"
PY
then pass=$((pass + 1)); echo "PASS  pipeline-subplan.schema.json knows placement and reason"
else fail=$((fail + 1)); echo "FAIL  pipeline-subplan.schema.json placement"; fi
# a UTF-8 BOM (PowerShell's Out-File / Set-Content) is no read error, for plans and subplans
printf '\xef\xbb\xbf' > "$TMP/bom.json"; cat "$OK" >> "$TMP/bom.json"
printf '\xef\xbb\xbf{"schema":"rpg-factory.pipeline-subplan/1","plan":"bom.json","task":"gw","subtasks":[{"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude"}]}\n' > "$TMP/sub-bom.json"
expect "a plan with a UTF-8 BOM validates" 0 "^OK$" validate "$TMP/bom.json"
expect "a subplan (and its plan) with a UTF-8 BOM validates" 0 "^OK$" subplan validate "$TMP/sub-bom.json"
expect "dispatch reads a plan with a UTF-8 BOM" 0 "^Task lead for task gw" dispatch "$TMP/bom.json" --task gw --phase lead
expect "the task-lead spec names the subplan schema, plan and task" 0 "pipeline-subplan.schema.json; .plan. is .*ok.json, .task. is gw" dispatch "$OK" --task gw --phase lead

case_end subplan
fi

if has_case dispatch; then
case_start
echo "-- dispatch"
expect "server task lead: git creates a no-track task worktree" 0 "^git -C .* worktree add --no-track -b feat/core/demo-gw .*feat-core-demo-gw'? develop" dispatch "$OK" --task gw --phase lead --runner orca
refute "the task lead is no nested Orca worker (no worker-start)" "^orca orchestration worker-start" dispatch "$OK" --task gw --phase lead --runner orca
expect "task lead of a claude-implementer task is claude" 0 "^orca agent launch --agent claude --worktree .* --prompt " dispatch "$OK" --task gw --phase lead --runner orca
expect "task lead of a codex-implementer task is still claude (pipeline.lead_agent)" 0 "^orca agent launch --agent claude " dispatch "$OK" --task c2 --phase lead --runner orca
refute "task lead of a codex-implementer task is never codex" "^orca .*--agent codex" dispatch "$OK" --task c2 --phase lead --runner orca
expect "--agent codex on --phase lead warns" 0 "the task lead is claude \(lead_agent\); --agent codex is ignored" dispatch "$OK" --task gw --phase lead --runner orca --agent codex
expect "--agent codex on --phase lead still prints --agent claude" 0 "^orca agent launch --agent claude --worktree .* --prompt " dispatch "$OK" --task gw --phase lead --runner orca --agent codex
refute "--agent codex on --phase lead never launches codex" "^orca .*--agent codex" dispatch "$OK" --task gw --phase lead --runner orca --agent codex
expect "the codex task's implement session keeps its implementer" 0 "^orca orchestration worker-start .*--agent codex" dispatch "$OK" --task c2 --phase implement --runner orca
python3 -c 'import json,sys; r=json.load(open(sys.argv[1],encoding="utf-8")); r["pipeline"].pop("lead_agent",None); json.dump(r,open(sys.argv[2],"w",encoding="utf-8"))' "$ROOT/registry.json" "$TMP/reg-nolead.json"
expect "registry without pipeline.lead_agent: the task lead defaults to claude" 0 "^orca agent launch --agent claude " --registry "$TMP/reg-nolead.json" dispatch "$OK" --task c2 --phase lead --runner orca
expect "task lead creates its own Orca Run" 0 "create your OWN Run \(.orca orchestration run-create" dispatch "$OK" --task gw --phase lead
expect "task lead runs tier S and docs-only QA after review" 0 "For tier S and docs-only tasks, the lead runs the tier command after the review and records QA" dispatch "$OK" --task gw --phase lead
expect "task lead reports to the run lead's Orca run" 0 "orca orchestration send --to run:R42 --type status --subject .task done: gw" dispatch "$OK" --task gw --phase lead --report-to R42
expect_spec "task lead records its durable report with the report verb before the message" "<pipeline> report <plan> --task gw --sha <HEAD> --body-file <file>.* then report to the run lead \(.orca orchestration send" dispatch "$OK" --task gw --phase lead --report-to R42 --runner orca
expect "--report-to accepts Orca's run:<id> form" 0 "orca orchestration send --to run:R42 --type status" dispatch "$OK" --task gw --phase lead --report-to run:R42
refute "--report-to run:<id> never doubles the prefix" "run:run:" dispatch "$OK" --task gw --phase lead --report-to run:R42
expect "--report-to goes only with the lead" 2 "--report-to .* goes with --phase lead" dispatch "$OK" --task gw --phase implement --report-to R42
for pat in '"owned_paths": \[' '"backend/gateway/"' '"branch": "feat/core/demo-gw"' '"acceptance": \[' "subplan validate <subplan.json>" \
  "ONE fresh session in this task worktree" "--phase implement --subplan <subplan.json> --subtask <id>" "does NOT commit \(one shared index\)" \
  "you commit it with explicit paths" "one verify session .<dispatch> --phase verify" "\(codex for claude" \
  "verdict --phase verify" "On FAIL start a fresh fix session" "worker-release" \
  "<dispatch> = .<pipeline> dispatch <plan> --task gw." "placement child .*merge that branch into feat/core/demo-gw and remove the child at once" \
  "never create or remove a child worktree while a full tests/run-all.sh runs" \
  "branch feat/core/demo-gw, HEAD SHA, your Orca Run id" "the moment it reports, its candidate is superseded or it stops - not at task end" "status <plan> --orca-run <your run id>" \
  "Never push, tag, merge into the integration branch or remove the task worktree"; do
  expect "task-lead spec: $pat" 0 "$pat" dispatch "$OK" --task gw --phase lead
done
expect "Unity task lead: an agent launched in the main checkout" 0 "^orca agent launch --agent claude --worktree '?path:[^' ]*IndieRPGMMOAdventure'?" dispatch "$OK" --task c1 --phase lead --runner orca
refute "Unity task lead never creates a worktree" "new-top-level|--base-branch|worktree create" dispatch "$OK" --task c1 --phase lead --runner orca
refute "Unity task lead in the agent fallback never creates a worktree" '"isolation"|Create your own worktree' dispatch "$OK" --task c1 --phase lead --runner agent
expect "Unity task lead runs subtasks one after another" 0 "Subtasks, review and QA run one after another" dispatch "$OK" --task c1 --phase lead
refute "Unity review never creates a worktree" "new-top-level|--base-branch|worktree create" dispatch "$OK" --task c2 --phase review --sha abc1234 --runner orca
refute "Unity per-task qa never creates a worktree" "new-top-level|--base-branch|worktree create" dispatch "$OK" --task c1 --phase qa --sha abc1234 --runner orca
expect "Unity task lead works on the integration branch in the main checkout" 0 "No worktree: .*on branch feat/core/demo;" dispatch "$OK" --task c1 --phase lead
refute "Unity task lead rules 7 and 8 never mention removing a worktree" "^[78]\..*remove(s)? the (task )?worktree" dispatch "$OK" --task c1 --phase lead
expect "Unity task lead rule 8: the main checkout is never removed" 0 "^8\. Never push, merge or tag: .*the main checkout is never removed" dispatch "$OK" --task c1 --phase lead
# the subagent rule of each session prompt comes from registry pipeline.subagents (scripts/lib/subagent_policy.py rule)
expect "task lead: rule 7 is the lead's subagent rule" 0 "^7\. Subagents: read-only scouts only, at most 2 in parallel, only when the task needs a broad search across the worktree.*use Agent subagent_type rpg-factory:factory-explorer with model sonnet \(claude-sonnet-5-5\)\.$" dispatch "$OK" --task gw --phase lead
expect "task lead: the push rule is now rule 8, after the subagent rule" 0 "^8\. Never push, tag, merge into the integration branch" dispatch "$OK" --task gw --phase lead
expect_spec "task lead (orca handoff spec): rule 7 is the subagent rule" "^7\. Subagents: read-only scouts only, at most 2 in parallel" dispatch "$OK" --task gw --phase lead --runner orca
expect_spec "task lead retains delivery reference" "Task lead for task .*references/delivery\.md" dispatch "$OK" --task gw --phase lead --runner orca
expect "task lead --runner agent runs claude: the claude subagent clause" 0 "7\. Subagents: read-only scouts only, at most 2 in parallel.*use Agent subagent_type rpg-factory:factory-explorer with model sonnet \(claude-sonnet-5-5\)" dispatch "$OK" --task gw --phase lead --runner agent
expect "Unity task lead: rule 7 is the subagent rule" 0 "^7\. Subagents: read-only scouts only, at most 2 in parallel" dispatch "$OK" --task c1 --phase lead
refute "Unity task lead prompt has no double period after the reason" "\.\. " dispatch "$OK" --task c1 --phase lead
# no_new_worktree <name> <args...>: exit 1, names the branch and `--phase lead`, and `git worktree list` is unchanged
no_new_worktree() {
  local name="$1"; shift; local before after out rc
  before=$(git -C "$S" worktree list --porcelain); out=$(python3 -B "$P" "$@" 2>&1); rc=$?; after=$(git -C "$S" worktree list --porcelain)
  if [ "$rc" = 1 ] && grep -q "has the task branch feat/core/demo-gw checked out" <<<"$out" && grep -q -- "--phase lead" <<<"$out" \
     && ! grep -q "new-top-level" <<<"$out" && [ "$before" = "$after" ]; then pass=$((pass + 1)); echo "PASS  $name"
  else fail=$((fail + 1)); echo "FAIL  $name (rc=$rc)"; sed 's/^/      /' <<<"$out" | head -10; fi
}
no_new_worktree "implement without the task worktree: error, no worktree" dispatch "$OK" --task gw --phase implement --runner orca
no_new_worktree "review without the task worktree: error, no worktree" dispatch "$OK" --task gw --phase review --sha abc1234 --runner orca
no_new_worktree "per-task qa without the task worktree: error, no worktree" dispatch "$OK" --task gw --phase qa --sha abc1234 --runner orca
no_new_worktree "agent fallback without the task worktree: error too" dispatch "$OK" --task gw --phase implement --runner agent
expect "client implement: main checkout, no new worktree" 0 "--agent claude --worktree '?path:[^' ]*IndieRPGMMOAdventure'?" dispatch "$OK" --task c1 --phase implement --runner orca
refute "client implement has no creation flags" "new-top-level|--base-branch|worktree create" dispatch "$OK" --task c1 --phase implement --runner orca
expect "Unity implement without --paths is a sub-session that does not commit" 0 "Do NOT commit, stage or stash" dispatch "$OK" --task c1 --phase implement
refute "Unity implement never prints a committing worker" "commit explicit|Implementation worker \(" dispatch "$OK" --task c1 --phase implement
refute "Unity implement in the agent fallback never commits or creates a worktree" "commit explicit|isolation|Create your own worktree" dispatch "$OK" --task c1 --phase implement --runner agent
expect_spec "registry worktrees=false: implement does not commit" "Do NOT commit, stage or stash" --registry "$TMP/reg-nowt.json" dispatch "$OK" --task gw --phase implement --runner orca
refute "registry worktrees=false: implement never creates a worktree" "new-top-level|--base-branch|worktree create" --registry "$TMP/reg-nowt.json" dispatch "$OK" --task gw --phase implement --runner orca
refute_spec "registry worktrees=false: the implement spec never commits" "commit explicit" --registry "$TMP/reg-nowt.json" dispatch "$OK" --task gw --phase implement --runner orca
expect_spec "Unity marker (unregistered repo): implement does not commit" "Do NOT commit, stage or stash" dispatch "$TOOL" --task t --phase implement --runner orca
refute "Unity marker: implement never creates a worktree" "new-top-level|--base-branch|worktree create" dispatch "$TOOL" --task t --phase implement --runner orca
refute_spec "Unity marker: the implement spec never commits" "commit explicit" dispatch "$TOOL" --task t --phase implement --runner orca
expect "next Unity task warns until the previous task has QA PASS" 0 "task c1 has no QA PASS yet" dispatch "$OK" --task c2 --phase implement
expect "review of codex's code goes to claude, read-only in the main checkout" 0 "--agent claude --worktree '?path:" dispatch "$OK" --task c2 --phase review --sha abc1234 --runner orca
expect "review needs a candidate SHA" 2 "review needs --sha" dispatch "$OK" --task gw --phase review
expect "per-task qa in the Unity project" 0 "task c1" dispatch "$OK" --task c1 --phase qa --sha abc1234
expect "agent fallback task lead for another repo: creates the task worktree from the base" 0 "Create your own worktree first: .*-b feat/core/demo-gw develop" dispatch "$OK" --task gw --phase lead --runner agent
refute "agent fallback for the Unity project has no isolation" '"isolation"' dispatch "$OK" --task c1 --phase implement --runner agent
# the task lead's worktree exists: every session of the task joins it
git -C "$S" worktree add -q "$TMP/demo-gw" -b feat/core/demo-gw develop 2>/dev/null
WT="--worktree '?path:[^' ]*demo-gw'?"
expect "implement joins the task worktree" 0 "--agent claude $WT" dispatch "$OK" --task gw --phase implement --runner orca
refute "implement never creates a worktree" "new-top-level|--base-branch" dispatch "$OK" --task gw --phase implement --runner orca
expect "implement sub-session does not commit" 0 "Do NOT commit, stage or stash: one shared index" dispatch "$OK" --task gw --phase implement
expect "implement runs no suites, only a syntax check" 0 "Run no test suites; only a syntax check of the files you edited" dispatch "$OK" --task gw --phase implement
expect "implement sub-session reports changed paths and check counts to the task lead" 0 "Report to the task lead: changed paths" dispatch "$OK" --task gw --phase implement
expect "subtask paths narrow the sub-session" 0 '"subtask_paths": \[' dispatch "$OK" --task gw --phase implement --paths backend/gateway/x.go
expect "a subtask session may name its own model" 0 "--agent codex $WT" dispatch "$OK" --task gw --phase implement --paths backend/gateway/x.go --agent codex --runner orca
expect "subtask paths inside a task exclusion are refused" 2 "--paths backend/shared/proto/wire.proto overlap the exclusions of task gw: backend/shared/proto/" dispatch "$EX" --task gw --phase implement --paths backend/shared/proto/wire.proto
expect "subtask paths containing a task exclusion are refused" 2 "--paths backend/shared/ overlap the exclusions of task gw" dispatch "$EX" --task gw --phase implement --paths backend/gateway/x.go backend/shared/
refute "an excluded subtask path never reaches a worker" "subtask_paths|orca orchestration" dispatch "$EX" --task gw --phase implement --paths backend/shared/proto/wire.proto --runner orca
expect "subtask paths outside the owned paths are refused" 2 "--paths backend/other outside the owned paths of task gw" dispatch "$OK" --task gw --phase implement --paths backend/other
expect "--paths goes only with implement" 2 "--paths .* goes with --phase implement" dispatch "$OK" --task gw --phase review --sha abc1234 --paths backend/gateway/x.go
expect "review of claude's code goes to codex, in the task worktree" 0 "--agent codex $WT" dispatch "$OK" --task gw --phase review --sha abc1234 --runner orca
refute "review never creates a worktree" "new-top-level|--base-branch" dispatch "$OK" --task gw --phase review --sha abc1234 --runner orca
expect "review checks HEAD is the candidate in the shared worktree" 0 "who keeps HEAD at the candidate: first check .git rev-parse HEAD. equals it" dispatch "$OK" --task gw --phase review --sha abc1234
expect "per-task qa in a worktree repo runs in the task worktree" 0 "--agent codex $WT" dispatch "$OK" --task gw --phase qa --sha abc1234 --runner orca
refute "per-task qa never creates a worktree" "new-top-level|--base-branch" dispatch "$OK" --task gw --phase qa --sha abc1234 --runner orca
expect "per-task qa names the task" 0 "QA worker .*branch feat/core/demo-gw, task gw" dispatch "$OK" --task gw --phase qa --sha abc1234
expect "a second task lead resumes in the existing task worktree" 0 "^orca agent launch --agent claude $WT" dispatch "$OK" --task gw --phase lead --runner orca
refute "a resumed task lead prints no worktree add and no orca worktree set" "worktree add|worktree set|worktree create" dispatch "$OK" --task gw --phase lead --runner orca
expect "agent fallback for a codex reviewer starts a fresh Claude session" 0 '"subagent_type": "general-purpose"' dispatch "$OK" --task gw --phase review --sha abc1234 --runner agent
expect "agent fallback for a codex reviewer says SAME_MODEL in the prompt" 0 'SAME_MODEL: this session was planned for codex; the Agent-tool fallback runs Claude only' dispatch "$OK" --task gw --phase review --sha abc1234 --runner agent
expect "agent fallback for a codex reviewer says SAME_MODEL on stderr" 0 "starts a fresh Claude session for this codex session: SAME_MODEL" dispatch "$OK" --task gw --phase review --sha abc1234 --runner agent
refute "agent fallback never uses the codex subagent" "codex:codex-rescue" dispatch "$OK" --task gw --phase review --sha abc1234 --runner agent
refute "agent fallback for a claude session is not SAME_MODEL" "SAME_MODEL: this session" dispatch "$OK" --task gw --phase implement --runner agent
expect "agent fallback for a codex subtask session: Claude, SAME_MODEL" 0 'SAME_MODEL: this session was planned for codex' dispatch "$OK" --task gw --phase implement --paths backend/gateway/x.go --agent codex --runner agent
expect "agent fallback names the existing task worktree" 0 "Placement: work in the existing checkout .*demo-gw" dispatch "$OK" --task gw --phase review --sha abc1234 --runner agent
expect "implement (shared, claude): the implement subagent rule" 0 "^Subagents: read-only scouts only, at most 2 in parallel, only when the change needs a search across many files.*use Agent subagent_type rpg-factory:factory-explorer with model sonnet \(claude-sonnet-5-5\)\.$" dispatch "$OK" --task gw --phase implement
expect "implement (shared, codex implementer): the codex subagent clause" 0 "^Subagents: read-only scouts only, at most 2 in parallel, only when the change needs a search across many files.*run them on gpt-6.1-terra with effort medium\.$" dispatch "$OK" --task c2 --phase implement
expect_spec "implement (shared, orca spec): the subagent rule" "^Subagents: read-only scouts only, at most 2 in parallel, only when the change needs a search" dispatch "$OK" --task gw --phase implement --runner orca
expect "implement (child): the implement subagent rule" 0 "^Subagents: read-only scouts only, at most 2 in parallel, only when the change needs a search across many files.*use Agent subagent_type rpg-factory:factory-explorer with model sonnet \(claude-sonnet-5-5\)\.$" dispatch "$OK" --task gw --phase implement --placement child
expect "implement of a codex subtask session --runner agent: the claude clause (the session runs claude)" 0 "Subagents: read-only scouts only, at most 2 in parallel, only when the change needs a search.*use Agent subagent_type rpg-factory:factory-explorer with model sonnet \(claude-sonnet-5-5\)" dispatch "$OK" --task gw --phase implement --paths backend/gateway/x.go --agent codex --runner agent
refute "implement of a codex subtask session --runner agent: no codex clause" "run them on gpt-6.1-terra with effort medium" dispatch "$OK" --task gw --phase implement --paths backend/gateway/x.go --agent codex --runner agent
expect "review by codex names the reviewer's own model (gpt-6.1-terra), the verdict stays the reviewer's" 0 "^Subagents: read-only scouts only, at most 3 in parallel, only when a claim in the diff needs a check across many files.*they stay on your own agent, codex \(run them on gpt-6.1-terra with effort medium\), never the other agent, and the verdict stays yours\.$" dispatch "$OK" --task gw --phase review --sha abc1234
expect "review by claude names claude's Sonnet alias" 0 "^Subagents: read-only scouts only, at most 3 in parallel, only when a claim in the diff.*they stay on your own agent, claude \(use Agent subagent_type rpg-factory:factory-explorer with model sonnet \(claude-sonnet-5-5\)\), never the other agent, and the verdict stays yours\.$" dispatch "$OK" --task c2 --phase review --sha abc1234
expect "review --runner agent turns a codex review into claude SAME_MODEL: the rule names claude's Sonnet alias" 0 "Subagents: read-only scouts only, at most 3 in parallel, only when a claim in the diff.*they stay on your own agent, claude \(use Agent subagent_type rpg-factory:factory-explorer with model sonnet \(claude-sonnet-5-5\)\), never the other agent, and the verdict stays yours\." dispatch "$OK" --task gw --phase review --sha abc1234 --runner agent
refute "review --runner agent: the rule never names the codex model" "your own agent, codex" dispatch "$OK" --task gw --phase review --sha abc1234 --runner agent
expect_spec "review (orca spec): the review rule" "^Subagents: read-only scouts only, at most 3 in parallel, only when a claim in the diff" dispatch "$OK" --task gw --phase review --sha abc1234 --runner orca
expect "task QA: no subagents" 0 "^Subagents: none in this session \(never: QA runs the checks itself and grades the evidence\)\.$" dispatch "$OK" --task gw --phase qa --sha abc1234
expect "task QA --runner agent: no subagents" 0 "Subagents: none in this session" dispatch "$OK" --task gw --phase qa --sha abc1234 --runner agent
expect_spec "task QA (orca spec): no subagents" "^Subagents: none in this session" dispatch "$OK" --task gw --phase qa --sha abc1234 --runner orca
SPEC_RULE='Your spec is complete: read skills/delivery/references/delivery\.md only when blocked by something the spec does not cover\.'
for phase in 'implement' 'implement --placement child' 'review --sha abc1234' 'verify --sha abc1234' 'qa --sha abc1234'; do
  expect_spec "$phase: spec is complete" "$SPEC_RULE" dispatch "$OK" --task gw --phase $phase --runner orca
  pp_spec dispatch "$OK" --task gw --phase $phase --runner orca
  if [ "$RC" = 0 ] && [ "$SRC" = 0 ] && ! grep -vF 'Your spec is complete: read skills/delivery/references/delivery.md only when blocked by something the spec does not cover.' <<<"$SPEC" | grep -q 'delivery\.md'; then
    pass=$((pass + 1)); echo "PASS  $phase: no other delivery reference"
  else fail=$((fail + 1)); echo "FAIL  $phase: another delivery reference or missing spec"; fi
done
refute_spec "non-plugin review does not name plugin checklist" 'plugin-review\.md' dispatch "$OK" --task gw --phase review --sha abc1234 --runner orca
expect_spec "non-plugin review retains routed checklist" "the routed lead skill's review checklist" dispatch "$OK" --task gw --phase review --sha abc1234 --runner orca
PLUGIN=$(plan plugin-prompt "{$HEAD,\"repos\":{\"plugin\":{\"path\":\"tool\",\"base\":\"develop\"}},\"tasks\":[{\"id\":\"t\",\"repo\":\"plugin\",\"objective\":\"o\",\"paths\":[\"x/\"],\"acceptance\":[\"a\"]}]}")
expect_spec "plugin key review names plugin checklist" 'skills/factory-core/references/plugin-review\.md' dispatch "$PLUGIN" --task t --phase review --sha abc1234 --runner orca
expect_spec "plugin key verify names plugin checklist" 'skills/factory-core/references/plugin-review\.md' dispatch "$PLUGIN" --task t --phase verify --sha abc1234 --runner orca
refute_spec "non-plugin verify does not name plugin checklist" 'plugin-review\.md' dispatch "$OK" --task gw --phase verify --sha abc1234 --runner orca
mkdir -p "$T/.claude-plugin"; printf '{}\n' > "$T/.claude-plugin/plugin.json"
expect_spec "plugin manifest review names plugin checklist" 'skills/factory-core/references/plugin-review\.md' dispatch "$TOOL" --task t --phase review --sha abc1234 --runner orca
rm "$T/.claude-plugin/plugin.json"; rmdir "$T/.claude-plugin"
# a checkout with tests/run-all.sh (no --list-suites: no suite list, no bash run) gets the tier command and the CI clause
mkdir -p "$T/tests"; echo 'exit 0' > "$T/tests/run-all.sh"
TASK_QA='Task QA: never a full tests/run-all\.sh run; CI runs the affected suites per change and ci-ok must be green before merging'
expect_spec "run-all repo verify spec: the task QA CI clause" "$TASK_QA" dispatch "$PLUGIN" --task t --phase verify --sha abc1234 --runner orca
expect_spec "run-all repo task QA spec: the task QA CI clause" "$TASK_QA" dispatch "$PLUGIN" --task t --phase qa --sha abc1234 --runner orca
rm "$T/tests/run-all.sh"; rmdir "$T/tests"
# the run lead's RPG_FACTORY_WORKSPACE reaches the implement, verify and QA specs (a worker may not inherit it);
# unset or empty, no such line
TEST_ENV="^Test environment: set RPG_FACTORY_WORKSPACE=[^ ]*ws'? for every test run \(the run lead's environment sets it; a worker session may not inherit it\)\.$"
for phase in 'implement' 'verify --sha abc1234' 'qa --sha abc1234'; do
  expect_spec "$phase spec: the run lead's RPG_FACTORY_WORKSPACE for every test run" "$TEST_ENV" dispatch "$TOOL" --task t --phase $phase --runner orca
  RPG_FACTORY_WORKSPACE= refute_spec "$phase spec: an empty RPG_FACTORY_WORKSPACE adds no test environment line" "Test environment: set RPG_FACTORY_WORKSPACE" dispatch "$TOOL" --task t --phase $phase --runner orca
done
expect_spec "worktree repo implement spec: the test environment line" "$TEST_ENV" dispatch "$OK" --task gw --phase implement --runner orca
# Session notes reach each kind of session; the lead also forwards them in its dispatch definition.
unset RPG_FACTORY_SESSION_NOTE
for phase in 'implement' 'verify --sha abc1234' 'lead --report-to run:x'; do
  RPG_FACTORY_SESSION_NOTE= expect_spec "$phase spec: first session note" '^Session note: one$' dispatch "$TOOL" --task t --phase $phase --runner orca --note one --note 'two  words'
  RPG_FACTORY_SESSION_NOTE= expect_spec "$phase spec: normalized second session note" '^Session note: two words$' dispatch "$TOOL" --task t --phase $phase --runner orca --note one --note 'two  words'
  RPG_FACTORY_SESSION_NOTE= refute_spec "$phase spec: no session note when empty" 'Session note:' dispatch "$TOOL" --task t --phase $phase --runner orca
  RPG_FACTORY_SESSION_NOTE= refute_spec "$phase spec: no session note forwarding rule when empty" '^9\. Session notes:' dispatch "$TOOL" --task t --phase $phase --runner orca
done
refute_spec "implement spec: an unset session note adds no note" 'Session note:' dispatch "$TOOL" --task t --phase implement --runner orca
for phase in 'review --sha abc1234' 'qa --sha abc1234'; do
  RPG_FACTORY_SESSION_NOTE='env note' expect_spec "$phase spec: environment session note" '^Session note: env note$' dispatch "$TOOL" --task t --phase $phase --runner orca
done
RPG_FACTORY_SESSION_NOTE= expect_spec "lead spec: dispatch forwards quoted notes" "<dispatch>.* --note one --note 'two words'" dispatch "$TOOL" --task t --phase lead --report-to run:x --runner orca --note one --note 'two  words'
RPG_FACTORY_SESSION_NOTE='env note' expect_spec "lead spec: dispatch forwards environment note" "<dispatch>.* --note one --note 'env note'" dispatch "$TOOL" --task t --phase lead --report-to run:x --runner orca --note one
RPG_FACTORY_SESSION_NOTE= expect_spec "lead spec: session note forwarding rule" '^9\. Session notes: <dispatch> carries the session notes below as --note; keep them on every session you dispatch\.$' dispatch "$TOOL" --task t --phase lead --report-to run:x --runner orca --note one --note 'two  words'
RPG_FACTORY_SESSION_NOTE= expect "dispatch: empty session note is rejected" 2 - dispatch "$TOOL" --task t --phase implement --runner orca --note ''
if python3 -B - "$ROOT" <<'PY'
import importlib.util, shlex, sys
spec = importlib.util.spec_from_file_location("fp", sys.argv[1] + "/scripts/factory-pipeline.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
alias = r'C:\Users\u\AppData\Local\Microsoft\WindowsApps\python3.exe'
exe = r'C:\Py\python.exe'
which = lambda n: alias
line = m.python_alias_line('win32', which, exe)
assert line.startswith('Python: python3 here is likely the Microsoft Store alias') and alias in line and shlex.quote(exe) in line
assert m.python_alias_line('linux', which, exe) == ''
assert m.python_alias_line('win32', lambda n: r'C:\Py\python3.exe', exe) == ''
assert m.python_alias_line('win32', lambda n: None, exe) == ''
PY
then pass=$((pass + 1)); echo "PASS  python3 Store alias detection uses platform and resolved path"
else fail=$((fail + 1)); echo "FAIL  python3 Store alias detection uses platform and resolved path"; fi
# pp_spec splits only the prompt line: a stderr line with an unbalanced ' and " cannot break it
printf 'stub spec: quotes survive\n' > "$TMP/pp-stub-spec.md"
cat > "$TMP/pp-stub.py" <<'PPSTUB'
import shlex, sys
print("factory-pipeline: the implementer's model said \"hi", file=sys.stderr, flush=True)
print("orca orchestration worker-start --agent claude --prompt "
      + shlex.quote("Read your task spec at " + sys.argv[2] + " and follow it."), flush=True)
PPSTUB
P_SAVED="$P"; P="$TMP/pp-stub.py"
expect_spec "pp_spec: a stderr line with quote characters does not break the spec read" "^stub spec: quotes survive$" pp-stub-quote "$TMP/pp-stub-spec.md"
P="$P_SAVED"
expect "Unity task QA: no subagents" 0 "^Subagents: none in this session" dispatch "$OK" --task c1 --phase qa --sha abc1234
refute "QA never offers a scout" "read-only scouts" dispatch "$OK" --task gw --phase qa --sha abc1234
# known_failing: the lead, QA and verify specs name the checks and the FAIL_AT_BASE rule; a plan without it adds nothing
KFP=$(plan kf-spec "{$(sed 's/"id":"demo"/"id":"demokf"/' <<<"$HEAD"),\"known_failing\":[{\"check\":\"tests/foo.test.sh\",\"reason\":\"fails on base\"}],\"tasks\":[{\"id\":\"gw\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend/gateway/\"],\"acceptance\":[\"a\"]}]}")
for ph in "--phase lead" "--phase qa --sha abc1234" "--phase verify --sha abc1234"; do
  expect_spec "known_failing: the $ph spec lists the checks" "^Known failing at base \(plan known_failing\):$" dispatch "$KFP" --task gw $ph --runner orca
  expect_spec "known_failing: the $ph spec names the check and reason" "^- tests/foo\.test\.sh: fails on base$" dispatch "$KFP" --task gw $ph --runner orca
  expect_spec "known_failing: the $ph spec carries FAIL_AT_BASE" "FAIL_AT_BASE" dispatch "$KFP" --task gw $ph --runner orca
  refute_spec "no known_failing: the $ph spec has no known-failing text" "Known failing at base|FAIL_AT_BASE" dispatch "$OK" --task gw $ph --runner orca
done
# base health hint: print only, for a repo with a GitHub remote
refute "base health hint: none without a remote" "base health" dispatch "$OK" --task gw --phase lead --runner orca
git -C "$S" remote add origin https://github.com/x/y.git
expect "base health hint: a GitHub remote prints the gh command" 0 'base health: run `gh run list --branch [^ ]+ --limit 1`' dispatch "$OK" --task gw --phase lead --runner orca
git -C "$S" remote set-url origin https://example.com/x/y.git
refute "base health hint: none for a non-GitHub remote" "base health" dispatch "$OK" --task gw --phase lead --runner orca
git -C "$S" remote remove origin
python3 -c 'import json,sys; r=json.load(open(sys.argv[1],encoding="utf-8")); r["pipeline"].pop("subagents",None); json.dump(r,open(sys.argv[2],"w",encoding="utf-8"))' "$ROOT/registry.json" "$TMP/reg-nosub.json"
for ph in "--task gw --phase lead" "--task gw --phase implement" "--task gw --phase review --sha abc1234" "--task gw --phase qa --sha abc1234"; do
  expect "registry without pipeline.subagents: dispatch $ph exits 1 and names the policy" 1 "subagent policy: registry pipeline.subagents is missing. Nothing was dispatched" --registry "$TMP/reg-nosub.json" dispatch "$OK" $ph --runner orca
done
expect "registry without pipeline.subagents: the planner exits 1 and names the policy" 1 "subagent policy: registry pipeline.subagents is missing" --registry "$TMP/reg-nosub.json" planner --request "add a thing"
# Every Orca launch emits one physical command line, with the exact full spec in persistent state. Include
# both new and resumed leads, narrowed subtasks, integration QA and planner requests containing newlines.
if python3 -B - "$P" "$OK" "$TMP" <<'PY'
import json, os, pathlib, shlex, subprocess, sys
p, plan, tmp = sys.argv[1:]
root = pathlib.Path(os.environ["RPG_FACTORY_STATE_DIR"])
def same(a, b):  # TEMP may be an 8.3 short path (windows CI: RUNNER~1); compare real, case-folded paths
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))
saved = {}
def check(args, key="demo", note=""):
    def run(runner):
        r = subprocess.run([sys.executable, "-B", p, *args, "--runner", runner], capture_output=True, text=True)
        assert r.returncode == 0, (args, r.stderr)
        return r.stdout
    command = run("orca")
    lines = command.splitlines()
    if len(lines) == 3:
        assert 'worktree add --no-track -b' in lines[0], command
        assert lines[1].startswith('orca worktree set ') and '--parent-worktree' in lines[1], command
        assert lines[2].startswith('orca agent launch '), command
    else:
        assert len(lines) == 1, repr(command)
    argv = shlex.split(lines[-1])
    assert all("\n" not in arg and "\r" not in arg for arg in argv), argv
    flag = "--prompt" if "--prompt" in argv else "--spec"
    prompt = argv[argv.index(flag) + 1]
    prefix, suffix = "Read your task spec at ", " and follow it." + note
    assert prompt.startswith(prefix) and prompt.endswith(suffix), prompt
    path = pathlib.Path(prompt[len(prefix):-len(suffix)])
    assert path.is_absolute() and same(path.parent, root / "pipeline" / key / "specs"), path
    full = path.read_text(encoding="utf-8")
    assert "\n" in full and full == run("print").split("\n", 1)[1][:-1], full  # remove only print()'s newline
    saved[str(path)] = full
    assert prompt == prefix + str(path) + suffix, prompt
    return path
for task in ("gw", "c1"):
    for phase in ("lead", "implement", "review", "qa"):
        args = ["dispatch", plan, "--task", task, "--phase", phase]
        check(args + (["--sha", "abc1234"] if phase in ("review", "qa") else []))
first = check(["dispatch", plan, "--task", "gw", "--phase", "implement", "--paths", "backend/gateway/a.go"])
second = check(["dispatch", plan, "--task", "gw", "--phase", "implement", "--paths", "backend/gateway/b.go"])
assert first != second, "subtasks must not overwrite each other's specs"
check(["dispatch", plan, "--task", "integration:client", "--phase", "qa", "--sha", "abc1234"])
fresh = pathlib.Path(tmp) / "fresh.json"
value = json.loads(pathlib.Path(plan).read_text(encoding="utf-8"))
value["topic"] += "-gw"  # the existing task worktree also serves as this fixture's integration checkout
value["tasks"] = [value["tasks"][0]]
fresh.write_text(json.dumps(value), encoding="utf-8")
check(["dispatch", str(fresh), "--task", "gw", "--phase", "lead"])  # no task branch/worktree yet
check(["dispatch", str(fresh), "--task", "integration:server", "--phase", "qa", "--sha", "abc1234"])
# the planner's one line also names the request, whitespace runs collapsed; the spec keeps it verbatim
request = "add a thing\n  with a\tsecond requirement\n"
spec = check(["planner", "--request", request], "_planner", " Request: add a thing with a second requirement")
assert f"Request: {request}" in spec.read_text(encoding="utf-8")
# A second prompt must never alter a spec an already-launched session has yet to read.
assert all(pathlib.Path(path).read_text(encoding="utf-8") == full for path, full in saved.items())
PY
then pass=$((pass + 1)); echo "PASS  Orca phases use one-line prompts and complete, immutable persistent specs"
else fail=$((fail + 1)); echo "FAIL  Orca one-line prompts and persistent specs"; fi
case_end dispatch
fi

if has_case model-policy; then
case_start
echo "-- model policy (registry pipeline.models, lib/model_policy.py): grades, roles, scope, override file"
MOD="--model claude-opus-5-5 --effort medium --json$"
# $OK with task gw owning a gateway directory free of contract and generated paths (backend/gateway/ holds the
# join-token source, so it grades heavy): its derived grade is light
LT=$(plan light "$(sed 's#"backend/gateway/"#"backend/gateway/internal/"#' < "$OK")")

expect "lead in the Unity project (orca agent launch): claude-opus-5-5 medium" 0 "^orca agent launch --agent claude .*$MOD" dispatch "$OK" --task c1 --phase lead --runner orca
expect "lead (print): the header names model and effort" 0 "^# agent: claude   model: claude-opus-5-5   effort: medium   worktree: " dispatch "$LT" --task gw --phase lead --runner print
expect "planner (orca): the planner profile" 0 "^orca orchestration worker-start .*--worktree current .*$MOD" planner --request "add a thing" --runner orca
expect "planner prompt: grade each task with the rubric" 0 "Grade each task light\|standard\|heavy with the rubric \(registry pipeline.models.rubric\)" planner --request "add a thing"
expect "planner prompt carries the rubric" 0 "^   - heavy: " planner --request "add a thing"
expect "planner prompt carries the planner's subagent rule" 0 "^Subagents: read-only scouts only, at most 3 in parallel, only when the plan needs facts from many files or repos.*never edits, git writes, Orca, dispatch or verdict, or nested subagents" planner --request "add a thing"
expect "planner --runner agent: the claude subagent clause" 0 "Subagents: read-only scouts only, at most 3 in parallel, only when the plan needs facts.*use Agent subagent_type rpg-factory:factory-explorer with model sonnet \(claude-sonnet-5-5\)" planner --request "add a thing" --runner agent
expect "lead spec: grade each subtask, write grade + grade_reason" 0 "Grade each subtask light\|standard\|heavy .*write .grade. \+ .grade_reason. per subtask \(none: the task's grade, light\)" dispatch "$LT" --task gw --phase lead
expect "lead spec: never a model outside the scope" 0 "never pass one outside its scope \(exit 2\)" dispatch "$LT" --task gw --phase lead
expect "lead spec carries the registry rubric" 0 "^- standard: Ordinary feature" dispatch "$LT" --task gw --phase lead
expect "lead spec names the task grade" 0 '"grade": "light"' dispatch "$LT" --task gw --phase lead
expect "validate prints the task lead's model" 0 "^Model: task lead claude claude-opus-5-5 medium$" validate "$LT"
expect "validate: grade derived from tier S is light" 0 "^Model: task gw grade light \(tier S of the owned paths\): implement claude claude-sonnet-5-5 high, review codex gpt-6.1-sol high, qa codex gpt-6.1-terra high$" validate "$LT"
expect "validate --json carries the models" 0 '"implement": \{' validate "$LT" --json
GR=$(plan grades "{$HEAD,\"tasks\":[
 {\"id\":\"wire\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend/shared/proto/wire.proto\"],\"acceptance\":[\"a\"],\"implementer\":\"codex\"},
 {\"id\":\"two\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend/loadtest/\",\"backend/integration_test/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"pg\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend/gameserver-dotnet/\"],\"acceptance\":[\"a\"],\"grade\":\"heavy\",\"grade_reason\":\"tick loop\"}]}")
expect "validate: a contract path derives heavy; codex heavy implement, claude heavy review" 0 "^Model: task wire grade heavy \(tier L of the owned paths, contract or generated path\): implement codex gpt-6.1-sol high, review claude claude-opus-5-5 high, qa claude claude-sonnet-5-5 high$" validate "$GR"
expect "lead (new worktree launch): the lead profile, claude-opus-5-5 medium" 0 "^orca agent launch --agent claude .*--prompt .*$MOD" dispatch "$GR" --task two --phase lead --runner orca
expect "lead (orca agent launch, task worktree exists): claude-opus-5-5 medium" 0 "^orca agent launch --agent claude .*--prompt .*$MOD" dispatch "$LT" --task gw --phase lead --runner orca
expect "validate: two modules derive standard" 0 "^Model: task two grade standard \(tier M of the owned paths\): implement claude claude-sonnet-5-5 high" validate "$GR"
expect "validate: the plan's grade wins" 0 "^Model: task pg grade heavy \(plan\): implement claude claude-opus-5-5 high, review codex gpt-6.1-sol high" validate "$GR"
X=$(plan badgrade "{$HEAD,\"tasks\":[{\"id\":\"a\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"x/\"],\"acceptance\":[\"a\"],\"grade\":\"huge\"}]}")
expect "validate: an unknown grade is an error" 1 'ERROR task a: grade "huge" is not one of light, standard, heavy' validate "$X"
expect "dispatch refuses a plan with an unknown grade" 1 "grade .*huge.* is not one of" dispatch "$X" --task a --phase lead --runner orca
GSP=$(subplan graded gw '[
 {"id":"s1","objective":"o","paths":["backend/gateway/internal/a/"],"implementer":"claude","grade":"light","grade_reason":"rename"},
 {"id":"s2","objective":"o","paths":["backend/gateway/internal/b.go"],"implementer":"codex"},
 {"id":"s3","objective":"o","paths":["backend/gateway/internal/c/"],"implementer":"claude","grade":"heavy","grade_reason":"locking"},
 {"id":"s4","objective":"o","paths":["backend/gateway/internal/d/"],"implementer":"codex","grade":"heavy"},
 {"id":"s5","objective":"o","paths":["backend/gateway/internal/e/"],"implementer":"claude","grade":"standard"}]' light.json)
expect "subplan validate: a graded subtask prints its models" 0 "^Model: subtask s1 grade light \(subplan\): implement claude claude-sonnet-5-5 high, review codex gpt-6.1-sol high$" subplan validate "$GSP"
expect "subplan validate: an ungraded subtask inherits the task grade" 0 "^Model: subtask s2 grade light \(task grade: tier S of the owned paths\): implement codex gpt-6.1-terra high, review claude claude-opus-5-5 medium$" subplan validate "$GSP"
expect "subplan validate: a heavy codex subtask gets the heavy claude reviewer" 0 "^Model: subtask s4 grade heavy \(subplan\): implement codex gpt-6.1-sol high, review claude claude-opus-5-5 high$" subplan validate "$GSP"
expect "subplan validate --json carries the models" 0 '"subtasks": \{' subplan validate "$GSP" --json
X=$(subplan badgrade gw '[{"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude","grade":"huge"}]')
expect "subplan validate: an unknown subtask grade is an error" 1 "ERROR subtask s1: grade huge is not one of light, standard, heavy" subplan validate "$X"
X=$(subplan intgrade gw '[{"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":"claude","grade":3}]')
expect "subplan validate: a non-string grade is an error" 1 "ERROR subtask s1: .grade. must be a string" subplan validate "$X"
X=$(plan badparent "{$HEAD,\"tasks\":[{\"id\":\"a\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"x/\"],\"acceptance\":[\"a\"],\"grade\":\"huge\"}]}")
BP=$(subplan badparent a '[{"id":"s1","objective":"o","paths":["x/a.go"],"implementer":"claude"}]')
expect "subplan validate: an unknown parent task grade is an error, never replaced by the default" 1 'ERROR task a: grade "huge" is not one of light, standard, heavy' subplan validate "$BP" --plan "$X"
refute "subplan validate: an unknown parent task grade is not OK" "^OK$" subplan validate "$BP" --plan "$X"
refute "subplan validate: an unknown parent task grade prints no inherited model" "^Model: subtask" subplan validate "$BP" --plan "$X"
for bad in 42 '"s1"' true; do
  X=$(subplan rawtype gw "$bad")
  expect "subplan validate: subtasks $bad is INVALID, not a traceback" 1 "ERROR .subtasks. must be a non-empty list of objects" subplan validate "$X"
  refute "subplan validate: subtasks $bad raises no traceback" "Traceback|TypeError" subplan validate "$X"
done
X=$(subplan rawimpl gw '[{"id":"s1","objective":"o","paths":["backend/gateway/a/"],"implementer":["claude"],"reviewer":{"a":1}}]')
expect "subplan validate: a non-string implementer and reviewer are errors, not a traceback" 1 "ERROR subtask s1: .implementer. must be a string" subplan validate "$X"
refute "subplan validate: a non-string implementer raises no traceback" "Traceback|TypeError" subplan validate "$X"
expect "implement of a light subtask: claude-sonnet-5-5 high" 0 "^orca orchestration worker-start .*--agent claude .*--model claude-sonnet-5-5 --effort high --json$" dispatch "$LT" --task gw --phase implement --subplan "$GSP" --subtask s1 --runner orca
expect "implement of a heavy subtask: claude-opus-5-5 high" 0 "^orca orchestration worker-start .*--model claude-opus-5-5 --effort high --json$" dispatch "$LT" --task gw --phase implement --subplan "$GSP" --subtask s3 --runner orca
expect "implement of an ungraded codex subtask of a light task: gpt-6.1-terra high" 0 "^orca orchestration worker-start .*--agent codex .*--model gpt-6.1-terra --effort high --json$" dispatch "$LT" --task gw --phase implement --subplan "$GSP" --subtask s2 --runner orca
expect "implement of the task (no subplan): the task grade" 0 "^orca orchestration worker-start .*--model claude-sonnet-5-5 --effort high --json$" dispatch "$LT" --task gw --phase implement --runner orca
expect "implement --grade heavy overrides the grade" 0 "^orca orchestration worker-start .*--model claude-opus-5-5 --effort high --json$" dispatch "$LT" --task gw --phase implement --grade heavy --runner orca
expect "codex review: gpt-6.1-sol high" 0 "^orca orchestration worker-start .*--agent codex .*--model gpt-6.1-sol --effort high --json$" dispatch "$LT" --task gw --phase review --sha abc1234 --runner orca
expect "claude review of a light codex subtask: the review profile" 0 "^orca orchestration worker-start .*--agent claude .*$MOD" dispatch "$LT" --task gw --phase review --sha abc1234 --subplan "$GSP" --subtask s2 --runner orca
expect "claude review of a heavy subtask: the heavy profile" 0 "^orca orchestration worker-start .*--agent claude .*--model claude-opus-5-5 --effort high --json$" dispatch "$LT" --task gw --phase review --sha abc1234 --subplan "$GSP" --subtask s4 --runner orca
expect "codex qa: gpt-6.1-terra high" 0 "^orca orchestration worker-start .*--agent codex .*--model gpt-6.1-terra --effort high --json$" dispatch "$LT" --task gw --phase qa --sha abc1234 --runner orca
expect "claude qa: claude-sonnet-5-5 high" 0 "^orca orchestration worker-start .*--agent claude .*--model claude-sonnet-5-5 --effort high --json$" dispatch "$OK" --task c2 --phase qa --sha abc1234 --runner orca
expect "--model inside the scope overrides the profile model" 0 "--model claude-sonnet-5-5 --effort medium --json$" dispatch "$LT" --task gw --phase lead --runner orca --model claude-sonnet-5-5
expect "--model outside the scope: usage error" 2 "claude claude-haiku-4-5 / medium is outside the model scope .*Nothing was dispatched" dispatch "$LT" --task gw --phase lead --runner orca --model claude-haiku-4-5
refute "--model outside the scope prints no command" "^orca |^# agent:" dispatch "$LT" --task gw --phase implement --runner orca --model claude-haiku-4-5
expect "--effort outside the scope: usage error" 2 "claude-sonnet-5-5 / low is outside the model scope" dispatch "$LT" --task gw --phase implement --runner orca --effort low
expect "--model of another agent's scope: usage error" 2 "codex claude-opus-5-5 / high is outside the model scope" dispatch "$LT" --task gw --phase review --sha abc1234 --runner orca --model claude-opus-5-5
expect "planner --model outside the scope: usage error" 2 "outside the model scope" planner --request "add a thing" --runner orca --model claude-haiku-4-5
expect "--grade takes light, standard or heavy only" 2 "invalid choice" dispatch "$LT" --task gw --phase implement --grade huge
# a non-canonical spelling of a path grades like the canonical one (dot and empty segments are dropped)
for spell in "./backend/shared/proto/wire.proto" "backend//shared/proto/wire.proto" "backend/./shared//proto/wire.proto" 'backend\shared\proto\wire.proto'; do
  esc=${spell//\\/\\\\}
  X=$(plan spell "{$HEAD,\"tasks\":[{\"id\":\"wire\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"$esc\"],\"acceptance\":[\"a\"]}]}")
  expect "validate: path spelling $spell grades heavy like the canonical wire.proto" 0 "^Model: task wire grade heavy \(tier L of the owned paths, contract or generated path\)" validate "$X"
done
# every valid spelling of one owned path grades alike in validate (plan_models, all tasks) and dispatch (one task):
# case (where the file system folds it: ICASE forced so the table bites on Linux too; routing still gets the
# registry's spelling), slashes, dot and empty segments, trailing slash, a directory with or without its slash (on
# disk or not), and the repo root
mkdir -p "$C/Assets/UI Toolkit/Screens.v2"; : > "$C/Assets/UI Toolkit/LICENSE"
if python3 - "$ROOT" "$C" <<'PY'
import importlib.util, json, os, sys
spec = importlib.util.spec_from_file_location("fp", sys.argv[1] + "/scripts/factory-pipeline.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
reg = json.load(open(sys.argv[1] + "/registry.json", encoding="utf-8"))
policy = m.model_policy.load(reg)
# the two rows below grade by what is on disk (file vs directory guess): their case-folded spellings only exist
# where the fixture file system folds case; on a case-sensitive one the folded path is not found and is guessed
# as a directory, which production never does because ICASE is only true on a folding file system
FOLDS = os.path.exists(os.path.join(sys.argv[2], "assets/ui toolkit/license"))
# (grade, repo, spellings of one path, spellings that differ only in case)
TABLE = [
    ("heavy", "server", ["backend/shared/proto/wire.proto", "./backend//shared/proto/wire.proto", "backend\\shared\\proto\\wire.proto"],
     ["BACKEND/SHARED/PROTO/WIRE.PROTO", "Backend/Shared/Proto/Wire.proto"]),
    ("heavy", "server", ["backend/shared/proto/", "backend/shared/proto", "backend/./shared/proto//"], ["BACKEND/SHARED/PROTO"]),
    ("heavy", "netcode", ["Runtime/Protocol/Generated/Wire.cs"], ["runtime/protocol/generated/wire.cs"]),
    ("heavy", "client", ["Assets/Scripts/UI/Hud/Generated/Hud.uxml.g.cs"], ["assets/scripts/ui/hud/generated/HUD.UXML.G.CS"]),
    ("heavy", "uitoolkit", ["Editor/Codegen/Generated/", "Editor/Codegen/Generated", "./Editor/Codegen/Generated"],
     ["editor/codegen/generated"]),
    ("heavy", "uitoolkit", ["Tests/Runtime/Generated/Screen.uxml.g.cs"], ["TESTS/RUNTIME/GENERATED/SCREEN.UXML.G.CS"]),
    ("heavy", "client", ["Assets/UI Toolkit/Screens.v2/", "Assets/UI Toolkit/Screens.v2"],
     ["assets/ui toolkit/screens.v2"] if FOLDS else []),  # a dotted directory on disk
    ("light", "client", ["Assets/UI Toolkit/LICENSE"], ["assets/ui toolkit/license"] if FOLDS else []),  # a file on disk, no extension
    ("light", "uitoolkit", ["Editor/Foo.cs", "./Editor//Foo.cs"], ["EDITOR/FOO.CS"]),
    ("light", "server", ["backend/gateway/internal/", "backend/gateway/internal"], ["Backend/Gateway/Internal/"]),
    ("heavy", "server", [".", "./", ".//"], []),  # the repo root owns every contract and generated path
    ("heavy", "uitoolkit", [".", "./"], []),
]
bad = []
for icase in (False, True):
    m.ICASE = icase
    tasks = []
    for n, (want, repo, plain, cased) in enumerate(TABLE):
        for k, p in enumerate(plain + (cased if icase else [])):
            tasks.append(({"id": f"t{n}-{k}", "repo": repo, "objective": "o", "paths": [p], "acceptance": ["a"]}, want))
    plan = {"schema": "rpg-factory.pipeline-plan/1", "id": "spell", "title": "t", "topic": "feat/core/spell", "deliver": "pr",
            "tasks": [t for t, _ in tasks], "_path": sys.argv[1] + "/x.json"}
    models = m.plan_models(plan, reg, [])["tasks"]
    for t, want in tasks:
        alone = m.task_grades(plan, reg, policy, [t])[t["id"]]["grade"]
        if not (models[t["id"]]["grade"] == alone == want):
            bad.append((icase, t["repo"], t["paths"][0], want, models[t["id"]]["grade"], alone))
assert not bad, bad
# routing (case-sensitive resolve.jq) sees the registry's spelling, never the folded one
m.ICASE = True
assert m.grade_paths(reg, "server", ["BACKEND/SHARED/PROTO/WIRE.PROTO", "Backend/Gateway/New/x.go"], None) ==     ["backend/shared/proto/wire.proto", "backend/gateway/New/x.go"]
PY
then pass=$((pass + 1)); echo "PASS  every spelling of an owned path grades alike in validate and dispatch (case forced, slashes, dots, dirs, root)"
else fail=$((fail + 1)); echo "FAIL  every spelling of an owned path grades alike in validate and dispatch"; fi
rm -rf "$C/Assets/UI Toolkit"  # the fixture paths must not count as changes outside the owned paths later
# the model preview skips tasks validation already rejects: validate --json keeps returning structured errors
for paths in '[{"path":"x"}]' '["x",42]' '["../x"]' '[""]'; do
  X=$(plan badpaths "{$HEAD,\"tasks\":[{\"id\":\"a\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":$paths,\"acceptance\":[\"a\"]}]}")
  out=$(python3 -B "$P" validate "$X" --json 2>&1); rc=$?
  if [ "$rc" = 1 ] && python3 -c 'import json,sys; d=json.loads(sys.argv[1]); assert d["errors"]' "$out" 2>/dev/null; then
    pass=$((pass + 1)); echo "PASS  validate --json with paths $paths: structured errors, no crash"
  else fail=$((fail + 1)); echo "FAIL  validate --json with paths $paths (rc=$rc)"; sed 's/^/      /' <<<"$out" | tail -5; fi
done
# an owned directory grades against the contract and generated paths it contains, not only what contains it
X=$(plan dirs "{$HEAD,\"tasks\":[
 {\"id\":\"proto\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend/shared/proto/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"protonoslash\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend/shared/proto\"],\"acceptance\":[\"a\"],\"deps\":[\"proto\"]},
 {\"id\":\"protocol\",\"repo\":\"netcode\",\"objective\":\"o\",\"paths\":[\"Runtime/Protocol/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"uiroot\",\"repo\":\"client\",\"objective\":\"o\",\"paths\":[\"Assets/UI Toolkit/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"uss\",\"repo\":\"client\",\"objective\":\"o\",\"paths\":[\"Assets/UI Toolkit/Themes/a.uss\"],\"acceptance\":[\"a\"],\"deps\":[\"uiroot\"]},
 {\"id\":\"gwdir\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend/gateway/x/\"],\"acceptance\":[\"a\"]}]}")
for t in proto protonoslash protocol uiroot; do
  expect "validate: owned directory of task $t contains a contract or generated path: heavy" 0 "^Model: task $t grade heavy \(tier L of the owned paths, contract or generated path\)" validate "$X"
done
expect "validate: a file beside a generated glob is not heavy" 0 "^Model: task uss grade light \(tier S of the owned paths\)" validate "$X"
expect "validate: a directory holding no contract or generated path stays light" 0 "^Model: task gwdir grade light \(tier S of the owned paths\)" validate "$X"
expect_spec "dispatch: the owned directory backend/shared/proto/ grades heavy, as validate does" '"grade": "heavy"' dispatch "$X" --task proto --phase lead --runner orca
# each task grades alone: a handoff source in one task must not make another task's copy path heavy, and validate
# (all tasks) and dispatch (one task) agree
X=$(plan handoff "{$HEAD,\"tasks\":[
 {\"id\":\"feature\",\"repo\":\"authoring\",\"objective\":\"o\",\"paths\":[\"design/features/example.md\"],\"acceptance\":[\"a\"]},
 {\"id\":\"brief\",\"repo\":\"authoring\",\"objective\":\"o\",\"paths\":[\"art2d/briefs/example.md\"],\"acceptance\":[\"a\"]}]}")
expect "validate: a handoff source task is heavy" 0 "^Model: task feature grade heavy \(tier L of the owned paths, contract or generated path\)" validate "$X"
expect "validate: the copy-side task beside it stays light" 0 "^Model: task brief grade light \(tier XS of the owned paths\): implement claude claude-sonnet-5-5 high" validate "$X"
expect_spec "dispatch of the copy-side task: light, as validate says" '"grade": "light"' dispatch "$X" --task brief --phase lead --runner orca
expect_spec "dispatch of the handoff source task: heavy, as validate says" '"grade": "heavy"' dispatch "$X" --task feature --phase lead --runner orca
# parity: validate's batch and a one-task call (dispatch, subplan) give every task the same grade
if python3 - "$ROOT" "$X" "$TMP/dirs.json" <<'PY'
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("fp", sys.argv[1] + "/scripts/factory-pipeline.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
reg = json.load(open(sys.argv[1] + "/registry.json", encoding="utf-8"))
policy = m.model_policy.load(reg)
for path in sys.argv[2:]:
    plan = json.load(open(path, encoding="utf-8"))
    batch = m.task_grades(plan, reg, policy, plan["tasks"])
    for t in plan["tasks"]:
        assert m.task_grades(plan, reg, policy, [t]) == {t["id"]: batch[t["id"]]}, (path, t["id"])
    models = m.plan_models(plan, reg, [])
    assert all(models["tasks"][t["id"]]["grade"] == batch[t["id"]]["grade"] for t in plan["tasks"]), path
PY
then pass=$((pass + 1)); echo "PASS  every task grades the same in validate's batch and alone (dispatch)"
else fail=$((fail + 1)); echo "FAIL  every task grades the same in validate's batch and alone (dispatch)"; fi
# the Agent tool takes the model alias only: a model without a valid alias is a usage error, never a silent default
jq 'del(.pipeline.models.agent_tool_alias["claude-sonnet-5-5"])' "$ROOT/registry.json" > "$TMP/reg-noalias.json"
jq '.pipeline.models.agent_tool_alias["claude-sonnet-5-5"] = ""' "$ROOT/registry.json" > "$TMP/reg-emptyalias.json"
out=$(python3 -B "$P" --registry "$TMP/reg-noalias.json" dispatch "$LT" --task gw --phase implement --runner agent 2>&1); rc=$?
if [ "$rc" = 2 ] && grep -q "claude-sonnet-5-5 has no Agent-tool model alias" <<<"$out" && ! grep -q '"subagent_type"' <<<"$out"
then pass=$((pass + 1)); echo "PASS  --runner agent with a model without an alias: usage error, no Agent call"
else fail=$((fail + 1)); echo "FAIL  --runner agent without an alias (rc=$rc)"; sed 's/^/      /' <<<"$out" | head -10; fi
out=$(python3 -B "$P" --registry "$TMP/reg-emptyalias.json" dispatch "$LT" --task gw --phase implement --runner agent 2>&1); rc=$?
if [ "$rc" = 1 ] && grep -q "agent_tool_alias claude-sonnet-5-5: must be a non-empty string" <<<"$out" && ! grep -q '"subagent_type"' <<<"$out"
then pass=$((pass + 1)); echo "PASS  --runner agent with an empty alias: policy error, no Agent call"
else fail=$((fail + 1)); echo "FAIL  --runner agent with an empty alias (rc=$rc)"; sed 's/^/      /' <<<"$out" | head -10; fi
out=$(python3 -B "$P" --registry "$TMP/reg-emptyalias.json" validate "$LT" 2>&1); rc=$?
if [ "$rc" = 1 ] && grep -q "agent_tool_alias claude-sonnet-5-5: must be a non-empty string" <<<"$out"
then pass=$((pass + 1)); echo "PASS  validate: an empty Agent-tool alias is a policy error"
else fail=$((fail + 1)); echo "FAIL  validate with an empty alias (rc=$rc)"; sed 's/^/      /' <<<"$out" | head -10; fi
expect "--runner orca still works for a model without an alias" 0 "^orca orchestration worker-start" --registry "$TMP/reg-noalias.json" dispatch "$LT" --task gw --phase implement --runner orca
# the Agent-tool fallback: the model alias, never an effort; a stderr note and one prompt line say so
out=$(python3 -B "$P" dispatch "$LT" --task gw --phase implement --runner agent 2>/dev/null)
if jq -e '.model == "sonnet" and (.prompt | test("\nModel: claude-sonnet-5-5 \\(light profile\\), planned effort high\\. The Claude Code Agent tool takes the model alias sonnet but cannot set an effort")) and has("effort") == false' <<<"$out" >/dev/null
then pass=$((pass + 1)); echo "PASS  --runner agent: JSON carries the model alias and a prompt line on effort"
else fail=$((fail + 1)); echo "FAIL  --runner agent model alias"; sed 's/^/      /' <<<"$out" | head -10; fi
expect "--runner agent: a stderr note that effort cannot be set" 0 "--runner agent: model sonnet \(claude-sonnet-5-5\); effort high cannot be set through the Agent tool" dispatch "$LT" --task gw --phase implement --runner agent
out=$(python3 -B "$P" dispatch "$LT" --task gw --phase review --sha abc1234 --runner agent 2>/dev/null)
if jq -e '.model == "opus"' <<<"$out" >/dev/null; then pass=$((pass + 1)); echo "PASS  --runner agent: a codex review runs the claude review profile (opus)"
else fail=$((fail + 1)); echo "FAIL  --runner agent codex review model"; sed 's/^/      /' <<<"$out" | head -10; fi
# a personal override file narrows the scope and replaces profiles; it is re-checked, never widens the scope
SON='{"model":"claude-sonnet-5-5","effort":"high"}'
printf '{"scope":{"claude":{"claude-sonnet-5-5":["high"]}},"profiles":{"claude":{"lead":%s,"planner":%s,"heavy":%s,"review":%s}}}\n' "$SON" "$SON" "$SON" "$SON" > "$TMP/mp-narrow.json"
RPG_FACTORY_MODEL_POLICY="$TMP/mp-narrow.json" expect "override file: a narrowed scope and its profiles apply" 0 "--model claude-sonnet-5-5 --effort high --json$" dispatch "$LT" --task gw --phase lead --runner orca
RPG_FACTORY_MODEL_POLICY="$TMP/mp-narrow.json" expect "override file: --model outside the narrowed scope exits 2" 2 "claude-opus-5-5 / high is outside the model scope .*claude: claude-sonnet-5-5: high\)" dispatch "$LT" --task gw --phase implement --runner orca --model claude-opus-5-5
RPG_FACTORY_MODEL_POLICY="$TMP/mp-narrow.json" expect "override file: validate prints the narrowed models" 0 "^Model: task lead claude claude-sonnet-5-5 high$" validate "$LT"
printf '{"scope":{"claude":{"claude-sonnet-5-5":["high"]}}}\n' > "$TMP/mp-bad.json"
RPG_FACTORY_MODEL_POLICY="$TMP/mp-bad.json" expect "override file: a profile left outside the narrowed scope is an error" 1 "profiles claude/lead: claude-opus-5-5 / medium is outside the scope" dispatch "$LT" --task gw --phase lead --runner orca
RPG_FACTORY_MODEL_POLICY="$TMP/mp-bad.json" refute "override file: a broken policy dispatches nothing" "^orca " dispatch "$LT" --task gw --phase lead --runner orca
RPG_FACTORY_MODEL_POLICY="$TMP/mp-bad.json" expect "override file: validate is INVALID with a profile outside the scope" 1 "^ERROR model policy .*profiles claude/lead" validate "$LT"
RPG_FACTORY_MODEL_POLICY="$TMP/mp-bad.json" expect "override file: subplan validate is INVALID too" 1 "^ERROR model policy" subplan validate "$GSP"
printf '{"scope":{"claude":{"claude-haiku-4-5":["high"]}}}\n' > "$TMP/mp-wide.json"
RPG_FACTORY_MODEL_POLICY="$TMP/mp-wide.json" expect "override file: widening the scope is an error" 1 "claude/claude-haiku-4-5 is outside the registry scope" dispatch "$LT" --task gw --phase lead --runner orca
STATE_MP=$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1] + "/scripts/lib"); import model_policy; print(model_policy.override_path())' "$ROOT")
mkdir -p "$(dirname "$STATE_MP")"; cp "$TMP/mp-narrow.json" "$STATE_MP"
expect "override file in the persistent state dir applies without the variable" 0 "--model claude-sonnet-5-5 --effort high --json$" dispatch "$LT" --task gw --phase lead --runner orca
rm -f "$STATE_MP"
# a verdict records what the session ran with
MV=$(plan models-verdict "$(sed 's/"id":"demo"/"id":"demo-models"/' < "$OK")")
SHA=$(git -C "$S" rev-parse HEAD)
expect "verdict --model/--effort: recorded and printed" 0 "recorded review PASS for gw at .* by codex gpt-6.1-sol high: " verdict "$MV" --task gw --phase review --sha "$SHA" --by codex --state PASS --model gpt-6.1-sol --effort high
if python3 -c 'import glob,json,sys; f=glob.glob(sys.argv[1]+"/**/demo-models/gw__review.json",recursive=True)[0]; r=json.load(open(f,encoding="utf-8")); assert r["model"]=="gpt-6.1-sol" and r["effort"]=="high", r' "$TMP/state"
then pass=$((pass + 1)); echo "PASS  verdict JSON stores model and effort"
else fail=$((fail + 1)); echo "FAIL  verdict JSON stores model and effort"; fi
expect "verdict without --model stores none" 0 "recorded qa PASS for gw at [0-9a-f]+ by codex: " verdict "$MV" --task gw --phase qa --sha "$SHA" --by codex --state PASS
if python3 - "$ROOT" "$GSP" "$GR" <<'PY'
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("lint", sys.argv[1] + "/scripts/checks/artifact-lint.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
for doc, schema_name in ((sys.argv[2], "pipeline-subplan"), (sys.argv[3], "pipeline-plan")):
    schema = json.load(open(f"{sys.argv[1]}/docs/schemas/{schema_name}.schema.json", encoding="utf-8"))
    value = json.load(open(doc, encoding="utf-8"))
    assert not m.schema_errors(value, schema, schema), (schema_name, m.schema_errors(value, schema, schema))
    items = value["subtasks"] if "subtasks" in value else value["tasks"]
    items[0]["grade"] = "huge"
    assert m.schema_errors(value, schema, schema), f"{schema_name}: an unknown grade must fail the schema"
PY
then pass=$((pass + 1)); echo "PASS  plan and subplan schemas know grade and grade_reason"
else fail=$((fail + 1)); echo "FAIL  plan and subplan schemas: grade"; fi
case_end model-policy
fi

if has_case child-dispatch; then
case_start
echo "-- dispatch: subplan subtasks and Orca child worktrees"
CH="^orca orchestration worker-start .*--worktree new-child --name feat/core/demo-gw--"
expect "subplan placement child: worker-start --worktree new-child from the task branch" 0 "${CH}s2 --base-branch feat/core/demo-gw .*--json$" dispatch "$OK" --task gw --phase implement --subplan "$SPC" --subtask s2 --runner orca
expect "the child subtask runs its implementer (codex)" 0 "worker-start .*--agent codex --worktree new-child" dispatch "$OK" --task gw --phase implement --subplan "$SPC" --subtask s2 --runner orca
expect "a child command says the run-all rule (stderr)" 0 "never create or remove a child worktree while a full tests/run-all.sh runs \(shared .git/config\)" dispatch "$OK" --task gw --phase implement --subplan "$SPC" --subtask s2 --runner orca
expect_spec "the child implement spec commits on the child branch" "Commit on your child branch with explicit paths" dispatch "$OK" --task gw --phase implement --subplan "$SPC" --subtask s2 --runner orca
expect_spec "the child implement spec runs no suites, only a syntax check" "Run no test suites; only a syntax check of the files you edited" dispatch "$OK" --task gw --phase implement --subplan "$SPC" --subtask s2 --runner orca
expect_spec "the child implement spec: the task lead merges and removes the child at once" "the task lead merges it into feat/core/demo-gw and removes the child at once" dispatch "$OK" --task gw --phase implement --subplan "$SPC" --subtask s2 --runner orca
expect_spec "the child implement spec says the run-all rule" "never create or remove a child worktree while a full tests/run-all.sh runs" dispatch "$OK" --task gw --phase implement --subplan "$SPC" --subtask s2 --runner orca
expect_spec "the subtask's paths are in the spec" '"subtask_paths": \["backend/gateway/b.go"\]' dispatch "$OK" --task gw --phase implement --subplan "$SPC" --subtask s2 --runner orca
expect_spec "the child's reason is in the spec" '"placement_reason": "runs the full suite"' dispatch "$OK" --task gw --phase implement --subplan "$SPC" --subtask s2 --runner orca
expect "subplan placement shared: the task worktree" 0 "--agent claude $WT" dispatch "$OK" --task gw --phase implement --subplan "$SPC" --subtask s1 --runner orca
expect_spec "a shared subtask does not commit" "Do NOT commit, stage or stash" dispatch "$OK" --task gw --phase implement --subplan "$SPC" --subtask s1 --runner orca
expect "--placement shared overrides the subtask's child" 0 "--agent codex $WT" dispatch "$OK" --task gw --phase implement --subplan "$SPC" --subtask s2 --placement shared --runner orca
expect "a subtask review goes to its implementer's pair (claude for codex)" 0 "worker-start .*--agent claude --worktree new-child --name feat/core/demo-gw--s2--review-abc1234 --base-branch abc1234 " dispatch "$OK" --task gw --phase review --sha abc1234 --subplan "$SPC" --subtask s2 --runner orca
expect_spec "a child review checks HEAD is the candidate in its child" "Orca child worktree of .*demo-gw created at it" dispatch "$OK" --task gw --phase review --sha abc1234 --subplan "$SPC" --subtask s2 --runner orca
expect_spec "a subtask review records with verdict --subtask" "record with .verdict --subtask s2." dispatch "$OK" --task gw --phase review --sha abc1234 --subplan "$SPC" --subtask s2 --runner orca
expect "--placement child on qa: a frozen child at the SHA" 0 "${CH}qa-abc1234 --base-branch abc1234 " dispatch "$OK" --task gw --phase qa --sha abc1234 --placement child --runner orca
# review, QA and implement of one child subtask get distinct Orca names (they run at once on one candidate)
names=$(for ph in "implement" "review --sha abc1234" "qa --sha abc1234"; do
  # shellcheck disable=SC2086
  python3 -B "$P" dispatch "$OK" --task gw --phase $ph --subplan "$SPC" --subtask s2 --runner orca 2>/dev/null | grep -oE -- "--name [^ ]+"; done)
if [ "$(sort -u <<<"$names" | wc -l)" = 3 ] && grep -qx -- "--name feat/core/demo-gw--s2--qa-abc1234" <<<"$names"; then
  pass=$((pass + 1)); echo "PASS  implement, review and QA children of one subtask have distinct names"
else fail=$((fail + 1)); echo "FAIL  child names collide: $names"; fi
out=$(python3 -B "$P" dispatch "$OK" --task gw --phase qa --sha abc1234 --placement child --runner agent 2>/dev/null)
if jq -e '.isolation == "worktree" and (.prompt | test("never create or remove a worktree yourself")) and (.prompt | test("git worktree add") | not)' <<<"$out" >/dev/null
then pass=$((pass + 1)); echo "PASS  --runner agent child placement: the Agent tool isolates, the session never runs git worktree add"
else fail=$((fail + 1)); echo "FAIL  --runner agent child placement"; head -c 600 <<<"$out"; fi
expect "a child command says where to run it (stderr)" 0 "run the command from .*demo-gw \(Orca makes the child of the worktree it runs in\)" dispatch "$OK" --task gw --phase qa --sha abc1234 --placement child --runner orca
expect "--subtask without --subplan is a usage error" 2 "--subplan and --subtask go together" dispatch "$OK" --task gw --phase implement --subtask s2
expect "an unknown subtask is a usage error" 2 "unknown subtask zz: subplan has s1, s2" dispatch "$OK" --task gw --phase implement --subplan "$SPC" --subtask zz
expect "a subplan of another task is a usage error" 2 "splits task gw, not c1" dispatch "$OK" --task c1 --phase implement --subplan "$SPC" --subtask s1
# child in a no-worktree repo: usage error, nothing on stdout
for args in "--task c1 --phase implement" "--task c1 --phase qa --sha abc1234" "--task c1 --phase lead" "--task integration:client --phase qa --sha abc1234"; do
  # shellcheck disable=SC2086
  out=$(python3 -B "$P" dispatch "$OK" $args --placement child --runner orca 2>/dev/null); rc=$?
  err=$(python3 -B "$P" dispatch "$OK" $args --placement child --runner orca 2>&1 >/dev/null)
  if [ "$rc" = 2 ] && [ -z "$out" ] && grep -q "takes no worktree" <<<"$err"; then pass=$((pass + 1)); echo "PASS  child in the Unity project ($args): usage error, nothing printed"
  else fail=$((fail + 1)); echo "FAIL  child in the Unity project ($args) (rc=$rc)"; head -5 <<<"$out$err"; fi
done
git -C "$S" worktree remove "$TMP/demo-gw"; git -C "$S" branch -q -D feat/core/demo-gw
expect "new task worktree without an integration checkout: git no-track" 0 "^git -C .* worktree add --no-track -b feat/core/demo-gw .*feat-core-demo-gw'? develop" dispatch "$OK" --task gw --phase lead --runner orca
expect "new task worktree uses main checkout as parent" 0 "^orca worktree set .*--parent-worktree .*rpg-mmo-server.*--workspace-status in-progress" dispatch "$OK" --task gw --phase lead --runner orca
refute "new task worktree does not use Orca create" "orca worktree create" dispatch "$OK" --task gw --phase lead --runner orca
# topic checked out nowhere: the Orca parent falls back to the main checkout, loudly (stderr only; stdout is unchanged)
out=$(python3 -B "$P" dispatch "$OK" --task gw --phase lead --runner orca 2>/dev/null)
err=$(python3 -B "$P" dispatch "$OK" --task gw --phase lead --runner orca 2>&1 >/dev/null)
if grep -q "^factory-pipeline: Orca parent: no checkout has the topic branch feat/core/demo checked out, .*falls back to the main checkout .*rpg-mmo-server; set plan.topic to your own integration branch" <<<"$err" \
   && ! grep -q "Orca parent:" <<<"$out" && grep -Eq -- "--parent-worktree '?path:[^' ]*rpg-mmo-server'? " <<<"$out"; then
  pass=$((pass + 1)); echo "PASS  topic not checked out: stderr hint names the main-checkout fallback, stdout has none and the parent is the main checkout"
else fail=$((fail + 1)); echo "FAIL  topic not checked out: Orca parent hint"; head -5 <<<"$err"; fi
expect "lead --placement child without integration checkout uses git" 0 "worktree add --no-track -b feat/core/demo-gw" dispatch "$OK" --task gw --phase lead --placement child --runner orca
# integration QA joins the checkout of plan.topic; without one it is an error and no worktree is created
before=$(git -C "$S" worktree list --porcelain); out=$(python3 -B "$P" dispatch "$OK" --task integration:server --phase qa --sha abc1234 --runner orca 2>&1); rc=$?
if [ "$rc" = 1 ] && grep -q "no worktree of .* has the integration branch feat/core/demo checked out" <<<"$out" && grep -q "No worktree was created" <<<"$out" \
   && ! grep -q "new-top-level" <<<"$out" && [ "$before" = "$(git -C "$S" worktree list --porcelain)" ]; then pass=$((pass + 1)); echo "PASS  integration QA without the integration checkout: error, no worktree"
else fail=$((fail + 1)); echo "FAIL  integration QA without the integration checkout (rc=$rc)"; sed 's/^/      /' <<<"$out" | head -10; fi
git -C "$S" worktree add -q "$TMP/demo-int" -b feat/core/demo develop 2>/dev/null
expect "integration QA joins the integration checkout of plan.topic" 0 "--agent codex --worktree '?path:[^' ]*demo-int'?" dispatch "$OK" --task integration:server --phase qa --sha abc1234 --runner orca
refute "integration QA never creates a worktree" "new-top-level|--base-branch|worktree create" dispatch "$OK" --task integration:server --phase qa --sha abc1234 --runner orca
expect "integration QA checks HEAD is the candidate in the shared checkout" 0 "You share the integration checkout .*demo-int with the run lead" dispatch "$OK" --task integration:server --phase qa --sha abc1234
expect "integration QA: no subagents" 0 "^Subagents: none in this session \(never: QA runs the checks itself" dispatch "$OK" --task integration:server --phase qa --sha abc1234
expect "integration QA --runner agent: no subagents" 0 "Subagents: none in this session" dispatch "$OK" --task integration:server --phase qa --sha abc1234 --runner agent
expect_spec "known_failing: the integration QA spec lists the checks" "^- tests/foo\.test\.sh: fails on base$" dispatch "$KFP" --task integration:server --phase qa --sha abc1234 --runner orca
expect_spec "integration QA (orca spec): no subagents" "^Subagents: none in this session" dispatch "$OK" --task integration:server --phase qa --sha abc1234 --runner orca
expect_spec "integration QA: spec is complete" "$SPEC_RULE" dispatch "$OK" --task integration:server --phase qa --sha abc1234 --runner orca
expect_spec "integration QA spec: the run lead's RPG_FACTORY_WORKSPACE for every test run" "^Test environment: set RPG_FACTORY_WORKSPACE=[^ ]*ws'? for every test run \(the run lead's environment sets it; a worker session may not inherit it\)\.$" dispatch "$OK" --task integration:server --phase qa --sha abc1234 --runner orca
expect "integration QA in the Unity project: no subagents" 0 "^Subagents: none in this session" dispatch "$OK" --task integration:client --phase qa --sha abc1234
expect "new task worktree beside integration checkout" 0 "^git -C .* worktree add --no-track -b feat/core/demo-gw .*feat-core-demo-gw'? develop" dispatch "$OK" --task gw --phase lead --runner orca
refute "new task worktree with an integration checkout has no --no-parent" "--no-parent" dispatch "$OK" --task gw --phase lead --runner orca
expect "new task worktree beside integration checkout --placement shared" 0 "^git -C .* worktree add --no-track -b feat/core/demo-gw .*feat-core-demo-gw'? develop" dispatch "$OK" --task gw --phase lead --placement shared --runner orca
expect "lead --placement shared uses integration parent" 0 "^orca worktree set .*--parent-worktree .*demo-int.*--workspace-status in-progress" dispatch "$OK" --task gw --phase lead --placement shared --runner orca
out=$(python3 -B "$P" dispatch "$OK" --task gw --phase lead --runner orca 2>/dev/null)
err=$(python3 -B "$P" dispatch "$OK" --task gw --phase lead --runner orca 2>&1 >/dev/null)
if ! grep -q "Orca parent:" <<<"$err" && grep -Eq -- "--parent-worktree '?path:[^' ]*demo-int'? " <<<"$out" && ! grep -Eq -- "--parent-worktree '?path:[^' ]*rpg-mmo-server'? " <<<"$out"; then
  pass=$((pass + 1)); echo "PASS  topic checked out: no Orca parent hint and the parent is the integration checkout"
else fail=$((fail + 1)); echo "FAIL  topic checked out: Orca parent hint"; head -5 <<<"$err"; fi
refute "lead prints no orca worktree create beside the integration checkout (any placement)" "orca worktree create" dispatch "$OK" --task gw --phase lead --placement child --runner orca
refute "no-worktree repo (Unity project): no worktree add and no orca worktree set" "worktree add|worktree set" dispatch "$OK" --task c1 --phase lead --runner orca
expect "new task worktree beside integration checkout --placement child" 0 "^git -C .* worktree add --no-track -b feat/core/demo-gw .*feat-core-demo-gw'? develop" dispatch "$OK" --task gw --phase lead --placement child --runner orca
refute "lead --placement child has no --no-parent" "--no-parent" dispatch "$OK" --task gw --phase lead --placement child --runner orca
expect "new task worktree launches lead by path" 0 "^orca agent launch --agent claude --worktree .*feat-core-demo-gw" dispatch "$OK" --task gw --phase lead --runner orca
expect "integration QA --placement child: a child of the integration checkout at the SHA" 0 "^orca orchestration worker-start .*--worktree new-child --name feat/core/demo--qa-abc1234 --base-branch abc1234 " dispatch "$OK" --task integration:server --phase qa --sha abc1234 --placement child --runner orca
expect "integration QA in a child: the command runs from the integration checkout (stderr)" 0 "run the command from .*demo-int " dispatch "$OK" --task integration:server --phase qa --sha abc1234 --placement child --runner orca
expect_spec "integration QA in a child checks HEAD in its child" "Orca child worktree of .*demo-int created at it" dispatch "$OK" --task integration:server --phase qa --sha abc1234 --placement child --runner orca
git -C "$S" worktree remove "$TMP/demo-int"; git -C "$S" branch -q -D feat/core/demo
expect "integration QA in the Unity project: main checkout" 0 "--worktree '?path:[^' ]*IndieRPGMMOAdventure'?" dispatch "$OK" --task integration:client --phase qa --sha abc1234 --runner orca
expect "planner runs in the lead's checkout (no worktree)" 0 "--worktree current" planner --request "add a thing" --runner orca

case_end child-dispatch
fi

if has_case tier; then
case_start
echo "-- tier"
ctx() { printf '%s\n' "$2" > "$TMP/ctx-$1.json"; echo "$TMP/ctx-$1.json"; }
X=$(ctx s '{"repos":[{"repo":"server","touched":["server.gateway"],"files":[{"path":"a","source":"given"}],"contracts":[],"generated_hits":[]}]}')
expect "one module, one file: S" 0 '"tier": "S"' tier --json --context-json "$X"
X=$(ctx m '{"repos":[{"repo":"server","touched":["server.gateway","server.shared"],"files":[{"path":"a","source":"given"}],"contracts":[],"generated_hits":[]}]}')
expect "two modules: M" 0 "^Tier: M" tier --context-json "$X"
X=$(ctx l '{"repos":[{"repo":"server","touched":["server.proto"],"files":[{"path":"a","source":"given"}],"contracts":[{"id":"wire-generated"}],"generated_hits":[]}]}')
expect "a contract: L" 0 "above M: contract wire-generated" tier --context-json "$X"
X=$(ctx l2 '{"repos":[{"repo":"server","touched":["server.a"],"files":[{"path":"a","source":"given"}],"contracts":[],"generated_hits":[]},{"repo":"client","touched":["client.a"],"files":[{"path":"b","source":"given"}],"contracts":[],"generated_hits":[]}]}')
expect "two repos: L" 0 "^Tier: L" tier --context-json "$X"

case_end tier
fi

if has_case verdict-gate; then
case_start
echo "-- verdict and gate"
# srv/cli: plan.repos aliases of the fixture checkouts (unregistered: no run-checks); cli is a Unity project by its marker
G=$(plan gate "{$HEAD,\"repos\":{\"srv\":{\"path\":\"ws/rpg-mmo-server\",\"base\":\"develop\"},\"cli\":{\"path\":\"ws/IndieRPGMMOAdventure\",\"base\":\"develop\"}},\"tasks\":[
 {\"id\":\"gw\",\"repo\":\"srv\",\"objective\":\"o\",\"paths\":[\"backend/gateway/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"c1\",\"repo\":\"cli\",\"objective\":\"o\",\"paths\":[\"Assets/A/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"c2\",\"repo\":\"cli\",\"objective\":\"o\",\"paths\":[\"./Assets/B\"],\"acceptance\":[\"a\"],\"implementer\":\"codex\"}]}")
expect "no integration branch: NOT_READY" 1 "BLOCKER srv: integration branch feat/core/demo does not exist" gate "$G"
gi "$S" checkout -qb feat/core/demo; mkdir -p "$S/backend/gateway"; echo x > "$S/backend/gateway/a.go"; gi "$S" add -A; gi "$S" commit -qm "feat(gateway): a"
SG=$(git -C "$S" rev-parse HEAD)
gi "$C" checkout -qb feat/core/demo; mkdir -p "$C/Assets/A" "$C/Assets/B"; echo a > "$C/Assets/A/a.cs"; gi "$C" add -A; gi "$C" commit -qm "feat(ui): a"
C1=$(git -C "$C" rev-parse HEAD); echo b > "$C/Assets/B/b.cs"; gi "$C" add -A; gi "$C" commit -qm "feat(ui): b"; C2=$(git -C "$C" rev-parse HEAD)
v() { python3 -B "$P" verdict "$G" "$@" >/dev/null || echo "verdict failed: $*"; }
expect "no verdicts yet: blockers name review and QA" 1 "BLOCKER gw: no review verdict" gate "$G"
expect "verdict rejects an unknown state" 2 "--state must be one of" verdict "$G" --task gw --phase review --sha "$SG" --by codex --state GREEN
expect "verdict rejects a SHA that is not a commit of the repo" 2 "is not a commit of repo srv" verdict "$G" --task gw --phase review --sha deadbeef1 --by codex --state PASS
expect "review verdicts are per task" 2 "review verdicts are per task" verdict "$G" --task integration:srv --phase review --sha "$SG" --by codex --state PASS
expect "per-task qa verdict of a worktree repo is recorded (the task lead's QA)" 0 "recorded qa PASS for gw" verdict "$G" --task gw --phase qa --sha "$SG" --by codex --state PASS
expect "a per-task qa verdict does not replace the integration QA" 1 "BLOCKER integration:srv: no qa verdict" gate "$G"
v --task gw --phase review --sha "$SG" --by claude --state PASS
expect "same-model review blocks" 1 "BLOCKER gw: reviewed by claude, cross-model review needs codex" gate "$G"
expect "same-model review accepted only with --allow-same-model" 1 "NOTE    gw: review SAME_MODEL \(claude\) accepted" gate "$G" --allow-same-model
v --task gw --phase review --sha "$SG" --by codex --state PASS
v --task c1 --phase review --sha "$C1" --by codex --state PASS
v --task c2 --phase review --sha "$C2" --by claude --state PASS
v --task integration:srv --phase qa --sha "$SG" --by codex --state PASS
v --task integration:cli --phase qa --sha "$C2" --by codex --state PASS
# subtask reviews and per-candidate records never replace the task review the gate reads
VD="$RPG_FACTORY_STATE_DIR/pipeline/demo"
expect "verdict --subtask records the subtask's own review" 0 "recorded review FAIL for gw subtask s2 at .*gw@s2__review.json" verdict "$G" --task gw --phase review --sha "$SG" --by claude --state FAIL --subtask s2
expect "a non-pair task review at the reviewed SHA keeps the pair's record" 0 "kept the codex review of gw .*kept per candidate only" verdict "$G" --task gw --phase review --sha "$SG" --by claude --state FAIL
if jq -e '.by == "codex" and .state == "PASS"' "$VD/gw__review.json" >/dev/null && jq -e '.subtask == "s2" and .state == "FAIL"' "$VD/gw@s2__review.json" >/dev/null \
   && [ -f "$VD/gw__review__${SG:0:12}__codex.json" ] && [ -f "$VD/gw__review__${SG:0:12}__claude.json" ] && [ -f "$VD/gw@s2__review__${SG:0:12}__claude.json" ]
then pass=$((pass + 1)); echo "PASS  verdict --subtask never overwrites the task review; every verdict is kept per candidate"
else fail=$((fail + 1)); echo "FAIL  verdict records"; ls "$VD" | sed 's/^/      /'; fi
expect "--subtask goes with a plan task" 2 "--subtask is the id of a subtask" verdict "$G" --task integration:srv --phase qa --sha "$SG" --by codex --state PASS --subtask s2
expect "Unity tasks need their own QA, one after another" 1 "BLOCKER c1: no qa verdict" gate "$G"
v --task c1 --phase qa --sha "$C1" --by codex --state PASS
v --task c2 --phase qa --sha "$C1" --by claude --state PASS
expect "per-task QA on a commit without the reviewed one blocks" 1 "BLOCKER c2: QA ran on .* does not contain the reviewed commit" gate "$G"
v --task c2 --phase qa --sha "$C2" --by claude --state PASS
# every task and integration verdict PASS, but the current subtask s2 review FAIL still blocks gate and status
expect "a current subtask review FAIL blocks the gate: NOT_READY" 1 "BLOCKER gw: subtask s2 review FAIL at .* by claude" gate "$G"
expect "status names the subtask FAIL and starts the task lead" 0 "note: subtask s2 review FAIL" status "$G"
refute "status offers no gate while a subtask FAIL is open" "^Next: .* gate " status "$G"
python3 -B "$P" verdict "$G" --task gw --phase qa --sha "$SG" --by codex --state FAIL --subtask s3 >/dev/null
expect "a subtask QA FAIL blocks the gate" 1 "BLOCKER gw: subtask s3 qa FAIL" gate "$G"
# verdict file names: task "a__sub-b" and subtask b of task a never share a file (the old <task>__sub-<id> did)
X=$(plan coll "{\"schema\":\"rpg-factory.pipeline-plan/1\",\"id\":\"coll\",\"title\":\"Coll\",\"topic\":\"feat/core/coll\",
 \"repos\":{\"srv\":{\"path\":\"ws/rpg-mmo-server\",\"base\":\"develop\"}},\"tasks\":[
 {\"id\":\"a\",\"repo\":\"srv\",\"objective\":\"o\",\"paths\":[\"ca/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"a__sub-b\",\"repo\":\"srv\",\"objective\":\"o\",\"paths\":[\"cb/\"],\"acceptance\":[\"a\"]}]}")
CVD="$RPG_FACTORY_STATE_DIR/pipeline/coll"
git -C "$S" branch -q feat/core/coll "$SG"
python3 -B "$P" verdict "$X" --task a --phase review --sha "$SG" --by claude --state FAIL --subtask b >/dev/null
python3 -B "$P" verdict "$X" --task a__sub-b --phase review --sha "$SG" --by codex --state PASS >/dev/null
if jq -e '.task == "a" and .subtask == "b" and .state == "FAIL"' "$CVD/a@b__review.json" >/dev/null    && jq -e '.task == "a__sub-b" and .state == "PASS" and (has("subtask") | not)' "$CVD/a__sub-b__review.json" >/dev/null    && [ -f "$CVD/a@b__review__${SG:0:12}__claude.json" ] && [ -f "$CVD/a__sub-b__review__${SG:0:12}__codex.json" ]
then pass=$((pass + 1)); echo "PASS  task a__sub-b and subtask b of task a keep their own verdict files"
else fail=$((fail + 1)); echo "FAIL  verdict file collision"; ls "$CVD" | sed 's/^/      /'; fi
expect "the subtask FAIL blocks its own task a" 1 "BLOCKER a: subtask b review FAIL" gate "$X" --no-run-checks
refute "task a__sub-b is not blocked by subtask b of task a" "BLOCKER a__sub-b: subtask|a__sub-b: no review verdict" gate "$X" --no-run-checks
# an older <task>__sub-<id> record still counts for its own task and subtask
python3 -c 'import json,sys; r=json.load(open(sys.argv[1],encoding="utf-8")); r.update(subtask="c",state="FAIL"); json.dump(r,open(sys.argv[2],"w",encoding="utf-8"))' "$CVD/a@b__review.json" "$CVD/a__sub-c__review.json"
expect "a legacy subtask record of task a still blocks it" 1 "BLOCKER a: subtask c review FAIL" gate "$X" --no-run-checks
python3 -B "$P" verdict "$X" --task a --phase review --sha "$SG" --by codex --state PASS --subtask c >/dev/null
refute "a new-style subtask PASS supersedes the legacy FAIL for that phase" "subtask c review FAIL" gate "$X" --no-run-checks
# Other phases retain their legacy evidence until that phase has a new-style record too.
python3 -c 'import json,sys; r=json.load(open(sys.argv[1],encoding="utf-8")); r["phase"]="qa"; json.dump(r,open(sys.argv[2],"w",encoding="utf-8"))' "$CVD/a__sub-c__review.json" "$CVD/a__sub-c__qa.json"
expect "a new-style review does not supersede a legacy QA FAIL" 1 "BLOCKER a: subtask c qa FAIL" gate "$X" --no-run-checks
v --task gw --phase review --sha "$SG" --by claude --state PASS --subtask s2
v --task gw --phase qa --sha "$SG" --by codex --state PASS --subtask s3
# late results: a PASS on an older candidate (SG~1) never resolves a FAIL on the newer SG; a PASS on SG resolves it, and
# a late FAIL on the older candidate then changes nothing
SA=$(git -C "$S" rev-parse "$SG~1")
v --task gw --phase review --sha "$SG" --by claude --state FAIL --subtask s4
v --task gw --phase review --sha "$SA" --by claude --state PASS --subtask s4
expect "a late subtask PASS on an older candidate keeps the newer FAIL: NOT_READY" 1 "BLOCKER gw: subtask s4 review FAIL at ${SG:0:10} by claude" gate "$G"
expect "status keeps the newer subtask FAIL after a late older PASS" 0 "note: subtask s4 review FAIL at ${SG:0:10}" status "$G"
v --task gw --phase review --sha "$SG" --by claude --state PASS --subtask s4
v --task gw --phase review --sha "$SA" --by claude --state FAIL --subtask s4
refute "a late subtask FAIL on an older candidate does not reopen the newer PASS" "subtask s4" gate "$G"
# a fix left on an unmerged child branch: its PASS on a descendant of the integration HEAD resolves nothing
SC=$(git -C "$S" commit-tree "$SG^{tree}" -p "$SG" -m "fix(gateway): child"); git -C "$S" branch -q gw-child-fix "$SC"
v --task gw --phase review --sha "$SG" --by claude --state FAIL --subtask s5
v --task gw --phase review --sha "$SC" --by claude --state PASS --subtask s5
expect "a subtask PASS on an unmerged child commit keeps the FAIL on the integration HEAD: NOT_READY" 1 "BLOCKER gw: subtask s5 review FAIL at ${SG:0:10} by claude" gate "$G"
expect "status keeps the subtask FAIL while its fix is on an unmerged child" 0 "note: subtask s5 review FAIL at ${SG:0:10}" status "$G"
git -C "$S" branch -q -D gw-child-fix
v --task gw --phase review --sha "$SG" --by claude --state PASS --subtask s5
expect "all verdicts PASS on the integrated tree: READY_FOR_PR" 0 "^Gate: READY_FOR_PR" gate "$G"
expect "manual fallback for an available model is refused, naming what --fallback takes" 2 "--fallback names the paired reviewer that is unavailable, but codex is available now, so it cannot be claimed as unavailable \(did you mean the other agent: --fallback 'claude unavailable'\?\)\. Example: --fallback 'codex unavailable' --by claude" verdict "$G" --task gw --phase review --sha "$SG" --by claude --state PASS --fallback codex
COLUMNS=250 expect "verdict --help states that --fallback names the unavailable paired reviewer, not the replacement" 0 "the paired reviewer that was unavailable \(not the replacement that reviewed\)" verdict --help
expect "refused fallback leaves paired evidence intact" 0 "^Gate: READY_FOR_PR" gate "$G"
expect "mark codex down after its implementation was reviewed" 0 "MODEL_UNAVAILABLE" agents "$G" --down codex --reason 401
expect "cross-model review survives implementer becoming unavailable" 0 "^Gate: READY_FOR_PR" gate "$G"
expect "clear codex runtime failure" 0 "codex: available" agents "$G" --up codex
# a fallback is stamped only from the review dispatch of that candidate, never from availability at verdict time
RPG_FACTORY_AGENTS=claude v --task c1 --phase review --sha "$C1" --by claude --state PASS
if ! grep -q '"fallback"' "$VD/c1__review__${C1:0:12}__claude.json"; then pass=$((pass + 1)); echo "PASS  single claude verdict without a fallback review dispatch stamps no fallback"
else fail=$((fail + 1)); echo "FAIL  single claude verdict without a fallback review dispatch stamps no fallback"; fi
# dr <task> <sha>: dispatch the review (records the reviewer and any fallback); gw joins a temporary task worktree
dr() {
  if [ "$1" = gw ]; then gi "$S" worktree add -q -b feat/core/demo-gw "$TMP/gate-gw" "$2"; fi
  python3 -B "$P" dispatch "$G" --task "$1" --phase review --sha "$2" --runner orca >/dev/null 2>&1 || echo "dispatch failed: $*"
  if [ "$1" = gw ]; then gi "$S" worktree remove --force "$TMP/gate-gw"; gi "$S" branch -q -D feat/core/demo-gw; fi
}
RPG_FACTORY_AGENTS=claude dr gw "$SG"; RPG_FACTORY_AGENTS=claude dr c1 "$C1"; RPG_FACTORY_AGENTS=claude dr c2 "$C2"
RPG_FACTORY_AGENTS=claude expect "single claude records the dispatched fallback" 0 "recorded review PASS" verdict "$G" --task gw --phase review --sha "$SG" --by claude --state PASS
RPG_FACTORY_AGENTS=claude v --task c1 --phase review --sha "$C1" --by claude --state PASS
RPG_FACTORY_AGENTS=claude v --task c2 --phase review --sha "$C2" --by claude --state PASS
RPG_FACTORY_AGENTS=claude expect "single claude fallback gate accepted" 0 "SAME_MODEL \(fallback: codex unavailable\)" gate "$G"
expect "fallback evidence stays SAME_MODEL when both models return" 0 "SAME_MODEL \(fallback: codex unavailable\)" gate "$G"
RPG_FACTORY_AGENTS=codex dr gw "$SG"; RPG_FACTORY_AGENTS=codex dr c1 "$C1"; RPG_FACTORY_AGENTS=codex dr c2 "$C2"
RPG_FACTORY_AGENTS=codex expect "single codex records the dispatched fallback" 0 "recorded review PASS" verdict "$G" --task gw --phase review --sha "$SG" --by codex --state PASS
RPG_FACTORY_AGENTS=codex v --task c1 --phase review --sha "$C1" --by codex --state PASS
RPG_FACTORY_AGENTS=codex v --task c2 --phase review --sha "$C2" --by codex --state PASS
RPG_FACTORY_AGENTS=codex expect "single codex fallback gate accepted" 0 "SAME_MODEL \(fallback: claude unavailable\)" gate "$G"
v --task c1 --phase review --sha "$C1" --by codex --state PASS
v --task c2 --phase review --sha "$C2" --by claude --state PASS
expect "restore paired review" 0 "recorded review PASS" verdict "$G" --task gw --phase review --sha "$SG" --by codex --state PASS
# start from no gw review and no gw QA: only `verdict --phase verify` may satisfy the gate, and it must record both
rm -f "$VD/gw__review.json" "$VD/gw__qa.json"
expect "without a gw review and QA the gate blocks" 1 "BLOCKER gw:" gate "$G"
expect "verify FAIL names where it failed" 2 "needs --failed-at review" verdict "$G" --task gw --phase verify --sha "$SG" --by codex --state FAIL
expect "verify --failed-at review records the review FAIL" 0 "recorded review FAIL" verdict "$G" --task gw --phase verify --sha "$SG" --by codex --state FAIL --failed-at review
if jq -e '.state == "FAIL"' "$VD/gw__review.json" >/dev/null && [ ! -e "$VD/gw__qa.json" ]; then pass=$((pass + 1)); echo "PASS  a review-only verify FAIL writes no QA record (QA stays NOT_RUN)"
else fail=$((fail + 1)); echo "FAIL  a review-only verify FAIL writes no QA record (QA stays NOT_RUN)"; fi
expect "verify records review and QA" 0 "recorded review PASS" verdict "$G" --task gw --phase verify --sha "$SG" --by codex --state PASS
if jq -e '.state == "PASS" and .by == "codex"' "$VD/gw__review.json" >/dev/null && jq -e '.state == "PASS" and .by == "codex"' "$VD/gw__qa.json" >/dev/null; then pass=$((pass + 1)); echo "PASS  verify wrote both the review and the QA record"
else fail=$((fail + 1)); echo "FAIL  verify wrote both the review and the QA record"; fi
expect "verify satisfies the gate" 0 "^Gate: READY_FOR_PR" gate "$G"
expect "mark model down" 0 "MODEL_UNAVAILABLE: revoked" agents "$G" --down codex --reason revoked
expect "restore model availability" 0 "codex: available" agents "$G" --up codex

expect "READY prints the PR command against the base branch" 0 "gh pr create --base develop --head feat/core/demo" gate "$G"
expect "READY prints the CI merge gate" 0 "gh pr checks <pr> --watch" gate "$G"
cp "$G" "$TMP/gate.bak"; sed -i 's/"objective":"o","paths":\["backend/"objective":"changed","paths":["backend/' "$G"
expect "a changed task in the plan makes its verdicts STALE" 1 "gw: review verdict is STALE - the plan" gate "$G"
cp "$TMP/gate.bak" "$G"
git -C "$C" worktree add -q "$TMP/client-wt" -b feat/core/demo-c1 2>/dev/null
expect "a pipeline worktree of the Unity project blocks" 1 "no-worktree repo has pipeline worktrees" gate "$G"
git -C "$C" worktree remove "$TMP/client-wt"; git -C "$C" branch -q -D feat/core/demo-c1
echo s > "$S/stray.txt"; gi "$S" add stray.txt; gi "$S" commit -qm "chore: stray"
expect "a change outside every owned path blocks" 1 "BLOCKER srv: changes outside every task's owned paths: stray.txt" gate "$G"
gi "$S" rm -q stray.txt; gi "$S" commit -qm "chore: drop stray"
echo y >> "$S/backend/gateway/a.go"; gi "$S" commit -qam "fix(gateway): after review"
expect "a change to owned paths after review makes it STALE" 1 "BLOCKER gw: review is STALE" gate "$G"
expect "and the QA on the old HEAD is STALE" 1 "BLOCKER srv: QA is STALE" gate "$G"
echo dirty > "$S/untracked.txt"
expect "an unclean integration tree blocks" 1 "integration tree .* has uncommitted changes" gate "$G"
rm "$S/untracked.txt"
SG2=$(git -C "$S" rev-parse HEAD)
v --task gw --phase review --sha "$SG2" --by codex --state PASS
v --task gw --phase review --sha "$SG2" --by claude --state PASS --subtask s2
v --task integration:srv --phase qa --sha "$SG2" --by codex --state PASS
N=$(plan none "$(sed 's/"deliver":"pr"/"deliver":"none"/' "$G")")
expect "deliver none: READY but no push or PR command" 0 "deliver is not .pr.: stop here" gate "$N"
refute "deliver none prints no gh pr create" "gh pr create" gate "$N"
R=$(plan reg "{$(sed 's/"id":"demo"/"id":"reg"/' <<<"$HEAD"),\"tasks\":[{\"id\":\"gw\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend/gateway/\"],\"acceptance\":[\"a\"]}]}")
python3 -B "$P" verdict "$R" --task gw --phase review --sha "$SG2" --by codex --state PASS >/dev/null
python3 -B "$P" verdict "$R" --task integration:server --phase qa --sha "$SG2" --by codex --state PASS >/dev/null
expect "--no-run-checks never delivers: UNVERIFIED" 1 "^Gate: UNVERIFIED" gate "$R" --no-run-checks
refute "UNVERIFIED prints no gh pr create" "gh pr create" gate "$R" --no-run-checks

case_end verdict-gate
fi

if has_case cleanup; then
case_start
echo "-- cleanup"
expect "before merge the integration branch remains" 0 "^Cleanup: CLEAN" cleanup "$G"
refute "before merge no integration branch deletion" "branch -d feat/core/demo($| )" cleanup "$G"
expect "no worktree or task branch left: CLEAN" 0 "^Cleanup: CLEAN" cleanup "$G"
git -C "$S" worktree add -q "$TMP/srv-gw" -b feat/core/demo-gw "$SG" 2>/dev/null
expect "an integrated task worktree is LEFTOVER with its remove command" 1 "git -C .* worktree remove .*srv-gw" cleanup "$G"
expect "and its merged branch is deleted with -d" 1 "branch -d feat/core/demo-gw" cleanup "$G"
expect "every run reminds to release worker sessions" 1 "orca orchestration worker-release --dispatch" cleanup "$G"
echo dirty > "$TMP/srv-gw/wip.txt"
expect "a worktree with uncommitted work is kept and named" 1 "KEPT  srv: worktree .* has uncommitted changes" cleanup "$G"
rm "$TMP/srv-gw/wip.txt"; git -C "$S" worktree remove "$TMP/srv-gw"; git -C "$S" branch -q -d feat/core/demo-gw
gi "$S" branch feat/core/demo-x develop; gi "$S" checkout -q feat/core/demo-x; echo z > "$S/z.txt"; gi "$S" add z.txt; gi "$S" commit -qm z; gi "$S" checkout -q feat/core/demo
expect "an unintegrated task branch is kept, not deleted" 1 "KEPT  srv: branch feat/core/demo-x is not in feat/core/demo" cleanup "$G"
refute "an unintegrated task branch gets no branch -d" "branch -d feat/core/demo-x" cleanup "$G"
gi "$S" branch -q -D feat/core/demo-x
expect "after removal: CLEAN" 0 "^Cleanup: CLEAN" cleanup "$G"
# a leftover Orca child of the task worktree (branch and directory <task branch>--<subtask>): status and cleanup name it
git -C "$S" worktree add -q "$TMP/srv-gw" -b feat/core/demo-gw "$SG" 2>/dev/null
git -C "$S" worktree add -q "$TMP/feat-core-demo-gw--s2" -b feat/core/demo-gw--s2 feat/core/demo-gw 2>/dev/null
echo c > "$TMP/feat-core-demo-gw--s2/backend/gateway/c.go"; gi "$TMP/feat-core-demo-gw--s2" add backend/gateway/c.go; gi "$TMP/feat-core-demo-gw--s2" commit -qm "feat(gateway): c"
expect "cleanup lists a leftover child as a child of its task" 1 "KEPT  srv: child of gw: leftover child worktree .*feat-core-demo-gw--s2 \(feat/core/demo-gw--s2\): merge it into feat/core/demo-gw" cleanup "$G"
refute "an unmerged child gets no remove command" "^  orca worktree rm .*--s2" cleanup "$G"
python3 -B "$P" status --json "$G" > "$TMP/status-child.json" 2>&1
if jq -e '(.tasks[] | select(.id == "gw") | .children) as $c | ($c | length) == 1 and ($c[0].branch == "feat/core/demo-gw--s2") and ($c[0].merged == false)' "$TMP/status-child.json" >/dev/null \
   && jq -e '.tasks[] | select(.id == "gw") | any(.notes[]; test("leftover child worktree .*--s2.*orca worktree rm --worktree"))' "$TMP/status-child.json" >/dev/null
then pass=$((pass + 1)); echo "PASS  status lists the leftover child with a note"
else fail=$((fail + 1)); echo "FAIL  status children"; head -c 1500 "$TMP/status-child.json"; fi
if python3 - "$ROOT" "$TMP/status-child.json" <<'PY'
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("lint", sys.argv[1] + "/scripts/checks/artifact-lint.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
schema = json.load(open(sys.argv[1] + "/docs/schemas/pipeline-status.schema.json", encoding="utf-8"))
assert not m.schema_errors(json.load(open(sys.argv[2], encoding="utf-8")), schema, schema)
PY
then pass=$((pass + 1)); echo "PASS  status --json with children matches the status schema"
else fail=$((fail + 1)); echo "FAIL  status --json children schema"; fi
gi "$TMP/srv-gw" merge -q --no-ff feat/core/demo-gw--s2 -m "merge s2"
expect "a merged child gets its orca worktree rm command" 1 "^  orca worktree rm --worktree '?path:[^ ]*feat-core-demo-gw--s2'?$" cleanup "$G"
echo wip > "$TMP/feat-core-demo-gw--s2/wip.txt"
expect "a merged child with uncommitted work is kept and named" 1 "KEPT  srv: child of gw: .*feat-core-demo-gw--s2 has uncommitted changes - not removed" cleanup "$G"
refute "a dirty child gets no remove command" "orca worktree rm .*--s2" cleanup "$G"
rm "$TMP/feat-core-demo-gw--s2/wip.txt"
cp "$TMP/feat-core-demo-gw--s2/.git" "$TMP/s2-gitfile"; echo "gitdir: $TMP/nowhere" > "$TMP/feat-core-demo-gw--s2/.git"
expect "a child whose git status fails is kept and named" 1 "KEPT  srv: child of gw: .git status. failed in .*feat-core-demo-gw--s2 - not removed" cleanup "$G"
refute "a child whose git status fails gets no remove command" "orca worktree rm .*--s2" cleanup "$G"
cp "$TMP/s2-gitfile" "$TMP/feat-core-demo-gw--s2/.git"
git -C "$S" worktree remove "$TMP/feat-core-demo-gw--s2"; git -C "$S" worktree remove "$TMP/srv-gw"
git -C "$S" branch -q -D feat/core/demo-gw--s2 feat/core/demo-gw
expect "child and task worktree removed: CLEAN" 0 "^Cleanup: CLEAN" cleanup "$G"
specs="$RPG_FACTORY_STATE_DIR/pipeline/demo/specs"; n=$(ls "$specs"/*.md 2>/dev/null | wc -l)
expect "cleanup names the plan's dispatch specs as kept state, still CLEAN" 0 "STATE $n spec file\(s\) in .*demo.specs .*delete by hand" cleanup "$G"
if [ "$n" -gt 0 ] && [ "$(ls "$specs"/*.md | wc -l)" = "$n" ]; then pass=$((pass + 1)); echo "PASS  cleanup never deletes the spec files"
else fail=$((fail + 1)); echo "FAIL  cleanup spec files ($n before)"; fi

case_end cleanup
fi

if has_case settled-workers; then
case_start
echo "-- cleanup and status: settled Orca workers that are not released"
# a fake `orca` first on PATH: worker-list prints $FAKE_ORCA_JSON (page 2 when --cursor is given), worktree list
# prints $FAKE_ORCA_WT (when set), `error` exits 1,
# `garbage` prints no JSON; every call is logged so the tests can prove only worker-list ran
FB="$TMP/fakebin"; mkdir -p "$FB"
cat > "$FB/fake_orca.py" <<'PY'
import json, os, sys
with open(os.environ["FAKE_ORCA_LOG"], "a", encoding="utf-8") as fh:
    fh.write(" ".join(sys.argv[1:]) + "\n")
mode = os.environ.get("FAKE_ORCA_MODE", "list")
if sys.argv[1:3] == ["status", "--json"]:
    reachable = os.environ.get("FAKE_ORCA_REACHABLE", "true") == "true"
    print(json.dumps({"ok": True, "result": {"runtime": {"reachable": reachable}}})); sys.exit(0)
if sys.argv[1:3] == ["worktree", "list"] and mode != "error" and os.environ.get("FAKE_ORCA_WT"):
    print(open(os.environ["FAKE_ORCA_WT"], encoding="utf-8").read()); sys.exit(0)
if sys.argv[1:3] == ["repo", "list"] and mode != "error" and os.environ.get("FAKE_ORCA_REPOS"):
    print(open(os.environ["FAKE_ORCA_REPOS"], encoding="utf-8").read()); sys.exit(0)
if sys.argv[1:3] == ["terminal", "list"] and mode != "error" and os.environ.get("FAKE_ORCA_TERMS"):
    print(open(os.environ["FAKE_ORCA_TERMS"], encoding="utf-8").read()); sys.exit(0)
if sys.argv[1:3] == ["orchestration", "check"] and mode != "error" and os.environ.get("FAKE_ORCA_CHECK"):
    print(open(os.environ["FAKE_ORCA_CHECK"], encoding="utf-8").read()); sys.exit(0)
if sys.argv[1:3] != ["orchestration", "worker-list"] or mode == "error":
    print("error: run not found", file=sys.stderr); sys.exit(1)
if mode == "garbage":
    print("not json"); sys.exit(0)
src = os.environ["FAKE_ORCA_JSON"] + (".page2" if "--cursor" in sys.argv else "")
print(json.dumps(json.load(open(src, encoding="utf-8"))))
PY
PYEXE=$(python3 -c 'import sys; print(sys.executable)')
if [ -n "$RPGF_WINDOWS" ]; then printf '@"%s" "%%~dp0fake_orca.py" %%*\r\n' "$PYEXE" > "$FB/orca.cmd"
else printf '#!/bin/sh\nexec "%s" "$(dirname "$0")/fake_orca.py" "$@"\n' "$PYEXE" > "$FB/orca"; chmod +x "$FB/orca"; fi
export FAKE_ORCA_LOG="$TMP/orca.log" FAKE_ORCA_JSON="$TMP/workers.json"
# w <dispatch> <workerState> <terminalState> <stage detail> [releaseRequestedAt]: one worker-list row
w() { jq -nc --arg d "$1" --arg ws "$2" --arg t "$3" --arg st "$4" --arg rq "${5:-}" '{dispatchId:$d,runId:"run_T",workerState:$ws,
  dispatchStatus:(if $ws=="running" then "dispatched" else "completed" end),terminalState:$t,
  resource:{releaseState:$t,releaseRequestedAt:(if $rq=="" then null else $rq end),
  retainedReason:(if $t=="retained" then "user_takeover" else null end)},projection:{stage:{detail:$st}}}'; }
jq -n --argjson a "$(w ctx_rel succeeded released settled 2026-11-05)" --argjson b "$(w ctx_ret succeeded retained settled)" \
  --argjson c "$(w ctx_run running active running)" --argjson d "$(w ctx_live succeeded active settled)" \
  '{ok:true,result:{workers:[$a,$b,$c,$d],page:{hasMore:true,nextCursor:"c2"},scope:{run:"run_T"}}}' > "$FAKE_ORCA_JSON"
jq -n --argjson e "$(w ctx_pend failed release_pending settled 2026-11-06)" --argjson f "$(w ctx_recl failed reclaimable settled)" \
  '{ok:true,result:{workers:[$e,$f],page:{hasMore:false,nextCursor:null}}}' > "$FAKE_ORCA_JSON.page2"
GO=$(plan gate-orca "$(sed 's/"id":"gw","repo":"srv"/"id":"gw","repo":"srv","orca_run":"run:run_T"/' "$G")")
fpath="$(path_entry "$FB"):$PATH"
# opath <name> <rc> <pattern> <args...> / oref <name> <pattern> <args...>: expect / refute with the fake orca first on PATH
opath() { local n="$1" rc="$2" pat="$3"; shift 3; PATH="$fpath" expect "$n" "$rc" "$pat" "$@"; }
oref() { local n="$1" pat="$2"; shift 2; PATH="$fpath" refute "$n" "$pat" "$@"; }
expect "a plan task's orca_run is valid" 0 "^OK" validate "$GO"
X=$(plan orca-bad "$(sed 's/"id":"gw","repo":"srv"/"id":"gw","repo":"srv","orca_run":""/' "$G")")
expect "an empty orca_run is an error" 1 "task gw: .orca_run. must be the task lead's Orca Run id" validate "$X"
if [ "$(python3 -B "$P" status --json "$G" | jq -c .tasks)" = "$(PATH="$fpath" python3 -B "$P" status --json "$GO" 2>/dev/null | jq -c .tasks)" ]
then pass=$((pass + 1)); echo "PASS  orca_run is not part of the verdict fingerprint (same task phases)"
else fail=$((fail + 1)); echo "FAIL  orca_run changed the task status"; fi
: > "$FAKE_ORCA_LOG"
opath "settled unreleased workers make cleanup LEFTOVER" 1 "^Cleanup: LEFTOVER" cleanup "$GO"
opath "a settled retained worker gets its release command" 1 "^  orca orchestration worker-release --dispatch ctx_ret$" cleanup "$GO"
opath "a settled worker with a live terminal is unreleased" 1 "worker-release --dispatch ctx_live$" cleanup "$GO"
opath "the next page is read: a reclaimable failed worker" 1 "UNRELEASED ctx_recl \(failed, terminal reclaimable\)" cleanup "$GO"
opath "a pending release is named with its request time" 1 "UNRELEASED ctx_pend .*release requested at 2026-11-06" cleanup "$GO"
opath "the run line counts unreleased, released and running" 1 "WORKERS UNRELEASED  run run_T: 4 settled worker\(s\) not released, 1 released, 1 running" cleanup "$GO"
oref "a released worker is no finding" "dispatch ctx_rel( |$)" cleanup "$GO"
oref "a running worker is no finding" "dispatch ctx_run( |$)" cleanup "$GO"
opath "--orca-run names a Run for a plan without orca_run" 1 "worker-release --dispatch ctx_ret" cleanup "$G" --orca-run run_T
if grep -q -- "--run run_T " "$FAKE_ORCA_LOG" && ! grep -qvE "^(orchestration worker-list --run run_T --limit 100 --full --json( --cursor c2)?|worktree list --limit 10000 --json|orchestration check --run run_T --all --json)$" "$FAKE_ORCA_LOG"
then pass=$((pass + 1)); echo "PASS  only read-only worker-list and worktree list calls, run:<id> normalised"
else fail=$((fail + 1)); echo "FAIL  orca calls"; sed 's/^/      /' "$FAKE_ORCA_LOG" | head; fi
PATH="$fpath" python3 -B "$P" cleanup --json "$GO" > "$TMP/cleanup-orca.json" 2>&1
if jq -e '.state == "LEFTOVER" and (.workers[0].unreleased | length) == 4 and any(.left[]; . == "orca:ctx_ret")' "$TMP/cleanup-orca.json" >/dev/null
then pass=$((pass + 1)); echo "PASS  cleanup --json carries the workers"
else fail=$((fail + 1)); echo "FAIL  cleanup --json workers"; head -c 1500 "$TMP/cleanup-orca.json"; fi
opath "status lists unreleased workers" 0 "^Workers:   UNRELEASED ctx_ret" status "$GO"
# one status --json run (stdout and stderr apart) for the next three cases
PATH="$fpath" python3 -B "$P" status --json "$GO" > "$TMP/so.json" 2> "$TMP/se.txt"; rc=$?
if jq -e '.next[0] | test("worker-release --dispatch ctx_ret$")' "$TMP/so.json" >/dev/null
then pass=$((pass + 1)); echo "PASS  status --json puts the release commands first in next"
else fail=$((fail + 1)); echo "FAIL  status --json next"; fi
if [ $rc = 0 ] && jq -e '.next[0] | test("worker-release --dispatch ctx_ret$")' "$TMP/so.json" >/dev/null && grep -q "^Workers:   UNRELEASED ctx_ret" "$TMP/se.txt"
then pass=$((pass + 1)); echo "PASS  status --json: unreleased workers on stderr, release command in next, exit 0"
else fail=$((fail + 1)); echo "FAIL  status --json unreleased (rc $rc)"; head -5 "$TMP/se.txt"; fi
if python3 - "$ROOT" "$TMP/so.json" <<'PY'
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("lint", sys.argv[1] + "/scripts/checks/artifact-lint.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
schema = json.load(open(sys.argv[1] + "/docs/schemas/pipeline-status.schema.json", encoding="utf-8"))
assert not m.schema_errors(json.load(open(sys.argv[2], encoding="utf-8")), schema, schema)
PY
then pass=$((pass + 1)); echo "PASS  status --json with workers still matches the status schema"
else fail=$((fail + 1)); echo "FAIL  status --json with workers schema"; fi
jq -n --argjson a "$(w ctx_rel succeeded released settled 2026-11-05)" --argjson c "$(w ctx_run running active running)" \
  '{ok:true,result:{workers:[$a,$c],page:{hasMore:false}}}' > "$FAKE_ORCA_JSON"
opath "every settled worker released: CLEAN" 0 "^Cleanup: CLEAN" cleanup "$GO"
opath "and the run line is OK" 0 "WORKERS OK  run run_T: 0 settled" cleanup "$GO"
# both row shapes of the real worker-list: the concise row (no --full: state, liveness, terminal, terminalState only) and
# the full row (workerState, dispatchStatus, resource, projection). Released is not UNRELEASED in either shape.
if grep -q -- "worker-list --run run_T --limit 100 --full --json" "$FAKE_ORCA_LOG"
then pass=$((pass + 1)); echo "PASS  worker-list is asked for --full rows"
else fail=$((fail + 1)); echo "FAIL  worker-list without --full"; sed 's/^/      /' "$FAKE_ORCA_LOG" | head -5; fi
cw() { jq -nc --arg d "$1" --arg s "$2" --arg t "$3" '{dispatchId:$d,taskId:"task_x",state:$s,liveness:"exited",terminal:"term_x",terminalState:$t,workspace:"w",host:"local"}'; }
# fw <dispatch> <ownershipState> <releaseState> <releaseCompletedAt|-> <projection resource state>: a settled full row
fw() { jq -nc --arg d "$1" --arg o "$2" --arg r "$3" --arg c "$4" --arg p "$5" '{dispatchId:$d,runId:"run_T",workerState:"succeeded",dispatchStatus:"completed",
  resource:{ownershipState:$o,releaseState:$r,retainedReason:null,releaseCompletedAt:(if $c=="-" then null else $c end)},
  projection:{stage:{worker:"succeeded",dispatch:"completed",detail:"settled"},resource:{state:$p}}}'; }
# aw <dispatch> <state> <reason>: a settled full row that never owned a terminal (live: ctx_24828b341e1e of run_386f601a03c7):
# resource, terminalState and the terminal handle are null, the projection says absent (not_materialized, or a failed terminal_create)
aw() { jq -nc --arg d "$1" --arg s "$2" --arg r "$3" '{dispatchId:$d,runId:"run_T",workerState:$s,dispatchStatus:(if $s=="failed" then "failed" else "completed" end),
  terminalState:null,agentTerminalHandle:null,resource:null,
  projection:{stage:{worker:$s,dispatch:"completed",detail:"settled"},resource:{state:"absent",reason:$r}}}'; }
jq -n --argjson a "$(cw ctx_c_rel succeeded released)" --argjson b "$(cw ctx_c_ret succeeded retained)" \
  --argjson c "$(cw ctx_c_act succeeded active)" --argjson d "$(cw ctx_c_run ready active)" \
  --argjson e "$(fw ctx_f_own released not_requested - owned)" --argjson f "$(fw ctx_f_done owned not_requested '2026-11-11 04:25:03' owned)" \
  --argjson g "$(fw ctx_f_proj owned not_requested - released)" --argjson h "$(fw ctx_f_ret external retained - retained)" \
  --argjson i "$(aw ctx_f_abs succeeded not_materialized)" --argjson j "$(aw ctx_f_tcf failed terminal_create_failed)" \
  '{ok:true,result:{workers:[$a,$b,$c,$d,$e,$f,$g,$h,$i,$j],page:{hasMore:false,nextCursor:null}}}' > "$FAKE_ORCA_JSON"
opath "concise and full rows: released ones are counted, the rest named" 1 "WORKERS UNRELEASED  run run_T: 3 settled worker\(s\) not released, 4 released, 1 running" cleanup "$GO"
oref "a concise released row is no finding" "dispatch ctx_c_rel( |$)" cleanup "$GO"
oref "a full row released by ownershipState is no finding" "dispatch ctx_f_own( |$)" cleanup "$GO"
oref "a full row with a releaseCompletedAt is no finding" "dispatch ctx_f_done( |$)" cleanup "$GO"
oref "a full row released by its projection is no finding" "dispatch ctx_f_proj( |$)" cleanup "$GO"
oref "a concise row of a running worker is no finding" "dispatch ctx_c_run( |$)" cleanup "$GO"
opath "a concise settled row whose terminal is retained gets its release command" 1 "^  orca orchestration worker-release --dispatch ctx_c_ret$" cleanup "$GO"
opath "a concise settled row whose terminal is still active is unreleased" 1 "UNRELEASED ctx_c_act \(succeeded, terminal active" cleanup "$GO"
opath "a full retained row is unreleased" 1 "worker-release --dispatch ctx_f_ret$" cleanup "$GO"
opath "status counts the same way" 0 "^Workers: UNRELEASED  run run_T: 3 settled worker\(s\) not released, 4 released, 1 running" status "$GO"
oref "a settled row that never had a terminal (absent, not_materialized) is no finding" "dispatch ctx_f_abs( |$)" cleanup "$GO"
oref "a failed terminal_create row with an absent resource is no finding" "dispatch ctx_f_tcf( |$)" cleanup "$GO"
PATH="$fpath" python3 -B "$P" cleanup --json "$GO" > "$TMP/cleanup-abs.json" 2>&1
if jq -e '([.left[]] | any(test("ctx_f_abs|ctx_f_tcf"))) | not' "$TMP/cleanup-abs.json" >/dev/null
then pass=$((pass + 1)); echo "PASS  rows with an absent resource are not in cleanup's left list"
else fail=$((fail + 1)); echo "FAIL  absent resource rows in left"; head -c 1200 "$TMP/cleanup-abs.json"; fi
jq -n --argjson a "$(fw ctx_f_own released not_requested - owned)" --argjson i "$(aw ctx_f_abs succeeded not_materialized)" \
  --argjson j "$(aw ctx_f_tcf failed terminal_create_failed)" '{ok:true,result:{workers:[$a,$i,$j],page:{hasMore:false,nextCursor:null}}}' > "$FAKE_ORCA_JSON"
opath "only released and never-had-a-terminal rows: cleanup stays CLEAN" 0 "^Cleanup: CLEAN" cleanup "$GO"
opath "and the run line is OK with one released worker" 0 "WORKERS OK  run run_T: 0 settled worker\(s\) not released, 1 released, 0 running" cleanup "$GO"
oref "status prints no release command for them" "worker-release --dispatch ctx_f_(abs|tcf)" status "$GO"
# a task lead's report: the durable record (`report`) and, with an Orca Run, a 'task done' message of an older lead
export FAKE_ORCA_CHECK="$TMP/orca-check.json"
jq -n '{ok:true,result:{messages:[{id:"m1",type:"heartbeat",subject:"alive"},{id:"m2",type:"status",subject:"task done: gw",body:"branch x"}]}}' > "$FAKE_ORCA_CHECK"
: > "$FAKE_ORCA_LOG"
opath "status --orca-run: a task done message without a durable record is a note" 0 "note: lead report: task done: gw \(an Orca message only" status "$GO"
if grep -q "^orchestration check --run run_T --all --json$" "$FAKE_ORCA_LOG" && ! grep -E "orchestration check" "$FAKE_ORCA_LOG" | grep -qE -- "--ack|--peek|--unread|--wait"
then pass=$((pass + 1)); echo "PASS  the inbox is read with check --all only (never marks a message read)"
else fail=$((fail + 1)); echo "FAIL  orchestration check call"; sed 's/^/      /' "$FAKE_ORCA_LOG" | head -5; fi
FAKE_ORCA_MODE=error oref "orca check failing: no opinion, no note, no traceback" "Orca message only|Traceback" status "$GO"
oref "without an Orca Run the inbox is not read" "Orca message only" status "$G"
expect "report: records the lead report of gw" 0 "^recorded lead report for gw at ${SG:0:10}: " report "$GO" --task gw --sha "$SG" --body "gw done: all checks pass"
opath "the durable record is shown with its SHA and summary" 0 "note: lead report: [0-9TZ:-]+ @${SG:0:10} gw done: all checks pass" status "$GO"
oref "a durable record replaces the message note" "Orca message only" status "$GO"
unset FAKE_ORCA_CHECK
for mode in error garbage; do
  FAKE_ORCA_MODE=$mode opath "orca $mode: NOT_AVAILABLE, never a failure" 0 "WORKERS NOT_AVAILABLE  run run_T: orca worker-list exited" cleanup "$GO"
  FAKE_ORCA_MODE=$mode oref "orca $mode: no traceback" "Traceback" status "$GO"
done
# status_json_na <name> [env...]: status --json exits 0, stdout is valid JSON, stderr has the NOT_AVAILABLE Run line
status_json_na() { local n="$1" rc; shift
  env "$@" python3 -B "$P" status --json "$GO" > "$TMP/so.json" 2> "$TMP/se.txt"; rc=$?
  if [ $rc = 0 ] && jq -e '.valid' "$TMP/so.json" >/dev/null && grep -q "^Workers: NOT_AVAILABLE  run run_T" "$TMP/se.txt"
  then pass=$((pass + 1)); echo "PASS  $n"
  else fail=$((fail + 1)); echo "FAIL  $n (rc $rc)"; head -5 "$TMP/se.txt"; fi; }
status_json_na "orca erroring: status --json prints NOT_AVAILABLE on stderr, valid JSON, exit 0" PATH="$fpath" FAKE_ORCA_MODE=error
noorca=""; IFS=: read -ra parts <<<"$PATH"
for d in "${parts[@]}"; do [ -e "$d/orca" ] || [ -e "$d/orca.exe" ] || [ -e "$d/orca.cmd" ] || noorca="$noorca${noorca:+:}$d"; done
PATH="$noorca" expect "orca missing: NOT_AVAILABLE, cleanup stays CLEAN" 0 "WORKERS NOT_AVAILABLE  run run_T: orca is not on PATH" cleanup "$GO"
PATH="$noorca" expect "orca missing: status still exits 0" 0 "^Workers: NOT_AVAILABLE  run run_T" status "$GO"
status_json_na "orca missing: status --json prints NOT_AVAILABLE on stderr, valid JSON, exit 0" PATH="$noorca"
refute "no Run named: no worker line" "WORKERS " cleanup "$G"
# a child with any name (orca worktree create --parent-worktree path:<task worktree> --name isolated-qa): Orca's
# lineage (parentWorktreeId, or the parent's childWorktreeIds) names it; orca unavailable means the naming rule only
git -C "$S" worktree add -q "$TMP/srv-gw" -b feat/core/demo-gw "$SG" 2>/dev/null
git -C "$S" worktree add -q "$TMP/isolated-qa" -b isolated-qa feat/core/demo-gw 2>/dev/null
wtp() { git -C "$1" rev-parse --show-toplevel; }
export FAKE_ORCA_WT="$TMP/orca-wt.json"
jq -n --arg p "$(wtp "$TMP/srv-gw")" --arg c "$(wtp "$TMP/isolated-qa")" --arg o "$TMP/other-child"   '{ok:true,result:{worktrees:[{id:"r::gw",path:$p,parentWorktreeId:null,childWorktreeIds:[]},
   {id:"r::qa",path:$c,parentWorktreeId:"r::gw",childWorktreeIds:[]},{id:"r::o",path:$o,parentWorktreeId:"r::gw"}]}}' > "$FAKE_ORCA_WT"
: > "$FAKE_ORCA_LOG"
opath "Orca lineage: a child named isolated-qa is a child of its task" 1 "KEPT  srv: child of gw: leftover child worktree .*isolated-qa \(isolated-qa\): merged, then remove it" cleanup "$G"
opath "Orca lineage: the merged child gets its orca worktree rm command" 1 "^  orca worktree rm --worktree '?path:[^ ]*isolated-qa'?$" cleanup "$G"
if PATH="$fpath" python3 -B "$P" status --json "$G" 2>/dev/null | jq -e '.tasks[] | select(.id == "gw") | (.children | length) == 1 and .children[0].branch == "isolated-qa"' >/dev/null
then pass=$((pass + 1)); echo "PASS  Orca lineage: status lists the isolated-qa child"
else fail=$((fail + 1)); echo "FAIL  Orca lineage: status children"; fi
if grep -q "^worktree list --limit 10000 --json$" "$FAKE_ORCA_LOG" && ! grep -qvE "^(worktree list --limit 10000 --json|terminal list --worktree path:[^ ]+ --limit 100 --json|orchestration worker-list .*)$" "$FAKE_ORCA_LOG"
then pass=$((pass + 1)); echo "PASS  Orca lineage is read with the read-only worktree list only"
else fail=$((fail + 1)); echo "FAIL  Orca lineage calls"; sed 's/^/      /' "$FAKE_ORCA_LOG" | head; fi
jq '.result.worktrees |= map(if .id == "r::qa" then .parentWorktreeId = null elif .id == "r::gw" then .childWorktreeIds = ["r::qa"] else . end)' "$FAKE_ORCA_WT" > "$FAKE_ORCA_WT.2"; mv "$FAKE_ORCA_WT.2" "$FAKE_ORCA_WT"
opath "Orca lineage: the parent's childWorktreeIds also name the child" 1 "KEPT  srv: child of gw: leftover child worktree .*isolated-qa" cleanup "$G"
FAKE_ORCA_MODE=error oref "orca failing: the naming rule only, the isolated-qa child is not named" "child of gw" cleanup "$G"
FAKE_ORCA_MODE=error oref "orca failing: no traceback" "Traceback" cleanup "$G"
PATH="$noorca" refute "orca missing: the naming rule only, never an error" "child of gw|Traceback" cleanup "$G"
PATH="$noorca" expect "orca missing: status still exits 0 with a child by lineage only" 0 "^Pipeline demo" status "$G"
unset FAKE_ORCA_WT
git -C "$S" worktree remove "$TMP/isolated-qa"; git -C "$S" worktree remove "$TMP/srv-gw"
git -C "$S" branch -q -D isolated-qa feat/core/demo-gw
expect "lineage children removed: CLEAN" 0 "^Cleanup: CLEAN" cleanup "$G"
echo "-- cleanup: plain task worktree, prunable record, leftover directory, stale Orca record, bound terminals"
NOKILL="kill|taskkill|Stop-Process|--force"
# a plain git task worktree: removed with `git worktree remove` (no --force)
git -C "$S" worktree add -q "$TMP/srv-gw" -b feat/core/demo-gw "$SG" 2>/dev/null
opath "plain task worktree: git worktree remove without --force" 1 "^  git -C .* worktree remove [^ ]*srv-gw'?$" cleanup "$G"
oref "plain task worktree: no --force, no process kill anywhere in the output" "$NOKILL" cleanup "$G"
# terminals bound to it (read-only orca terminal list) and the CLI-exit reminder
export FAKE_ORCA_TERMS="$TMP/orca-terms.json"
jq -n '{ok:true,result:{terminals:[{handle:"term_codex1",title:"codex implementer"}]}}' > "$FAKE_ORCA_TERMS"
opath "a bound Orca terminal is named before the removal" 1 "KEPT  srv: worktree .*srv-gw is still bound to Orca terminal term_codex1 \(codex implementer\)" cleanup "$G"
opath "the removal still prints git worktree remove" 1 "worktree remove .*srv-gw" cleanup "$G"
opath "the task lead confirms each released worker's CLI exited (codex process gone)" 1 "confirms that each released worker's CLI exited \(a released Codex worker: its codex process is gone\)" cleanup "$G"
opath "a process the run did not start is named to the user, never stopped" 1 "named to the user \(PID, command\) and left to the user's decision, never stopped by the run" cleanup "$G"
FAKE_ORCA_MODE=error opath "terminal list failing: no opinion, no traceback, still LEFTOVER" 1 "^Cleanup: LEFTOVER" cleanup "$G"
FAKE_ORCA_MODE=error oref "terminal list failing: no terminal line, no traceback" "bound to Orca terminal|Traceback" cleanup "$G"
unset FAKE_ORCA_TERMS
git -C "$S" worktree remove "$TMP/srv-gw"; git -C "$S" branch -q -d feat/core/demo-gw
# a prunable record (directory gone, git still lists the worktree): `git branch -d` fails until git worktree prune
git -C "$S" worktree add -q "$TMP/srv-gw" -b feat/core/demo-gw "$SG" 2>/dev/null
rm -rf "$TMP/srv-gw"
if ! git -C "$S" branch -d feat/core/demo-gw >/dev/null 2>&1; then pass=$((pass + 1)); echo "PASS  precondition: a prunable record blocks git branch -d"
else fail=$((fail + 1)); echo "FAIL  precondition: git branch -d succeeded on a prunable record"; fi
opath "a prunable task worktree record is LEFTOVER, never CLEAN" 1 "^Cleanup: LEFTOVER" cleanup "$G"
opath "the prunable record is named" 1 "KEPT  srv: LEFTOVER worktree record .*srv-gw .*feat/core/demo-gw.* is prunable" cleanup "$G"
opath "git worktree prune is printed" 1 "^  git -C .* worktree prune$" cleanup "$G"
PATH="$fpath" python3 -B "$P" cleanup "$G" > "$TMP/cleanup-prune.txt" 2>&1
if [ "$(grep -n 'worktree prune$' "$TMP/cleanup-prune.txt" | head -1 | cut -d: -f1)" -lt "$(grep -n 'branch -d feat/core/demo-gw' "$TMP/cleanup-prune.txt" | head -1 | cut -d: -f1)" ] 2>/dev/null
then pass=$((pass + 1)); echo "PASS  git worktree prune comes before git branch -d"
else fail=$((fail + 1)); echo "FAIL  prune order"; sed 's/^/      /' "$TMP/cleanup-prune.txt" | head -12; fi
git -C "$S" worktree prune
if git -C "$S" branch -q -d feat/core/demo-gw 2>/dev/null; then pass=$((pass + 1)); echo "PASS  after git worktree prune the task branch deletes with -d"
else fail=$((fail + 1)); echo "FAIL  git branch -d after prune"; fi
expect "after prune and branch delete: CLEAN" 0 "^Cleanup: CLEAN" cleanup "$G"
# a leftover task directory (empty, then with a file), no git worktree any more: LEFTOVER with prune then orca worktree rm
LD="$WS/feat-core-demo-gw"; mkdir -p "$LD"
opath "an empty leftover task directory is LEFTOVER, never CLEAN" 1 "^Cleanup: LEFTOVER" cleanup "$G"
opath "the leftover directory is named" 1 "KEPT  srv: LEFTOVER directory .*feat-core-demo-gw \(no git worktree any more\)" cleanup "$G"
opath "the leftover directory gets git worktree prune" 1 "^  git -C .* worktree prune$" cleanup "$G"
opath "then orca worktree rm of the directory" 1 "^  orca worktree rm --worktree '?path:[^ ]*feat-core-demo-gw'?$" cleanup "$G"
opath "a busy directory: a process holds it, the user decides" 1 "reports the directory busy .*name its PID and command to the user and leave the decision to them" cleanup "$G"
refute "an empty leftover directory is never CLEAN" "^Cleanup: CLEAN" cleanup "$G"
PATH="$fpath" python3 -B "$P" cleanup --json "$G" > "$TMP/cleanup-left.json" 2>&1
if jq -e '.state == "LEFTOVER" and any(.leftovers[]; .kind == "directory" and (.path | test("feat-core-demo-gw$")) and (.commands | length) == 2 and (.commands[0] | test("worktree prune$")) and (.commands[1] | test("orca worktree rm")))' "$TMP/cleanup-left.json" >/dev/null
then pass=$((pass + 1)); echo "PASS  cleanup --json carries the leftover directory with its commands"
else fail=$((fail + 1)); echo "FAIL  cleanup --json leftovers"; head -c 1500 "$TMP/cleanup-left.json"; fi
# the processes that may keep the leftover directory busy (read-only process listing, injected fixture): named with PID,
# command and start time; the user decides
jq -n --arg d "$LD" '[{pid:3101,ppid:1,name:"codex.exe",command:("C:/tools/codex.exe --cwd " + $d),started:"2026-11-10T08:00:00"},
  {pid:3102,ppid:99999,name:"wsl.exe",command:"wsl.exe -d Ubuntu -- sleep infinity",started:"2026-11-09T20:00:00"},
  {pid:3103,ppid:3101,name:"wsl.exe",command:"wsl.exe -d Ubuntu -- sleep infinity",started:"2026-11-10T08:00:05"},
  {pid:3104,ppid:1,name:"node.exe",command:"node other.js",started:"2026-11-10T09:00:00"},
  {pid:3105,ppid:1,name:"node.exe",command:("node " + $d + "2/tool.js"),started:"2026-11-10T09:30:00"},
  {pid:3106,ppid:1,name:"node.exe",command:("node " + $d + "/sub/tool.js"),started:"2026-11-10T09:40:00"}]' > "$TMP/proc-busy.json"
export BUSYP="$TMP/proc-busy.json"
RPG_FACTORY_PROCESS_TABLE="$BUSYP" opath "a process whose command line names the leftover directory is listed with PID, command and start" 1 "KEPT  srv: BUSY\? process 3101 \(codex.exe\) started 2026-11-10T08:00:00: .*codex.exe --cwd .*feat-core-demo-gw - its command line names the directory; .*the user decides" cleanup "$G"
RPG_FACTORY_PROCESS_TABLE="$BUSYP" opath "an orphaned wsl.exe sleep infinity is listed" 1 "BUSY\? process 3102 \(wsl.exe\) started 2026-11-09T20:00:00: .*sleep infinity - orphaned wsl.exe sleep infinity" cleanup "$G"
RPG_FACTORY_PROCESS_TABLE="$BUSYP" oref "a wsl.exe sleep infinity whose parent is alive is not named" "process 3103" cleanup "$G"
RPG_FACTORY_PROCESS_TABLE="$BUSYP" oref "an unrelated process is not named" "process 3104" cleanup "$G"
RPG_FACTORY_PROCESS_TABLE="$BUSYP" oref "a sibling directory with the same prefix (...-gw2) is not named" "process 3105" cleanup "$G"
RPG_FACTORY_PROCESS_TABLE="$BUSYP" opath "a process inside the directory (path boundary) is named" 1 "BUSY\? process 3106 \(node.exe\) started 2026-11-10T09:40:00: .*sub/tool.js - its command line names the directory" cleanup "$G"
RPG_FACTORY_PROCESS_TABLE="$BUSYP" oref "busy processes: never a kill command" "$NOKILL" cleanup "$G"
RPG_FACTORY_PROCESS_TABLE="$BUSYP" oref "busy processes: no traceback" "Traceback" cleanup "$G"
RPG_FACTORY_PROCESS_TABLE=none opath "a process listing that fails names nothing, still LEFTOVER" 1 "^Cleanup: LEFTOVER" cleanup "$G"
RPG_FACTORY_PROCESS_TABLE=none oref "a failing process probe: no BUSY line, no traceback" "BUSY\? process|Traceback" cleanup "$G"
PATH="$fpath" RPG_FACTORY_PROCESS_TABLE="$BUSYP" python3 -B "$P" cleanup --json "$G" > "$TMP/cleanup-busy.json" 2>&1
if jq -e 'any(.leftovers[]; .kind == "directory" and (.processes | map(.pid) | sort) == [3101, 3102, 3106] and all(.processes[]; .command != "" and .started != "" and .why != ""))' "$TMP/cleanup-busy.json" >/dev/null
then pass=$((pass + 1)); echo "PASS  cleanup --json lists the busy candidates (PID, command, start) per leftover directory"
else fail=$((fail + 1)); echo "FAIL  cleanup --json processes"; head -c 1500 "$TMP/cleanup-busy.json"; fi
echo x > "$LD/file.txt"
opath "a non-empty leftover task directory is LEFTOVER too" 1 "KEPT  srv: LEFTOVER directory .*feat-core-demo-gw" cleanup "$G"
oref "cleanup output never kills a process" "$NOKILL" cleanup "$G"
# a stale Orca record of a removed task worktree (directory gone): LEFTOVER with the same commands
rm -rf "$LD"
export FAKE_ORCA_WT="$TMP/orca-wt-stale.json"
jq -n --arg p "$LD" '{ok:true,result:{worktrees:[{id:"r::gw",path:$p,parentWorktreeId:null}]}}' > "$FAKE_ORCA_WT"
opath "a stale Orca record of a removed task worktree is LEFTOVER" 1 "KEPT  srv: LEFTOVER Orca record of the removed task worktree .*feat-core-demo-gw: .git worktree prune., then .orca worktree rm." cleanup "$G"
opath "the stale record gets prune then orca worktree rm" 1 "^  orca worktree rm --worktree '?path:[^ ]*feat-core-demo-gw'?$" cleanup "$G"
oref "a stale Orca record is never CLEAN" "^Cleanup: CLEAN" cleanup "$G"
oref "the stale record output never kills a process" "$NOKILL" cleanup "$G"
FAKE_ORCA_MODE=error opath "orca failing: no opinion on records, CLEAN" 0 "^Cleanup: CLEAN" cleanup "$G"
PATH="$noorca" expect "orca missing: no opinion on records, CLEAN" 0 "^Cleanup: CLEAN" cleanup "$G"
unset FAKE_ORCA_WT
opath "no leftover directory and no record: CLEAN again" 0 "^Cleanup: CLEAN" cleanup "$G"
# no printed dispatch or cleanup command is an orca worktree create (it writes branch.<name>.base into the shared .git/config)
: > "$FAKE_ORCA_LOG"
git -C "$S" worktree add -q "$TMP/srv-gw" -b feat/core/demo-gw "$SG" 2>/dev/null
for c in "dispatch $G --task gw --phase lead --runner orca" "dispatch $G --task gw --phase lead --placement child --runner orca" "cleanup $G" "cleanup $G --after-merge"; do
  out=$(PATH="$fpath" python3 -B "$P" $c 2>&1)
  if ! grep -q "worktree create" <<<"$out"; then pass=$((pass + 1)); echo "PASS  no orca worktree create printed: $c" | sed "s#$TMP/##g"
  else fail=$((fail + 1)); echo "FAIL  orca worktree create printed: $c"; fi
done
git -C "$S" worktree remove "$TMP/srv-gw"; git -C "$S" branch -q -d feat/core/demo-gw
if ! grep -qE "worktree (create|set|rm)|terminal (close|send)" "$FAKE_ORCA_LOG"; then pass=$((pass + 1)); echo "PASS  dispatch and cleanup only read Orca: no worktree create, set or rm, no terminal close"
else fail=$((fail + 1)); echo "FAIL  orca write call"; sed 's/^/      /' "$FAKE_ORCA_LOG" | head; fi
# a new task worktree is an Orca child of the integration checkout ($S on feat/core/demo); dispatch only prints it
: > "$FAKE_ORCA_LOG"
opath "fake orca: git creates the task worktree" 0 "^git -C .* worktree add --no-track -b feat/core/demo-gw" dispatch "$G" --task gw --phase lead --runner orca
oref "fake orca: a new task worktree under the integration checkout has no --no-parent" "--no-parent" dispatch "$G" --task gw --phase lead --runner orca
opath "fake orca: orca worktree set names the integration checkout as parent, printed (not run)" 0 "^orca worktree set --worktree '?path:[^' ]*feat-core-demo-gw'? --parent-worktree '?path:[^' ]*rpg-mmo-server'? --display-name " dispatch "$G" --task gw --phase lead --runner orca
opath "fake orca: shared placement launches the lead" 0 "^orca agent launch --agent claude --worktree .*feat-core-demo-gw" dispatch "$G" --task gw --phase lead --placement shared --runner orca
if ! grep -q "worktree create" "$FAKE_ORCA_LOG"; then pass=$((pass + 1)); echo "PASS  fake orca: dispatch --phase lead only prints the worktree create"
else fail=$((fail + 1)); echo "FAIL  fake orca: dispatch ran orca worktree create"; sed 's/^/      /' "$FAKE_ORCA_LOG" | head; fi
# Orca lists a worktree it did not create (git worktree add) under "Hidden worktrees" when the repo's
# externalWorktreeVisibility is hide: dispatch prints `orca repo set ... show` before the worktree add (lead handoff)
# or the worker-start that creates one (child placement), only for hide; show, inherit, absent, an unlisted repo and a
# failing orca print nothing. The fake orca only answers the read-only `repo list`.
export FAKE_ORCA_REPOS="$TMP/orca-repos.json"
repos() { jq -n --arg p "$1" --arg v "$2" '{ok:true,result:{repos:[{id:"r1",path:$p,externalWorktreeVisibility:(if $v=="" then null else $v end)}]}}' > "$FAKE_ORCA_REPOS"; }
vis_out() { PATH="$fpath" python3 -B "$P" "$@" 2>&1; }
SHOW_RE="^orca repo set --repo '?path:[^' ]*rpg-mmo-server'? --external-worktree-visibility show$"
line_of() { grep -nE "$1" <<<"$2" | head -1 | cut -d: -f1; }
: > "$FAKE_ORCA_LOG"
repos "$(wtp "$S")" hide
out=$(vis_out dispatch "$G" --task gw --phase lead --runner orca)
repo_ln=$(line_of "$SHOW_RE" "$out"); add_ln=$(line_of "^git -C .* worktree add --no-track" "$out")
if [ -n "$repo_ln" ] && [ -n "$add_ln" ] && [ "$repo_ln" -lt "$add_ln" ]; then pass=$((pass + 1)); echo "PASS  visibility hide: the lead dispatch prints orca repo set ... show before the worktree add"
else fail=$((fail + 1)); echo "FAIL  visibility hide: repo set line $repo_ln, worktree add line $add_ln"; sed 's/^/      /' <<<"$out" | head -8; fi
if grep -qx "repo list --json" "$FAKE_ORCA_LOG" && ! grep -q "^repo set" "$FAKE_ORCA_LOG"; then pass=$((pass + 1)); echo "PASS  visibility hide: only the read-only repo list ran, repo set is printed, never run"
else fail=$((fail + 1)); echo "FAIL  visibility hide: orca calls"; sed 's/^/      /' "$FAKE_ORCA_LOG" | head -5; fi
for v in show inherit ""; do
  repos "$(wtp "$S")" "$v"; out=$(vis_out dispatch "$G" --task gw --phase lead --runner orca)
  if ! grep -q "orca repo set" <<<"$out" && grep -q "^git -C .* worktree add --no-track" <<<"$out"; then pass=$((pass + 1)); echo "PASS  visibility '${v:-absent}': no repo set line, the worktree add is still printed"
  else fail=$((fail + 1)); echo "FAIL  visibility '${v:-absent}' printed a repo set line"; sed 's/^/      /' <<<"$out" | head -5; fi
done
repos "$TMP/another-repo" hide; out=$(vis_out dispatch "$G" --task gw --phase lead --runner orca)
if ! grep -q "orca repo set" <<<"$out"; then pass=$((pass + 1)); echo "PASS  visibility hide of another repo: no repo set line"
else fail=$((fail + 1)); echo "FAIL  visibility hide of another repo printed a repo set line"; fi
repos "$(wtp "$S")" hide; out=$(FAKE_ORCA_MODE=error vis_out dispatch "$G" --task gw --phase lead --runner orca); rc=$?
if ! grep -q "orca repo set" <<<"$out" && grep -q "^git -C .* worktree add --no-track" <<<"$out"; then pass=$((pass + 1)); echo "PASS  orca failing: no repo set line, no error"
else fail=$((fail + 1)); echo "FAIL  orca failing: rc=$rc"; sed 's/^/      /' <<<"$out" | head -5; fi
repos "$(wtp "$S")" hide
out=$(vis_out dispatch "$G" --task integration:srv --phase qa --sha "$SG" --placement child --runner orca)
repo_ln=$(line_of "$SHOW_RE" "$out"); start_ln=$(line_of "^orca orchestration worker-start .*--worktree new-child" "$out")
if [ -n "$repo_ln" ] && [ -n "$start_ln" ] && [ "$repo_ln" -lt "$start_ln" ]; then pass=$((pass + 1)); echo "PASS  visibility hide: a child placement prints repo set before its worker-start"
else fail=$((fail + 1)); echo "FAIL  visibility hide, child placement: repo set line $repo_ln, worker-start line $start_ln"; sed 's/^/      /' <<<"$out" | head -8; fi
# `orca repo list` holds the main checkout: a placement whose repo path (or child parent) is a linked worktree of it
# still gets the hint, naming the main checkout; show prints nothing
git -C "$S" worktree add -q "$TMP/vis-link" -b vis-link develop 2>/dev/null
if PATH="$fpath" python3 -B - "$ROOT" "$(wtp "$S")" "$(wtp "$TMP/vis-link")" "$FAKE_ORCA_REPOS" <<'PY'
import importlib.util, json, shlex, sys
spec = importlib.util.spec_from_file_location("fp", sys.argv[1] + "/scripts/factory-pipeline.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
main, link, repos = sys.argv[2:5]
def names_main(line):
    args = shlex.split(line or "")
    return args[:3] == ["orca", "repo", "set"] and any(m.norm_wt(a[len("path:"):]) == m.norm_wt(main) for a in args if a.startswith("path:"))
top = {"worktree": "new-top-level", "new": True, "repo": f"path:{link}", "base": "develop"}
child = {"worktree": "new-child", "new": True, "child_of": link, "base": "develop"}
assert names_main(m.place_show_line(top)), m.place_show_line(top)
assert names_main(m.place_show_line(child)), m.place_show_line(child)
assert m.place_show_line({"worktree": "current", "new": False}) is None
assert m.place_show_line({"worktree": "new-top-level", "new": True}) is None
json.dump({"ok": True, "result": {"repos": [{"id": "r1", "path": main, "externalWorktreeVisibility": "show"}]}}, open(repos, "w"))
assert m.place_show_line(top) is None
PY
then pass=$((pass + 1)); echo "PASS  visibility hide: a repo path that is a linked worktree maps to its main checkout for the hint (show: none)"
else fail=$((fail + 1)); echo "FAIL  visibility hide: linked-worktree repo path"; fi
git -C "$S" worktree remove --force "$TMP/vis-link"; git -C "$S" branch -q -D vis-link
unset FAKE_ORCA_REPOS
# children of the integration checkout ($S on feat/core/demo): the integration QA child dispatch names
# (<topic>--qa) and a helper with any name whose Orca lineage parent is the integration checkout; status lists them
# once per repo in integration_children with cleanup guidance, cleanup names them "child of integration:srv"
opath "integration QA --placement child (orca on PATH): worker-start --worktree new-child at the SHA" 0 "^orca orchestration worker-start .*--worktree new-child --name feat/core/demo--qa-${SG:0:7} --base-branch $SG " dispatch "$G" --task integration:srv --phase qa --sha "$SG" --placement child --runner orca
git -C "$S" worktree add -q "$TMP/feat-core-demo--qa" -b feat/core/demo--qa "$SG" 2>/dev/null
git -C "$S" worktree add -q "$TMP/int-helper" -b int-helper "$SG" 2>/dev/null
export FAKE_ORCA_WT="$TMP/orca-wt.json"
jq -n --arg p "$(wtp "$S")" --arg h "$(wtp "$TMP/int-helper")" \
  '{ok:true,result:{worktrees:[{id:"r::int",path:$p,parentWorktreeId:null},{id:"r::h",path:$h,parentWorktreeId:"r::int"}]}}' > "$FAKE_ORCA_WT"
PATH="$fpath" python3 -B "$P" status --json "$G" > "$TMP/status-int.json" 2>/dev/null
if jq -e '(.integration_children | length) == 2 and all(.integration_children[]; .repo == "srv" and .merged
     and (.note | test("leftover child worktree .*merged, then remove it at once: orca worktree rm --worktree")))
   and ([.integration_children[].branch] | sort) == ["feat/core/demo--qa", "int-helper"]
   and all(.tasks[]; (.children | length) == 0)' "$TMP/status-int.json" >/dev/null && python3 - "$ROOT" "$TMP/status-int.json" <<'PY'
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("lint", sys.argv[1] + "/scripts/checks/artifact-lint.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
schema = json.load(open(sys.argv[1] + "/docs/schemas/pipeline-status.schema.json", encoding="utf-8"))
assert not m.schema_errors(json.load(open(sys.argv[2], encoding="utf-8")), schema, schema)
PY
then pass=$((pass + 1)); echo "PASS  status lists integration-checkout children once per repo (name and lineage), schema-valid"
else fail=$((fail + 1)); echo "FAIL  status integration_children"; head -c 1500 "$TMP/status-int.json"; fi
opath "status text names the integration child with its rm command" 0 "^  \[integration:srv\] child: leftover child worktree .*feat-core-demo--qa .*orca worktree rm" status "$G"
opath "cleanup names the integration QA child" 1 "KEPT  srv: child of integration:srv: leftover child worktree .*feat-core-demo--qa" cleanup "$G"
opath "cleanup names the lineage helper of the integration checkout" 1 "KEPT  srv: child of integration:srv: leftover child worktree .*int-helper" cleanup "$G"
unset FAKE_ORCA_WT
# test slots (tests/run-all.sh lock_publish: <state>/locks/run-all-slots/<n>/{pid,winpid,checkout,started}) held by a run
# in one of the plan's checkouts are named with PID, checkout, start and liveness; one elsewhere is not; nothing is stopped
SLOTS="$RPG_FACTORY_STATE_DIR/locks/run-all-slots"; mkdir -p "$SLOTS/1" "$SLOTS/2" "$SLOTS/3"
printf '4242\n' > "$SLOTS/1/pid"; printf '4242\n' > "$SLOTS/1/winpid"; wtp "$S" > "$SLOTS/1/checkout"; printf '2026-11-11T01:02:03Z\n' > "$SLOTS/1/started"
printf '5151\n' > "$SLOTS/2/pid"; printf '5151\n' > "$SLOTS/2/winpid"; printf '%s\n' "$TMP/elsewhere" > "$SLOTS/2/checkout"; printf '2026-11-11T02:00:00Z\n' > "$SLOTS/2/started"
printf '9999\n' > "$SLOTS/3/pid"; printf '9999\n' > "$SLOTS/3/winpid"; printf '%s/sub\n' "$(wtp "$S")" > "$SLOTS/3/checkout"; printf '2026-11-11T03:00:00Z\n' > "$SLOTS/3/started"
jq -n '[{pid:4242,ppid:1,name:"bash.exe",command:"bash tests/run-all.sh",started:"2026-11-11T01:02:03"}]' > "$TMP/proc-slots.json"
export SLOTP="$TMP/proc-slots.json"
RPG_FACTORY_PROCESS_TABLE="$SLOTP" opath "status names the slot held in the plan's checkout, alive" 0 "^Slots: slot 1 held by PID 4242 in .*rpg-mmo-server since 2026-11-11T01:02:03Z \(alive\)" status "$G"
RPG_FACTORY_PROCESS_TABLE="$SLOTP" opath "status names a slot whose holder is gone" 0 "^Slots: slot 3 held by PID 9999 in .*rpg-mmo-server/sub since 2026-11-11T03:00:00Z \(not running\)" status "$G"
RPG_FACTORY_PROCESS_TABLE="$SLOTP" oref "a slot held in another checkout is not named" "slot 2 held" status "$G"
RPG_FACTORY_PROCESS_TABLE="$SLOTP" oref "slot lines never carry a kill command" "$NOKILL" status "$G"
RPG_FACTORY_PROCESS_TABLE=none opath "process listing failing: liveness unknown, never an error" 0 "^Slots: slot 1 held by PID 4242 .*\(liveness unknown\)" status "$G"
RPG_FACTORY_PROCESS_TABLE="$SLOTP" opath "cleanup names the slot too" 1 "^  SLOT slot 1 held by PID 4242 in .*rpg-mmo-server since 2026-11-11T01:02:03Z \(alive\)" cleanup "$G"
RPG_FACTORY_PROCESS_TABLE="$SLOTP" oref "cleanup slot lines never carry a kill command" "$NOKILL" cleanup "$G"
# winpid equal to pid (slots 1 and 3 above): no "(Windows PID" text in status or cleanup
RPG_FACTORY_PROCESS_TABLE="$SLOTP" oref "equal winpid: status prints no Windows PID text" "Windows PID" status "$G"
RPG_FACTORY_PROCESS_TABLE="$SLOTP" oref "equal winpid: cleanup prints no Windows PID text" "Windows PID" cleanup "$G"
PATH="$fpath" RPG_FACTORY_PROCESS_TABLE="$SLOTP" python3 -B "$P" status --json "$G" > "$TMP/so-slots.json" 2> "$TMP/se-slots.txt"; rc=$?
if [ $rc = 0 ] && jq -e '.valid and (has("_slots") | not)' "$TMP/so-slots.json" >/dev/null && grep -q "^Slots: slot 1 held by PID 4242" "$TMP/se-slots.txt"
then pass=$((pass + 1)); echo "PASS  status --json: slots on stderr, stdout stays the status schema"
else fail=$((fail + 1)); echo "FAIL  status --json slots (rc $rc)"; head -5 "$TMP/se-slots.txt"; fi
PATH="$fpath" RPG_FACTORY_PROCESS_TABLE="$SLOTP" python3 -B "$P" cleanup --json "$G" > "$TMP/cleanup-slots.json" 2>&1
if jq -e '(.slots | map(.slot) | sort) == ["1", "3"] and (.slots[] | select(.slot == "1") | .alive == true and .pid == "4242") and (.slots[] | select(.slot == "3") | .alive == false)' "$TMP/cleanup-slots.json" >/dev/null
then pass=$((pass + 1)); echo "PASS  cleanup --json carries the slot holders"
else fail=$((fail + 1)); echo "FAIL  cleanup --json slots"; head -c 1200 "$TMP/cleanup-slots.json"; fi
# a slot whose winpid differs from its pid (MSYS shell PID vs Windows PID) names both; liveness follows the winpid
mkdir -p "$SLOTS/4"
printf '6161\n' > "$SLOTS/4/pid"; printf '6262\n' > "$SLOTS/4/winpid"; wtp "$S" > "$SLOTS/4/checkout"; printf '2026-11-11T04:00:00Z\n' > "$SLOTS/4/started"
jq -n '[{pid:6262,ppid:1,name:"bash.exe",command:"bash tests/run-all.sh",started:"2026-11-11T04:00:00"}]' > "$TMP/proc-slots-win.json"
SLOTW="$TMP/proc-slots-win.json"
RPG_FACTORY_PROCESS_TABLE="$SLOTW" opath "status names both PIDs when winpid differs, alive by the Windows PID" 0 "^Slots: slot 4 held by PID 6161 \(Windows PID 6262\) in .*rpg-mmo-server since 2026-11-11T04:00:00Z \(alive\)" status "$G"
RPG_FACTORY_PROCESS_TABLE="$SLOTW" opath "cleanup names both PIDs when winpid differs" 1 "^  SLOT slot 4 held by PID 6161 \(Windows PID 6262\) in .*rpg-mmo-server since 2026-11-11T04:00:00Z \(alive\)" cleanup "$G"
RPG_FACTORY_PROCESS_TABLE="$SLOTW" oref "differing winpid: an equal-winpid slot (1) still prints no Windows PID text" "slot 1 held by PID 4242 \(Windows PID" status "$G"
# children of the plan's worktrees count as the plan's checkouts, as `children_of` finds them: a branch with an Orca prefix
# (codex/<task branch>--qa in a sibling directory) and a child known only through Orca's lineage (any name, any
# directory); a slot in a checkout that is neither stays unnamed
git -C "$S" worktree add -q "$TMP/slot-pfx-child" -b codex/feat/core/demo-gw--qa "$SG" 2>/dev/null
git -C "$S" worktree add -q "$TMP/slot-lineage-child" -b slot-lineage-br "$SG" 2>/dev/null
git -C "$S" worktree add -q "$TMP/slot-unrelated" -b slot-unrelated-br "$SG" 2>/dev/null
mkdir -p "$SLOTS/5" "$SLOTS/6" "$SLOTS/7"
for n in 5:slot-pfx-child:7001 6:slot-lineage-child:7002 7:slot-unrelated:7003; do
  IFS=: read -r sn sd sp <<<"$n"
  printf '%s\n' "$sp" > "$SLOTS/$sn/pid"; printf '%s\n' "$sp" > "$SLOTS/$sn/winpid"; wtp "$TMP/$sd" > "$SLOTS/$sn/checkout"; printf '2026-11-11T05:0%s:00Z\n' "$sn" > "$SLOTS/$sn/started"
done
export FAKE_ORCA_WT="$TMP/orca-wt-slots.json"
jq -n --arg p "$(wtp "$S")" --arg c "$(wtp "$TMP/slot-lineage-child")" \
  '{ok:true,result:{worktrees:[{id:"r::int",path:$p,parentWorktreeId:null},{id:"r::lc",path:$c,parentWorktreeId:"r::int"}]}}' > "$FAKE_ORCA_WT"
RPG_FACTORY_PROCESS_TABLE="$SLOTP" opath "status names a slot held in a prefixed child worktree (codex/<task branch>--qa)" 0 "^Slots: slot 5 held by PID 7001 in .*slot-pfx-child since 2026-11-11T05:05:00Z" status "$G"
RPG_FACTORY_PROCESS_TABLE="$SLOTP" opath "status names a slot held in a lineage-only child worktree" 0 "^Slots: slot 6 held by PID 7002 in .*slot-lineage-child since 2026-11-11T05:06:00Z" status "$G"
RPG_FACTORY_PROCESS_TABLE="$SLOTP" oref "a slot in an unrelated worktree of the repo is not named" "slot 7 held" status "$G"
RPG_FACTORY_PROCESS_TABLE="$SLOTP" opath "cleanup names the prefixed child's slot" 1 "^  SLOT slot 5 held by PID 7001 in .*slot-pfx-child" cleanup "$G"
RPG_FACTORY_PROCESS_TABLE="$SLOTP" opath "cleanup names the lineage-only child's slot" 1 "^  SLOT slot 6 held by PID 7002 in .*slot-lineage-child" cleanup "$G"
RPG_FACTORY_PROCESS_TABLE="$SLOTP" oref "cleanup does not name the unrelated worktree's slot" "slot 7 held" cleanup "$G"
RPG_FACTORY_PROCESS_TABLE="$SLOTP" oref "child slot lines never carry a kill command" "$NOKILL" status "$G"
# Orca unavailable: the naming rule alone still names the prefixed child, never the lineage-only one
RPG_FACTORY_PROCESS_TABLE="$SLOTP" FAKE_ORCA_MODE=error opath "orca failing: the prefixed child's slot is still named" 0 "^Slots: slot 5 held by PID 7001" status "$G"
RPG_FACTORY_PROCESS_TABLE="$SLOTP" FAKE_ORCA_MODE=error oref "orca failing: a lineage-only child's slot is not named, no traceback" "slot 6 held|Traceback" status "$G"
unset FAKE_ORCA_WT
git -C "$S" worktree remove --force "$TMP/slot-pfx-child"; git -C "$S" worktree remove --force "$TMP/slot-lineage-child"
git -C "$S" worktree remove --force "$TMP/slot-unrelated"
git -C "$S" branch -q -D codex/feat/core/demo-gw--qa slot-lineage-br slot-unrelated-br
rm -rf "$SLOTS"

case_end settled-workers
fi

if has_case orca-first; then
case_start
echo "-- Orca first: --runner agent inside a reachable Orca session needs --orca-unavailable"
# the fake orca's `status --json` answers reachable unless FAKE_ORCA_REACHABLE=false
inorca() { PATH="$fpath" ORCA_WORKTREE_ID=x "$@"; }
inorca expect "inside Orca: dispatch --runner agent exits 2 naming --runner orca" 2 "ORCA_WORKTREE_ID is set.*use --runner orca" dispatch "$OK" --task integration:client --phase qa --sha abc1234 --runner agent
inorca expect "inside Orca: the refusal names --orca-unavailable REASON" 2 "needs --orca-unavailable REASON" dispatch "$OK" --task c1 --phase lead --runner agent
inorca refute "inside Orca: the refusal prints no agent call" '"subagent_type"' dispatch "$OK" --task c1 --phase lead --runner agent
inorca expect "inside Orca: planner --runner agent exits 2 too" 2 "use --runner orca" planner --request "add a thing" --runner agent
PATH="$fpath" ORCA_AGENT_HOOK_ENDPOINT=e expect "inside Orca (ORCA_AGENT_HOOK_ENDPOINT only): refused" 2 "ORCA_AGENT_HOOK_ENDPOINT is set" planner --request "add a thing" --runner agent
inorca expect "inside Orca with --orca-unavailable: the planner prompt opens with the reason" 0 '"prompt": "Orca unavailable: quota hit\. This session runs through' planner --request "add a thing" --runner agent --orca-unavailable "quota hit"
inorca expect "inside Orca with --orca-unavailable: the agent call's prompt names the reason (whitespace collapsed)" 0 '\\nOrca unavailable: quota hit\. This session runs through the Claude Code Agent-tool fallback' dispatch "$OK" --task integration:client --phase qa --sha abc1234 --runner agent --orca-unavailable 'quota   hit'
inorca expect "inside Orca with --orca-unavailable: stderr note" 0 "Orca unavailable \(quota hit\)" planner --request "add a thing" --runner agent --orca-unavailable "quota hit"
inorca expect "inside Orca with --orca-unavailable: the lead prompt passes the flag on" 0 "pass --orca-unavailable with it to every factory-pipeline.py planner or dispatch" dispatch "$OK" --task c1 --phase lead --runner agent --orca-unavailable "quota hit"
expect "outside Orca with --orca-unavailable: the reason is named too" 0 "Orca unavailable: quota hit\." planner --request "add a thing" --runner agent --orca-unavailable "quota hit"
inorca expect "inside Orca: the default runner is orca" 0 "^orca orchestration worker-start " planner --request "add a thing"
inorca refute "inside Orca: the default runner is not print" "^# agent:" planner --request "add a thing"
expect "outside Orca: the default runner is print" 0 "^# agent: " planner --request "add a thing"
PATH="$fpath" expect "orca reachable but no ORCA_* variable: the default runner is print" 0 "^# agent: " planner --request "add a thing"
PATH="$fpath" expect "orca reachable but no ORCA_* variable: --runner agent as before" 0 '"subagent_type": "general-purpose"' planner --request "add a thing" --runner agent
FAKE_ORCA_REACHABLE=false inorca expect "Orca env set, runtime unreachable: --runner agent as before" 0 '"subagent_type": "general-purpose"' planner --request "add a thing" --runner agent
FAKE_ORCA_REACHABLE=false inorca expect "Orca env set, runtime unreachable: the default runner is print" 0 "^# agent: " planner --request "add a thing"
noorca=$(IFS=:; for d in $PATH; do [ -e "$d/orca" ] || [ -e "$d/orca.cmd" ] || [ -e "$d/orca.exe" ] || printf '%s:' "$d"; done)
PATH="${noorca%:}" ORCA_WORKTREE_ID=x expect "Orca env set, orca not on PATH: --runner agent as before" 0 '"subagent_type": "general-purpose"' dispatch "$OK" --task integration:client --phase qa --sha abc1234 --runner agent
inorca expect "--orca-unavailable with --runner orca is a usage error" 2 "--orca-unavailable REASON goes with --runner agent only" planner --request "add a thing" --runner orca --orca-unavailable x
expect "--orca-unavailable without --runner is a usage error" 2 "goes with --runner agent only" planner --request "add a thing" --orca-unavailable x
expect "--orca-unavailable with a blank reason is a usage error" 2 "--orca-unavailable needs a REASON" planner --request "add a thing" --runner agent --orca-unavailable "  "
git -C "$S" worktree remove "$TMP/feat-core-demo--qa"; git -C "$S" worktree remove "$TMP/int-helper"
git -C "$S" branch -q -D feat/core/demo--qa int-helper
if python3 -B "$P" status --json "$G" 2>/dev/null | jq -e '.integration_children == []' >/dev/null
then pass=$((pass + 1)); echo "PASS  integration children removed: status lists none"
else fail=$((fail + 1)); echo "FAIL  integration_children after removal"; fi

case_end orca-first
fi

if has_case review-findings; then
case_start
echo "-- review findings"
expect "--agent cannot swap the planned implementer" 2 "is planned for claude; set .implementer: codex." dispatch "$OK" --task gw --phase implement --agent codex
X=$(plan alias "{$HEAD,\"repos\":{\"cli2\":{\"path\":\"ws/IndieRPGMMOAdventure\"}},\"tasks\":[
 {\"id\":\"a\",\"repo\":\"client\",\"objective\":\"o\",\"paths\":[\"Assets/A/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"b\",\"repo\":\"cli2\",\"objective\":\"o\",\"paths\":[\"Assets/A/x.cs\"],\"acceptance\":[\"a\"]}]}")
expect "two keys for one Unity checkout: overlap still found" 1 "ERROR tasks a and b own overlapping paths" validate "$X"
X=$(plan alias2 "{$HEAD,\"repos\":{\"cli2\":{\"path\":\"ws/IndieRPGMMOAdventure\"}},\"tasks\":[
 {\"id\":\"a\",\"repo\":\"client\",\"objective\":\"o\",\"paths\":[\"Assets/A/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"b\",\"repo\":\"cli2\",\"objective\":\"o\",\"paths\":[\"Assets/B/\"],\"acceptance\":[\"a\"]}]}")
expect "two keys for one Unity checkout: still one task per wave" 0 "^Wave 2: b$" validate "$X"
# status and dispatch serialize by checkout too: two plan aliases of one Unity checkout are never both ready
X=$(plan alias3 "{\"schema\":\"rpg-factory.pipeline-plan/1\",\"id\":\"alias3\",\"title\":\"Alias\",\"topic\":\"feat/core/alias3\",
 \"repos\":{\"u1\":{\"path\":\"ws/IndieRPGMMOAdventure\",\"base\":\"develop\"},\"u2\":{\"path\":\"ws/IndieRPGMMOAdventure\",\"base\":\"develop\"}},\"tasks\":[
 {\"id\":\"a\",\"repo\":\"u1\",\"objective\":\"o\",\"paths\":[\"Assets/A/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"b\",\"repo\":\"u2\",\"objective\":\"o\",\"paths\":[\"Assets/B/\"],\"acceptance\":[\"a\"]}]}")
if python3 -B "$P" status --json "$X" 2>/dev/null | python3 -c 'import json,sys; o=json.load(sys.stdin); r={t["id"]:t for t in o["tasks"]}
assert o["ready"]==["a"], o["ready"]
assert r["b"]["next"] is None and any(n=="waits for a" for n in r["b"]["notes"]), r["b"]'
then pass=$((pass + 1)); echo "PASS  status: two aliases of one Unity checkout are never both ready (b waits for a)"
else fail=$((fail + 1)); echo "FAIL  status alias serialization"; python3 -B "$P" status "$X" 2>&1 | head -20; fi
expect "dispatch warns the second alias task that the first has no QA PASS" 0 "takes one task at a time: task a has no QA PASS yet" dispatch "$X" --task b --phase lead --runner print
# after task a's review and per-task QA PASS (task b not started), the checkout is b's: no integration QA of either
# alias runs beside b's task lead, and the aliases' integration QAs run one at a time once b passed its QA too
gi "$C" checkout -qb feat/core/alias3 develop; mkdir -p "$C/Assets/A" "$C/Assets/B"
echo a > "$C/Assets/A/al.cs"; gi "$C" add Assets/A; gi "$C" commit -qm "feat: alias a"; UA=$(git -C "$C" rev-parse HEAD)
python3 -B "$P" verdict "$X" --task a --phase review --sha "$UA" --by codex --state PASS >/dev/null
python3 -B "$P" verdict "$X" --task a --phase qa --sha "$UA" --by codex --state PASS >/dev/null
if python3 -B "$P" status --json "$X" 2>/dev/null | python3 -c 'import json,sys; o=json.load(sys.stdin); r={t["id"]:t for t in o["tasks"]}
assert o["ready"]==["b"] and o["ready_wave"]==2, (o["ready"], o["ready_wave"])
assert r["a"]["phase"]=="qa" and r["a"]["next"] is None, r["a"]
assert "--task b --phase lead" in r["b"]["next"] and "integration:" not in json.dumps(o), r["b"]'
then pass=$((pass + 1)); echo "PASS  status: after the first alias task's QA only the next task lead is offered (no integration QA)"
else fail=$((fail + 1)); echo "FAIL  status alias integration QA beside a task lead"; python3 -B "$P" status "$X" 2>&1 | head -20; fi
expect "dispatch warns an alias's integration QA while a task of the checkout has no QA PASS" 0 "u1 takes one task at a time: task b has no QA PASS yet" dispatch "$X" --task integration:u1 --phase qa --sha "$UA" --runner print
echo b > "$C/Assets/B/al.cs"; gi "$C" add Assets/B; gi "$C" commit -qm "feat: alias b"; UB=$(git -C "$C" rev-parse HEAD)
python3 -B "$P" verdict "$X" --task b --phase review --sha "$UB" --by codex --state PASS >/dev/null
python3 -B "$P" verdict "$X" --task b --phase qa --sha "$UB" --by codex --state PASS >/dev/null
# dispatch reads the per-task QA like status: a PASS recorded for an older version of task a is STALE, not PASS
python3 -c 'import json,sys; p=json.load(open(sys.argv[1],encoding="utf-8")); p["tasks"][0]["objective"]="changed"; json.dump(p,open(sys.argv[2],"w",encoding="utf-8"))' "$X" "$TMP/alias3-stale.json"
expect "dispatch: a STALE per-task QA PASS leaves the alias's integration QA open" 0 "u1 takes one task at a time: task a has no QA PASS yet" dispatch "$TMP/alias3-stale.json" --task integration:u1 --phase qa --sha "$UB" --runner print
expect "dispatch: a STALE QA PASS of the serial predecessor still warns the next task lead" 0 "takes one task at a time: task a has no QA PASS yet" dispatch "$TMP/alias3-stale.json" --task b --phase lead --runner print
refute "dispatch: a current QA PASS of every alias task: no warning" "takes one task at a time" dispatch "$X" --task integration:u1 --phase qa --sha "$UB" --runner print
if python3 -B "$P" status --json "$X" 2>/dev/null | python3 -c 'import json,sys; o=json.load(sys.stdin); r={t["id"]:t for t in o["tasks"]}
assert "--task integration:u1 --phase qa" in r["a"]["next"], r["a"]
assert r["b"]["next"] is None and any("integration QA of u1 runs first" in n for n in r["b"]["notes"]), r["b"]'
then pass=$((pass + 1)); echo "PASS  status: integration QAs of two aliases of one Unity checkout run one at a time"
else fail=$((fail + 1)); echo "FAIL  status alias integration QA order"; python3 -B "$P" status "$X" 2>&1 | head -20; fi
python3 -B "$P" verdict "$X" --task integration:u1 --phase qa --sha "$UB" --by codex --state PASS >/dev/null
if python3 -B "$P" status --json "$X" 2>/dev/null | python3 -c 'import json,sys; o=json.load(sys.stdin); r={t["id"]:t for t in o["tasks"]}
assert r["a"]["phase"]=="qa" and r["a"]["next"] is None, r["a"]
assert "--task integration:u2 --phase qa" in r["b"]["next"], r["b"]'
then pass=$((pass + 1)); echo "PASS  status: the second alias's integration QA follows the first one's PASS"
else fail=$((fail + 1)); echo "FAIL  status alias second integration QA"; python3 -B "$P" status "$X" 2>&1 | head -20; fi
python3 -B "$P" verdict "$X" --task integration:u2 --phase qa --sha "$UB" --by codex --state PASS >/dev/null
refute "gate: the aliases' tasks share the integration branch, so neither alias's changes are stray" "changes outside every task's owned paths" gate "$X" --no-run-checks
expect "gate: two aliases of one Unity checkout with every verdict are READY_FOR_PR" 0 "READY_FOR_PR" gate "$X" --no-run-checks
# a dependent no-worktree task owning its predecessor's path: the predecessor's commits on the shared integration
# branch are not its own, so it is no review candidate before the predecessor's verdict and its own commit
X=$(plan uov "{\"schema\":\"rpg-factory.pipeline-plan/1\",\"id\":\"uov\",\"title\":\"Uov\",\"topic\":\"feat/core/uov\",
 \"repos\":{\"u1\":{\"path\":\"ws/IndieRPGMMOAdventure\",\"base\":\"develop\"}},\"tasks\":[
 {\"id\":\"a\",\"repo\":\"u1\",\"objective\":\"o\",\"paths\":[\"Assets/U/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"b\",\"repo\":\"u1\",\"objective\":\"o\",\"paths\":[\"Assets/U/\"],\"acceptance\":[\"a\"],\"deps\":[\"a\"]}]}")
gi "$C" checkout -qb feat/core/uov develop; mkdir -p "$C/Assets/U"
echo a > "$C/Assets/U/u.cs"; gi "$C" add Assets/U; gi "$C" commit -qm "feat: uov a"; VA=$(git -C "$C" rev-parse HEAD)
echo wip > "$C/Assets/U/wip.cs"  # the predecessor's uncommitted work in the shared path is not b's
if python3 -B "$P" status --json "$X" 2>/dev/null | python3 -c 'import json,sys; o=json.load(sys.stdin); r={t["id"]:t for t in o["tasks"]}
assert r["a"]["phase"]=="candidate" and "--task a --phase verify --sha "+sys.argv[1] in r["a"]["next"], r["a"]
assert r["b"]["phase"]=="pending" and r["b"]["next"] is None and any(n=="waits for a" for n in r["b"]["notes"]), r["b"]
assert "--task b --phase review" not in json.dumps(o), o' "$VA"
then pass=$((pass + 1)); echo "PASS  status: a dependent no-worktree task with the same path is pending before its predecessor's QA (no review at a's commit)"
else fail=$((fail + 1)); echo "FAIL  status no-worktree dependent before QA"; python3 -B "$P" status "$X" 2>&1 | head -20; fi
rm -f "$C/Assets/U/wip.cs"
for failed_phase in review qa; do
  python3 -B "$P" verdict "$X" --task a --phase review --sha "$VA" --by codex --state PASS >/dev/null
  python3 -B "$P" verdict "$X" --task a --phase "$failed_phase" --sha "$VA" --by codex --state FAIL >/dev/null
  echo "fix after $failed_phase FAIL" >> "$C/Assets/U/u.cs"
  gi "$C" add Assets/U; gi "$C" commit -qm "fix: uov a after $failed_phase FAIL"; VA=$(git -C "$C" rev-parse HEAD)
  if python3 -B "$P" status --json "$X" 2>/dev/null | python3 -c 'import json,sys; o=json.load(sys.stdin); r={t["id"]:t for t in o["tasks"]}
assert r["a"]["phase"]=="candidate" and "--task a --phase verify --sha "+sys.argv[1] in r["a"]["next"], r["a"]
assert r["b"]["phase"]=="pending" and r["b"]["next"] is None and "waits for a" in r["b"]["notes"], r["b"]
assert "--task b --phase review" not in json.dumps(o), o' "$VA"
  then pass=$((pass + 1)); echo "PASS  status: predecessor fixes after $failed_phase FAIL keep the dependent pending without a review command"
  else fail=$((fail + 1)); echo "FAIL  status dependent after predecessor $failed_phase FAIL"; python3 -B "$P" status "$X" 2>&1 | head -20; fi
done
python3 -B "$P" verdict "$X" --task a --phase review --sha "$VA" --by codex --state PASS >/dev/null
python3 -B "$P" verdict "$X" --task a --phase qa --sha "$VA" --by codex --state PASS >/dev/null
echo b >> "$C/Assets/U/u.cs"; gi "$C" add Assets/U; gi "$C" commit -qm "feat: uov b"; VB=$(git -C "$C" rev-parse HEAD)
if python3 -B "$P" status --json "$X" 2>/dev/null | python3 -c 'import json,sys; o=json.load(sys.stdin); r={t["id"]:t for t in o["tasks"]}
assert r["b"]["phase"]=="candidate" and r["b"]["sha"]==sys.argv[1] and "--task b --phase verify --sha "+sys.argv[1] in r["b"]["next"], r["b"]' "$VB"
then pass=$((pass + 1)); echo "PASS  status: after the predecessor's QA PASS, the dependent task's own commit makes it a candidate at that SHA"
else fail=$((fail + 1)); echo "FAIL  status no-worktree dependent after QA"; python3 -B "$P" status "$X" 2>&1 | head -20; fi
gi "$C" checkout -q feat/core/demo
X=$(plan norm "{$HEAD,\"tasks\":[
 {\"id\":\"a\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"./backend/gateway\"],\"acceptance\":[\"a\"]},
 {\"id\":\"b\",\"repo\":\"server\",\"objective\":\"o\",\"paths\":[\"backend\\\\gateway\\\\x.go\"],\"acceptance\":[\"a\"]}]}")
expect "./ and backslash spellings of one path overlap" 1 "ERROR tasks a and b own overlapping paths" validate "$X"
X=$(ctx br '{"repos":[{"repo":"server","touched":["server.gateway"],"files":[{"path":"a","source":"branch"},{"path":"b","source":"branch"},{"path":"c","source":"branch"},{"path":"d","source":"branch"},{"path":"e","source":"branch"},{"path":"f","source":"branch"},{"path":"g","source":"branch"}],"contracts":[],"generated_hits":[]}]}')
expect "files committed on the branch count for the tier" 0 "7 files > 6" tier --context-json "$X"
TP=$(plan tp "{$HEAD,\"repos\":{\"other\":{\"path\":\"ws/rpg-mmo-server\",\"base\":\"develop\"}},\"tasks\":[{\"id\":\"o\",\"repo\":\"other\",\"objective\":\"o\",\"paths\":[\"x/\"],\"acceptance\":[\"a\"]}]}")
out=$(cd "$TMP" && python3 -B "$P" dispatch "$TP" --task o --phase lead --runner agent 2>&1)
if grep -q "Create your own worktree first" <<<"$out" && ! grep -q '"isolation"' <<<"$out"; then pass=$((pass + 1)); echo "PASS  agent fallback for another repo names repo and base, no isolation"
else fail=$((fail + 1)); echo "FAIL  agent fallback placement"; head -c 400 <<<"$out"; fi

case_end review-findings
fi

if has_case tier-plugin; then
case_start
echo "-- tier for a repo the registry does not know (the plugin repo)"
PL=$(plan plug "{$HEAD,\"repos\":{\"plugin\":{\"path\":\"tool\",\"base\":\"develop\"}},\"tasks\":[{\"id\":\"t\",\"repo\":\"plugin\",\"objective\":\"o\",\"paths\":[\"scripts/\"],\"acceptance\":[\"a\"]}]}")
expect "one file of a plan repo: S from the paths alone" 0 '"tier": "S"' tier --json --plan "$PL" --repo plugin --paths scripts/factory-pipeline.py
expect "plan repo tier names its basis" 0 "basis: paths \(repo not in the registry\)" tier --plan "$PL" --repo plugin --paths scripts/a.py
out=$(python3 -B "$P" tier --json --plan "$PL" --repo plugin --paths skills/factory-core/SKILL.md skills/ui-ux/SKILL.md scripts/lib/x.py scripts/y.py tests/z.sh README.md 2>&1)
if python3 -c 'import json,sys; o=json.loads(sys.argv[1]); f=o["facts"]
assert o["tier"]=="M", o["tier"]
assert f["modules"]==["other","scripts","scripts/lib","skills/factory-core","skills/ui-ux","tests"], f["modules"]
assert f["files"]==6 and f["repos"]==["plugin"] and f["contracts"]==[] and f["generated"]==[]' "$out"; then
  pass=$((pass + 1)); echo "PASS  plan repo tier: skills/<name>, scripts/lib, listed dirs and other are modules; M"
else fail=$((fail + 1)); echo "FAIL  plan repo tier facts"; head -c 600 <<<"$out"; fi
out=$(python3 -B "$P" tier --json --plan "$PL" --repo plugin --paths .claude/CLAUDE.md evals/e.json changelog.d/x.md README.md skills/README.md hooks/hooks.json registry/core.json docs/d.md commands/c.md 2>&1)
if python3 -c 'import json,sys; f=json.loads(sys.argv[1])["facts"]
assert f["modules"]==["commands","docs","hooks","other","registry"], f["modules"]' "$out"; then
  pass=$((pass + 1)); echo "PASS  plan repo tier: .claude, evals, changelog.d and root files are one other module"
else fail=$((fail + 1)); echo "FAIL  plan repo tier other module"; head -c 600 <<<"$out"; fi
expect "seven files of a plan repo: above S" 0 "7 files > 6" tier --plan "$PL" --repo plugin --paths scripts/a scripts/b scripts/c scripts/d scripts/e scripts/f scripts/g
expect "tier --plan needs --paths" 2 "needs --repo <plan repo key> and --paths" tier --plan "$PL" --repo plugin
expect "tier --plan with an unknown repo key fails cleanly" 2 "neither a registry repo nor in plan.repos" tier --plan "$PL" --repo nope --paths x
expect "--repo without --plan is a usage error" 2 "go with --plan" tier --repo plugin --paths x
expect "tier <plan> names the right forms, not a factory-context error" 2 "tier takes no positional argument .*tier --plan <plan.json> --repo <key> --paths <files>.*tier -- --repo <key> --paths <files>" tier "$PL"
refute "tier <plan> never reaches factory-context.sh" "factory-context: unknown argument" tier "$PL"
expect "tier <plan> with trailing flags is the same usage error" 2 "tier takes no positional argument" tier --json "$PL" --repo plugin --paths scripts/a.py

case_end tier-plugin
fi

if has_case status; then
case_start
echo "-- status (resume a run from git and the verdicts)"
# srv: a worktree repo (a, then b); cli: a Unity project (c1, then c2 in the main checkout); topic feat/core/st
ST=$(plan st "{\"schema\":\"rpg-factory.pipeline-plan/1\",\"id\":\"st\",\"title\":\"Status\",\"topic\":\"feat/core/st\",
 \"repos\":{\"srv\":{\"path\":\"ws/rpg-mmo-server\",\"base\":\"develop\"},\"cli\":{\"path\":\"ws/IndieRPGMMOAdventure\",\"base\":\"develop\"}},\"tasks\":[
 {\"id\":\"a\",\"repo\":\"srv\",\"objective\":\"o\",\"paths\":[\"sa/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"b\",\"repo\":\"srv\",\"objective\":\"o\",\"paths\":[\"sb/\"],\"acceptance\":[\"a\"],\"deps\":[\"a\"]},
 {\"id\":\"c1\",\"repo\":\"cli\",\"objective\":\"o\",\"paths\":[\"Assets/C/\"],\"acceptance\":[\"a\"]},
 {\"id\":\"c2\",\"repo\":\"cli\",\"objective\":\"o\",\"paths\":[\"Assets/D/\"],\"acceptance\":[\"a\"],\"implementer\":\"codex\"}]}")
sv() { python3 -B "$P" verdict "$ST" "$@" >/dev/null || echo "verdict failed: $*"; }
# review_diff_lists <name> <files>: run the `git diff X...Y` printed in b's review spec in the fixture; it lists exactly <files>
review_diff_lists() {
  local name="$1" want="$2" out spec range got
  out=$(python3 -B "$P" dispatch "$ST" --task b --phase review --sha "$SB" --runner orca 2>&1)
  spec=$(python3 -c 'import pathlib,shlex,sys
args=shlex.split(sys.argv[1]); flag="--prompt" if "--prompt" in args else "--spec"; prompt=args[args.index(flag)+1]
print(pathlib.Path(prompt[len("Read your task spec at "):-len(" and follow it.")]).read_text(encoding="utf-8"))' "$out" 2>&1)
  range=$(grep -oE 'git diff [^ `]+\.\.\.[0-9a-f]+' <<<"$spec" | head -1 | cut -d' ' -f3)
  got=$([ -n "$range" ] && git -C "$S" diff --name-only "$range" | tr '\n' ' ' | sed 's/ $//')
  if [ -n "$range" ] && [ "$got" = "$want" ]; then pass=$((pass + 1)); echo "PASS  $name"
  else fail=$((fail + 1)); echo "FAIL  $name (range '$range' lists '$got', want '$want')"; fi
}
# st_phase <name> <task> <phase> [<next-regex>]: the task's phase in status --json (and its next command)
st_phase() {
  local name="$1" id="$2" want="$3" nx="${4:-}" out
  pp status --json "$ST"; out="$OUT"
  if python3 -c 'import json,re,sys; o=json.loads(sys.argv[1]); r={t["id"]:t for t in o["tasks"]}[sys.argv[2]]
assert r["phase"]==sys.argv[3], r
assert not sys.argv[4] or re.search(sys.argv[4], r["next"] or ""), r' "$out" "$id" "$want" "$nx"; then
    pass=$((pass + 1)); echo "PASS  $name"
  else fail=$((fail + 1)); echo "FAIL  $name"; head -c 1500 <<<"$out"; echo; fi
}
# st_note <name> <task> <regex>: one of the task's notes in status --json matches
st_note() {
  local name="$1" id="$2" pat="$3" out; pp status --json "$ST"; out="$OUT"
  if python3 -c 'import json,re,sys; o=json.loads(sys.argv[1]); r={t["id"]:t for t in o["tasks"]}[sys.argv[2]]
assert any(re.search(sys.argv[3], n) for n in r["notes"]), r["notes"]' "$out" "$id" "$pat"; then
    pass=$((pass + 1)); echo "PASS  $name"
  else fail=$((fail + 1)); echo "FAIL  $name"; head -c 1500 <<<"$out"; echo; fi
}
st_phase "nothing started in a worktree repo: pending, next starts the task lead" a pending "dispatch .* --task a --phase lead --runner orca"
st_phase "nothing started in the Unity project: next starts its task lead in the main checkout" c1 pending "dispatch .* --task c1 --phase lead --runner orca"
st_phase "a dependent task waits (no next command)" b pending '^$'
refute "no integration commits in owned paths: no \"integrated earlier\" note" "no review record: integrated earlier" status "$ST"
expect "the first Unity task is ready, the second waits for its QA" 0 "note: waits for c1" status "$ST"
expect "status prints the ready wave and its tasks" 0 "^Ready wave: 1  \(dispatch: a, c1\)" status "$ST"
git -C "$S" worktree add -q "$TMP/st-a" -b feat/core/st-a develop 2>/dev/null
st_phase "task branch and worktree without commits: implementing" a implementing '^$'
expect "implementing names the worker's worktree" 0 "implementation worker on feat/core/st-a in .*st-a" status "$ST"
mkdir -p "$TMP/st-a/sa"; echo a > "$TMP/st-a/sa/a.go"; gi "$TMP/st-a" add sa; gi "$TMP/st-a" commit -qm "feat: a"; SA=$(git -C "$S" rev-parse feat/core/st-a)
st_phase "commits ahead of the base: candidate, next is the review at that SHA" a candidate "--task a --phase verify --sha $SA --runner orca"
sv --task a --phase review --sha "$SA" --by codex --state FAIL
st_phase "review FAIL: reviewed, next resumes the task lead (only it commits the fix)" a reviewed "--task a --phase lead --runner orca"
expect "review FAIL is named with its SHA" 0 "review FAIL@${SA:0:10}" status "$ST"
echo a2 >> "$TMP/st-a/sa/a.go"; gi "$TMP/st-a" commit -qam "fix: a"; SA=$(git -C "$S" rev-parse feat/core/st-a)
st_phase "a fix after the FAIL is a new candidate" a candidate "--phase verify --sha $SA"
expect "and the old review is named STALE" 0 "review at .* is STALE: owned paths changed since" status "$ST"
# a reported task whose review is not current for the task HEAD is never ready (the review/QA currency test is the
# phase's own: task_status), even with a lead report at that HEAD
expect "stale review: the lead reports at the task HEAD" 0 "^recorded lead report for a at ${SA:0:10}: " report "$ST" --task a --sha "$SA" --body "a done"
st_note "stale review with a lead report at HEAD: READY_FOR_PR: no names the stale review" a '^READY_FOR_PR: no \(review at [0-9a-f]{10} is STALE: owned paths changed since\)$'
rm -f "$RPG_FACTORY_STATE_DIR/pipeline/st/a__lead-report.json"
sv --task a --phase review --sha "$SA" --by codex --state PASS
st_phase "review PASS without an integration branch: create it from the base" a reviewed "branch feat/core/st develop"
expect "no integration branch yet: a later-wave task lead starts from the base" 0 "worktree add --no-track -b feat/core/st-b .* develop" dispatch "$ST" --task b --phase lead --runner orca
git -C "$S" worktree add -q "$TMP/st-int" -b feat/core/st develop 2>/dev/null
st_phase "review PASS: next merges the task branch into the integration worktree" a reviewed "merge --no-ff feat/core/st-a"
# the task lead's durable report (`report`): status shows it per task with READY_FOR_PR, no message needed
st_note "no lead report yet: READY_FOR_PR: no, the first missing thing" a '^READY_FOR_PR: no \(no lead report\)$'
refute "no lead report: no lead report line" "note: lead report:" status "$ST"
expect "report: an unknown task is a usage error" 2 "unknown task zz" report "$ST" --task zz --sha "$SA" --body x
expect "report: a body is required" 2 "one of the arguments --body --body-file is required" report "$ST" --task a --sha "$SA"
expect "report: an empty body is refused" 2 "report body is empty" report "$ST" --task a --sha "$SA" --body "  "
expect "report: a SHA that is no commit of the repo is refused" 2 "is not a commit of repo srv" report "$ST" --task a --sha 1234567abcdef --body x
expect "report: an integration task is refused" 2 "report is per plan task" report "$ST" --task integration:srv --sha "$SA" --body x
SD=$(git -C "$S" rev-parse develop)
{ printf 'First line of the lead report %0190d\n' 0; echo 'second line stays in the body'; } > "$TMP/lead-report.txt"
expect "report --body-file records the report at its SHA" 0 "^recorded lead report for a at ${SD:0:10}: " report "$ST" --task a --sha "$SD" --body-file "$TMP/lead-report.txt"
if jq -e --arg sha "$SD" '.sha == $sha and .task == "a" and (.summary | length) <= 200 and (.summary | endswith("...")) and (.body | contains("second line stays in the body")) and (.at | test("^[0-9]{4}-"))' "$RPG_FACTORY_STATE_DIR/pipeline/st/a__lead-report.json" >/dev/null
then pass=$((pass + 1)); echo "PASS  the report record keeps SHA, time, a summary capped at 200 characters and the full body"
else fail=$((fail + 1)); echo "FAIL  report record"; head -c 800 "$RPG_FACTORY_STATE_DIR/pipeline/st/a__lead-report.json"; fi
st_note "a report at an older commit is shown with the stale marker" a "^lead report: .* @${SD:0:10} First line.*\(stale: task HEAD is ${SA:0:10}\)$"
st_note "a stale report: READY_FOR_PR: no names both commits" a "^READY_FOR_PR: no \(lead report is for ${SD:0:10}, task HEAD is ${SA:0:10}\)$"
expect "report: a later report replaces the first one" 0 "^recorded lead report for a at ${SA:0:10}: " report "$ST" --task a --sha "$SA" --body $'Task a done: all green\nsecond line'
st_note "a report at the task HEAD: no stale marker, first line as summary" a "^lead report: [0-9TZ:-]+ @${SA:0:10} Task a done: all green$"
st_note "report at HEAD and review PASS, no QA yet: READY_FOR_PR: no (no QA)" a '^READY_FOR_PR: no \(no QA\)$'
gi "$TMP/st-int" merge -q --no-ff feat/core/st-a -m "merge a"
st_phase "merged after review PASS: integrated" a integrated '^$'
# Prior tasks can touch paths a later task also owns. That integration history is not evidence the later
# task started: without a local task branch/worktree or prior review record it must stay pending, with no SHA.
if python3 -B - "$P" "$ST" "$TMP/st-unstarted.json" <<'PY'
import json, pathlib, subprocess, sys
p, source, target = sys.argv[1:]
plan = json.loads(pathlib.Path(source).read_text(encoding="utf-8"))
plan["tasks"].append({"id": "unstarted", "repo": "srv", "objective": "follow-up in existing paths",
                      "paths": ["sa/"], "acceptance": ["a"], "deps": ["a"]})
pathlib.Path(target).write_text(json.dumps(plan), encoding="utf-8")
r = subprocess.run([sys.executable, "-B", p, "status", target, "--json"], capture_output=True, text=True)
assert r.returncode == 0, r.stderr
row = next(t for t in json.loads(r.stdout)["tasks"] if t["id"] == "unstarted")
assert row["phase"] == "pending" and row["sha"] is None and row["worktree"] is None, row
assert "--task unstarted --phase lead --runner orca" in row["next"], row
assert any("commits in owned paths on feat/core/st but no review record: integrated earlier?" in n for n in row["notes"]), row
PY
then pass=$((pass + 1)); echo "PASS  task without branch/worktree stays pending despite earlier integration commits in its paths"
else fail=$((fail + 1)); echo "FAIL  unstarted task inherits an integration candidate"; fi
# A dependent task that owns the same paths, cut from the integration branch after a was merged: a's commits are
# not its own. Without own commits it is implementing, never a review candidate; its first commit makes it one.
python3 -c 'import json,sys; p=json.load(open(sys.argv[1],encoding="utf-8")); p["tasks"].append({"id":"ov","repo":"srv","objective":"o","paths":["sa/"],"acceptance":["a"],"deps":["a"]}); json.dump(p,open(sys.argv[2],"w",encoding="utf-8"))' "$ST" "$TMP/st-ov.json"
git -C "$S" worktree add -q "$TMP/st-ov" -b feat/core/st-ov feat/core/st 2>/dev/null
ov_phase() {  # ov_phase <name> <phase> [<sha>]
  local out; out=$(python3 -B "$P" status --json "$TMP/st-ov.json" 2>&1)
  if python3 -c 'import json,sys; r={t["id"]:t for t in json.loads(sys.argv[1])["tasks"]}["ov"]
assert r["phase"]==sys.argv[2], r
assert not sys.argv[3] or (r["next"] or "").find("--phase verify --sha "+sys.argv[3])>=0, r' "$out" "$2" "${3:-}"
  then pass=$((pass + 1)); echo "PASS  $1"; else fail=$((fail + 1)); echo "FAIL  $1"; head -c 1200 <<<"$out"; echo; fi
}
ov_phase "dependent task with a's paths, cut after a's merge, no own commits: implementing (not a candidate)" implementing
echo ov > "$TMP/st-ov/sa/ov.go"; gi "$TMP/st-ov" add sa; gi "$TMP/st-ov" commit -qm "feat: ov"; SOV=$(git -C "$S" rev-parse feat/core/st-ov)
ov_phase "its own first commit makes it a review candidate at that SHA" candidate "$SOV"
git -C "$S" worktree remove --force "$TMP/st-ov"; git -C "$S" branch -q -D feat/core/st-ov
expect "QA waits for the other tasks of the repo" 0 "QA runs once all tasks of the repo are integrated: waits for b" status "$ST"
st_phase "the dependency is integrated: b is ready, next starts its task lead" b pending "--task b --phase lead"
expect "wave 2: the task lead's worktree starts from the integration branch (it carries wave 1)" 0 "worktree add --no-track -b feat/core/st-b .* feat/core/st" dispatch "$ST" --task b --phase lead --runner orca
expect_spec "wave 2: the task spec names the integration branch as its base" '"base": "feat/core/st"' dispatch "$ST" --task b --phase lead --runner orca
st_phase "status is unchanged by the wave-2 dispatch: b still pending" b pending "--task b --phase lead"
expect "ready tasks span waves: b (wave 3) next to c1 (wave 1)" 0 "^Ready wave: 1  \(dispatch: b, c1\)$" status "$ST"
git -C "$S" worktree remove "$TMP/st-a"; git -C "$S" branch -q -D feat/core/st-a
st_phase "a removed task branch stays integrated (verdict + integration branch)" a integrated
expect "wave 1 starts from the base even when the integration branch exists" 0 "worktree add --no-track -b feat/core/st-a .* develop" dispatch "$ST" --task a --phase lead --runner orca
git -C "$S" worktree add -q "$TMP/st-b" -b feat/core/st-b feat/core/st 2>/dev/null
st_phase "a task branch cut from the integration branch, no own commits yet: implementing" b implementing
mkdir -p "$TMP/st-b/sb"; echo b > "$TMP/st-b/sb/b.go"; gi "$TMP/st-b" add sb; gi "$TMP/st-b" commit -qm "feat: b"; SB=$(git -C "$S" rev-parse feat/core/st-b)
expect_spec "wave-2 review diffs against the integration branch, not the base" "git diff feat/core/st\.\.\.$SB" dispatch "$ST" --task b --phase review --sha "$SB" --runner orca
review_diff_lists "wave-2 review before the merge: the printed diff lists only b's files" sb/b.go
st_phase "status still compares b against the base: candidate at its SHA" b candidate "--task b --phase verify --sha $SB"
sv --task b --phase review --sha "$SB" --by codex --state PASS
gi "$TMP/st-int" merge -q --no-ff feat/core/st-b -m "merge b"; SI=$(git -C "$S" rev-parse feat/core/st)
review_diff_lists "wave-2 re-review after the merge: the printed diff still lists only b's files (its fork point)" sb/b.go
refute_spec "wave-2 re-review after the merge never diffs against the integration branch (empty)" "git diff feat/core/st\.\.\." dispatch "$ST" --task b --phase review --sha "$SB" --runner orca
refute_spec "wave-2 re-review after the merge needs no fallback note" "without a merge commit" dispatch "$ST" --task b --phase review --sha "$SB" --runner orca
st_phase "every task of the repo integrated: next is the integration QA at its HEAD" a integrated "--task integration:srv --phase qa --sha $SI"
sv --task integration:srv --phase qa --sha "$SI" --by codex --state PASS
st_phase "QA PASS on a commit containing the review: qa" a qa
st_phase "and for the second task" b qa
st_note "report at HEAD, review and QA PASS: READY_FOR_PR: yes (without any message)" a '^READY_FOR_PR: yes$'
st_note "a task without a lead report is not ready, whatever its verdicts" b '^READY_FOR_PR: no \(no lead report\)$'
# a current subtask review FAIL at the task HEAD blocks the task in status (next redispatches the lead), so the same
# status must not call it ready, though the lead report, task review and QA are all PASS at HEAD
sv --task a --phase review --sha "$SA" --by claude --state FAIL --subtask sx
st_note "subtask review FAIL at HEAD: READY_FOR_PR: no names the subtask" a '^READY_FOR_PR: no \(subtask sx review FAIL at '
st_note "and status names the subtask FAIL as a note too" a '^subtask sx review FAIL at '
st_phase "and next redispatches the task lead, as the same blocker says" a qa "--task a --phase lead --runner orca"
refute "and status offers no gate while it is open" "^Next: .* gate " status "$ST"
sv --task a --phase review --sha "$SA" --by claude --state PASS --subtask sx
st_note "the subtask PASS clears it: READY_FOR_PR: yes again" a '^READY_FOR_PR: yes$'
# lead_report_notes called directly: blockers and a stale QA (no-worktree, QA at an ancestor with owned paths changed since)
if python3 -B - "$ROOT" "$TMP" <<'PY'
import importlib.util, os, pathlib, subprocess, sys, tempfile
root, tmp = sys.argv[1:]
os.environ['RPG_FACTORY_STATE_DIR'] = tempfile.mkdtemp(dir=tmp)
spec = importlib.util.spec_from_file_location('ready_pipeline', root + '/scripts/factory-pipeline.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
repo = pathlib.Path(tempfile.mkdtemp(dir=tmp))
def git(*args):
    p = subprocess.run(['git', '-C', str(repo), '-c', 'user.name=test', '-c', 'user.email=t@t', *args], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()
git('init', '-q', '-b', 'main')
(repo / 'f.txt').write_text('a'); git('add', '.'); git('commit', '-qm', 'A'); a = git('rev-parse', 'HEAD')
(repo / 'f.txt').write_text('b'); git('commit', '-qam', 'B'); b = git('rev-parse', 'HEAD')
plan = {'id': 'ready-notes', 'tasks': []}
task = {'id': 't1', 'repo': 'srv'}
m.fstate.write_json(m.lead_report_file(plan, 't1'), {'sha': b, 'at': '2026-11-11T00:00:00Z', 'summary': 't1 done', 'task': 't1'})
row = {'sha': b, 'phase': 'qa', 'review': {'state': 'PASS', 'sha': b}, 'qa': {'state': 'PASS', 'sha': b}}
assert 'READY_FOR_PR: yes' in m.lead_report_notes(plan, row, task, set(), path=str(repo)), 'baseline'
fails = ['subtask s1 qa FAIL at abcdef1234 by codex (fix it)', 'subtask s2 review FAIL at 1234567890 by claude (fix it)']
notes = m.lead_report_notes(plan, row, task, set(), path=str(repo), blockers=fails)
assert 'READY_FOR_PR: no (subtask s1 qa FAIL at abcdef1234 by codex (fix it) (+1 more))' in notes, notes
row = dict(row, phase='integrated', qa={'state': 'PASS', 'sha': a}, stale={'qa': 'QA at ' + a[:10] + ' is STALE: owned paths changed on t since'})
notes = m.lead_report_notes(plan, row, task, set(), path=str(repo), no_worktree=True)
assert 'READY_FOR_PR: no (QA at ' + a[:10] + ' is STALE: owned paths changed on t since)' in notes, notes
notes = m.lead_report_notes(plan, dict(row, phase='candidate', stale={'review': 'review at x is STALE: owned paths changed since'}), task, set(), path=str(repo))
assert 'READY_FOR_PR: no (review at x is STALE: owned paths changed since)' in notes, notes
notes = m.lead_report_notes(plan, dict(row, phase='implementing', stale={}), task, set(), path=str(repo))
assert not any(n.startswith('READY_FOR_PR') for n in notes), notes
PY
then pass=$((pass + 1)); echo "PASS  lead_report_notes: blockers and stale review/QA are never READY_FOR_PR"
else fail=$((fail + 1)); echo "FAIL  lead_report_notes blockers and stale"; fi
# a worktree repo: a report at A with a later commit B on the task branch is superseded, even in the qa phase with
# review and QA PASS at B (only a no-worktree repo, whose HEAD is the shared topic, accepts a report at an ancestor)
if python3 -B - "$ROOT" "$TMP" <<'PY'
import importlib.util, os, pathlib, subprocess, sys, tempfile
root, tmp = sys.argv[1:]
os.environ['RPG_FACTORY_STATE_DIR'] = tempfile.mkdtemp(dir=tmp)
spec = importlib.util.spec_from_file_location('report_ancestor_pipeline', root + '/scripts/factory-pipeline.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
repo = pathlib.Path(tempfile.mkdtemp(dir=tmp))
def git(*args):
    p = subprocess.run(['git', '-C', str(repo), '-c', 'user.name=test', '-c', 'user.email=t@t', *args], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()
git('init', '-q', '-b', 'main')
(repo / 'f.txt').write_text('a'); git('add', '.'); git('commit', '-qm', 'A'); a = git('rev-parse', 'HEAD')
(repo / 'f.txt').write_text('b'); git('commit', '-qam', 'B'); b = git('rev-parse', 'HEAD')
plan = {'id': 'ancestor-report', 'tasks': []}
task = {'id': 't1', 'repo': 'srv'}
m.fstate.write_json(m.lead_report_file(plan, 't1'), {'sha': a, 'at': '2026-11-11T00:00:00Z', 'summary': 't1 done', 'task': 't1'})
row = {'sha': b, 'phase': 'qa', 'review': {'state': 'PASS', 'sha': b}, 'qa': {'state': 'PASS', 'sha': b}}
notes = m.lead_report_notes(plan, row, task, set(), path=str(repo), no_worktree=False)
assert any('(stale: task HEAD is ' + b[:10] + ')' in n for n in notes), notes
assert 'READY_FOR_PR: no (lead report is for ' + a[:10] + ', task HEAD is ' + b[:10] + ')' in notes, notes
notes = m.lead_report_notes(plan, row, task, set(), path=str(repo), no_worktree=True)
assert not any('stale' in n for n in notes) and 'READY_FOR_PR: yes' in notes, notes
PY
then pass=$((pass + 1)); echo "PASS  worktree repo: a report at an ancestor of the task HEAD is stale (READY_FOR_PR: no); no-worktree keeps it current"
else fail=$((fail + 1)); echo "FAIL  worktree repo ancestor report"; fi
pp status --json "$ST"; echo "$OUT" > "$TMP/so-report.json"
if python3 - "$ROOT" "$TMP/so-report.json" <<'PY'
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("lint", sys.argv[1] + "/scripts/checks/artifact-lint.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
schema = json.load(open(sys.argv[1] + "/docs/schemas/pipeline-status.schema.json", encoding="utf-8"))
assert not m.schema_errors(json.load(open(sys.argv[2], encoding="utf-8")), schema, schema)
PY
then pass=$((pass + 1)); echo "PASS  status --json with the lead report notes still matches the status schema"
else fail=$((fail + 1)); echo "FAIL  status --json lead report notes schema"; fi
# the Unity project: tasks run on the integration branch in the main checkout
gi "$C" checkout -qb feat/core/st develop
mkdir -p "$C/Assets/C"; echo c > "$C/Assets/C/c.cs"
st_phase "uncommitted work in the Unity task's paths: implementing" c1 implementing
gi "$C" add Assets/C; gi "$C" commit -qm "feat: c1"; SC=$(git -C "$C" rev-parse HEAD)
st_phase "a commit on the integration branch touching the task: candidate" c1 candidate "--task c1 --phase verify --sha $SC"
st_phase "the next Unity task still waits" c2 pending '^$'
sv --task c1 --phase review --sha "$SC" --by codex --state FAIL
st_phase "Unity review FAIL: next resumes the task lead in the main checkout, not an implement worker" c1 reviewed "--task c1 --phase lead --runner orca$"
# follow status.next: the resumed task lead is launched in the main checkout, never a worktree or a committing worker
NX=$(python3 -B "$P" status --json "$ST" | python3 -c 'import json,sys; print({t["id"]:t for t in json.load(sys.stdin)["tasks"]}["c1"]["next"])')
out=$(eval "$NX" 2>&1)
if grep -qE "^orca agent launch --agent claude --worktree '?path:[^' ]*IndieRPGMMOAdventure" <<<"$out" \
   && ! grep -qE "new-top-level|--base-branch|worktree create|commit explicit" <<<"$out"; then
  pass=$((pass + 1)); echo "PASS  Unity review FAIL: status.next launches the task lead in the main checkout"
else fail=$((fail + 1)); echo "FAIL  Unity review FAIL: status.next"; sed 's/^/      /' <<<"$out" | head -10; fi
expect_spec "Unity fix session after the FAIL does not commit" "Do NOT commit, stage or stash" dispatch "$ST" --task c1 --phase implement --runner orca
refute "Unity fix session after the FAIL creates no worktree" "new-top-level|--base-branch|worktree create" dispatch "$ST" --task c1 --phase implement --runner orca
refute_spec "Unity fix session after the FAIL: the spec never commits" "commit explicit" dispatch "$ST" --task c1 --phase implement --runner orca
sv --task c1 --phase review --sha "$SC" --by codex --state PASS
st_phase "Unity review PASS is integrated at once; next is the per-task QA" c1 integrated "--task c1 --phase qa --sha $SC"
sv --task c1 --phase qa --sha "$SC" --by codex --state PASS
st_phase "per-task QA PASS: qa" c1 qa
# a no-worktree repo: the task HEAD is plan.topic, which moves when the next task commits. A finished task keeps
# READY_FOR_PR: yes and shows no stale marker while its report is an ancestor of the HEAD (phase qa)
expect "report: the Unity task lead reports at its commit" 0 "^recorded lead report for c1 at ${SC:0:10}: " report "$ST" --task c1 --sha "$SC" --body "c1 done"
st_note "no-worktree: report at the HEAD, review and QA PASS: READY_FOR_PR: yes" c1 '^READY_FOR_PR: yes$'
st_phase "and the next Unity task is ready: its task lead" c2 pending "--task c2 --phase lead --runner orca"
refute "no gate command while c2 is pending" "^Next: .* gate " status "$ST"
mkdir -p "$C/Assets/D"; echo d > "$C/Assets/D/d.cs"; gi "$C" add Assets/D; gi "$C" commit -qm "feat: c2"; SD=$(git -C "$C" rev-parse HEAD)
st_phase "no-worktree: the next task committed, c1 is still qa" c1 qa
st_note "no-worktree: after the next task commits, c1 keeps READY_FOR_PR: yes (report is an ancestor of the HEAD)" c1 '^READY_FOR_PR: yes$'
st_note "no-worktree: and its report line has no stale marker" c1 "^lead report: [0-9TZ:-]+ @${SC:0:10} c1 done$"
# a report at a commit that is no ancestor of the HEAD is still stale
SX=$(gi "$C" commit-tree 'develop^{tree}' -p develop -m "side")
expect "report: a report at a commit outside the task's history" 0 "^recorded lead report for c1 at ${SX:0:10}: " report "$ST" --task c1 --sha "$SX" --body "c1 done"
st_note "no-worktree: a report at a non-ancestor is shown stale" c1 "^lead report: [0-9TZ:-]+ @${SX:0:10} c1 done \(stale: task HEAD is ${SD:0:10}\)$"
st_note "no-worktree: and READY_FOR_PR: no names both commits" c1 "^READY_FOR_PR: no \(lead report is for ${SX:0:10}, task HEAD is ${SD:0:10}\)$"
expect "report: the Unity task lead reports again at its commit" 0 "^recorded lead report for c1 at ${SC:0:10}: " report "$ST" --task c1 --sha "$SC" --body "c1 done"
sv --task c2 --phase review --sha "$SD" --by claude --state PASS
sv --task c2 --phase qa --sha "$SD" --by claude --state PASS
st_note "no-worktree: every task at QA flips c1 to integrated, yet c1 keeps READY_FOR_PR: yes (its QA is an ancestor of the HEAD)" c1 '^READY_FOR_PR: yes$'
# agree <name>: status names the gate as next exactly when the gate (no registry checks here) is READY_FOR_PR
agree() {
  local out g rc
  pp gate "$ST"; g="$OUT"; rc="$RC"; pp status --json "$ST"; out="$OUT"
  if python3 -c 'import json,sys; o=json.loads(sys.argv[1]); said=any(" gate " in c for c in o["next"])
assert said == (sys.argv[2] == "0"), (o["next"], sys.argv[2])' "$out" "$rc"; then pass=$((pass + 1)); echo "PASS  $1"
  else fail=$((fail + 1)); echo "FAIL  $1 (gate rc=$rc)"; head -c 800 <<<"$out"; echo; sed 's/^/      /' <<<"$g" | head -10; fi
}
st_phase "per-task QA of every Unity task: integration QA at the HEAD is still due" c2 integrated "--task integration:cli --phase qa --sha $SD"
expect "and the missing integration QA is named" 0 "no integration QA for cli: the gate needs it" status "$ST"
refute "no gate command before the Unity integration QA" "^Next: .* gate " status "$ST"
expect "the gate agrees: integration QA missing" 1 "BLOCKER integration:cli: no qa verdict" gate "$ST"
agree "status and gate agree before the Unity integration QA"
sv --task integration:cli --phase qa --sha "$SC" --by codex --state PASS
st_phase "an integration QA on an older HEAD is STALE" c1 integrated "--task integration:cli --phase qa --sha $SD"
agree "status and gate agree on a stale integration QA"
sv --task integration:cli --phase qa --sha "$SD" --by codex --state PASS
expect "every task has QA: the plan-level next is the gate" 0 "^Next: .* gate .*st.json" status "$ST"
expect "and the gate is READY_FOR_PR" 0 "^Gate: READY_FOR_PR" gate "$ST"
agree "status and gate agree once every QA is at the HEAD"
expect "every wave integrated" 0 "^Every wave is integrated" status "$ST"
python3 -B "$P" status --json "$ST" > "$TMP/status.json" 2>&1
if python3 - "$ROOT" "$TMP/status.json" <<'PY'
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("lint", sys.argv[1] + "/scripts/checks/artifact-lint.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
schema = json.load(open(sys.argv[1] + "/docs/schemas/pipeline-status.schema.json", encoding="utf-8"))
value = json.load(open(sys.argv[2], encoding="utf-8"))
assert value["schema"] == "rpg-factory.pipeline-status/1"
errors = m.schema_errors(value, schema, schema)
assert not errors, errors
PY
then pass=$((pass + 1)); echo "PASS  status --json matches docs/schemas/pipeline-status.schema.json"
else fail=$((fail + 1)); echo "FAIL  status --json schema"; head -c 800 "$TMP/status.json"; fi
sed -i 's/"objective":"o","paths":\["sa\/"\]/"objective":"changed","paths":["sa\/"]/' "$ST"
st_phase "a changed task in the plan: its review is no longer counted; review the integration HEAD" a candidate "--task a --phase verify --sha $SI"
expect "and the stale verdict is named" 0 "review verdict is STALE: the plan's task changed" status "$ST"
X=$(plan stbad "{$HEAD,\"tasks\":[{\"id\":\"a\",\"repo\":\"nope\",\"objective\":\"o\",\"paths\":[\"x/\"],\"acceptance\":[\"a\"]}]}")
expect "status of an invalid plan: exit 1, next is validate" 1 "^Next: .* validate " status "$X"
# the chain unit creates feat/core/demo; a standalone status unit has no such branch
git -C "$C" rev-parse -q --verify refs/heads/feat/core/demo >/dev/null && gi "$C" checkout -q feat/core/demo
git -C "$S" worktree remove "$TMP/st-b"; git -C "$S" worktree remove "$TMP/st-int"

case_end status
fi

if has_case owned-case; then
case_start
echo "-- owned paths in another case (Windows: case-insensitive pathspecs)"
# The plan owns SRC/ while the commits touch src/a.txt. On Windows (os.name nt, as specs() checks) the owned-path check
# and the git pathspecs agree case-insensitively: status counts the commit and a later change makes the review STALE.
# Elsewhere git is case-sensitive: the commit is not the task's own, so the task is still implementing.
I="$WS/icase"; cp -R "$TMP/base-server" "$I"
IC=$(plan icase '{"schema":"rpg-factory.pipeline-plan/1","id":"icase","title":"Case","topic":"feat/core/ic","deliver":"pr",
 "repos":{"ic":{"path":"ws/icase","base":"develop"}},"tasks":[{"id":"t","repo":"ic","objective":"o","paths":["SRC/"],"acceptance":["a"]}]}')
gi "$I" checkout -qb feat/core/ic-t; mkdir -p "$I/src"; echo a > "$I/src/a.txt"; gi "$I" add -A; gi "$I" commit -qm "feat: a"; IT=$(git -C "$I" rev-parse HEAD)
ic_phase() {  # ic_phase <name> <phase>: task t's phase in status --json
  local out; out=$(python3 -B "$P" status --json "$IC" 2>&1)
  if python3 -c 'import json,sys; r={t["id"]:t for t in json.loads(sys.argv[1])["tasks"]}["t"]; assert r["phase"]==sys.argv[2], r' "$out" "$2"
  then pass=$((pass + 1)); echo "PASS  $1"; else fail=$((fail + 1)); echo "FAIL  $1"; head -c 1200 <<<"$out"; echo; fi
}
if [ "$(python3 -c 'import os; print(os.name)')" = nt ]; then
  ic_phase "Windows: status counts a commit in src/ for the owned path SRC/ (candidate)" candidate
  python3 -B "$P" verdict "$IC" --task t --phase review --sha "$IT" --by codex --state PASS >/dev/null || echo "verdict failed: icase review"
  gi "$I" checkout -qb feat/core/ic develop; gi "$I" merge -q --no-ff feat/core/ic-t -m "merge t"; II=$(git -C "$I" rev-parse HEAD)
  python3 -B "$P" verdict "$IC" --task integration:ic --phase qa --sha "$II" --by codex --state PASS >/dev/null || echo "verdict failed: icase qa"
  expect "Windows: review and QA PASS on the owned path in another case: READY_FOR_PR" 0 "^Gate: READY_FOR_PR" gate "$IC"
  echo b >> "$I/src/a.txt"; gi "$I" commit -qam "fix: a after review"
  expect "Windows: a change to src/ after review makes the review of SRC/ STALE" 1 "BLOCKER t: review is STALE" gate "$IC"
  expect "Windows: and the QA on the old HEAD is STALE" 1 "BLOCKER ic: QA is STALE" gate "$IC"
else
  ic_phase "case-sensitive host: a commit in src/ is not the task's own for SRC/ (implementing)" implementing
fi

case_end owned-case
fi

if has_case dogfood; then
case_start
echo "-- dogfood two-level grader (offline, synthetic transcripts)"
# tl_transcript <file> <bash command> <its result text> [extra tool_use json]: a stream-json run lead transcript that
# loads factory-core, runs one Bash command (is_error false, as a pipe reports) and finishes with success
tl_transcript() {
  local f="$1" cmd="$2" res="$3" extra="${4:-}"
  {
    jq -nc '{type:"assistant",message:{content:[{type:"tool_use",id:"s1",name:"Skill",input:{skill:"rpg-factory:factory-core"}}]}}'
    jq -nc '{type:"user",message:{content:[{type:"tool_result",tool_use_id:"s1",content:"Launching skill: rpg-factory:factory-core"}]}}'
    jq -nc --arg c "$cmd" '{type:"assistant",message:{content:[{type:"tool_use",id:"b1",name:"Bash",input:{command:$c}}]}}'
    jq -nc --arg r "$res" '{type:"user",message:{content:[{type:"tool_result",tool_use_id:"b1",content:$r,is_error:false}]}}'
    [ -z "$extra" ] || jq -nc --argjson u "$extra" '{type:"assistant",message:{content:[$u]}}'
    jq -nc '{type:"result",subtype:"success",is_error:false}'
  } > "$f"
}
# grade <name> <rc> <grep-regex> <transcript>: tests/dogfood.sh --grade-two-level exit code and result line
grade() {
  local name="$1" want="$2" pat="$3" out rc; out=$(bash "$ROOT/tests/dogfood.sh" --grade-two-level "$4" 2>&1); rc=$?
  if [ "$rc" = "$want" ] && has_ere "$out" "$pat"; then pass=$((pass + 1)); echo "PASS  $name"
  else fail=$((fail + 1)); echo "FAIL  $name (rc=$rc, want $want, pattern '$pat')"; sed 's/^/      /' <<<"$out" | head -10; fi
}
LEAD_CMD='python3 -B scripts/factory-pipeline.py dispatch plan.json --task t --phase lead --runner print 2>&1 | head -60'
LEAD_OUT=$'# agent: claude   worktree: new-top-level   base: main\nTask lead for task t of plan p (Demo), references/parallel-work.md. You own this task and this task worktree.\n{\n  "plan": "p"\n}'
tl_transcript "$TMP/tl-pass.jsonl" "$LEAD_CMD" "$LEAD_OUT"
grade "grader: factory-core + successful print-runner lead dispatch: PASS" 0 "dispatch tool_use: b1 \| PASS$" "$TMP/tl-pass.jsonl"
tl_transcript "$TMP/tl-warn.jsonl" "$LEAD_CMD" "$LEAD_OUT"$'\nfactory-pipeline: `codex` is not on PATH here: the codex task lead may be unavailable'
grade "grader: a not-on-PATH warning next to the printed spec still passes" 0 "\| PASS$" "$TMP/tl-warn.jsonl"
tl_transcript "$TMP/tl-masked.jsonl" "$LEAD_CMD" "factory-pipeline: cannot read plan plan.json: [Errno 2] No such file or directory"
grade "grader: failed dispatch masked by a pipe (is_error false): FAIL" 1 "FAIL: no successful factory-pipeline.py dispatch --phase lead" "$TMP/tl-masked.jsonl"
tl_transcript "$TMP/tl-trace.jsonl" "$LEAD_CMD" "$LEAD_OUT"$'\nTraceback (most recent call last):\n  File "x", line 1'
grade "grader: a traceback in the dispatch output: FAIL" 1 "FAIL: no successful factory-pipeline.py dispatch" "$TMP/tl-trace.jsonl"
tl_transcript "$TMP/tl-tier.jsonl" "python3 -B scripts/factory-pipeline.py tier -- --repo plugin --paths scripts/factory-cmd.py" "Tier M"
grade "grader: tier only: FAIL" 1 "FAIL: no successful factory-pipeline.py dispatch --phase lead" "$TMP/tl-tier.jsonl"
tl_transcript "$TMP/tl-edit.jsonl" "$LEAD_CMD" "$LEAD_OUT" '{"type":"tool_use","id":"e1","name":"Edit","input":{"file_path":"C:\\w\\rpg-factory\\skills\\factory-core\\SKILL.md","old_string":"a","new_string":"b"}}'
grade "grader: run lead edits skills/factory-core/SKILL.md: FAIL" 1 "FAIL: run lead edited task files with file tools: .*skills/factory-core/SKILL\.md" "$TMP/tl-edit.jsonl"
tl_transcript "$TMP/tl-orca.jsonl" "python3 -B scripts/factory-pipeline.py dispatch plan.json --task t --phase lead --runner orca" "orca worktree create --name feat/x --prompt 'Read your task spec at /s/t.md and follow it.' --json"
grade "grader: --runner orca dispatch: FAIL" 1 "FAIL: no successful factory-pipeline.py dispatch --phase lead" "$TMP/tl-orca.jsonl"
grade "grader: missing transcript: FAIL" 1 "FAIL: no transcript" "$TMP/tl-none.jsonl"
if tail -n 1 "$ROOT/tests/dogfood.sh" | grep -qF '"${tl_fail:-0}" -eq 0'; then pass=$((pass + 1)); echo "PASS  dogfood --all exit status includes the two-level result"
else fail=$((fail + 1)); echo "FAIL  dogfood --all exit status includes the two-level result (last line of tests/dogfood.sh)"; fi

case_end dogfood
fi

if has_case recorded-implementer; then
case_start
echo "-- recorded implementer"
# a fallback implementation is recorded: after the model returns, review pairs against the recorded implementer
R="$TMP/rec"; mkdir -p "$R/ProjectSettings" "$R/code" "$R/docs"; echo 'm_EditorVersion: 6000.0.0f1' > "$R/ProjectSettings/ProjectVersion.txt"
git init -q -b develop "$R"; echo a > "$R/code/a.cs"; echo a > "$R/docs/a.md"; gi "$R" add -A; gi "$R" commit -qm init
gi "$R" checkout -qb feat/core/rec; echo b > "$R/code/a.cs"; echo b > "$R/docs/a.md"; gi "$R" commit -qam "feat: b"; RS=$(git -C "$R" rev-parse HEAD)
RP=$(plan rec '{"schema":"rpg-factory.pipeline-plan/1","id":"rec","title":"Recorded","topic":"feat/core/rec","repos":{"rec":{"path":"rec","base":"develop"}},"tasks":[
 {"id":"k","repo":"rec","kind":"code","objective":"o","paths":["code/"],"acceptance":["a"]},
 {"id":"d","repo":"rec","kind":"docs","objective":"o","paths":["docs/"],"acceptance":["a"]},
 {"id":"q","repo":"rec","kind":"code","objective":"o","paths":["ProjectSettings/"],"acceptance":["a"]}]}')
RVD="$RPG_FACTORY_STATE_DIR/pipeline/rec"
RPG_FACTORY_AGENTS=claude expect "claude-only: the code task is implemented by claude (fallback)" 0 "implement -> claude" dispatch "$RP" --task k --phase implement --runner orca
expect "codex back: the review pairs against the recorded claude implementer" 0 "implement -> claude \(recorded implementer: fallback: codex unavailable\)" dispatch "$RP" --task k --phase review --sha "$RS" --runner print
expect "codex back: the review of the recorded claude implementation goes to codex" 0 "^# agent: codex" dispatch "$RP" --task k --phase review --sha "$RS" --runner print
expect "verdict records the recorded implementer" 0 "recorded review PASS for k" verdict "$RP" --task k --phase review --sha "$RS" --by claude --state PASS
expect "explicit task implementer cannot contradict dispatch" 2 "--implementer codex conflicts with recorded implementer claude for k" verdict "$RP" --task k --phase review --sha "$RS" --by claude --state PASS --implementer codex
expect "explicit task implementer matching dispatch is accepted" 0 "recorded review PASS for k" verdict "$RP" --task k --phase review --sha "$RS" --by claude --state PASS --implementer claude
expect "a claude review of the recorded claude implementation is not cross-model" 1 "BLOCKER k: reviewed by claude, cross-model review needs codex" gate "$RP" --no-run-checks
RPG_FACTORY_AGENTS=codex expect "codex-only: the docs task is implemented by codex (fallback)" 0 "implement -> codex" dispatch "$RP" --task d --phase implement --runner orca
expect "claude back: the review of the recorded codex implementation goes to claude" 0 "^# agent: claude" dispatch "$RP" --task d --phase review --sha "$RS" --runner print
python3 -B "$P" verdict "$RP" --task d --phase review --sha "$RS" --by codex --state PASS >/dev/null
expect "a codex review of the recorded codex implementation is not cross-model" 1 "BLOCKER d: reviewed by codex, cross-model review needs claude" gate "$RP" --no-run-checks
expect "per-task QA pairs against the recorded implementer too" 0 "qa -> codex" dispatch "$RP" --task k --phase qa --sha "$RS" --runner print
RPG_FACTORY_AGENTS=claude expect "no record: review pairs against the planned implementer, not availability" 0 "implement -> codex \(planned implementer: kind: code\)" dispatch "$RP" --task q --phase review --sha "$RS" --runner print
# verdict stamps a fallback only from this candidate's review dispatch and only for its reviewer
RPG_FACTORY_AGENTS=claude python3 -B "$P" verdict "$RP" --task k --phase review --sha "$RS" --by claude --state PASS >/dev/null
expect "claude-only verdict with no fallback review dispatch: still NOT_READY" 1 "BLOCKER k: reviewed by claude, cross-model review needs codex" gate "$RP" --no-run-checks
RPG_FACTORY_AGENTS=claude expect "claude-only review dispatch of the claude implementation is a SAME_MODEL fallback" 0 "review -> claude \(SAME_MODEL \(fallback: codex unavailable\)\)" dispatch "$RP" --task k --phase review --sha "$RS" --runner orca
python3 -B "$P" verdict "$RP" --task k --phase review --sha "$RS" --by codex --state FAIL >/dev/null
if ! grep -q '"fallback": "' "$RVD/k__review.json"; then pass=$((pass + 1)); echo "PASS  a verdict by another model than the dispatched fallback reviewer stamps no fallback"
else fail=$((fail + 1)); echo "FAIL  a verdict by another model than the dispatched fallback reviewer stamps no fallback"; fi
expect "the dispatched fallback reviewer's verdict is stamped (both models back)" 0 "recorded review PASS for k" verdict "$RP" --task k --phase review --sha "$RS" --by claude --state PASS
expect "gate accepts the dispatched fallback" 1 "NOTE    k: SAME_MODEL \(fallback: codex unavailable\)" gate "$RP" --no-run-checks
gi "$R" commit -q --allow-empty -m "chore: next"; RS2=$(git -C "$R" rev-parse HEAD)
RPG_FACTORY_AGENTS=claude python3 -B "$P" verdict "$RP" --task k --phase review --sha "$RS2" --by claude --state PASS >/dev/null
if ! grep -q '"fallback": "' "$RVD/k__review__${RS2:0:12}__claude.json"; then pass=$((pass + 1)); echo "PASS  a fallback dispatch of another candidate stamps no fallback"
else fail=$((fail + 1)); echo "FAIL  a fallback dispatch of another candidate stamps no fallback"; fi
# a subtask fallback is never laundered by the task review: subtask s by claude (codex down), codex back, task review by
# claude paired against the lead's explicitly declared codex implementation
RSP=$(plan recsub '{"schema":"rpg-factory.pipeline-plan/1","id":"recsub","title":"Recorded subtasks","topic":"feat/core/rec","repos":{"rec":{"path":"rec","base":"develop"}},"tasks":[
 {"id":"k","repo":"rec","kind":"code","objective":"o","paths":["code/","docs/"],"acceptance":["a"]}]}')
RSS="$TMP/sub-recsub.json"
printf '%s\n' '{"schema":"rpg-factory.pipeline-subplan/1","plan":"recsub.json","task":"k","subtasks":[
 {"id":"s","objective":"o","kind":"code","paths":["code/"]},{"id":"s2","objective":"o","kind":"code","paths":["docs/a.md"]},
 {"id":"s3","objective":"o","kind":"docs","paths":["docs/b/"]}]}' > "$RSS"
RSVD="$RPG_FACTORY_STATE_DIR/pipeline/recsub"
rs() { python3 -B "$P" "$@" --runner orca >/dev/null 2>&1 || echo "dispatch failed: $*"; }
rv() { python3 -B "$P" verdict "$RSP" "$@" >/dev/null || echo "verdict failed: $*"; }
RPG_FACTORY_AGENTS=claude rs dispatch "$RSP" --task k --phase implement --subplan "$RSS" --subtask s
RPG_FACTORY_AGENTS=claude rs dispatch "$RSP" --task k --phase implement --subplan "$RSS" --subtask s2
rs dispatch "$RSP" --task k --phase review --sha "$RS2"
rv --task k --phase review --sha "$RS2" --by claude --state PASS
expect "unanimous claude subtasks require codex task review by default" 1 "reviewed by claude, cross-model review needs codex" gate "$RSP" --no-run-checks
expect "explicit subtask implementer cannot contradict dispatch" 2 "--implementer codex conflicts with recorded implementer claude for k subtask s" verdict "$RSP" --task k --subtask s --phase review --sha "$RS2" --by claude --state PASS --implementer codex
expect "explicit subtask implementer matching dispatch is accepted" 0 "recorded review PASS for k subtask s" verdict "$RSP" --task k --subtask s --phase review --sha "$RS2" --by claude --state PASS --implementer claude
# a task review pairs against the unanimous subtask implementers when the task has no implementer record of its own, so an
# explicit --implementer that contradicts them is refused too (not only one that contradicts a task-level record)
expect "explicit task implementer contradicting the unanimous subtask implementers is refused" 2 "--implementer codex conflicts with the recorded subtask implementer claude for k" verdict "$RSP" --task k --phase review --sha "$RS2" --by claude --state PASS --implementer codex
expect "explicit task implementer matching the unanimous subtask implementers is accepted" 0 "recorded review PASS for k" verdict "$RSP" --task k --phase review --sha "$RS2" --by codex --state PASS --implementer claude
# the lead's own task-level implement dispatch (codex, planned for a code task): the record the explicit declarations below match
rs dispatch "$RSP" --task k --phase implement
expect "explicit task implementer matching the task-level dispatch is accepted" 0 "recorded review PASS for k" verdict "$RSP" --task k --phase review --sha "$RS2" --by claude --state PASS --implementer codex
expect "explicit task implementer contradicting the task-level dispatch is still refused" 2 "--implementer claude conflicts with recorded implementer codex for k" verdict "$RSP" --task k --phase review --sha "$RS2" --by codex --state PASS --implementer claude
expect "explicit implementer preserves its paired reviewer record" 0 "kept the claude review of k" verdict "$RSP" --task k --phase review --sha "$RS2" --by codex --state FAIL --implementer codex
if jq -e '.by == "claude" and .state == "PASS" and .implementer == "codex"' "$RSVD/k__review.json" >/dev/null; then pass=$((pass + 1)); echo "PASS  explicit implementer keeps paired PASS intact"
else fail=$((fail + 1)); echo "FAIL  explicit implementer keeps paired PASS intact"; fi
rv --task k --phase review --sha "$RS2" --by claude --state PASS --implementer codex
rv --task integration:rec --phase qa --sha "$RS2" --by codex --state PASS
expect "code subtask by the verifier is accepted with a note" 0 "NOTE    k: subtask s SAME_MODEL \(single verify\)" gate "$RSP" --no-run-checks
rv --task k --phase review --sha "$RS2" --by codex --state PASS --subtask s
refute "a subtask review by its implementer's pair covers that subtask" "BLOCKER k: subtask s recorded" gate "$RSP" --no-run-checks
RPG_FACTORY_AGENTS=claude rs dispatch "$RSP" --task k --phase review --sha "$RS2" --subplan "$RSS" --subtask s2
rv --task k --phase review --sha "$RS2" --by claude --state PASS --subtask s2
expect "a dispatch-recorded SAME_MODEL fallback subtask review passes the gate" 0 "^Gate: READY_FOR_PR" gate "$RSP" --no-run-checks
refute "prose subtask by the verifier is silent" "subtask s2 SAME_MODEL" gate "$RSP" --no-run-checks
# An ancestral PASS covers only unchanged reviewed paths; old records conservatively cover the whole task.
rv --task k --phase review --sha "$RS2" --by codex --state PASS --subtask s --subplan "$RSS"
rv --task k --phase review --sha "$RS2" --by codex --state PASS --subtask s2 --subplan "$RSS"
echo c > "$R/code/a.cs"; gi "$R" commit -qam "fix: later subtask edit"; RS3=$(git -C "$R" rev-parse HEAD)
rv --task k --phase review --sha "$RS3" --by claude --state PASS --implementer codex
rv --task integration:rec --phase qa --sha "$RS3" --by codex --state PASS
expect "single verify covers the later subtask edit" 0 "^Gate: READY_FOR_PR" gate "$RSP" --no-run-checks
rv --task k --phase review --sha "$RS3" --by codex --state PASS --subtask s --subplan "$RSS"
expect "a fresh paired subtask review covers the later edit" 0 "^Gate: READY_FOR_PR" gate "$RSP" --no-run-checks
echo c > "$R/docs/a.md"; gi "$R" commit -qam "docs: outside code subtask"; RS4=$(git -C "$R" rev-parse HEAD)
rv --task k --phase review --sha "$RS4" --by claude --state PASS --implementer codex
rv --task integration:rec --phase qa --sha "$RS4" --by codex --state PASS
rv --task k --phase review --sha "$RS4" --by codex --state PASS --subtask s2 --subplan "$RSS"
expect "an edit outside subtask paths keeps its ancestral review valid" 0 "^Gate: READY_FOR_PR" gate "$RSP" --no-run-checks
# Restore the fixture candidate used by subsequent verdict routing checks.
RS2=$RS4
# verdict --subtask pairs against the subtask's routing: --subplan (docs subtask s3: claude), else its review dispatch
rv --task k --phase review --sha "$RS2" --by codex --state PASS --subtask s3 --subplan "$RSS"
if jq -e '.implementer == "claude"' "$RSVD/k@s3__review.json" >/dev/null; then pass=$((pass + 1)); echo "PASS  verdict --subtask --subplan routes the implementer over the subtask's kind"
else fail=$((fail + 1)); echo "FAIL  verdict --subtask --subplan routes the implementer over the subtask's kind"; fi
rs dispatch "$RSP" --task k --phase review --sha "$RS" --subplan "$RSS" --subtask s3
rv --task k --phase review --sha "$RS" --by codex --state PASS --subtask s3
if jq -e '.implementer == "claude"' "$RSVD/k@s3__review__${RS:0:12}__codex.json" >/dev/null; then pass=$((pass + 1)); echo "PASS  verdict --subtask takes the implementer its review dispatch routed"
else fail=$((fail + 1)); echo "FAIL  verdict --subtask takes the implementer its review dispatch routed"; fi
expect "verdict --fallback refuses an unknown agent" 2 "--fallback must be one of claude, codex" verdict "$RSP" --task k --phase review --sha "$RS2" --by claude --state PASS --fallback gemini
expect "verdict --fallback goes with review only" 2 "--fallback .* goes with --phase review" verdict "$RSP" --task k --phase qa --sha "$RS2" --by claude --state PASS --fallback codex
expect "retrospective fallback requires a note" 2 "requires --note" verdict "$RSP" --task k --subtask s --phase review --sha "$RS2" --by claude --state PASS --fallback 'codex unavailable'
RPG_FACTORY_AGENTS=claude expect "legacy manual fallback also requires a note" 2 "requires --note" verdict "$RSP" --task k --subtask s --phase review --sha "$RS2" --by claude --state PASS --fallback codex
expect "retrospective fallback rejects a blank note" 2 "requires --note" verdict "$RSP" --task k --subtask s --phase review --sha "$RS2" --by claude --state PASS --fallback 'codex unavailable' --note ' '
expect "retrospective fallback requires same-model review" 2 "requires a SAME_MODEL review" verdict "$RSP" --task k --subtask s --phase review --sha "$RS2" --by codex --state PASS --fallback 'codex unavailable' --note '401 outage'
expect "retrospective fallback validates unavailable model" 2 "--fallback must be one of" verdict "$RSP" --task k --subtask s --phase review --sha "$RS2" --by claude --state PASS --fallback 'codex offline' --note '401 outage'
expect "retrospective fallback rejects an empty reason" 2 "--fallback must be one of" verdict "$RSP" --task k --subtask s --phase review --sha "$RS2" --by claude --state PASS --fallback '' --note '401 outage'
expect "retrospective fallback must name the paired model" 2 "requires a SAME_MODEL review" verdict "$RSP" --task k --subtask s --phase review --sha "$RS2" --by claude --state PASS --fallback 'claude unavailable' --note '401 outage'
# Exercise acceptance when the fallback is needed, without an archived current paired PASS covering the same slice.
rm -f "$RSVD/k@s__review__"*"__codex.json"
jq '.subtasks[0] += {implementer: "claude", reviewer: "codex"}' "$RSS" > "$TMP/sub-own-reviewer.json"
expect "retrospective subtask fallback accepts a subplan with its own reviewer" 0 "recorded review PASS" verdict "$RSP" --task k --subtask s --phase review --sha "$RS2" --by claude --state PASS --fallback 'codex unavailable' --note '401 outage' --subplan "$TMP/sub-own-reviewer.json"
expect "verdict rejects undocumented reviewer alias" 2 "unrecognized arguments: --reviewer" verdict "$RSP" --task k --phase review --sha "$RS2" --by claude --reviewer claude --state PASS
expect "gate displays single verify note for code" 0 "NOTE    k: subtask s SAME_MODEL \(single verify\)" gate "$RSP" --no-run-checks
if jq -e '.fallback == "codex unavailable" and .note == "401 outage"' "$RSVD/k@s__review.json" >/dev/null; then pass=$((pass + 1)); echo "PASS  retrospective fallback stores reason and note"
else fail=$((fail + 1)); echo "FAIL  retrospective fallback stores reason and note"; fi
expect "retrospective task fallback requires --subtask" 2 "requires --subtask" verdict "$RSP" --task k --phase review --sha "$RS2" --by claude --state PASS --implementer claude --fallback 'codex unavailable' --note 'past outage'
rv --task k --phase review --sha "$RS2" --by claude --state PASS --implementer codex
rv --task k --subtask s --phase review --sha "$RS2" --by codex --state PASS --subplan "$RSS"
NOID=$(plan noid '{"schema":"rpg-factory.pipeline-plan/1","id":"noid","title":"t","topic":"feat/core/noid","repos":{"rec":{"path":"rec","base":"develop"}},"tasks":[{"repo":"rec","objective":"o","paths":["x/"],"acceptance":["a"]}]}')
expect "status of a task without id: INVALID" 1 "INVALID" status "$NOID"
refute "status of a task without id: no traceback" "Traceback" status "$NOID"
jq 'del(.pipeline.qa_prefer)' "$ROOT/registry.json" > "$TMP/reg-noqa.json"
out=$("$ROOT/scripts/check-registry.sh" --structure-only --registry "$TMP/reg-noqa.json" 2>&1)
if ! grep -qE "jq: error|qa_prefer" <<<"$out"; then pass=$((pass + 1)); echo "PASS  check-registry without pipeline.qa_prefer: no jq error"
else fail=$((fail + 1)); echo "FAIL  check-registry without pipeline.qa_prefer: no jq error"; echo "$out" | head -5; fi
# check_reg <name> <jq mutation> <problem regex>: check-registry.sh fails on the mutated registry and names the problem
check_reg() {
  local out rc; jq "$2" "$ROOT/registry.json" > "$TMP/reg-bad.json"
  out=$("$ROOT/scripts/check-registry.sh" --structure-only --registry "$TMP/reg-bad.json" 2>&1); rc=$?
  if [ "$rc" != 0 ] && grep -qE -- "$3" <<<"$out"; then pass=$((pass + 1)); echo "PASS  $1"
  else fail=$((fail + 1)); echo "FAIL  $1 (rc=$rc)"; echo "$out" | head -5; fi
}
check_reg "check-registry: unknown agent in agent_routing fails" '.pipeline.agent_routing.code = "gpt"' "pipeline.agent_routing: invalid kind or agent code"
check_reg "check-registry: unknown kind in agent_routing fails" '.pipeline.agent_routing.bogus = "claude"' "pipeline.agent_routing: invalid kind or agent bogus"
check_reg "check-registry: unknown agent in qa_prefer fails" '.pipeline.qa_prefer = "gpt"' "pipeline.qa_prefer: unknown agent"
check_reg "check-registry: unknown agent in available_agents fails" '.pipeline.available_agents = ["gpt"]' "pipeline.available_agents: unknown agent gpt"

case_end recorded-implementer
fi

if has_case cleanup-merged; then
case_start
echo "-- cleanup after merge to main"
M="$TMP/merged-repo"; O="$TMP/merged-origin.git"; MW="$TMP/merged-topic"
git init -q --bare "$O"
git init -q -b main "$M"
echo base > "$M/base"; gi "$M" add base; gi "$M" commit -qm base
git -C "$M" remote add origin "$O"; git -C "$M" push -qu origin main
git -C "$M" worktree add -q -b feat/merged "$MW" main
echo merged > "$MW/change"; gi "$MW" add change; gi "$MW" commit -qm change
git -C "$M" branch feat/merged-task feat/merged
git -C "$M" branch feat/merged-other main
git -C "$M" worktree add -q "$TMP/other-wt" feat/merged-other
echo other > "$TMP/other-wt/other"; gi "$TMP/other-wt" add other; gi "$TMP/other-wt" commit -qm other
git -C "$M" worktree remove "$TMP/other-wt"
git -C "$M" push -q origin feat/merged feat/merged-task feat/merged-other
MP=$(plan merged "{\"schema\":\"rpg-factory.pipeline-plan/1\",\"id\":\"merged\",\"title\":\"t\",\"topic\":\"feat/merged\",\"repos\":{\"srv\":{\"path\":\"$M\",\"base\":\"main\"}},\"tasks\":[{\"id\":\"task\",\"repo\":\"srv\",\"objective\":\"o\",\"paths\":[\"change\"],\"acceptance\":[\"a\"]}]}")
refute "unmerged integration worktree stays" "worktree remove .*merged-topic" cleanup "$MP"
git -C "$M" merge -q --ff-only feat/merged; git -C "$M" push -q origin main
refute "without after-merge the integration worktree stays" "worktree remove .*merged-topic" cleanup "$MP"
refute "without after-merge remote branches stay" "push origin --delete" cleanup "$MP"
expect "merged integration worktree is removable" 1 "worktree remove .*merged-topic" cleanup "$MP" --after-merge
expect "merged integration branch is removable" 1 "branch -d feat/merged$" cleanup "$MP" --after-merge
expect "merged task branch is removable" 1 "branch -d feat/merged-task$" cleanup "$MP" --after-merge
expect "merged remote branch is removable" 1 "push origin --delete feat/merged-task$" cleanup "$MP" --after-merge
expect "merged remote integration branch is removable" 1 "push origin --delete feat/merged$" cleanup "$MP" --after-merge
expect "unmerged remote branch is kept" 1 "remote branch feat/merged-other is not in main" cleanup "$MP" --after-merge
refute "unmerged remote branch is never deleted" "push origin --delete feat/merged-other$" cleanup "$MP" --after-merge
refute "primary checkout is never removed" "worktree remove .*merged-repo$" cleanup "$MP" --after-merge
MWP=$(plan merged-wt "{\"schema\":\"rpg-factory.pipeline-plan/1\",\"id\":\"merged-wt\",\"title\":\"t\",\"topic\":\"feat/merged\",\"repos\":{\"srv\":{\"path\":\"$MW\",\"base\":\"main\"}},\"tasks\":[{\"id\":\"task\",\"repo\":\"srv\",\"objective\":\"o\",\"paths\":[\"change\"],\"acceptance\":[\"a\"]}]}")
expect "integration checkout removal runs from primary checkout" 1 "git -C .*merged-repo worktree remove .*merged-topic" cleanup "$MWP" --after-merge
echo dirty > "$MW/wip"
expect "dirty integration worktree is kept" 1 "KEPT  srv: worktree .*merged-topic has uncommitted changes" cleanup "$MP" --after-merge
refute "dirty integration worktree is not removed" "worktree remove .*merged-topic" cleanup "$MP" --after-merge
rm "$MW/wip"
git -C "$M" worktree remove "$MW"
git -C "$M" branch -d feat/merged-task feat/merged >/dev/null
git -C "$M" push -q origin --delete feat/merged
expect "merged remote task remains removable without topic refs" 1 "push origin --delete feat/merged-task$" cleanup "$MP" --after-merge
MISSING=$(plan missing "{\"schema\":\"rpg-factory.pipeline-plan/1\",\"id\":\"missing\",\"title\":\"t\",\"topic\":\"feat/merged\",\"repos\":{\"srv\":{\"path\":\"$MW\",\"base\":\"main\"}},\"tasks\":[{\"id\":\"task\",\"repo\":\"srv\",\"objective\":\"o\",\"paths\":[\"change\"],\"acceptance\":[\"a\"]}]}")
expect "missing integration checkout is LEFTOVER and names the main checkout remedy" 1 "KEPT  srv: repo path .*merged-topic is missing - point repos.srv.path at the main checkout" cleanup "$MISSING" --after-merge
git -C "$M" push -q origin --delete feat/merged-task feat/merged-other
git -C "$M" branch -D feat/merged-other >/dev/null
expect "cleanup is clean after removal" 0 "^Cleanup: CLEAN" cleanup "$MP" --after-merge
expect "clean cleanup names the next plan" 0 "^Next: start the next plan from main$" cleanup "$MP" --after-merge

case_end cleanup-merged
fi

if has_case model-routing; then
case_start
echo "-- model routing"
for case in $ROUTING_CASES; do bg_report "routing $case" "routing-$case"; done

case_end model-routing
fi

if has_case multiwave; then
case_start
echo "-- multi-wave currency and verdict provenance"
for case in $MULTIWAVE_CASES; do bg_report "multiwave $case" "multiwave-$case"; done

case_end multiwave
fi

if has_case gate-merge; then
case_start
echo "-- gate after a merge of the default branch"
# A merge of the default branch into the topic after the reviews keeps them current (the owned paths' content on the
# default branch is nobody's task work), a real later change to an owned path still makes them STALE, and the run lead's
# plan file and report.md are never stray.
GM="$TMP/gm-repo"; git init -q -b main "$GM"
mkdir -p "$GM/own"; echo v1 > "$GM/AGENTS.md"; echo a > "$GM/own/a.txt"; gi "$GM" add -A; gi "$GM" commit -qm base
gi "$GM" checkout -qb feat/gm
echo t > "$GM/own/t.txt"; gi "$GM" add -A; gi "$GM" commit -qm "feat: task"
GP=$(plan gm "{\"schema\":\"rpg-factory.pipeline-plan/1\",\"id\":\"gm\",\"title\":\"Gm\",\"topic\":\"feat/gm\",\"deliver\":\"pr\",\"repos\":{\"r\":{\"path\":\"$GM\",\"base\":\"main\"}},\"tasks\":[{\"id\":\"t\",\"repo\":\"r\",\"objective\":\"o\",\"paths\":[\"own/\",\"AGENTS.md\"],\"acceptance\":[\"a\"]}]}")
gmv() { python3 -B "$P" verdict "$GP" "$@" >/dev/null || echo "verdict failed: $*"; }
# gmqa: integration QA PASS on the current HEAD
gmqa() { gmv --task integration:r --phase qa --sha "$(git -C "$GM" rev-parse HEAD)" --by codex --state PASS; }
GM0=$(git -C "$GM" rev-parse HEAD)
gmv --task t --phase review --sha "$GM0" --by codex --state PASS; gmqa
expect "gate-merge: reviewed and QA'd: READY_FOR_PR" 0 "^Gate: READY_FOR_PR" gate "$GP" --no-run-checks
# the default branch changes an owned path (AGENTS.md) and the topic merges it
git -C "$GM" worktree add -q "$TMP/gm-main" main
echo v2 > "$TMP/gm-main/AGENTS.md"; gi "$TMP/gm-main" commit -qam "docs: agents v2"
gi "$GM" merge -q --no-ff main -m "Merge main into feat/gm"; gmqa
expect "gate-merge: a merge of the default branch after the review keeps it current" 0 "^Gate: READY_FOR_PR" gate "$GP" --no-run-checks
refute "gate-merge: no STALE after the default-branch merge" "STALE" gate "$GP" --no-run-checks
# a task branch that merged the default branch, itself merged into the topic (the main-sync shape)
echo v3 > "$TMP/gm-main/AGENTS.md"; gi "$TMP/gm-main" commit -qam "docs: agents v3"
gi "$GM" checkout -q -b feat/gm-sync; gi "$GM" merge -q --no-ff main -m "Merge main into feat/gm-sync"
gi "$GM" checkout -q feat/gm; gi "$GM" merge -q --no-ff feat/gm-sync -m "Merge task sync"; gmqa
expect "gate-merge: a task branch merge that brought the default branch keeps the review current" 0 "^Gate: READY_FOR_PR" gate "$GP" --no-run-checks
refute "gate-merge: nested default-branch merge is not STALE" "STALE" gate "$GP" --no-run-checks
# content equal to the reviewed commit: changed and changed back after the review
echo x >> "$GM/own/t.txt"; gi "$GM" commit -qam "fix: tweak"; git -C "$GM" checkout -q "$GM0" -- own/t.txt; gi "$GM" commit -qm "fix: revert tweak"; gmqa
expect "gate-merge: an owned path with the reviewed content is not STALE" 0 "^Gate: READY_FOR_PR" gate "$GP" --no-run-checks
# a real later change to an owned path
echo real >> "$GM/own/t.txt"; gi "$GM" commit -qam "fix: real change"; gmqa
expect "gate-merge: a real later change to an owned path makes the review STALE" 1 "BLOCKER t: review is STALE - owned paths changed after .*own/t.txt" gate "$GP" --no-run-checks
gmv --task t --phase review --sha "$(git -C "$GM" rev-parse HEAD)" --by codex --state PASS
expect "gate-merge: a new review clears it" 0 "^Gate: READY_FOR_PR" gate "$GP" --no-run-checks
# the run lead's plan file and report.md are never stray; any other unowned file still is
mkdir -p "$GM/docs/plans/gm"; cp "$GP" "$GM/docs/plans/gm.json"; echo r > "$GM/docs/plans/gm/report.md"
gi "$GM" add -A; gi "$GM" commit -qm "docs(plans): gm plan and report"; gmqa
expect "gate-merge: the plan file and its report.md are not stray" 0 "^Gate: READY_FOR_PR" gate "$GP" --no-run-checks
refute "gate-merge: no stray line for docs/plans" "changes outside every task's owned paths" gate "$GP" --no-run-checks
# the run lead's follow-ups in docs/plans/backlog.md (delivery.md section 8) are never stray either
echo b > "$GM/docs/plans/backlog.md"; gi "$GM" add -A; gi "$GM" commit -qm "docs(plans): backlog follow-ups"; gmqa
expect "gate-merge: the run lead's docs/plans/backlog.md is not stray" 0 "^Gate: READY_FOR_PR" gate "$GP" --no-run-checks
refute "gate-merge: no stray line for docs/plans/backlog.md" "changes outside every task's owned paths" gate "$GP" --no-run-checks
# a plan file inside the repo under another name: its own path, its sibling directory's report.md and the backlog.md
# next to it
mkdir -p "$GM/runlead/other"; cp "$GP" "$GM/runlead/other.json"; echo r > "$GM/runlead/other/report.md"
echo b > "$GM/runlead/backlog.md"
gi "$GM" add -A; gi "$GM" commit -qm "docs(plans): in-repo plan"; gmqa
GP2="$GM/runlead/other.json"; gmv() { python3 -B "$P" verdict "$GP2" "$@" >/dev/null || echo "verdict failed: $*"; }
gmv --task t --phase review --sha "$(git -C "$GM" rev-parse HEAD)" --by codex --state PASS; gmqa
refute "gate-merge: a plan file inside the repo is not stray" "changes outside every task's owned paths: .*runlead" gate "$GP2" --no-run-checks
echo o > "$GM/other.txt"; gi "$GM" add other.txt; gi "$GM" commit -qm "chore: stray"
expect "gate-merge: another unowned file is still stray" 1 "BLOCKER r: changes outside every task's owned paths: other.txt$" gate "$GP2" --no-run-checks
git -C "$GM" worktree remove --force "$TMP/gm-main"
# gm_fixture <dir> <branch> <default> <plan id> <repo key> <base>: a repo with own/t.txt reviewed and QA'd on the topic; sets GX, GXP
gm_fixture() {
  GX="$TMP/$1"; git init -q -b "$3" "$GX"; mkdir -p "$GX/own"; echo a > "$GX/own/t.txt"; gi "$GX" add -A; gi "$GX" commit -qm base
  gi "$GX" checkout -qb "$2"; echo t1 > "$GX/own/t.txt"; gi "$GX" commit -qam "feat: task"
  local base="$6"; [ "$base" = HEAD ] && base="$(git -C "$GX" rev-parse HEAD)"
  GXP=$(plan "$4" "{\"schema\":\"rpg-factory.pipeline-plan/1\",\"id\":\"$4\",\"title\":\"X\",\"topic\":\"$2\",\"deliver\":\"pr\",\"repos\":{\"$5\":{\"path\":\"$GX\",\"base\":\"$base\"}},\"tasks\":[{\"id\":\"t\",\"repo\":\"$5\",\"objective\":\"o\",\"paths\":[\"own/\"],\"acceptance\":[\"a\"]}]}")
  gxv "$GXP" --task t --phase review --sha "$(git -C "$GX" rev-parse HEAD)" --by codex --state PASS; gxqa "$GXP" "$5"
}
gxv() { local plan="$1"; shift; python3 -B "$P" verdict "$plan" "$@" >/dev/null || echo "verdict failed: $*"; }
gxqa() { gxv "$1" --task "integration:$2" --phase qa --sha "$(git -C "$GX" rev-parse HEAD)" --by codex --state PASS; }
# a default-branch merge whose own conflict resolution edits an owned path to new content is task-owned work: STALE
gm_fixture gm-conf feat/gc main gc r main
git -C "$GX" worktree add -q "$TMP/gm-conf-main" main; echo m > "$TMP/gm-conf-main/own/t.txt"; gi "$TMP/gm-conf-main" commit -qam "fix: main edits t"
gi "$GX" merge -q --no-ff main -m "Merge main into feat/gc" >/dev/null 2>&1; echo resolved > "$GX/own/t.txt"; gi "$GX" add own/t.txt; gi "$GX" commit -qm "Merge main into feat/gc"; gxqa "$GXP" r
expect "gate-merge: a default-branch merge whose conflict resolution edits an owned path is STALE" 1 "BLOCKER t: review is STALE - owned paths changed after .*own/t.txt" gate "$GXP" --no-run-checks
git -C "$GX" worktree remove --force "$TMP/gm-conf-main"
# a registry default branch other than main, with the plan base pinned to a SHA: the merge of develop keeps the review current
gm_fixture gm-dev feat/gd develop gd server HEAD
git -C "$GX" worktree add -q "$TMP/gm-dev-main" develop; mkdir -p "$TMP/gm-dev-main/own"; echo d > "$TMP/gm-dev-main/own/d.txt"
gi "$TMP/gm-dev-main" add -A; gi "$TMP/gm-dev-main" commit -qm "feat: develop adds own/d.txt"
gi "$GX" merge -q --no-ff develop -m "Merge develop into feat/gd"; gxqa "$GXP" server
expect "gate-merge: a merge of the registry default branch (plan base a SHA) keeps the review current (registered repo: checks not graded)" 1 "^Gate: UNVERIFIED" gate "$GXP" --no-run-checks
refute "gate-merge: no STALE after the develop merge with a SHA base" "STALE|BLOCKER" gate "$GXP" --no-run-checks
git -C "$GX" worktree remove --force "$TMP/gm-dev-main"
# a topic commit made after the review that later lands on the default branch through another PR stays task work: STALE
gm_fixture gm-late feat/gl main gl r main
echo late > "$GX/own/t.txt"; gi "$GX" commit -qam "fix: after review"
git -C "$GX" worktree add -q "$TMP/gm-late-main" main; gi "$TMP/gm-late-main" merge -q --no-ff feat/gl -m "Merge PR: feat/gl"
gi "$GX" merge -q --no-ff main -m "Merge main into feat/gl"; gxqa "$GXP" r
expect "gate-merge: a post-review topic commit that also landed on the default branch is STALE" 1 "BLOCKER t: review is STALE - owned paths changed after .*own/t.txt" gate "$GXP" --no-run-checks
git -C "$GX" worktree remove --force "$TMP/gm-late-main"
# The plan plugin-subagent-rules shape: task ta owns own/a.txt, ts (main-sync) depends on ta (or not) and also owns it, tl depends
# on ts and owns own/l.txt only. ta is reviewed on the topic; main edits own/a.txt; ts merges main inside its branch (a conflict
# resolution) and the topic merges ts; tl is cut from the topic before that merge, syncs the topic into itself and the topic merges tl.
# gn_build <name> <ts depends on ta: 1|0> <variant: ok|direct|evil|topic>; sets GX, GXP
gn_set() { sed -i "$2s/.*/$3/" "$GX/own/$1"; }
gn_build() {
  GX="$TMP/$1"; git init -q -b main "$GX"; mkdir -p "$GX/own"; seq 1 10 > "$GX/own/a.txt"; echo l > "$GX/own/l.txt"; gi "$GX" add -A; gi "$GX" commit -qm base
  local deps='"ta"'; [ "$2" = 0 ] && deps=''
  GXP=$(plan "$1" "{\"schema\":\"rpg-factory.pipeline-plan/1\",\"id\":\"$1\",\"title\":\"X\",\"topic\":\"feat/$1\",\"deliver\":\"pr\",\"repos\":{\"r\":{\"path\":\"$GX\",\"base\":\"main\"}},\"tasks\":[{\"id\":\"ta\",\"repo\":\"r\",\"objective\":\"o\",\"paths\":[\"own/a.txt\"],\"acceptance\":[\"a\"]},{\"id\":\"ts\",\"repo\":\"r\",\"objective\":\"o\",\"paths\":[\"own/a.txt\"],\"deps\":[$deps],\"acceptance\":[\"a\"]},{\"id\":\"tl\",\"repo\":\"r\",\"objective\":\"o\",\"paths\":[\"own/l.txt\"],\"deps\":[\"ts\"],\"acceptance\":[\"a\"]}]}")
  gi "$GX" checkout -qb "feat/$1"; gn_set a.txt 5 a1; gi "$GX" commit -qam "feat: ta"
  gxv "$GXP" --task ta --phase review --sha "$(git -C "$GX" rev-parse HEAD)" --by codex --state PASS
  gi "$GX" branch "feat/$1-ts"; gi "$GX" branch "feat/$1-tl"
  git -C "$GX" worktree add -q "$TMP/$1-main" main; echo m > "$TMP/$1-main/own/a.txt"; seq 2 10 >> "$TMP/$1-main/own/a.txt"; gi "$TMP/$1-main" commit -qam "fix: main edits a"
  gi "$GX" checkout -q "feat/$1-ts"; gn_set a.txt 1 s; gi "$GX" commit -qam "feat: ts"
  gi "$GX" merge -q --no-ff main -m "Merge main into ts" >/dev/null 2>&1; gn_set a.txt 1 resolved; gi "$GX" add own/a.txt; gi "$GX" commit -qm "Merge main into ts"
  gxv "$GXP" --task ts --phase review --sha "$(git -C "$GX" rev-parse HEAD)" --by codex --state PASS
  gi "$GX" checkout -q "feat/$1"; gi "$GX" merge -q --no-ff "feat/$1-ts" -m "Merge task ts"
  gi "$GX" checkout -q "feat/$1-tl"; echo l2 >> "$GX/own/l.txt"; gi "$GX" commit -qam "feat: tl"
  [ "$3" = direct ] && { gn_set a.txt 10 evil; gi "$GX" commit -qam "fix: tl edits a"; }
  gi "$GX" merge -q --no-ff --no-commit "feat/$1" >/dev/null; [ "$3" = evil ] && gn_set a.txt 8 evil; gi "$GX" add -A; gi "$GX" commit -qm "Merge topic into tl"
  gxv "$GXP" --task tl --phase review --sha "$(git -C "$GX" rev-parse HEAD)" --by codex --state PASS
  gi "$GX" checkout -q "feat/$1"; gi "$GX" merge -q --no-ff "feat/$1-tl" -m "Merge task tl"
  [ "$3" = topic ] && { gn_set a.txt 10 evil; gi "$GX" commit -qam "fix: topic edits a"; }
  gxqa "$GXP" r; git -C "$GX" worktree remove --force "$TMP/$1-main"
}
gn_build gn-ok 1 ok
refute "gate-merge: a default-branch merge nested in a task merge keeps the earlier task's review current" "ta: review is STALE" gate "$GXP" --no-run-checks
gn_build gn-nodep 0 ok
expect "gate-merge: a nested merge's conflict resolution is STALE for the earlier task without a covering review" 1 "BLOCKER ta: review is STALE - owned paths changed after .*own/a.txt" gate "$GXP" --no-run-checks
gn_build gn-direct 1 direct
expect "gate-merge: a direct edit in a task branch outside the merge keeps the earlier review STALE" 1 "BLOCKER ta: review is STALE - owned paths changed after .*own/a.txt" gate "$GXP" --no-run-checks
gn_build gn-evil 1 evil
expect "gate-merge: an edit inside a task branch's sync merge commit keeps the earlier review STALE" 1 "BLOCKER ta: review is STALE - owned paths changed after .*own/a.txt" gate "$GXP" --no-run-checks
gn_build gn-topic 1 topic
expect "gate-merge: a direct post-review topic edit keeps the earlier review STALE" 1 "BLOCKER ta: review is STALE - owned paths changed after .*own/a.txt" gate "$GXP" --no-run-checks

case_end gate-merge
fi

if has_case qa-tiers; then
case_start
echo "-- QA tiers"
bg_report "QA tiers regression matrix" qa-tiers
case_end qa-tiers
fi

if has_case tier-xs; then
case_start
echo "-- tier XS"
bg_report "tier XS: tier prints XS only for prose-only changes within the thresholds" tier-xs-tier
bg_report "tier XS: validate accepts a one-task prose plan; non-prose, multi-task, oversize, contract and generated are errors" tier-xs-validate
bg_report "tier XS: dispatch lead prints the run lead's steps, no implement session, review reads the topic checkout" tier-xs-dispatch
bg_report "tier XS: gate READY_FOR_PR with review PASS and lead QA; an oversize, non-prose, contract or generated diff blocks" tier-xs-gate
bg_report "tier XS: status shows the run lead's review dispatch and QA record, then the gate, as the gate sees it" tier-xs-status
case_end tier-xs
fi
[ "$reused" = 0 ] || echo "capture once: $reused assertion(s) reused the output of the identical command before them"
total=$((pass + fail)); echo "pipeline tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
