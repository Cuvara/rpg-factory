#!/usr/bin/env bash
# The parallel-work policy checks in tests/skills-lint.sh bite: on a throwaway copy of this plugin the pristine
# copy passes the relevant production lint sections, and each mutation (lost link, copied policy text, blocking wording variants, gate-create, a
# dropped safety rule, a missing policy file) makes the copy's own lint FAIL with the expected message. The same
# harness proves the allowed-tools coverage lint bites (a script use the skill's allowed-tools does not grant).
# One minimal copy (the tracked and untracked files minus what neither the lint nor its tools read), one cheap copy
# of only the lint inputs per mutation, and the relevant lint sections run concurrently (PARALLEL_POLICY_JOBS, default 4); results print in
# the order below. A mutation command that itself fails is a FAIL (the copy is writable even for read-only sources).
# Cases are the groups below; --case NAMES runs only those (tests/affected.py maps changed files to cases). The plugin copy
# is built only for the cases that mutate one (lint-mutations, which-model, qa-tiers).
# case-map: orca-wait tests/orca-wait.test.sh scripts/orca-wait.sh scripts/lib/compat.sh
# case-map: lint-mutations tests/skills-lint.sh scripts/* skills/* docs/* scripts/lib/compat.sh
# case-map: policy-markers skills/factory-core/references/parallel-work.md scripts/lib/compat.sh
# case-map: which-model skills/* docs/* scripts/lib/compat.sh
# case-map: qa-tiers skills/* docs/* scripts/lib/compat.sh
# case-map: orca-first skills/factory-core/references/parallel-work.md scripts/lib/compat.sh
# case-map: agents-roles scripts/lib/compat.sh
# case-map: plan-paths scripts/lib/plan_paths.py scripts/lib/compat.sh
# case-map: portable-plans docs/plans/* scripts/lib/compat.sh
# case-map: cli-selftest scripts/lib/compat.sh
# scripts/lib/compat.sh is sourced by the suite itself (temp dirs, copies), so it maps to every case. Inputs with no line run ALL:
# the suite's own file, root files (AGENTS.md, README.md: agents-roles reads AGENTS.md, so it only runs with ALL), registry.json,
# registry/*, tests/affected.py and every other shared lib. parallel-work.md also selects the lint copy cases through skills/*.
set -uo pipefail
CASES='orca-wait lint-mutations policy-markers which-model qa-tiers orca-first agents-roles plan-paths portable-plans cli-selftest'
usage() {
  printf '%s\n' 'Usage: parallel-policy.test.sh [--case NAMES | --only NAMES] [--list-cases] [-h|--help]' \
    'NAMES is a comma-separated list; selectors may be repeated. No selector runs every case.'
}
SELECTED=; list_cases=0
add_cases() {
  local selected
  local -a tokens
  read -r -a tokens <<< "${1//,/ }"
  [ "${#tokens[@]}" -gt 0 ] || { printf 'Empty case selector\n' >&2; exit 2; }
  for selected in "${tokens[@]}"; do
    [[ " $CASES " == *" $selected "* ]] || { printf 'Unknown case: %s\n' "$selected" >&2; exit 2; }
    [[ " $SELECTED " == *" $selected "* ]] || SELECTED+=" $selected"
  done
}
while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --list-cases) list_cases=1; shift ;;
    --case|--only) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; add_cases "$2"; shift 2 ;;
    --case=*|--only=*) add_cases "${1#*=}"; shift ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done
# Validate before the plugin copy or any temp dir exists.
if [ "$list_cases" = 1 ]; then printf '%s\n' $CASES; exit 0; fi
all_cases=0; [ -n "$SELECTED" ] || { SELECTED="$CASES"; all_cases=1; }
has_case() { [[ " $SELECTED " == *" $1 "* ]]; }
needs_plugin_copy() { has_case lint-mutations || has_case which-model || has_case qa-tiers; }
PW=skills/factory-core/references/parallel-work.md
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
P="$TMP/plugin"; mkdir -p "$P"
# copy_files <src> <dest>: copies the files named on stdin (relative to src). tar keeps file modes, so a read-only
# source file (Windows read-only attribute) would stay read-only and an `echo >> file` mutation would not apply:
# the copy is made writable.
copy_files() {
  (cd "$1" && while IFS= read -r f; do [ -f "$f" ] && printf '%s\n' "$f"; done | tar -cf - -T - | tar -xf - -C "$2") \
    && chmod -R u+w "$2"
}
if needs_plugin_copy; then
# not read by tests/skills-lint.sh or the scripts it runs (touchpoints, citations --offline, english-only, check-registry)
(cd "$ROOT" && git ls-files -co --exclude-standard) | grep -vE '^(testlab|templates|\.github|changelog\.d)/|^CHANGELOG\.md$' \
  | copy_files "$ROOT" "$P"
fi
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; [ -n "${2:-}" ] && echo "$2" | head -15 | sed 's/^/      /'; }

if has_case orca-wait; then
# Keep the waiter standalone while including it in run-all and CI through this suite.
wait_out=$(bash "$ROOT/tests/orca-wait.test.sh" 2>&1); wait_rc=$?
if [ "$wait_rc" -eq 0 ]; then
  ok "$(tail -n 1 <<<"$wait_out")"
else no "orca-wait suite (rc=$wait_rc)" "$(tail -n 15 <<<"$wait_out")"; fi

fi
if has_case lint-mutations; then
# regression: a read-only file in the source tree still mutates in the copy (a temp source, never the real worktree)
RO_SRC="$TMP/ro-src"; RO_DST="$TMP/ro-dst"; RO_F=skills/client-integration/SKILL.md
mkdir -p "$RO_SRC/${RO_F%/*}" "$RO_DST"; cp "$P/$RO_F" "$RO_SRC/$RO_F"; chmod a-w "$RO_SRC/$RO_F"
printf '%s\n' "$RO_F" | copy_files "$RO_SRC" "$RO_DST"
ro_err=$( (cd "$RO_DST" && echo 'zz-ro-mutation' >> "$RO_F") 2>&1 ); ro_rc=$?
if [ $ro_rc -eq 0 ] && tail -n 1 "$RO_DST/$RO_F" | grep -qx 'zz-ro-mutation'; then ok "read-only source file still mutates in the copy"
else no "read-only source file did not mutate in the copy (rc=$ro_rc)" "$ro_err"; fi
chmod -R u+w "$RO_SRC"
# (PW is defined with the helpers above)

