#!/usr/bin/env bash
# Session state (scripts/factory_session.py, lib/fstate.py) and the 1.0.1 tripwire removal: state paths never
# resolve relative to the cwd, and no hook, guard or script still snapshots, latches or asks for an ack.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
SESS="$ROOT/scripts/factory_session.py"; GUARD="$ROOT/scripts/git-guard.py"; FG="$ROOT/scripts/file-guard.py"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
export TMPDIR="$TMP" RPG_FACTORY_WORKSPACE="$TMP/ws" CLAUDE_PLUGIN_ROOT="$ROOT" RPG_FACTORY_STATE_DIR="$TMP/state"
WS="$TMP/ws"; SERVER="$WS/rpg-mmo-server"; CLIENT="$WS/IndieRPGMMOAdventure"
mkdir -p "$SERVER/backend" "$CLIENT/ProjectSettings"
touch "$SERVER/backend/TEAM.md" "$CLIENT/ProjectSettings/ProjectVersion.txt"
gc() { git -C "$1" -c user.email=t@t -c user.name=t "${@:2}"; }
for r in "$SERVER" "$CLIENT"; do git -C "$r" init -q -b develop; gc "$r" add -A; gc "$r" commit -qm init; done
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; }

# ---- the tripwire is gone: no script, no hook, no ack command
[ ! -e "$ROOT/scripts/tripwire.py" ] && ok "scripts/tripwire.py removed" || no "scripts/tripwire.py still exists"
jq -e '[.. | .command? // empty] | all(test("tripwire") | not)' "$ROOT/hooks/hooks.json" >/dev/null \
  && ok "hooks.json runs no tripwire command" || no "hooks.json still runs tripwire"
jq -e '(.hooks | has("PostToolUse") | not) and (.hooks | has("PostToolUseFailure") | not)' "$ROOT/hooks/hooks.json" >/dev/null \
  && ok "no PostToolUse / PostToolUseFailure hooks (nothing compares state after a command)" || no "a post-command hook is still wired"
hits=$(grep -rlE 'latch_dir|has_open_events|ack_command|latched\(|LATCH"' "$ROOT/scripts" 2>/dev/null)
[ -z "$hits" ] && ok "no script reads latch state or prints an ack command" || no "latch code left in: $hits"

# ---- stale state from older versions (open events, a legacy latch, a session LATCH) blocks nothing
python3 -B - "$TMP/state" "$WS" <<'PY'
import hashlib, json, os, sys
key = hashlib.sha1(os.path.abspath(sys.argv[2]).encode()).hexdigest()[:12]
os.makedirs(os.path.join(sys.argv[1], "latch", key), exist_ok=True)
for p in (os.path.join(sys.argv[1], "latch", key, "20261021T151023Z-651036.json"), os.path.join(sys.argv[1], "latch", key + ".json")):
    json.dump({"workspace": sys.argv[2], "session": "old", "message": "[client] pre-existing user file ProjectSettings/ProjectSettings.asset was modified"}, open(p, "w"))
PY
mkdir -p "$TMP/rpg-factory/stale" && echo "STOP" > "$TMP/rpg-factory/stale/LATCH"
dec() { # tool cwd command-or-path
  local o pl
  if [ "$1" = Bash ]; then pl=$(jq -cn --arg c "$3" --arg d "$2" '{tool_name:"Bash",tool_input:{command:$c},cwd:$d,session_id:"stale"}'); o=$(python3 -B "$GUARD" <<<"$pl")
  else pl=$(jq -cn --arg t "$1" --arg p "$3" --arg d "$2" '{tool_name:$t,tool_input:{file_path:$p,content:"x"},cwd:$d,session_id:"stale"}'); o=$(python3 -B "$FG" <<<"$pl"); fi
  jq -r 'if .hookSpecificOutput.permissionDecision then "DECISION" else ((.hookSpecificOutput.additionalContext // "") | (capture("^rpg-factory advisory [(](?<l>[a-z]+)[)]") // {l: "allow"}) | .l) end' <<<"${o:-{\}}"; }
for c in "git fetch --tags" "git fetch --all --tags --prune" "git pull --ff-only" "git switch -c feat/server/after-latch" "touch x" "python3 tools/build.py"; do
  [ "$(dec Bash "$SERVER" "$c")" = allow ] && ok "stale latch state: allowed  $c" || no "stale latch state: not allowed  $c"; done
[ "$(dec Write "$CLIENT" "$CLIENT/ProjectSettings/ProjectSettings.asset")" = allow ] && ok "stale latch state: Write allowed" || no "stale latch state: Write blocked"
[ "$(dec Bash "$SERVER" "git push origin --tags")" = high ] && ok "unrelated git safety still flags it: tag push advisory high" || no "tag push not flagged high"

