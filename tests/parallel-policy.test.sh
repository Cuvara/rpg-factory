#!/usr/bin/env bash
# The parallel-work policy checks in tests/skills-lint.sh bite: on a throwaway copy of this plugin the pristine
# copy passes the lint, and each mutation (lost link, copied policy text, blocking wording variants, gate-create, a
# dropped safety rule, a missing policy file) makes the copy's own lint FAIL with the expected message.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
P="$TMP/plugin"; mkdir -p "$P"
(cd "$ROOT" && git ls-files -co --exclude-standard -z | while IFS= read -r -d '' f; do
  [ -f "$f" ] && mkdir -p "$P/$(dirname "$f")" && cp "$f" "$P/$f"; done)
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; [ -n "${2:-}" ] && echo "$2" | head -15 | sed 's/^/      /'; }
lint() { (cd "$1" && CLAUDE_PLUGIN_ROOT="$1" bash tests/skills-lint.sh 2>&1); }
PW=skills/factory-core/references/parallel-work.md

out=$(lint "$P"); rc=$?
[ $rc -eq 0 ] && ! grep -q 'parallel-work' <<<"$(grep '^FAIL' <<<"$out")" && ok "pristine copy passes the lint" || no "pristine copy (rc=$rc)" "$(grep '^FAIL' <<<"$out")"

# mutate <name> <expected FAIL text> <shell commands run inside a fresh copy>
mutate() {
  local name="$1" expect="$2" cmd="$3" M="$TMP/m" out rc
  rm -rf "$M"; cp -r "$P" "$M"
  (cd "$M" && eval "$cmd")
  out=$(lint "$M"); rc=$?
  if [ $rc -ne 0 ] && grep '^FAIL' <<<"$out" | grep -qF -- "$expect"; then ok "$name -> lint FAIL: $expect"
  else no "$name: lint did not fail with '$expect' (rc=$rc)" "$(grep '^FAIL' <<<"$out")"; fi
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
mutate "policy file deleted" "parallel-work: $PW missing" "rm $PW"

echo "parallel-policy: $((pass + fail)) checks, $pass passed, $fail failed"
[ "$fail" -eq 0 ] && [ "$pass" -gt 0 ]