# Extract the production checks, rather than duplicate their implementation. Fail closed if
# their section boundaries move: a missing section must never make a mutation pass.
python3 -B - "$P/tests/skills-lint.sh" "$TMP" <<'PY_SECTIONS'
import sys
from pathlib import Path
source = Path(sys.argv[1]).read_text(encoding="utf-8")
for name, start, end in (
    ("allowed", "allow_out=$(", "# every skill appears everywhere"),
    ("parallel", 'pw="skills/factory-core/references/parallel-work.md"', "# the budget warning itself"),
):
    section = source.split(start, 1)[1].split(end, 1)
    assert len(section) == 2, name + " lint section boundary missing"
    Path(sys.argv[2], name + ".sh").write_text(start + section[0], encoding="utf-8")
PY_SECTIONS
[ $? -eq 0 ] || exit 1
lint_mutation() {
  local root="$1" section="$2"
  (cd "$root" && ROOT="$root"; fail=0
    ok() { :; }
    bad() { echo "FAIL  $*"; fail=$((fail + 1)); }
    . "$TMP/$section.sh"
    [ "$fail" -eq 0 ])
}
out=$(lint_mutation "$P" parallel); rc=$?
[ "$rc" -eq 0 ] && ok "pristine parallel-work lint section passes" || no "pristine parallel-work lint (rc=$rc)" "$out"
out=$(lint_mutation "$P" allowed); rc=$?
[ "$rc" -eq 0 ] && ok "pristine allowed-tools lint section passes" || no "pristine allowed-tools lint (rc=$rc)" "$out"

# Only these files are read by the extracted checks; script contents are not read,
# but their names determine allowed-tools coverage. Use one Python copy operation
# per worker rather than spawning cp/mkdir for each file on Windows.
python3 -B - "$P" "$TMP/lint-inputs" <<'PY_INPUTS'
import shutil, sys
from pathlib import Path
src, dst = map(Path, sys.argv[1:])
shutil.copytree(src / "skills", dst / "skills")
for pattern in ("scripts/*", "scripts/checks/*"):
    for path in src.glob(pattern):
        if path.is_file():
            target = dst / path.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()
PY_INPUTS
[ $? -eq 0 ] || exit 1

# mutate <name> <expected FAIL text> <shell commands run inside a fresh copy>: queued; `grade` runs and checks them
MN=(); ME=(); MC=()
mutate() { MN+=("$1"); ME+=("$2"); MC+=("$3"); }
lint_one() { # index: fresh copy, mutation, lint -> $TMP/r<i>.rc / .out
  local M="$TMP/m$1" section=parallel
  case "${ME[$1]}" in *allowed-tools*|*not\ covered*|server-ops:*) section=allowed ;; esac
  python3 -B - "$TMP/lint-inputs" "$M" <<'PY_COPY'
import shutil, sys
shutil.copytree(sys.argv[1], sys.argv[2])
PY_COPY
  (cd "$M" && eval "${MC[$1]}") > "$TMP/r$1.merr" 2>&1; echo $? > "$TMP/r$1.mrc"
  lint_mutation "$M" "$section" > "$TMP/r$1.out"; echo $? > "$TMP/r$1.rc"; rm -rf "$M"
}
grade() {
  local i out rc mrc jobs="${PARALLEL_POLICY_JOBS:-4}"
  for i in "${!MN[@]}"; do
    while [ "$(jobs -rp | wc -l)" -ge "$jobs" ]; do wait -n 2>/dev/null || wait; done
    lint_one "$i" &
  done
  wait
  for i in "${!MN[@]}"; do
    out=$(cat "$TMP/r$i.out"); rc=$(cat "$TMP/r$i.rc"); mrc=$(cat "$TMP/r$i.mrc")
    if [ "$mrc" -ne 0 ]; then no "${MN[i]}: mutation command failed (rc=$mrc)" "$(cat "$TMP/r$i.merr")"
    elif [ "$rc" -ne 0 ] && grep '^FAIL' <<<"$out" | grep -qF -- "${ME[i]}"; then ok "${MN[i]} -> lint FAIL: ${ME[i]}"
    else no "${MN[i]}: lint did not fail with '${ME[i]}' (rc=$rc)" "$(grep '^FAIL' <<<"$out")"; fi
  done
}

mutate "factory-core SKILL.md link removed" "skills/factory-core/SKILL.md does not link parallel-work.md" \
  "sed -i '/parallel-work\.md/d' skills/factory-core/SKILL.md"
mutate "git-safety.md link removed" "references/git-safety.md does not link parallel-work.md" \
  "sed -i 's/parallel-work\.md/the policy/g' skills/factory-core/references/git-safety.md"
mutate "report.md link removed" "references/report.md does not link parallel-work.md" \
  "sed -i 's/parallel-work\.md/the policy/g' skills/factory-core/references/report.md"
mutate "worker-start pasted into client-integration" "policy phrase 'worker-start' copied outside" \
  "echo 'Start workers with \`orca orchestration worker-start\`.' >> skills/client-integration/SKILL.md"
mutate "Lead/Integrator restated in git-safety.md" "policy phrase 'Lead/Integrator' copied outside" \
  "echo 'The main session is the Lead/Integrator.' >> skills/factory-core/references/git-safety.md"
mutate "'wait for approval' added to the policy" "blocking wording in $PW" \
  "echo '- Wait for approval before integrating.' >> $PW"
mutate "'ask the user' added to the policy" "blocking wording in $PW" \
  "echo '- Ask the user before each dispatch.' >> $PW"
mutate "'requires approval' added to the policy" "blocking wording in $PW"   "echo '- Integration requires approval from the user.' >> $PW"
mutate "'get explicit confirmation' added to the policy" "blocking wording in $PW"   "echo '- Get explicit confirmation before each dispatch.' >> $PW"
mutate "'until the user' added to the policy" "blocking wording in $PW"   "echo '- Workers idle until the user replies.' >> $PW"
mutate "gate-create recommended" "gate-create outside a 'never' sentence" \
  "echo '- Use \`orca orchestration gate-create\` before each merge.' >> $PW"
mutate "human_gates dropped" "safety rule missing from $PW: 'human_gates'" \
  "sed -i 's/human_gates/gates/g' $PW"