# ---- a real git change made outside the guard (another process, Unity) is never reported or latched
printf '#!/usr/bin/env bash\ngit tag v9.9.9\n' > "$TMP/script-tag.sh"; chmod +x "$TMP/script-tag.sh"
(cd "$SERVER" && "$TMP/script-tag.sh"); echo "unity save" >> "$CLIENT/ProjectSettings/ProjectVersion.txt"
[ "$(dec Bash "$SERVER" "git fetch --tags")" = allow ] && [ "$(dec Edit "$CLIENT" "$CLIENT/ProjectSettings/ProjectVersion.txt")" = allow ] \
  && [ -z "$(ls "$TMP/state/latch/"*/2026*.json 2>/dev/null | grep -v 151023Z)" ] \
  && ok "changes outside the guard: next commands allowed, no new event written" || no "an out-of-band change still has an effect"

# ---- 1.0.3: no hook asks the user or blocks the agent - every former ask/deny is an advisory (additionalContext)
hits=$(grep -rn '"permissionDecision' "$ROOT/scripts" --include=*.py 2>/dev/null)
[ -z "$hits" ] && ok "no script emits permissionDecision" || no "permissionDecision emitted in: $hits"
raw() { jq -cn --arg c "$2" --arg d "$1" '{tool_name:"Bash",tool_input:{command:$c},cwd:$d,session_id:"adv"}' | python3 -B "$GUARD"; }
for c in "git rebase origin/develop" "git push --force origin develop" "git tag v9.9.9" "gh repo delete Cuvara/rpg-mmo-server --yes" \
         "git reset --hard HEAD~1" "bash Tools/run-clients.sh 4" "kubectl apply -f x.yaml"; do
  o=$(raw "$SERVER" "$c")
  if jq -e '(.hookSpecificOutput | has("permissionDecision") | not) and (.hookSpecificOutput.additionalContext | startswith("rpg-factory advisory ("))' <<<"$o" >/dev/null 2>&1
  then ok "advisory only, no decision: $c"; else no "not advisory-only: $c -> ${o:0:200}"; fi
done
o=$(jq -cn --arg p "$CLIENT/Packages/com.gdk.core/x.cs" --arg d "$CLIENT" '{tool_name:"Write",tool_input:{file_path:$p,content:"x"},cwd:$d,session_id:"adv"}' | python3 -B "$FG")
jq -e '.hookSpecificOutput | has("permissionDecision") | not' <<<"${o:-{\}}" >/dev/null && ok "file guard never decides" || no "file guard decided: $o"
sk=$(jq -cn --arg d "$SERVER" '{tool_name:"Skill",tool_input:{skill:"rpg-factory:go-backend"},cwd:$d,session_id:"adv-tech"}' | python3 -B "$SESS" --skill)
jq -e '(.hookSpecificOutput | has("permissionDecision") | not) and (.hookSpecificOutput.additionalContext | startswith("rpg-factory advisory (high)"))' <<<"$sk" >/dev/null \
  && grep -qx go-backend "$TMP/rpg-factory/adv-tech/SKILLS" && ok "tech skill before its lead: advisory, still runs (recorded)" || no "tech skill: ${sk:0:200}"

# ---- state paths never resolve relative to the cwd, whatever TMPDIR is
PROBE="$TMP/cwdprobe"; mkdir -p "$PROBE" "$TMP/tmpok"
for td in "" "relative/dir" "/nonexistent/x" "$TMP/tmpok"; do
  pl=$(jq -cn --arg d "$SERVER" '{tool_name:"Skill",tool_input:{skill:"rpg-factory:factory-core",args:"plan only"},cwd:$d,session_id:"tmpdir-case"}')
  (cd "$PROBE" && TMPDIR="$td" python3 -B "$SESS" --skill <<<"$pl" >/dev/null
   TMPDIR="$td" python3 -B -c "import sys; sys.path.insert(0,'$ROOT/scripts/lib'); import fstate, os; r=fstate.scratch(); assert os.path.isabs(r), r; print(r)" > "$TMP/root.txt")
  root=$(cat "$TMP/root.txt")
  if [ -z "$(ls -A "$PROBE")" ] && is_abs "$root"; then ok "TMPDIR='$td' -> $root (nothing written in the cwd)"
  else no "TMPDIR='$td' root=$root cwd has: $(ls -A "$PROBE")"; fi
done
rm -rf /tmp/rpg-factory/tmpdir-case                                   # fallback cases used the real /tmp: clean up
is_abs "$(cd "$PROBE" && env -u TMPDIR python3 -B -c "import sys; sys.path.insert(0,'$ROOT/scripts/lib'); import fstate; print(fstate.scratch())")" \
  && ok "TMPDIR unset -> absolute" || no "TMPDIR unset"

# ---- the session hook: bad usage and bad input never break a session
out=$(python3 -B "$SESS" 2>&1; echo "rc=$?"); case "$out" in *"usage:"*"rc=2") ok "factory_session.py without --skill: usage, exit 2";; *) no "usage: $out";; esac
out=$(echo 'garbage' | python3 -B "$SESS" --skill; echo "rc=$?"); [ "$out" = "rc=0" ] && ok "malformed Skill payload -> no opinion" || no "malformed: $out"

total=$((pass + fail))
echo "session-state tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
