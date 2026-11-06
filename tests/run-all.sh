#!/usr/bin/env bash
# run-all.sh — every local validation for the plugin. Read-only against the workspace.
# Prints one line per check and a final count; exits non-zero if anything failed.
#
# Usage: tests/run-all.sh [-j N] [--no-workspace] [--no-claude] [--release] [--affected [--base REF]]
#   -j N, --jobs N  run up to N independent suites at once (default 1). Lines print in the -j 1 order with the
#                   same count and exit code. Read-only live-workspace checks (runl, block) run one at a time
#                   next to the fixture suites; run1 suites (shared git config guard, installed plugin, claude
#                   validate) run alone. Ends with the wall time.
#   --affected      run only the suites the change touches (tests/affected.py: files changed since
#                   merge-base(REF|origin/main|main) plus untracked); the cheap inline checks always run.
#                   For iteration; the full run (no --affected) is the gate before a PR and for --release.
#   --release       the installed plugin must equal the source (install-status CURRENT), the source
#                   must be committed, and tests/installed-safety.sh must pass against the installed hooks
#   --no-workspace  skip checks that need the RPG MMO workspace on disk
#   --no-claude     skip `claude plugin validate`
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/gitcfg-guard.sh"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
cd "$ROOT" || exit 1
gitcfg_snapshot "$ROOT"      # M4/P0: no test may rewrite the shared git config of the repo this runs in (checked at the end)
use_ws=true; use_claude=true; release=false; affected=false; base=""; jobs=1
while [ $# -gt 0 ]; do
  case "$1" in --no-workspace) use_ws=false ;; --no-claude) use_claude=false ;; --release) release=true ;;
    --affected) affected=true ;; --base) base="${2:-}"; shift ;;
    -j|--jobs) jobs="${2:-}"; shift ;; -j*) jobs="${1#-j}" ;; --jobs=*) jobs="${1#--jobs=}" ;; esac
  shift
done
case "$jobs" in ''|*[!0-9]*|0*) echo "run-all: -j/--jobs needs a positive integer, got '$jobs'" >&2; exit 2 ;; esac
t_start=$(date +%s)
AFF=""
if $affected && ! $release; then
  AFF=$(mktemp_win)/changed.txt
  if python3 -B tests/affected.py changed $base > "$AFF"; then echo "affected mode: $(wc -l < "$AFF" | tr -d ' ') changed file(s)"
  else echo "affected mode: no base, running everything"; AFF=""; fi
fi

pass=0; fail=0; skip=0; naff=0; cleanup=()
_ok()   { pass=$((pass + 1)); echo "PASS  $1"; }
_bad()  { fail=$((fail + 1)); echo "FAIL  $1"; [ -n "${2:-}" ] && echo "$2" | sed 's/^/      /'; }
_skp()  { skip=$((skip + 1)); echo "SKIP  $1 ($2)"; }
_note() { echo "$1"; }
# Suites read /dev/null, never the caller's stdin. -j 1: every line prints when its check ends. -j N: suites are
# queued and started in the background (at most N at a time: live-lane suites first, one at a time, one slot for the
# earliest queued suite, then the SLOW ones, then the rest in order; output buffered in $QD). Every line - suite results and inline checks alike - waits
# in the queue until the lines before it are out, so the output order, the count and the exit code are those of -j 1.
QD=""; qn=0; qnext=0; nrun=0; nlive=0; nord=0; QK=(); QM=(); QX=(); QC=(); QS=(); QL=(); QA=(); PEND=()
# the longest suites (Windows, -j 1), started early so none of them is the tail of the parallel phase
SLOW="tests/parallel-policy.test.sh tests/git-guard.test.sh tests/run-checks.test.sh tests/routing-golden.test.sh
      tests/check-registry.test.sh tests/checks-candidate.test.sh tests/factory-status.test.sh tests/new-skill.test.sh
      tests/devtools.test.sh tests/domains.test.sh testlab/tests/test_lab.py"