mutate "rule 5 dropped" "safety rule missing from $PW: 'rule 5'" \
  "sed -i 's/rule 5/the rules/g' $PW"
mutate "orca worktree rm caveat dropped" "cites orca worktree rm without its branch-deletion caveat"   "sed -i 's/also deletes the checked-out local branch/may tidy branches/' $PW"
mutate "allowed-tools entry dropped" "runs bash scripts/checks/netcode-headless.sh, not covered by allowed-tools" \
  "sed -i '5s|, Bash(bash [^)]*/netcode-headless.sh:[*])||' skills/netcode-client/SKILL.md"
mutate "bare script name not granted" "server-ops: skills/server-ops/SKILL.md:" \
  "echo 'Run \`pin-plan.py\` first.' >> skills/server-ops/SKILL.md"
mutate "interpreter differs from the entry" "runs python3 -B scripts/factory-status.py, not covered" \
  "echo 'Run \`python3 -B \${CLAUDE_PLUGIN_ROOT}/scripts/factory-status.py\`.' >> skills/server-ops/SKILL.md"
mutate "allowed-tools lint crashes (unreadable SKILL.md)" "allowed-tools coverage: lint crashed"   "mkdir -p skills/zz-broken/SKILL.md"
mutate "UTF-8 reference text still linted (no locale decode crash)" "server-ops: skills/server-ops/references/zz.md:"   "mkdir -p skills/server-ops/references && printf 'K\xc5\x8d: run \x60pin-plan.py\x60 first.\n' > skills/server-ops/references/zz.md"
mutate "policy file deleted" "parallel-work: $PW missing" "rm $PW"
grade

fi
if has_case policy-markers; then
# Two-level rules (parallel-work.md is their only copy) are machine-checkable, not matched in free prose: each rule
# is a marker comment `<!-- policy:<id> -->` on its own line, present exactly once, whose next non-empty line is the
# canonical sentence below, byte for byte. No line may carry a retired shortcut phrasing (fixed strings, any case).
# Prints each problem; rc 1.
POLICY_IDS=(run-lead-never-implements only-task-lead-commits no-worktree-repo task-lead-claude speed-rule placement-table
  child-merge-remove child-no-run-all which-model)
declare -A POLICY_SENTENCE=(
  [run-lead-never-implements]='The run lead never edits task files; an S-tier task is a one-task plan with its own task lead.'
  [only-task-lead-commits]='Sub-sessions in the shared task worktree never commit, stage or stash; only the task lead commits there, with explicit paths.'
  [no-worktree-repo]='A no-worktree (Unity) repo never gets a worktree; its task lead and all its sessions run in its main checkout.'
  [task-lead-claude]="The task lead is a Claude session (registry pipeline.lead_agent), whatever the task's implementer, and Codex only when Claude is unavailable; implementation, review and QA sessions keep the cross-model pairing."
  [speed-rule]='Prefer many short, focused parallel sessions over one long session; every spec stays short: objective, owned paths, checks, report format.'
  [placement-table]='| Placement | When | How |'
  [child-merge-remove]='The owner merges a child'"'"'s branch into its parent branch and removes the child at once (`orca worktree rm --worktree path:<child>`).'
  [child-no-run-all]='Never create or remove a child worktree while a full tests/run-all.sh runs: every checkout shares one .git/config.'
  [which-model]='| Role or kind | Model | Registry |'
)
# The placement table under its marker keeps both rows: shared (the default) and child.
PLACEMENT_ROWS=('| shared (default) |' '| child |')
RETIRED_PHRASES=(
  'the lead implements in its own session'
  'lead implements in-session'
  'the run lead implements'
  'the run lead writes the code'
  'the run lead edits'
  'the lead edits the files directly'
  'implements in its own session, then the review'
  'always starts a sub-session that does not commit'
)
policy_markers() {
  # Batch the marker checks in one process on Windows; keep the shell data above
  # as the single source for canonical sentences and expected diagnostics.
  local args=() id
  for id in "${POLICY_IDS[@]}"; do args+=("$id" "${POLICY_SENTENCE[$id]}"); done
  python3 -B - "$1" "${#POLICY_IDS[@]}" "${args[@]}" "${PLACEMENT_ROWS[@]}" -- "${RETIRED_PHRASES[@]}" <<'PY_MARKERS'
import re, sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8")
lines = text.splitlines()
count = int(sys.argv[2]); args = sys.argv[3:]; errors = []
for i in range(count):
    name, sentence = args[2*i:2*i+2]
    marker = "<!-- policy:" + name + " -->"
    positions = [i for i, line in enumerate(lines) if line == marker]
    if not positions:
        errors.append("marker missing: policy:" + name); continue
    if len(positions) > 1:
        errors.append(f"marker duplicated: policy:{name} appears {len(positions)} times"); continue
    got = next((line for line in lines[positions[0]+1:] if line.strip()), "")
    if got != sentence:
        errors.append(f"sentence changed under policy:{name}: '{got}'")
match = re.search(r"<!-- policy:placement-table -->\s*\n((?:\|[^\n]*\n)+)", text)
table = match.group(1) if match else ""
rest = args[2*count:]; split = rest.index("--")
for row in rest[:split]:
    if row not in table:
        errors.append(f"placement table row missing: '{row}'")
for phrase in rest[split+1:]:
    hit = next((f"{i}:{line}" for i, line in enumerate(lines, 1) if phrase.lower() in line.lower()), None)
    if hit:
        errors.append(f"retired shortcut phrasing '{phrase}': {hit}")
match = re.search(r"^4\. \*\*Cross-model review\.\*\*.*?(?=^5\. |\Z)", text, re.M | re.S)
if not match:
    errors.append("section 10 step 4 (Cross-model review) missing")
else:
    step = " ".join(match.group().split())
    for phrase in ("in the shared placement starts a sub-session that does not commit", "commits on its own child branch"):
        if phrase not in step:
            errors.append(f"section 10 step 4 lacks the child exception: '{phrase}'")
print("\n".join(errors), end="\n" if errors else "")
sys.exit(bool(errors))
PY_MARKERS
}

