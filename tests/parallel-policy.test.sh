#!/usr/bin/env bash
# The parallel-work policy checks in tests/skills-lint.sh bite: on a throwaway copy of this plugin the pristine
# copy passes the lint, and each mutation (lost link, copied policy text, blocking wording variants, gate-create, a
# dropped safety rule, a missing policy file) makes the copy's own lint FAIL with the expected message. The same
# harness proves the allowed-tools coverage lint bites (a script use the skill's allowed-tools does not grant).
# One minimal copy (the tracked and untracked files minus what neither the lint nor its tools read), one cheap copy
# of it per mutation, and the mutations' lints run concurrently (PARALLEL_POLICY_JOBS, default 4); results print in
# the order below. A mutation command that itself fails is a FAIL (the copy is writable even for read-only sources).
set -uo pipefail
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
# not read by tests/skills-lint.sh or the scripts it runs (touchpoints, citations --offline, english-only, check-registry)
(cd "$ROOT" && git ls-files -co --exclude-standard) | grep -vE '^(testlab|templates|\.github|changelog\.d)/|^CHANGELOG\.md$' \
  | copy_files "$ROOT" "$P"
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; [ -n "${2:-}" ] && echo "$2" | head -15 | sed 's/^/      /'; }

# regression: a read-only file in the source tree still mutates in the copy (a temp source, never the real worktree)
RO_SRC="$TMP/ro-src"; RO_DST="$TMP/ro-dst"; RO_F=skills/client-integration/SKILL.md
mkdir -p "$RO_SRC/${RO_F%/*}" "$RO_DST"; cp "$P/$RO_F" "$RO_SRC/$RO_F"; chmod a-w "$RO_SRC/$RO_F"
printf '%s\n' "$RO_F" | copy_files "$RO_SRC" "$RO_DST"
ro_err=$( (cd "$RO_DST" && echo 'zz-ro-mutation' >> "$RO_F") 2>&1 ); ro_rc=$?
if [ $ro_rc -eq 0 ] && tail -n 1 "$RO_DST/$RO_F" | grep -qx 'zz-ro-mutation'; then ok "read-only source file still mutates in the copy"
else no "read-only source file did not mutate in the copy (rc=$ro_rc)" "$ro_err"; fi
chmod -R u+w "$RO_SRC"
lint() { (cd "$1" && CLAUDE_PLUGIN_ROOT="$1" bash tests/skills-lint.sh 2>&1); }
PW=skills/factory-core/references/parallel-work.md

out=$(lint "$P"); rc=$?
[ $rc -eq 0 ] && ! grep -q 'parallel-work' <<<"$(grep '^FAIL' <<<"$out")" && ok "pristine copy passes the lint" || no "pristine copy (rc=$rc)" "$(grep '^FAIL' <<<"$out")"

# mutate <name> <expected FAIL text> <shell commands run inside a fresh copy>: queued; `grade` runs and checks them
MN=(); ME=(); MC=()
mutate() { MN+=("$1"); ME+=("$2"); MC+=("$3"); }
lint_one() { # index: fresh copy, mutation, lint -> $TMP/r<i>.rc / .out
  local M="$TMP/m$1"; rm -rf "$M"; cp -r "$P" "$M"
  (cd "$M" && eval "${MC[$1]}") > "$TMP/r$1.merr" 2>&1; echo $? > "$TMP/r$1.mrc"
  lint "$M" > "$TMP/r$1.out"; echo $? > "$TMP/r$1.rc"; rm -rf "$M"
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

# Two-level rules (parallel-work.md is their only copy) are machine-checkable, not matched in free prose: each rule
# is a marker comment `<!-- policy:<id> -->` on its own line, present exactly once, whose next non-empty line is the
# canonical sentence below, byte for byte. No line may carry a retired shortcut phrasing (fixed strings, any case).
# Prints each problem; rc 1.
POLICY_IDS=(run-lead-never-implements only-task-lead-commits no-worktree-repo task-lead-claude speed-rule placement-table
  child-merge-remove child-no-run-all)
declare -A POLICY_SENTENCE=(
  [run-lead-never-implements]='The run lead never edits task files; an S-tier task is a one-task plan with its own task lead.'
  [only-task-lead-commits]='Sub-sessions in the shared task worktree never commit, stage or stash; only the task lead commits there, with explicit paths.'
  [no-worktree-repo]='A no-worktree (Unity) repo never gets a worktree; its task lead and all its sessions run in its main checkout.'
  [task-lead-claude]="The task lead is always a Claude session (registry pipeline.lead_agent), whatever the task's implementer; implementation, review and QA sessions keep the cross-model pairing."
  [speed-rule]='Prefer many short, focused parallel sessions over one long session; every spec stays short: objective, owned paths, checks, report format.'
  [placement-table]='| Placement | When | How |'
  [child-merge-remove]='The owner merges a child'"'"'s branch into its parent branch and removes the child at once (`orca worktree rm --worktree path:<child>`).'
  [child-no-run-all]='Never create or remove a child worktree while a full tests/run-all.sh runs: every checkout shares one .git/config.'
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
)
policy_markers() {
  local f="$1" id n got errs=() p hits
  for id in "${POLICY_IDS[@]}"; do
    n=$(grep -cxF -- "<!-- policy:$id -->" "$f")
    if [ "$n" -eq 0 ]; then errs+=("marker missing: policy:$id"); continue; fi
    if [ "$n" -gt 1 ]; then errs+=("marker duplicated: policy:$id appears $n times"); continue; fi
    got=$(awk -v m="<!-- policy:$id -->" 'f && NF { print; exit } $0 == m { f = 1 }' "$f")
    [ "$got" = "${POLICY_SENTENCE[$id]}" ] || errs+=("sentence changed under policy:$id: '$got'")
  done
  local table
  table=$(awk '$0 == "<!-- policy:placement-table -->" { f = 1; next } f && /^\|/ { print; t = 1; next } f && t { exit }' "$f")
  for p in "${PLACEMENT_ROWS[@]}"; do
    grep -qF -- "$p" <<<"$table" || errs+=("placement table row missing: '$p'")
  done
  for p in "${RETIRED_PHRASES[@]}"; do
    hits=$(grep -niF -- "$p" "$f" | head -1)
    [ -z "$hits" ] || errs+=("retired shortcut phrasing '$p': $hits")
  done
  [ ${#errs[@]} -eq 0 ] && return 0
  printf '%s\n' "${errs[@]}"; return 1
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
  'sed -i "s/^The task lead is always a Claude session (registry pipeline\.lead_agent), whatever/The task lead runs on the implementer model, whatever/" "$F"'
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

echo "parallel-policy: $((pass + fail)) checks, $pass passed, $fail failed"
[ "$fail" -eq 0 ] && [ "$pass" -gt 0 ]
