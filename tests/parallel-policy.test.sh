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

echo "parallel-policy: $((pass + fail)) checks, $pass passed, $fail failed"
[ "$fail" -eq 0 ] && [ "$pass" -gt 0 ]