s_out=$(policy_markers "$ROOT/$PW" 2>&1); s_rc=$?
[ $s_rc -eq 0 ] && ok "two-level policy markers intact in $PW" || no "two-level policy markers broken in $PW (rc=$s_rc)" "$s_out"
# s_mutate <name> <expected text|PASS> <commands in a copy of the policy file $F>: the checker must FAIL with that
# text (PASS: must still pass). A mutation command that fails or changes nothing is a FAIL.
s_mutate() {
  local F="$TMP/pw-mut.md" merr out rc
  cp "$ROOT/$PW" "$F" && chmod u+w "$F"
  if ! merr=$(F="$F" bash -c "$3" 2>&1); then no "$1: mutation command failed" "$merr"; return; fi
  if cmp -s "$ROOT/$PW" "$F"; then no "$1: mutation changed nothing"; return; fi
  out=$(policy_markers "$F" 2>&1); rc=$?
  if [ "$2" = PASS ]; then
    [ $rc -eq 0 ] && ok "$1 -> policy markers still PASS" || no "$1: policy markers did not pass (rc=$rc)" "$out"
  elif [ $rc -ne 0 ] && grep -qF -- "$2" <<<"$out"; then ok "$1 -> policy markers FAIL: $2"
  else no "$1: policy markers did not fail with '$2' (rc=$rc)" "$out"; fi
}
for id in "${POLICY_IDS[@]}"; do
  s_mutate "marker policy:$id deleted" "marker missing: policy:$id" \
    "sed -i '/^<!-- policy:$id -->\$/d' \"\$F\""
  s_mutate "marker policy:$id duplicated" "marker duplicated: policy:$id appears 2 times" \
    "printf '\n<!-- policy:$id -->\n%s\n' $(printf %q "${POLICY_SENTENCE[$id]}") >> \"\$F\""
done
s_mutate "canonical sentence changed (task lead follows the implementer)" "sentence changed under policy:task-lead-claude" \
  'sed -i "s/^The task lead is a Claude session (registry pipeline\.lead_agent), whatever/The task lead runs on the implementer model, whatever/" "$F"'
s_mutate "canonical sentence changed (S tier shortcut allowed)" "sentence changed under policy:run-lead-never-implements" \
  'sed -i "s/^The run lead never edits task files; an S-tier task is a one-task plan with its own task lead\.$/The run lead never edits task files, except for an S-tier task, which it implements in its own session./" "$F"'
s_mutate "canonical sentence changed (sub-sessions may commit)" "sentence changed under policy:only-task-lead-commits" \
  'sed -i "s/^Sub-sessions in the shared task worktree never commit, stage or stash;/Sub-sessions may commit;/" "$F"'
s_mutate "placement table removed" "marker missing: policy:placement-table" \
  'sed -i "/^<!-- policy:placement-table -->\$/,/^\$/d" "$F"'
s_mutate "placement table child row removed" "placement table row missing: '| child |'" \
  'sed -i "/^| child |/d" "$F"'
s_mutate "run-all/child rule removed" "marker missing: policy:child-no-run-all" \
  'sed -i "/^<!-- policy:child-no-run-all -->\$/,+1d" "$F"'
s_mutate "run-all/child rule weakened" "sentence changed under policy:child-no-run-all" \
  'sed -i "s/^Never create or remove a child worktree while a full tests\/run-all.sh runs:/Avoid creating a child worktree during a full run:/" "$F"'
s_mutate "child merge-and-remove rule removed" "marker missing: policy:child-merge-remove" \
  'sed -i "/^<!-- policy:child-merge-remove -->\$/d" "$F"'
s_mutate "canonical sentence moved off its marker" "sentence changed under policy:no-worktree-repo" \
  'sed -i "/^<!-- policy:no-worktree-repo -->$/a Unity projects are special." "$F"'
s_mutate "old S-tier shortcut re-added" "retired shortcut phrasing 'the run lead implements'" \
  'sed -i "s/^   S: the run lead writes/   S: the run lead implements in its own session, then the review, QA and gate steps below with one plan task. The run lead writes/" "$F"'
s_mutate "reworded shortcut re-added" "retired shortcut phrasing 'the lead edits the files directly'" \
  'printf "\nFor an S task the lead edits the files directly.\n" >> "$F"'
s_mutate "shortcut re-added in another case" "retired shortcut phrasing 'lead implements in-session'" \
  'printf "\nAt S tier the Lead Implements In-Session.\n" >> "$F"'
s_mutate "harmless rewording outside a marker" PASS \
  'sed -i "s/^It never pushes, merges, tags or removes its worktree\.$/It never pushes, merges or tags, and it never removes its worktree./" "$F"'
s_mutate "harmless S-tier sentence about the task lead" PASS \
  'printf "\nFor an S-tier task the task lead reviews the code directly; one task lead per task.\n" >> "$F"'

s_mutate "step 4 child exception dropped" "section 10 step 4 lacks the child exception: 'commits on its own child branch'" \
  'sed -i "s/the session commits on its own child branch only/the session works in the child/" "$F"'
s_mutate "step 4 says implement never commits" "retired shortcut phrasing 'always starts a sub-session that does not commit'" \
  'sed -i "s/^   \`--phase implement\` in the shared placement starts a sub-session that does not commit/   \`--phase implement\` always starts a sub-session that does not commit/" "$F"'

fi
if has_case which-model; then
# The "Which model" table (section 10) is the only copy of the routing rule: under policy:which-model it keeps one row
# per role or kind, at most 8 table lines, the code kinds on codex (never claude), next to the token rule and the
# availability fallback; no other Markdown file in the tree carries its header.
# which_model <policy file> [<tree root>]: prints each problem; rc 1.
WHICH_MODEL_ROWS=('| lead, plan, orchestration | claude |' '| docs, policy ' '| design '
  '| code, test, fix, refactor, generated | codex |' '| review | the other model |'
  '| QA | the model that did not implement (`qa_prefer` codex when codex did not implement) |')
WHICH_MODEL_REQUIRED=('delegates code to Codex and does not implement' 'QA runs go to Codex when Claude implemented'
  'RPG_FACTORY_AGENTS'
  '--down <agent>' 'SAME_MODEL (fallback: <model> unavailable)' 'no command fails because a model is missing')