[ "$jobs" -gt 1 ] && QD=$(mktemp_win) && trap 'kill $(jobs -p) 2>/dev/null; rm -rf "$QD"' EXIT
queue() { # kind message [detail]
  if [ -z "$QD" ]; then "_$1" "$2" "${3:-}"; return; fi
  QK[qn]=$1; QM[qn]=$2; QX[qn]=${3:-}; qn=$((qn + 1)); flush
}
ok()   { queue ok "$@"; }
bad()  { queue bad "$@"; }
skp()  { queue skp "$@"; }
note() { queue note "$1"; }
flush() { # print the queue up to the first suite still running
  local i st secs
  while [ "$qnext" -lt "$qn" ]; do
    i=$qnext
    if [ "${QK[i]}" = job ]; then
      [ -f "$QD/$i.res" ] || return 0
      read -r st secs < "$QD/$i.res"
      if [ -n "${QX[i]}" ]; then "${QX[i]}" "$st" "$(cat "$QD/$i.out")" "${QM[i]}"
      elif [ "$st" = 0 ]; then _ok "${QM[i]} [${secs}s]"; else _bad "${QM[i]} [${secs}s]" "$(cat "$QD/$i.out")"; fi
      rm -f "$QD/$i.res" "$QD/$i.out"
    else "_${QK[i]}" "${QM[i]}" "${QX[i]}"; fi
    unset 'QK[i]' 'QM[i]' 'QX[i]' 'QC[i]' 'QS[i]' 'QL[i]' 'QA[i]'; qnext=$((i + 1))
  done
}
running() { # sets nrun (started, not ended), nlive (of them in the live lane), nord (started as the in-order one)
  local i; nrun=0; nlive=0; nord=0
  for ((i = qnext; i < qn; i++)); do
    [ -n "${QL[i]:-}" ] && [ ! -f "$QD/$i.res" ] && { nrun=$((nrun + 1)); [ -n "${QA[i]:-}" ] && nlive=$((nlive + 1))
      [ "${QL[i]}" = o ] && nord=$((nord + 1)); }
  done
}
start() { # queue index [o: the in-order pick]
  QL[$1]=${2:-1}
  ( t0=$(date +%s); eval "${QC[$1]}" > "$QD/$1.out" 2>&1 < /dev/null; rc=$?; t1=$(date +%s)
    echo "$rc $((t1 - t0))" > "$QD/$1.tmp" && mv "$QD/$1.tmp" "$QD/$1.res" ) &
}
pump() { # start queued suites while fewer than $jobs run: a live-lane one when none runs, the earliest queued one when
  # none of those runs (keeps the output moving), else SLOW first, else in order
  local i k pick kind
  while [ ${#PEND[@]} -gt 0 ]; do
    running; [ "$nrun" -lt "$jobs" ] || return 0
    pick=""; kind=""
    [ "$nlive" -eq 0 ] && for i in "${!PEND[@]}"; do [ -n "${QA[${PEND[i]}]}" ] && { pick=$i; break; }; done
    [ -n "$pick" ] || [ "$nord" -gt 0 ] || for i in "${!PEND[@]}"; do [ -z "${QA[${PEND[i]}]}" ] && { pick=$i; kind=o; break; }; done
    [ -n "$pick" ] || for k in $SLOW; do for i in "${!PEND[@]}"; do [ "${QS[${PEND[i]}]}" = "$k" ] && { pick=$i; break 2; }; done; done
    [ -n "$pick" ] || for i in "${!PEND[@]}"; do [ -z "${QA[${PEND[i]}]}" ] && { pick=$i; break; }; done
    [ -n "$pick" ] || return 0   # only live-lane suites left and one is running
    start "${PEND[pick]}" "$kind"; unset 'PEND[pick]'
  done
}
drain() { [ -n "$QD" ] || return 0; while pump; flush; [ "$qnext" -lt "$qn" ]; do sleep 0.2; done; }
# suite_of <args>: sets $s to the test or script file a run line executes (the unit tests/affected.py selects on)
suite_of() { local a; s=""; for a in "$@"; do case "$a" in tests/*|testlab/*|scripts/*) s=$a; return ;; esac; done; }
# run <name> <cmd...>: a suite; with -j N it runs in the background.
# runl <name> <cmd...>: a read-only suite against the live workspace: in the background, but never two at once.
# run1 <name> <cmd...>: a suite that must run alone (shared git config, installed plugin, `claude plugin validate`):
#   every queued suite ends first.
# runp <name> <post> <cmd...>: like run, but <post> <rc> <output> grades the result (with _ok/_bad/_skp).
# block <fn>: inline checks in function <fn> as one live-lane suite; its PASS/FAIL/SKIP lines are counted (replay).
run()  { _run bg "" "" "$@"; }
runl() { _run bg "" live "$@"; }
runp() { local name="$1" post="$2"; shift 2; _run bg "$post" "" "$name" "$@"; }
run1() { drain; _run fg "" "" "$@"; }
block() { if [ -z "$QD" ]; then "$1"; else _run bg replay live "$1" in_block "$1"; fi; }
in_block() { ( QD=""; "$1"; echo "<end of block>" ); }   # inside the job: the checks print at once
replay() { # rc output name: the lines a block printed, counted by their prefix
  local l done=""
  while IFS= read -r l; do
    case "$l" in "PASS  "*) pass=$((pass + 1)) ;; "FAIL  "*) fail=$((fail + 1)) ;; "SKIP  "*) skip=$((skip + 1)) ;;
      "<end of block>") done=1; continue ;; esac
    printf '%s\n' "$l"
  done <<<"$2"
  [ -n "$done" ] || _bad "checks block $3 ended early (rc=$1)"
}
_run() {
  local mode="$1" post="$2" lane="$3" name="$4"; shift 4; local out s t0 t1 n rc
  suite_of "$@"
  if [ -n "$AFF" ] && [ -n "$s" ] && ! python3 -B tests/affected.py select "$AFF" "$s"; then skip=$((skip + 1)); naff=$((naff + 1)); return; fi
  if [ -z "$QD" ] || [ "$mode" = fg ]; then
    if [ -n "$post" ]; then out=$("$@" 2>&1 < /dev/null); rc=$?; "$post" "$rc" "$out"; return; fi
    t0=$(date +%s)
    if out=$("$@" 2>&1 < /dev/null); then t1=$(date +%s); ok "$name [$((t1 - t0))s]"; else t1=$(date +%s); bad "$name [$((t1 - t0))s]" "$out"; fi
    return
  fi
  n=$qn; printf -v "QC[$n]" '%q ' "$@"; QK[n]=job; QM[n]=$name; QX[n]=$post; QS[n]=$s; QA[n]=$lane; PEND+=("$n"); qn=$((qn + 1))
  pump; flush
}
# sourced (tests/run-all-parallel.test.sh): the scheduler above only, no checks
[ "${BASH_SOURCE[0]}" != "$0" ] && return 0

# ---- syntax
json_count=0
while IFS= read -r f; do json_count=$((json_count + 1)); run "json: $f" jq empty "$f"; done \
  < <(find . -name '*.json' -not -path './.git/*' | sort)
[ "$json_count" -ge 4 ] && ok "json files found: $json_count" || bad "json files found: $json_count (expected >= 4)"
for f in scripts/*.sh scripts/checks/*.sh tests/*.sh; do run "bash -n: $f" bash -n "$f"; done
for f in scripts/*.py scripts/checks/*.py scripts/lib/*.py scripts/lib/guard/*.py testlab/*.py testlab/lab/*.py testlab/tests/*.py; do run "py_compile: $f" python3 -B -W error::SyntaxWarning -c "import ast,sys; ast.parse(open(sys.argv[1], encoding='utf-8').read(), sys.argv[1])" "$f"; done
run "jq compile: scripts/lib/resolve.jq" \
  jq -e --arg repo server --argjson files '[]' --argjson subst '{}' --argjson tools '{}' -f scripts/lib/resolve.jq registry.json
find scripts tests -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null

# ---- executable bits (as recorded in git when available, else filesystem)
for f in scripts/factory-context.sh scripts/check-registry.sh scripts/git-guard.py scripts/checks/*.py scripts/checks/*.sh \
         tests/*.sh; do
  mode=$(git ls-files -s "$f" 2>/dev/null | awk '{print $1}')
  if [ "$mode" = "100755" ] || { [ -z "$mode" ] && [ -x "$f" ]; }; then ok "executable: $f"
  else bad "executable: $f" "git mode=${mode:-untracked}"; fi
done

# ---- manifest consistency
name=$(jq -r .name .claude-plugin/plugin.json)
mname=$(jq -r '.plugins[0].name' .claude-plugin/marketplace.json)
msrc=$(jq -r '.plugins[0].source' .claude-plugin/marketplace.json)
[ "$name" = "rpg-factory" ] && [ "$mname" = "$name" ] && [ "$msrc" = "./" ] \
  && ok "manifest: plugin.json name == marketplace entry, source ./" \
  || bad "manifest consistency" "plugin=$name marketplace=$mname source=$msrc"
ver=$(jq -r .version .claude-plugin/plugin.json); mver=$(jq -r '.plugins[0].version // empty' .claude-plugin/marketplace.json)
fver=$(tr -d '[:space:]' < VERSION 2>/dev/null)
rver=$(sed -n 's/^Version \([0-9][0-9.]*\) (see `VERSION`).*/\1/p' README.md)
# Codex packaging, when present: .codex-plugin/plugin.json must carry the version; the Codex marketplace only if it has one
cver=$ver; [ -f .codex-plugin/plugin.json ] && cver=$(jq -r '.version // "none"' .codex-plugin/plugin.json 2>/dev/null || echo invalid)
cmver=""; [ -f .agents/plugins/marketplace.json ] && cmver=$(jq -r '[.version?, (.plugins[]? | select(.name == "rpg-factory") | .version?)]
  | map(select(. != null)) | unique | join(",")' .agents/plugins/marketplace.json 2>/dev/null || echo invalid)
{ [ "$ver" = "$fver" ] && [ -z "$mver" -o "$mver" = "$ver" ] && grep -q "^## \[$ver\]" CHANGELOG.md && [ "$rver" = "$ver" ] \
  && [ "$cver" = "$ver" ] && [ -z "$cmver" -o "$cmver" = "$ver" ]; } \
  && ok "version: VERSION == plugin.json == marketplace == CHANGELOG section == README == Codex manifest/marketplace when present ($ver)" \
  || bad "version consistency" "VERSION=$fver plugin=$ver marketplace=$mver README=${rver:-none} codex=$cver codex-marketplace=${cmver:-none} changelog section missing?"
# release policy wording: tags and releases are the lead's by default and the agent's only with explicit release
# authorization in the current task - no authoritative text may state the absolute "agents never tag" rule again
policy_files=(.claude/CLAUDE.md README.md registry.json skills/factory-core/SKILL.md skills/factory-core/references/git-safety.md
              skills/factory-core/references/skill-contract.md skills/unity-package/SKILL.md scripts/git-guard.py scripts/lib/gitguard.py scripts/lib/guard/*.py
              scripts/lib/context.py scripts/lib/procrun.py scripts/lib/snapshot_render.py
              .claude-plugin/plugin.json .claude-plugin/marketplace.json)
absolute=$(grep -nE -i "agents never tag|never create the tag|tags are never (done|created) by agents|never tag, never publish|; never tag\b" "${policy_files[@]}" 2>/dev/null)
missing=$(for f in .claude/CLAUDE.md README.md registry.json skills/factory-core/references/git-safety.md skills/factory-core/references/skill-contract.md skills/unity-package/SKILL.md; do
  grep -qiE "explicit(ly)? (release authorization|authoriz)" "$f" || echo "$f"; done)
[ -z "$absolute$missing" ] && ok "release policy: default READY_TO_TAG, tag/release only with explicit authorization (${#policy_files[@]} files)" \
  || bad "release policy wording" "absolute 'never tag' text: ${absolute:-none}; no authorization rule in: ${missing:-none}"
# since 1.0.3 the hooks are advisory only: agent-facing text must not claim they deny, block or enforce
advisory_files=(.claude/CLAUDE.md README.md scripts/lib/context.py scripts/lib/snapshot_render.py scripts/factory-context.sh commands/*.md skills/*/SKILL.md skills/*/references/*.md)
blocking=$(grep -nE -i "denied by the guard|hooks enforce|\(deny\)|enforced by (both|the) (guards?|hooks)" "${advisory_files[@]}" 2>/dev/null)
[ -z "$blocking" ] && ok "advisory wording: no 'denied by the guard' / 'hooks enforce' / '(deny)' in agent-facing text (${#advisory_files[@]} files)" \
  || bad "advisory wording (hooks never block since 1.0.3)" "$blocking"
[ -f "skills/factory-core/SKILL.md" ] && head -5 skills/factory-core/SKILL.md | grep -q '^name: factory-core$' \
  && ok "skill: factory-core frontmatter name" || bad "skill: factory-core frontmatter name"
for ref in $(grep -o 'references/[a-z-]*\.md' skills/factory-core/SKILL.md | sort -u); do
  [ -f "skills/factory-core/$ref" ] && ok "skill reference exists: $ref" || bad "skill reference missing: $ref"
done
jq -e '(.hooks.PreToolUse[0].matcher == "Bash|PowerShell")
        and ([.hooks.PreToolUse[0].hooks[].command] | any(test("git-guard.py")))
        and ([.hooks.PreToolUse[] | select(.matcher == "Skill") | .hooks[].command] | any(test("factory_session.py\" --skill")))
        and ([.hooks.SessionStart[0].hooks[].command] | any(test("install-status.py\" --session")))
        and ([.. | .command? // empty] | all(test("tripwire") | not))
        and ([.. | .command? // empty] | length >= 4 and all(endswith("; exit 0")))' hooks/hooks.json >/dev/null \
  && ok "hooks: guard on Bash|PowerShell, skill order on Skill, session install check, no tripwire, every command fail-safe (; exit 0)" || bad "hooks wiring"
# exit 2 is Claude Code's blocking code (python exits 2 on a missing script): a missing or crashing hook script
# must exit 0 and its stdout must still reach Claude Code
HT=$(mktemp_win); mkdir -p "$HT/missing/scripts" "$HT/broken/scripts"
for f in $(jq -r '[.. | .command? // empty | capture("scripts/(?<f>[a-z_-]+\\.py)").f] | unique[]' hooks/hooks.json); do
  printf 'import sys\nprint("{\\"marker\\": \\"%s\\"}")\nsys.exit(2)\n' "$f" > "$HT/broken/scripts/$f"
done
hfail=""
while IFS= read -r h; do
  out=$(CLAUDE_PLUGIN_ROOT="$HT/missing" bash -c "$h" </dev/null 2>/dev/null); rc=$?
  [ $rc -eq 0 ] && [ -z "$out" ] || hfail+="missing script rc=$rc: $h"$'\n'
  out=$(CLAUDE_PLUGIN_ROOT="$HT/broken" bash -c "$h" </dev/null 2>/dev/null); rc=$?
  [ $rc -eq 0 ] && grep -q '"marker"' <<<"$out" || hfail+="exit-2 script rc=$rc stdout='$out': $h"$'\n'
done < <(jq -r '.. | .command? // empty' hooks/hooks.json)
rm -rf "$HT"
[ -z "$hfail" ] && ok "hooks: a missing or exit-2 script never blocks (exit 0, stdout passes through)" || bad "hooks fail-safe" "$hfail"

# ---- testlab (pure parts: scenarios, plan expansion, analysis checks; no stack, no Unity)
run "testlab: unit tests" python3 -B testlab/tests/test_lab.py
run "testlab: packet impairment (S18) unit tests" python3 -B testlab/tests/test_netem.py
run "testlab: native game server mode unit tests" python3 -B testlab/tests/test_native.py
run "testlab: failure-summary unit tests" python3 -B testlab/tests/test_failsum.py
run "testlab: harness defects H1-H7 (M4) unit tests" python3 -B testlab/tests/test_m4_harness.py
run "testlab: frame GC columns (UCF F-21) unit tests" python3 -B testlab/tests/test_framegc.py
run "testlab: scenarios load" python3 -B testlab/testlab.py list
find testlab -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null

# ---- registry
run "registry structure" scripts/check-registry.sh --structure-only
run "registry domain rules + optional repos" tests/check-registry.test.sh
if $use_ws; then runl "registry paths exist in workspace" scripts/check-registry.sh
else skp "registry paths exist in workspace" "--no-workspace"; fi

# ---- git guard, skill contract lint, routing (task + historical replay)
run "cross-platform helpers + UTF-8 output (Linux, WSL, Windows git-bash)" env -u TMPDIR tests/compat.test.sh
run "git-guard unit tests" tests/git-guard.test.sh
run "skills lint (contract)" tests/skills-lint.sh
run "English-only fixture cases" env -u TMPDIR tests/english-only.test.sh
run "English-only enforcement (report available)" python3 -B scripts/checks/english-only.py --enforce
run "session state + tripwire removed (state paths, stale latch files inert)" env -u TMPDIR tests/session-state.test.sh
run "file guard (Write/Edit/MultiEdit/NotebookEdit/Read)" env -u TMPDIR tests/file-guard.test.sh
run "hook cost (no git guard on Read, bytecode in the state dir, gitlinks cache, python3 alias)" env -u TMPDIR tests/hook-perf.test.sh
run "slash commands (files, parsing, invocation)" env -u TMPDIR tests/commands.test.sh
run "UI component catalog + selection (UIToolkit git fixture, refs, NOT_AVAILABLE)" env -u TMPDIR tests/ui-catalog.test.sh
run "UI plan commands (intent, skills per verb, NOT_UI, NEEDS_CONTEXT, Figma URL)" env -u TMPDIR tests/ui-commands.test.sh
run "UI plan routing, golden matrix, component selection (fixture workspace)" env -u TMPDIR tests/ui-skill-routing.test.sh
run "UI skills content, docs, snapshot Next line for UI paths (fixture workspace)" env -u TMPDIR tests/ui-skills.test.sh
run "dev tools + services (probes, snapshot, doctor, no secrets, registry checks)" env -u TMPDIR tests/devtools.test.sh
run "Figma connector environment check (fixture Unity projects, no network)" env -u TMPDIR tests/ui-figma-env.test.sh
run "worktree-aware context" tests/worktree.test.sh
run "check runner state model" tests/run-checks.test.sh
run "artifact contract, lifecycle, trace and approval fixtures" tests/artifacts.test.sh
run "run-checks targets the invoking worktree, writes no pyc, guards the canonical checkout" tests/worktree-target.test.sh
run "candidate tree checks" tests/checks-candidate.test.sh
run "factory-status rollout / resume fixture" tests/factory-status.test.sh
run "install-status stale-install detection" tests/install-status.test.sh
run "release-check gate (throwaway repo, local bare origin)" env -u TMPDIR tests/release-check.test.sh
run "delivery pipeline (tier, plan, dispatch, verdicts, gate)" env -u TMPDIR tests/pipeline.test.sh
run "run-all --affected suite selection" tests/affected.test.sh
run "run-all -j scheduler (order, counts, concurrency cap, live lane, run1 alone)" tests/run-all-parallel.test.sh
run "changelog fragments (changelog.d, scripts/changelog.py; [Unreleased] stays empty)" tests/changelog.test.sh
run "registry fragments (registry/ -> registry.json build, placement, merge)" tests/registry-fragments.test.sh
# Codex packaging (.codex-plugin, .agents/plugins, hooks/codex-hooks.json, scripts/codex_hook.py)
codex_post() { # rc output
  local cxsum cxpass; cxsum=$(tail -1 <<<"$2"); cxpass=$(sed -n 's/.*, \([0-9]*\) passed,.*/\1/p' <<<"$cxsum")
  if [ "$1" -ne 0 ]; then _bad "Codex plugin: manifest, marketplace, hook config, adapter" "$2"
  elif [ "${cxpass:-0}" -eq 0 ]; then _skp "Codex plugin: manifest, marketplace, hook config, adapter" "${cxsum#codex-plugin tests: }: Codex packaging files absent"
  else _ok "Codex plugin: manifest, marketplace, hook config, adapter (${cxsum#codex-plugin tests: })"; fi
}
runp "Codex plugin" codex_post env -u TMPDIR tests/codex-plugin.test.sh
run "skill citation checker (fixture repos)" env -u TMPDIR tests/skill-citations.test.sh
run "engineering routing contract unchanged (golden, stand-in workspace)" env -u TMPDIR tests/routing-golden.test.sh
run "repos without a remote do not crash status or the git guard" env -u TMPDIR tests/registry-nulls.test.sh
  run "domain and artifact-kind routing (stand-in workspace)" env -u TMPDIR tests/domains-routing.test.sh
  run "Game Design domain: routing, feature-state ownership, standalone (no game-ai-workflows)" env -u TMPDIR tests/domains.test.sh
run "Game Design production workflow" tests/design-workflow.test.sh
run "dogfood write grader (offline, recorded transcripts)" tests/dogfood-grader.test.sh
run "UI/UX production workflow" tests/ui-workflow.test.sh
run "2D Art production workflow" tests/art2d-workflow.test.sh
run "3D Art production workflow" tests/art3d-workflow.test.sh
run "VFX production workflow" tests/vfx-workflow.test.sh
run "netcode-headless server resolution (fixture repos)" env -u TMPDIR tests/netcode-headless.test.sh
run "skill scaffolder + touchpoints (throwaway plugin copy)" env -u TMPDIR tests/new-skill.test.sh
run "parallel-work policy lint bites (throwaway plugin copy)" env -u TMPDIR tests/parallel-policy.test.sh
if ! $use_ws; then skp "orca commands cited in parallel-work.md" "--no-workspace"
elif ! command -v orca >/dev/null 2>&1; then skp "orca commands cited in parallel-work.md" "orca not on PATH"
else run "orca commands cited in parallel-work.md exist in orca --help" tests/orca-commands.test.sh; fi
# ---- live workspace (read-only): runl / block - with -j N in the background next to the fixture suites, one at a time
if $use_ws; then runl "routing properties over real history" python3 -B tests/routing-properties.test.py
else skp "routing properties over real history" "--no-workspace"; fi
if $use_ws; then runl "registry facts re-probed in the repos" tests/facts.test.sh
else skp "registry facts re-probed in the repos" "--no-workspace"; fi
live_citations() {  # MOVED (anchor unique elsewhere) is a warning here and a failure under --release
  local cit citrc l
  if $release; then run "skill line citations point at their symbols (integration branches, --strict)" python3 -B scripts/checks/skill-citations.py --strict
  else
    cit=$(python3 -B scripts/checks/skill-citations.py 2>&1); citrc=$?
    if [ $citrc -ne 0 ]; then bad "skill line citations point at their symbols (integration branches)" "$cit"
    else ok "skill line citations point at their symbols (integration branches)"
      while IFS= read -r l; do note "WARN  moved citation: ${l#MOVED }"; done < <(grep '^MOVED ' <<<"$cit")
      grep -q '^MOVED ' <<<"$cit" && note "WARN  rewrite moved citations: python3 -B scripts/checks/skill-citations.py --fix (fails under --release)"
    fi
  fi
}
if $use_ws; then block live_citations
else skp "skill line citations against the repos" "--no-workspace"; fi
if $use_ws; then runl "routing + history replay" tests/routing.test.sh
else
  # task scenarios resolve --paths only, but factory-context still needs the workspace markers and a git
  # work tree per registry repo: a throwaway stand-in (empty repos), never the real workspace
  SW=$(mktemp_win)
  while IFS= read -r p; do
    git init -q "$SW/$p" && git -C "$SW/$p" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
  done < <(jq -r '.repos[].path' registry.json)
  while IFS= read -r m; do mkdir -p "$SW/$(dirname "$m")"; touch "$SW/$m"; done < <(jq -r '.workspace.root_markers[]' registry.json)
  run "routing (task scenarios only, stand-in workspace)" env RPG_FACTORY_WORKSPACE="$SW" tests/routing.test.sh --no-history
  cleanup+=("$SW")  # removed after the last suite ended (with -j N this one may still be running)
fi

# ---- resolver behaviour (pure jq, no workspace needed)
resolve() { # repo files-json
  jq -c --arg repo "$1" --argjson files "$2" --argjson subst '{"{dotnet}":"dotnet.exe","{plugin_root}":"/p"}' \
    --argjson tools '{"go":"/usr/bin/go","dotnet":"/x/dotnet.exe","python3":"/usr/bin/python3","protoc":"/usr/bin/protoc","protoc-gen-go":"/x","jq":"/usr/bin/jq","docker":null}' \
    -f scripts/lib/resolve.jq registry.json
}
expect() { # name jq-predicate json
  if jq -e "$2" <<<"$3" >/dev/null 2>&1; then ok "resolve: $1"; else bad "resolve: $1" "$(jq -c '{touched,dependents,unmapped}' <<<"$3")"; fi
}
r=$(resolve server '[{"path":"backend/shared/proto/wire.proto","status":"--","source":"given"}]')
expect "wire.proto -> server.proto (longest prefix)" '.touched == ["server.proto"]' "$r"
expect "wire.proto dependents include C# server + integration" '(.dependents | index("server.gameserver-dotnet")) and (.dependents | index("server.integration-test"))' "$r"
expect "proto triggers proto-regen extended check" 'any(.checks[]; .id == "proto-regen" and .tier == "extended")' "$r"
r=$(resolve server '[{"path":"backend/gateway/internal/redirect.go","status":" M","source":"worktree"}]')
expect "gateway fast checks = vet+test+build" '[.checks[] | select(.tier=="fast" and .module=="server.gateway") | .id] == ["go-vet","go-test","go-build"]' "$r"
expect "gateway dependents = integration only" '.dependents == ["server.integration-test"]' "$r"
r=$(resolve server '[{"path":"backend/gameserver-dotnet/GameServer/Program.cs","status":" M","source":"worktree"}]')
expect "{dotnet} substituted" 'any(.checks[]; .run == "dotnet.exe build -c Release")' "$r"
r=$(resolve server '[{"path":"backend/gameserver-dotnet/GameServer/Net/Generated/Wire.cs","status":" M","source":"worktree"}]')
expect "generated path flagged" '.generated_hits | length == 1' "$r"
r=$(resolve client '[{"path":"Assets/Samples/Netcode/DOTS Sample/Scripts/A.cs","status":" M","source":"worktree"},{"path":"Assets/Samples/Cuvara UI Toolkit/","status":"??","source":"worktree"},{"path":"Packages/com.gdk.core","status":" M","source":"worktree"},{"path":"weird/file.txt","status":"??","source":"worktree"}]')
expect "DOTS Sample beats Assets/Samples" '.files[0].module == "client.dots-sample"' "$r"
expect "untracked sample dir -> samples-imported" '.files[1].module == "client.samples-imported"' "$r"
expect "submodule pointer -> gdk-submodules" '.files[2].module == "client.gdk-submodules"' "$r"
expect "unknown path -> repo-level (client.root), not unmapped" '.unmapped == [] and .repo_level == ["weird/file.txt"]' "$r"
expect "{plugin_root} substituted in package-pins" 'any(.checks[]; .run == "python3 -B /p/scripts/checks/unity-package-pins.py .")' "$r"
r=$(resolve server '[]')
expect "no files -> no checks" '.checks == [] and .touched == []' "$r"

# ---- live context script (read-only against the real workspace)
live_context() {
  local out out2 md
  # every registered repo is snapshotted, except optional repos that are absent on disk, which are reported
  if out=$(scripts/factory-context.sh --json 2>&1) && jq -e --slurpfile reg registry.json '
      ([.repos[].repo] + (.optional_repos_absent // [])) as $seen
      | ($seen | sort) == ($reg[0].repos | keys | sort)
        and all((.optional_repos_absent // [])[]; $reg[0].repos[.].optional == true)' <<<"$out" >/dev/null; then
    ok "factory-context --json: every registered repo (absent optional repos reported)"
    jq -e 'all(.repos[]; .error == null and (.branch | length) > 0)' <<<"$out" >/dev/null \
      && ok "factory-context: branch resolved for each repo" || bad "factory-context: branch per repo" "$out"
    out2=$(scripts/factory-context.sh --repo server --json --paths backend/gameserver-dotnet/GameServer/Program.cs 2>&1)
    jq -e 'any(.toolchain[]; .tool == "dotnet" and .resolved != null)' <<<"$out2" >/dev/null \
      && ok "factory-context: dotnet resolved lazily for a .NET change ($(jq -r '.toolchain[] | select(.tool=="dotnet") | .resolved' <<<"$out2"))" \
      || bad "factory-context: dotnet not resolved (dotnet / dotnet.exe)"
  else
    bad "factory-context --json" "$out"
  fi
  out=$(scripts/factory-context.sh --repo server --json --paths backend/gateway/x.go 2>&1)
  jq -e '.repos[0].touched == ["server.gateway"] and (.repos[0].files | length == 1)' <<<"$out" >/dev/null \
    && ok "factory-context --paths ignores working tree" || bad "factory-context --paths" "$out"
  scripts/factory-context.sh --paths x >/dev/null 2>&1; [ $? -eq 2 ] \
    && ok "factory-context --paths without --repo is rejected" || bad "factory-context --paths without --repo"
  md=$(scripts/factory-context.sh --repo client 2>&1)
  grep -q "^## client:" <<<"$md" && ok "factory-context markdown renders" || bad "factory-context markdown" "$md"
}
if $use_ws; then block live_context
else skp "factory-context live checks" "--no-workspace"; fi

# ---- sgl-determinism (ADR-10) against fixtures: banned calls fail, comments/strings/allowed MathF pass
dt=$(mktemp_win)
printf '%s\n' 'class A {' '  float F(float x) => MathF.Sqrt(x) + MathF.Abs(x); // MathF.Sin(x) in a comment' \
  '  string S = "Math.Pow(1, 2)";' '}' > "$dt/Ok.cs"
out=$(python3 -B scripts/checks/sgl-determinism.py "$dt" 2>&1); rc=$?
[ $rc -eq 0 ] && grep -q "^OK: sgl-determinism files=1 banned=0" <<<"$out" \
  && ok "sgl-determinism: allowed MathF, comments and strings pass" || bad "sgl-determinism allowed fixture" "$out"
printf '%s\n' 'class B {' '  float G(float x) => MathF.Atan2(x, 1f);' '  double H(double y) => System.Math.Pow(y, 2);' '}' > "$dt/Bad.cs"
out=$(python3 -B scripts/checks/sgl-determinism.py "$dt" 2>&1); rc=$?
[ $rc -eq 1 ] && grep -q "Bad.cs:2: MathF.Atan2" <<<"$out" && grep -q "Bad.cs:3: Math.Pow" <<<"$out" \
  && ok "sgl-determinism: banned calls fail with path:line" || bad "sgl-determinism banned fixture" "$out"
rm -f "$dt"/*.cs
python3 -B scripts/checks/sgl-determinism.py "$dt" >/dev/null 2>&1; [ $? -eq 2 ] \
  && ok "sgl-determinism: empty directory is an error, not a pass" || bad "sgl-determinism empty dir"
rm -rf "$dt"

# ---- Factory check scripts against the live workspace (read-only)
live_checks() {
  local wsr cl pin_files out hout ph r p rc
  run "sgl-determinism on Shared.GameLogic" python3 -B scripts/checks/sgl-determinism.py \
    "${RPG_FACTORY_WORKSPACE:-/mnt/c/Workspaces/UnityIndie}/rpg-mmo-server/backend/gameserver-dotnet/Shared.GameLogic"
  # pin-status reads the client's working tree. When the user has uncommitted pin files (the local file:
  # toggle is a human gate and their state), a live FAIL says nothing about this plugin: then verify the
  # committed HEAD through a read-only export and report SKIP with the reason - never PASS.
  wsr="${RPG_FACTORY_WORKSPACE:-/mnt/c/Workspaces/UnityIndie}"; cl="$wsr/IndieRPGMMOAdventure"
  pin_files=(Packages/manifest.json Packages/packages-lock.json "Assets/Samples/Netcode/DOTS Sample/.sample-source")
  if out=$(python3 -B scripts/checks/pin-status.py 2>&1); then ok "pin-status (client pins vs upstream tags)"
  elif [ -n "$(git -C "$cl" status --porcelain -- "${pin_files[@]}" 2>/dev/null)" ]; then
    ph=$(mktemp_win); mkdir -p "$ph/ws/IndieRPGMMOAdventure"
    git -C "$cl" archive HEAD -- "${pin_files[@]}" | tar -x -C "$ph/ws/IndieRPGMMOAdventure"
    for r in Netcode UnityDots UIToolkit rpg-mmo-server; do
      [ -d "$wsr/$r/.git" ] && git clone -q --shared --no-checkout "$wsr/$r" "$ph/ws/$r"; done
    if hout=$(python3 -B scripts/checks/pin-status.py --workspace "$ph/ws" 2>&1); then
      skp "pin-status on the live tree" "client pin files have uncommitted user changes; committed HEAD: $(tail -1 <<<"$hout")"
    else bad "pin-status (committed HEAD, live tree also has user changes)" "$hout"; fi
    rm -rf "$ph"
  else bad "pin-status (client pins vs upstream tags)" "$out"; fi
  run "wire-parity (Wire.cs bytes + protocol version)" bash scripts/checks/wire-parity.sh
  out=$(python3 -B scripts/checks/pin-plan.py com.cuvara.netcode v0.45.0 --client-ref 17b7737^ 2>&1)
  grep -q "hash=2eb6ddbc4e0c62544fa860b3a4f7e64071918f0b" <<<"$out" && grep -q "DOTSNetworkBridge.cs" <<<"$out" \
    && ok "pin-plan replays 17b7737 (lock hash + DOTS Sample file)" || bad "pin-plan replay of 17b7737" "$out"
  out=$(python3 -B scripts/checks/pin-plan.py com.cuvara.dots v99.0.0 2>&1); rc=$?
  [ $rc -eq 1 ] && grep -q "BLOCKED: tag v99.0.0 not found" <<<"$out" && ok "pin-plan blocks on a missing tag" || bad "pin-plan missing-tag gate" "$out"
  for p in Netcode UnityDots UIToolkit; do
    out=$(python3 -B scripts/checks/package-ready.py "${RPG_FACTORY_WORKSPACE:-/mnt/c/Workspaces/UnityIndie}/$p" 2>&1); rc=$?
    { [ $rc -eq 0 ] && grep -q "READY to tag" <<<"$out"; } || { [ $rc -eq 1 ] && grep -q "NOT READY" <<<"$out"; } \
      && ok "package-ready $p -> $(grep -m1 -oE 'NOT READY|READY to tag v[0-9.]+' <<<"$out")" || bad "package-ready $p" "$out"
  done
  if command -v dotnet >/dev/null 2>&1 || command -v dotnet.exe >/dev/null 2>&1; then
    out=$(bash scripts/checks/netcode-headless.sh 2>&1); rc=$?
    [ $rc -eq 0 ] && ok "netcode headless tests: $(sed -n 's/^headless tests: //p' <<<"$out")" || bad "netcode headless tests" "$(tail -5 <<<"$out")"
  else skp "netcode headless tests" "no dotnet/dotnet.exe"; fi
}
$use_ws && block live_checks

# ---- live derived status + install state
if $use_ws; then
  runl "factory-status on the real workspace (read-only)" python3 -B scripts/factory-status.py
fi
ist=$(python3 -B scripts/install-status.py --json 2>/dev/null | jq -r .state)
if $release; then
  [ "$ist" = "CURRENT" ] && ok "installed plugin == source (release gate)" || bad "installed plugin == source (release gate)" "$(python3 -B scripts/install-status.py)"
  [ -z "$(git status --porcelain)" ] && ok "source is committed (release gate)" || bad "source is committed (release gate)" "uncommitted changes"
  run1 "safety through the installed hooks (disposable workspace)" env -u TMPDIR tests/installed-safety.sh
else
  skp "installed plugin == source" "install state $ist; required only with --release"
fi

# ---- package pins checker behaviour
T=$(mktemp_win); mkdir -p "$T/Packages"
echo '{"dependencies":{"a":"https://x/a.git#v1","b":"1.0.0"}}' > "$T/Packages/manifest.json"
echo '{"dependencies":{"a":{"version":"https://x/a.git#v1"}}}' > "$T/Packages/packages-lock.json"
python3 scripts/checks/unity-package-pins.py "$T" >/dev/null && ok "package-pins: agreeing pins pass" || bad "package-pins: agreeing pins pass"
echo '{"dependencies":{"a":{"version":"https://x/a.git#v0"}}}' > "$T/Packages/packages-lock.json"
python3 scripts/checks/unity-package-pins.py "$T" >/dev/null && bad "package-pins: mismatch must fail" || ok "package-pins: mismatch fails"
echo '{"dependencies":{"a":"file:/mnt/c/x"}}' > "$T/Packages/manifest.json"
python3 scripts/checks/unity-package-pins.py "$T" >/dev/null && bad "package-pins: file: must fail" || ok "package-pins: file: path fails"
echo '{"dependencies":{"b":"1.0.0"}}' > "$T/Packages/manifest.json"
python3 scripts/checks/unity-package-pins.py "$T" >/dev/null && bad "package-pins: empty selection must fail" || ok "package-pins: zero git deps fails"
rm -rf "$T"

# ---- package-ready: when git cannot read the tree, readiness is unknown (exit 2), never READY
T=$(mktemp_win)
printf '{"name":"com.cuvara.netcode","version":"9.9.9"}\n' > "$T/package.json"; printf '## [9.9.9] - 2026-01-01\n' > "$T/CHANGELOG.md"
out=$(GIT_CEILING_DIRECTORIES="$T" python3 -B scripts/checks/package-ready.py "$T" 2>&1); rc=$?
[ $rc -eq 2 ] && grep -q "readiness unknown" <<<"$out" && ! grep -q "READY to tag" <<<"$out" \
  && ok "package-ready: unreadable git tree is an error, not READY" || bad "package-ready on a non-repo (rc=$rc)" "$out"
rm -rf "$T"

# ---- alone (run1): the shared git config guard suite, then Claude Code's own validator
run1 "git environment isolation + shared-config guard (throwaway repos)" env -u TMPDIR tests/git-env-isolation.test.sh
if $use_claude && command -v claude >/dev/null 2>&1; then
  run1 "claude plugin validate --strict . (marketplace)" claude plugin validate --strict .
  run1 "claude plugin validate --strict .claude-plugin/plugin.json (plugin + skills)" claude plugin validate --strict .claude-plugin/plugin.json
else
  skp "claude plugin validate" "claude CLI unavailable or --no-claude"
fi

drain
[ -n "$QD" ] && rm -rf "$QD"
[ ${#cleanup[@]} -gt 0 ] && rm -rf "${cleanup[@]}"
find scripts tests testlab -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null

# ---- the shared git config (common dir) must be byte-identical to what it was when the run started
if [ -n "${GITCFG_FILE:-}" ]; then
  if out=$(gitcfg_verify); then ok "shared git config unchanged during the run"; else bad "shared git config changed during the run" "$out"; fi
else skp "shared git config unchanged during the run" "not inside a git repository"; fi

total=$((pass + fail + skip))
echo "----"
echo "wall time: $(( $(date +%s) - t_start ))s (-j $jobs)"
echo "run-all: $total checks, $pass passed, $fail failed, $skip skipped$( [ -n "$AFF" ] && echo " ($naff not affected by the change)")"
[ "$pass" -gt 0 ] && [ "$fail" -eq 0 ]