which_model() {
  python3 -B - "$1" "${2:-}" "$PW" "${#WHICH_MODEL_ROWS[@]}" "${WHICH_MODEL_ROWS[@]}" "${WHICH_MODEL_REQUIRED[@]}" <<'PY_MODEL'
import re, sys
from pathlib import Path
file, root, relative, count = sys.argv[1:5]
count = int(count); rows = sys.argv[5:5+count]; required = sys.argv[5+count:]
text = Path(file).read_text(encoding="utf-8"); errors = []
match = re.search(r"<!-- policy:which-model -->\s*\n((?:\|[^\n]*\n)+)", text)
if not match:
    print("which-model table missing"); sys.exit(1)
table = match.group(1)
for row in rows:
    if row not in table:
        errors.append(f"which-model table row missing: '{row}'")
if len(table.splitlines()) > 8:
    errors.append("which-model table longer than 8 lines")
code = next((line for line in table.splitlines() if "| code" in line), "")
if "claude" in code.lower():
    errors.append(f"which-model table names claude for code: '{code}'")
qa = next((line for line in table.splitlines() if "| QA |" in line), "")
if re.search(r"implementer('s)? model|same model|implementing model", qa, re.I):
    errors.append(f"which-model QA row names the implementer's model: '{qa}'")
section10 = re.search(r"^## 10\. .*?(?=^## |\Z)", text, re.M | re.S)
if not section10:
    errors.append("section 10 missing")
else:
    section = " ".join(section10.group(0).split())
    for phrase in required:
        if phrase not in section:
            errors.append(f"section 10 lacks the routing rule: '{phrase}'")
if root:
    copies = [path.relative_to(root).as_posix() for path in sorted(Path(root).rglob("*.md"))
              if path.relative_to(root).as_posix() != relative
              and "| Role or kind | Model | Registry |" in path.read_text(encoding="utf-8")]
    if copies:
        errors.append("which-model table copied outside " + relative + ": " + " ".join(copies))
print("\n".join(errors), end="\n" if errors else "")
sys.exit(bool(errors))
PY_MODEL
}

w_out=$(which_model "$ROOT/$PW" "$P" 2>&1); w_rc=$?
[ $w_rc -eq 0 ] && ok "which-model table intact, single copy" || no "which-model table (rc=$w_rc)" "$w_out"
w_mutate() { # <name> <expected text> <commands run in a fresh copy $T of the tree; $F is its policy file>
  local T="$TMP/wm" merr out rc
  # Reuse one overlay: these mutations touch only the policy and two known
  # duplicate destinations. Restore all three before each case.
  mkdir -p "$T/${PW%/*}" "$T/docs" "$T/skills/client-integration"
  cp "$P/$PW" "$T/$PW"
  cp "$P/skills/client-integration/SKILL.md" "$T/skills/client-integration/SKILL.md"
  rm -f "$T/docs/zz-models.md"
  if ! merr=$(cd "$T" && F="$T/$PW" bash -c "$3" 2>&1); then no "$1: mutation command failed" "$merr"; return; fi
  if cmp -s "$P/$PW" "$T/$PW" && cmp -s "$P/skills/client-integration/SKILL.md" "$T/skills/client-integration/SKILL.md" && [ ! -f "$T/docs/zz-models.md" ]; then
    no "$1: mutation changed nothing"; return
  fi
  out=$(which_model "$T/$PW" "$T" 2>&1); rc=$?
  if [ $rc -ne 0 ] && grep -qF -- "$2" <<<"$out"; then ok "$1 -> which-model check FAIL: $2"
  else no "$1: which-model check did not fail with '$2' (rc=$rc)" "$out"; fi
}
w_mutate "which-model code row removed" "which-model table row missing: '| code, test, fix, refactor, generated | codex |'" \
  'sed -i "/^| code, test, fix, refactor, generated |/d" "$F"'
w_mutate "which-model review row removed" "which-model table row missing: '| review | the other model |'" \
  'sed -i "/^| review | the other model |/d" "$F"'
w_mutate "which-model names claude for code" "which-model table names claude for code" \
  'sed -i "s/^| code, test, fix, refactor, generated | codex |/| code, test, fix, refactor, generated | claude |/" "$F"'
w_mutate "which-model table grows past 8 lines" "which-model table longer than 8 lines" \
  'sed -i "/^| review | the other model |/i | asset | claude | x |\n| data | codex | x |" "$F"'
w_mutate "which-model QA row names the implementer's model" "which-model QA row names the implementer's model" \
  'sed -i "s/^| QA | the model that did not implement (\`qa_prefer\` codex when codex did not implement) |/| QA | the implementer'"'"'s model; long full-suite QA prefers codex |/" "$F"'
w_mutate "QA token rule loses the implementer condition" "section 10 lacks the routing rule: 'QA runs go to Codex when Claude implemented'" \
  'perl -0pi -e "s/QA runs go\s+to Codex when Claude implemented/QA runs go to Codex/" "$F"'
w_mutate "token rule dropped" "section 10 lacks the routing rule: 'delegates code to Codex and does not implement'" \
  'sed -i "s/delegates code to Codex and does not implement/may implement/" "$F"'
w_mutate "fallback marker dropped" "section 10 lacks the routing rule: 'SAME_MODEL (fallback: <model> unavailable)'" \
  'sed -i "s/SAME_MODEL (fallback: <model> unavailable)/SAME_MODEL/g" "$F"'
w_mutate "which-model section 10 heading renamed" "section 10 missing" \
  'sed -i "s/^## 10\. /## Ten. /" "$F"'
w_mutate "which-model table copied into docs" "which-model table copied outside $PW: docs/zz-models.md" \
  'mkdir -p docs && sed -n "/^| Role or kind |/,/^| QA |/p" "$F" > docs/zz-models.md'
w_mutate "which-model table copied into a skill" "which-model table copied outside $PW: skills/client-integration/SKILL.md" \
  'printf "\n| Role or kind | Model | Registry |\n|---|---|---|\n| code | codex | x |\n" >> skills/client-integration/SKILL.md'

fi
if has_case qa-tiers; then
# QA tiers stay under their marker in section 10, with one canonical table.
# Inspect the whole tree for copies, including untracked Markdown.
qa_tiers() {
  python3 -B - "$1" "$2" "$PW" <<'PY_QA'
import re, sys
from pathlib import Path
policy, root, relative = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
text = policy.read_text(encoding="utf-8")
marker = "<!-- policy:qa-tiers -->"
errors = []
section10 = re.search(r"^## 10\. .*?(?=^## |\Z)", text, re.M | re.S)
section = section10.group(0) if section10 else ""
match = re.search(re.escape(marker) + r"\s*\n((?:\|[^\n]*\n)+)", section)
if not section10:
    errors.append("section 10 missing")
elif text.count(marker) != 1 or not match:
    errors.append("qa-tiers table missing or marker duplicated")
else:
    table = match.group(1)
    rows = {line.split("|", 2)[1].strip(): line for line in table.splitlines()}
    required = {
        "Task QA, each candidate": ("--affected", "never a full run"),
        "Re-QA after a FAIL": ("failed suites", "task check suites", "--affected", "previous FAIL candidate"),
        "Tier S or prose-only task (every owned path a .md file, under changelog.d/ or a skills/ directory)": ("task lead", "after the review PASS", "no QA session", "tier S only"),
        "Reviewer": ("no suites",),
        "Integration QA, once per batch before the PR": ("--workspace-only", "gh pr checks", "CI green is the full gate", "ci+workspace"),
        "Release": ("--release", "dogfood.sh --installed"),
    }
    for label, phrases in required.items():
        row = rows.get(label, "")
        if not row:
            errors.append("qa-tiers row missing: " + label)
        elif any(phrase not in row for phrase in phrases):
            errors.append("qa-tiers row changed: " + label)
    task = rows.get("Task QA, each candidate", "")
    if re.search(r"(?<!never a )full run", task, re.I):
        errors.append("qa-tiers task row permits a full run")
header = "| When | Runs | Who |"
for path in sorted(root.rglob("*.md")):
    if path.relative_to(root).as_posix() == relative:
        continue
    contents = path.read_text(encoding="utf-8")
    if header in contents or marker in contents:
        errors.append("qa-tiers table copied outside " + relative + ": " + path.relative_to(root).as_posix())
print("\n".join(errors), end="\n" if errors else "")
sys.exit(bool(errors))
PY_QA
}
q_out=$(qa_tiers "$ROOT/$PW" "$P" 2>&1); q_rc=$?
[ "$q_rc" -eq 0 ] && ok "QA tiers table intact, single copy" || no "QA tiers table (rc=$q_rc)" "$q_out"
q_mutate() {
  local T="$TMP/qa-tiers" F merr out rc
  F="$T/$PW"
  mkdir -p "${F%/*}" "$T/skills/client-integration"
  cp "$P/$PW" "$F"
  rm -f "$T/skills/client-integration/SKILL.md"
  if ! merr=$(cd "$T" && F="$F" bash -c "$3" 2>&1); then no "$1: mutation command failed" "$merr"; return; fi
  if cmp -s "$P/$PW" "$F" && [ ! -f "$T/skills/client-integration/SKILL.md" ]; then no "$1: mutation changed nothing"; return; fi
  out=$(qa_tiers "$F" "$T" 2>&1); rc=$?
  if [ "$rc" -ne 0 ] && grep -qF -- "$2" <<<"$out"; then ok "$1 -> QA tiers check FAIL: $2"
  else no "$1: QA tiers check did not fail with '$2' (rc=$rc)" "$out"; fi
}
q_mutate "QA tiers table removed" "qa-tiers table missing" \
  'sed -i "/^<!-- policy:qa-tiers -->$/,/^$/d" "$F"'
q_mutate "QA tiers reviewer row removed" "qa-tiers row missing: Reviewer" \
  'sed -i "/^| Reviewer |/d" "$F"'
q_mutate "QA tiers re-QA row drops the task check suites" "qa-tiers row changed: Re-QA after a FAIL"   'sed -i "/^| Re-QA after a FAIL |/s/, with the task check suites//" "$F"'
q_mutate "QA tiers tier S row back to changed paths" "qa-tiers row missing: Tier S"   'sed -i "/^| Tier S or prose-only task/s/every owned path/every changed path/" "$F"'
q_mutate "QA tiers tier S row counts docs/ as prose again" "qa-tiers row missing: Tier S"   'sed -i "/^| Tier S or prose-only task/s/a .md file, under changelog.d\/ or a skills\/ directory/docs, skills, changelog or .md/" "$F"'
q_mutate "QA tiers task row requires a full run" "qa-tiers task row permits a full run" \
  'sed -i "/^| Task QA,/s/never a full run/run a full run/" "$F"'
q_mutate "QA tiers integration row back to a full local run" "qa-tiers row changed: Integration QA, once per batch before the PR" \
  'sed -i "/^| Integration QA,/s/tests\/run-all.sh --workspace-only/tests\/run-all.sh --reuse -j 4/" "$F"'
q_mutate "QA tiers integration row drops the CI watch" "qa-tiers row changed: Integration QA, once per batch before the PR" \
  'sed -i "/^| Integration QA,/s/gh pr checks/gh pr view/" "$F"'
q_mutate "QA tiers integration row drops the CI gate statement" "qa-tiers row changed: Integration QA, once per batch before the PR" \
  'sed -i "/^| Integration QA,/s/CI green is the full gate/a green CI helps/" "$F"'
q_mutate "QA tiers section 10 heading renamed" "section 10 missing" \
  'sed -i "s/^## 10\. /## Ten. /" "$F"'
q_mutate "QA tiers table copied into a skill" "qa-tiers table copied outside" \
  'sed -n "/^<!-- policy:qa-tiers -->$/,/^$/p" "$F" > skills/client-integration/SKILL.md'

fi
if has_case orca-first; then
# Section 5 keeps the Orca-first runner rule: inside Orca, planner/dispatch refuse --runner agent without
# --orca-unavailable, and the reason (Agent-tool task leads are invisible in Orca) stays with it. Phrases are
# matched in section 5 only, with its lines joined. Prints each problem; rc 1.
ORCA_FIRST_REQUIRED=('ORCA_WORKTREE_ID' 'ORCA_AGENT_HOOK_ENDPOINT' 'default to `--runner orca`'
  'refuse `--runner agent`' '`--orca-unavailable <reason>`' 'into the session prompt'
  'Agent-tool task leads with plain git worktrees are invisible in Orca')
orca_first() {
  local f="$1" p sec errs=()
  sec=$(awk '/^## 5\. / { f = 1 } f && /^## 6\. / { exit } f' "$f" | tr '\n' ' ' | tr -s ' ')
  if [ -z "$sec" ]; then echo "section 5 (Orca) missing"; return 1; fi
  for p in "${ORCA_FIRST_REQUIRED[@]}"; do grep -qF -- "$p" <<<"$sec" || errs+=("section 5 lacks the Orca-first rule: '$p'"); done
  [ ${#errs[@]} -eq 0 ] && return 0
  printf '%s\n' "${errs[@]}"; return 1
}
o_out=$(orca_first "$ROOT/$PW" 2>&1); o_rc=$?
[ $o_rc -eq 0 ] && ok "section 5 keeps the Orca-first runner rule" || no "section 5 Orca-first rule (rc=$o_rc)" "$o_out"
o_mutate() { # <name> <expected text> <commands in a copy of the policy file $F>
  local F="$TMP/pw-orca-mut.md" merr out rc
  cp "$ROOT/$PW" "$F" && chmod u+w "$F"
  if ! merr=$(F="$F" bash -c "$3" 2>&1); then no "$1: mutation command failed" "$merr"; return; fi
  if cmp -s "$ROOT/$PW" "$F"; then no "$1: mutation changed nothing"; return; fi
  out=$(orca_first "$F" 2>&1); rc=$?
  if [ $rc -ne 0 ] && grep -qF -- "$2" <<<"$out"; then ok "$1 -> Orca-first check FAIL: $2"
  else no "$1: Orca-first check did not fail with '$2' (rc=$rc)" "$out"; fi
}
o_mutate "--orca-unavailable flag dropped" "lacks the Orca-first rule: '\`--orca-unavailable <reason>\`'" \
  'sed -i "s/--orca-unavailable <reason>/a reason/g" "$F"'
o_mutate "invisible-in-Orca reason dropped" "lacks the Orca-first rule: 'Agent-tool task leads with plain git worktrees are invisible in Orca'" \
  'sed -i "s/are invisible in Orca/are fine/" "$F"'
o_mutate "refusal softened to a preference" "lacks the Orca-first rule: 'refuse \`--runner agent\`'" \
  'sed -i "s/and refuse\$/and prefer over/" "$F"'
o_mutate "rule moved out of section 5" "lacks the Orca-first rule: 'ORCA_WORKTREE_ID'" \
  'sed -i "/^- \*\*Orca first inside Orca\.\*\*/,/^  Agent-tool task leads/d" "$F"'

fi
if has_case agents-roles; then
# AGENTS.md (the Codex entry) never makes Codex the run lead, and a task lead only when Claude is unavailable
# (policy:task-lead-claude); Codex is the default implementer of the code kinds. Prints each problem; rc 1.
AGENTS_REQUIRED=('Codex leads a task only when Claude is unavailable' 'as a session a task lead starts'
  'default implementer for the code, test, fix, refactor and generated kinds')
AGENTS_FORBIDDEN=('as a task lead' 'as the main session (run lead)' 'as the run lead' 'drive it through factory-core'
  'codex is the run lead' 'codex is the task lead')
agents_roles() {
  local f="$1" p hits errs=() flat
  flat=$(tr '\n' ' ' < "$f" | tr -s ' ')
  for p in "${AGENTS_REQUIRED[@]}"; do grep -qiF -- "$p" <<<"$flat" || errs+=("AGENTS.md lacks: '$p'"); done
  for p in "${AGENTS_FORBIDDEN[@]}"; do
    hits=$(grep -oiF -- "$p" <<<"$flat" | head -1)
    [ -z "$hits" ] || errs+=("AGENTS.md names Codex as a lead: '$p'")
  done
  [ ${#errs[@]} -eq 0 ] && return 0
  printf '%s\n' "${errs[@]}"; return 1
}
a_out=$(agents_roles "$ROOT/AGENTS.md" 2>&1); a_rc=$?
[ $a_rc -eq 0 ] && ok "AGENTS.md keeps Codex out of the lead roles" || no "AGENTS.md lead roles (rc=$a_rc)" "$a_out"
a_mutate() { # <name> <expected text> <commands in a copy of AGENTS.md $F>
  local F="$TMP/agents-mut.md" merr out rc
  cp "$ROOT/AGENTS.md" "$F" && chmod u+w "$F"
  if ! merr=$(F="$F" bash -c "$3" 2>&1); then no "$1: mutation command failed" "$merr"; return; fi
  if cmp -s "$ROOT/AGENTS.md" "$F"; then no "$1: mutation changed nothing"; return; fi
  out=$(agents_roles "$F" 2>&1); rc=$?
  if [ $rc -ne 0 ] && grep -qF -- "$2" <<<"$out"; then ok "$1 -> AGENTS.md check FAIL: $2"
  else no "$1: AGENTS.md check did not fail with '$2' (rc=$rc)" "$out"; fi
}
a_mutate "Codex as task lead re-added" "names Codex as a lead: 'as a task lead'" \
  'printf "\n- Codex follows the same flow as a task lead or as a session a task lead starts.\n" >> "$F"'
a_mutate "Codex as run lead re-added" "names Codex as a lead: 'as the main session (run lead)'" \
  'printf "\nAs the main session (run lead), drive it through factory-core steps 6, 7, 11 and 12.\n" >> "$F"'
a_mutate "Claude task-lead rule dropped" "AGENTS.md lacks: 'Codex leads a task only when Claude is unavailable'" \
  'sed -i "s/Codex leads a task only when Claude is unavailable/Codex may lead any task/" "$F"'
a_mutate "Codex default implementer dropped" "AGENTS.md lacks: 'default implementer for the code, test, fix, refactor and generated kinds'" \
  'sed -i "s/Codex is the default implementer for the code, test, fix, refactor and generated kinds/Codex implements when asked/" "$F"'

fi
if has_case plan-paths; then
# Portable plan paths: no subprocesses or changes to the real workspace.
paths_out=$(python3 -B - "$ROOT" "$TMP" <<'PY'
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(sys.argv[1], 'scripts', 'lib'))  # as factory-pipeline.py imports lib modules
from plan_paths import resolve_repo_path

tmp = Path(sys.argv[2]).resolve()
plan = tmp / 'plans' / 'nested' / 'plan.json'
workspace = tmp / 'workspace'
workspace.mkdir()
(workspace / 'marker').mkdir()
variable = 'RPG_FACTORY_WORKSPACE'
registry = {'workspace': {'root_env': variable, 'root_markers': ['marker'],
                          'root_default': str(tmp / 'missing')}}

def expect(label, value, wanted):
    assert value == wanted, (label, value, wanted)
    print(label)

with patch.dict(os.environ, {variable: str(workspace)}):
    expect('absolute normalized', resolve_repo_path(str(tmp / 'a' / '..' / 'repo'), plan, registry),
           (str(tmp / 'repo'), None))
    expect('plan-relative ../..', resolve_repo_path('../../repo', plan, registry),
           (str(tmp / 'repo'), None))
    for prefix in ('${' + variable + '}', '$' + variable):
        expect('workspace prefix ' + prefix, resolve_repo_path(prefix + '/repo', plan, registry),
               (str(workspace / 'repo'), None))
        expect('workspace root ' + prefix, resolve_repo_path(prefix, plan, registry),
               (str(workspace), None))
    expect('variable boundary', resolve_repo_path('$' + variable + '_OTHER/repo', plan, registry),
           (str(plan.parent / ('$' + variable + '_OTHER') / 'repo'), None))
with patch.dict(os.environ, {variable: ''}):
    result, reason = resolve_repo_path('${' + variable + '}/repo', plan, registry)
    assert result is None and variable in reason, (result, reason)
    print('missing workspace names variable')
# The prefix comes from registry data rather than a second hard-coded variable name.
registry['workspace']['root_env'] = 'FACTORY_TEST_WORKSPACE'
with patch.dict(os.environ, {'FACTORY_TEST_WORKSPACE': str(workspace)}):
    expect('registry variable', resolve_repo_path('$FACTORY_TEST_WORKSPACE/repo', plan, registry),
           (str(workspace / 'repo'), None))
PY
); paths_rc=$?
if [ "$paths_rc" -eq 0 ]; then
  while IFS= read -r label; do ok "plan_paths: $label"; done <<<"$paths_out"
else no "plan_paths unit cases (rc=$paths_rc)" "$paths_out"; fi

fi
if has_case portable-plans; then
# Check every file, including untracked plans; use the same checker on injected copies.
portable_plans() {
  python3 -B - "$1" <<'PY'
import re
import sys
from pathlib import Path

machine_path = re.compile(r'(?<![A-Za-z])[A-Za-z]:[/\\]|(?<![\w/:.-])/[A-Za-z]/|/mnt/[A-Za-z](?:/|$)|/Users/|/home/|AppData', re.I | re.M)
bad = []
for path in sorted(Path(sys.argv[1]).rglob('*')):
    if path.is_file() and machine_path.search(path.read_bytes().decode('utf-8', errors='replace')):
        bad.append(str(path))
if bad:
    print('machine-specific absolute path: ' + ', '.join(bad))
    sys.exit(1)
PY
}
portable_out=$(portable_plans "$ROOT/docs/plans" 2>&1); portable_rc=$?
[ "$portable_rc" -eq 0 ] && ok "docs/plans contains no machine-specific absolute paths" \
  || no "docs/plans portable paths (rc=$portable_rc)" "$portable_out"
PLAN_COPY="$TMP/plans-portable"; mkdir -p "$PLAN_COPY"
if [ -d "$ROOT/docs/plans" ]; then cp -r "$ROOT/docs/plans/." "$PLAN_COPY/"; fi
printf '%s\n' 'see https://example.com/x and https://example.com/c/workspace/example' 'docs/plans/x and docs/plans/c/example' > "$PLAN_COPY/zz-url.md"
portable_out=$(portable_plans "$PLAN_COPY" 2>&1) && ok "docs/plans check allows URLs and repo-relative paths" || no "docs/plans check rejects URLs or repo-relative paths" "$portable_out"
rm -f "$PLAN_COPY/zz-url.md"
for machine_path in 'C:/workspace/repo' 'C:\workspace\repo' '/mnt/c/workspace/repo' '/mnt/c' '/c/workspace/repo' '/Users/person/repo' '/home/person/repo' 'AppData/Local/state'; do
  printf '%s\n' "$machine_path" > "$PLAN_COPY/zz-machine-path.md"
  portable_out=$(portable_plans "$PLAN_COPY" 2>&1); portable_rc=$?
  if [ "$portable_rc" -ne 0 ] && grep -qF 'machine-specific absolute path:' <<<"$portable_out"; then
    ok "docs/plans mutation rejected: $machine_path"
  else no "docs/plans mutation was not rejected: $machine_path (rc=$portable_rc)" "$portable_out"; fi
done

fi
# The case selection itself: --help exits 0, an unknown argument or case exits 2 before any run, and a subset runs
# fewer checks than the full run.
if has_case cli-selftest; then
  self="${BASH_SOURCE[0]}"
  bash "$self" --help >/dev/null 2>&1 && ok "--help exits 0" || no "--help did not exit 0"
  bash "$self" --no-such-option >/dev/null 2>&1; rc=$?
  [ "$rc" -eq 2 ] && ok "unknown argument exits 2" || no "unknown argument exited $rc, want 2"
  bash "$self" --case no-such-case >/dev/null 2>&1; rc=$?
  [ "$rc" -eq 2 ] && ok "unknown case exits 2" || no "unknown case exited $rc, want 2"
  for selector in ',' ' '; do
    for option in --case --only; do
      bash "$self" "$option" "$selector" >/dev/null 2>&1; rc=$?
      [ "$rc" -eq 2 ] && ok "$option empty selector exits 2" || no "$option empty selector exited $rc, want 2"
    done
  done
  child=$(bash "$self" --case plan-paths --only plan-paths 2>&1); rc=$?
  n_one=$(sed -n 's/^parallel-policy: \([0-9]*\) checks.*/\1/p' <<<"$child")
  n_failed=$(sed -n 's/^parallel-policy: [0-9]* checks, [0-9]* passed, \([0-9]*\) failed$/\1/p' <<<"$child")
  # plan-paths is the cheapest case (~2 s); in a full run the parent has run more checks than the one case
  if [ "$rc" -eq 0 ] && [ "${n_failed:-missing}" = 0 ] && [ "${n_one:-0}" -gt 0 ] && { [ "$all_cases" = 0 ] || [ "$n_one" -lt $((pass + fail)) ]; }; then ok "--case plan-paths runs $n_one checks, fewer than a full run"
  else no "--case plan-paths: exit $rc, ${n_failed:-?} failed, ${n_one:-?} checks; parent has $((pass + fail))"; fi
fi
echo "parallel-policy: $((pass + fail)) checks, $pass passed, $fail failed"
[ "$fail" -eq 0 ] && [ "$pass" -gt 0 ]
