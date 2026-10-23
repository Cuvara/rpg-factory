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
jq -e '(.hookSpecificOutput | has("permissionDecision") | not) and (.hookSpecificOutput.updatedInput.skill == "rpg-factory:factory-core")
        and (.hookSpecificOutput.additionalContext | startswith("rpg-factory advisory (high)"))' <<<"$sk" >/dev/null \
  && grep -qx factory-core <<<"$(python3 -B "$SESS" --skills adv-tech)" && ok "tech skill before factory-core: auto-corrected to factory-core, no decision (recorded)" || no "tech skill: ${sk:0:200}"
sk=$(jq -cn --arg d "$SERVER" '{tool_name:"Skill",tool_input:{skill:"rpg-factory:go-backend"},cwd:$d,session_id:"adv-tech"}' | python3 -B "$SESS" --skill)
jq -e '(.hookSpecificOutput | has("permissionDecision") | not) and (.hookSpecificOutput | has("updatedInput") | not)
        and (.hookSpecificOutput.additionalContext | test("This call continues"))' <<<"$sk" >/dev/null \
  && grep -qx go-backend <<<"$(python3 -B "$SESS" --skills adv-tech)" && ok "tech skill before its lead: advisory, the call runs as requested (recorded)" || no "tech skill 2nd: ${sk:0:200}"

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

# ---- 1.0.5 robustness: parallel Skill calls, atomic MODE, safe session ids, unwritable state
skpl() { jq -cn --arg sk "$1" --arg s "$2" --arg d "$SERVER" --arg a "${3:-x}" '{tool_name:"Skill",tool_input:{skill:$sk,args:$a},cwd:$d,session_id:$s}'; }
# 20 parallel early tech-skill calls: exactly one is auto-corrected, every call is recorded (no lost lines)
# (the processes import the hook first and start together on a go-file, so the race window is really hit)
python3 -B - "$ROOT/scripts" "$TMP" <<'PY'
import json, os, subprocess, sys, time
code = ("import io, json, os, sys, time; sys.path.insert(0, %r); import factory_session as fs\n"
        "fs.load_registry(); fs.guard\n"
        "while not os.path.exists(%r): time.sleep(0.001)\n"
        "out = io.StringIO(); sys.stdout = out\n"
        "fs.skill_hook({'tool_name': 'Skill', 'tool_input': {'skill': 'rpg-factory:go-backend', 'args': 'x'}, 'session_id': 'par-tech'})\n"
        "open(sys.argv[1], 'w').write(out.getvalue())\n") % (sys.argv[1], os.path.join(sys.argv[2], "par-go"))
ps = [subprocess.Popen([sys.executable, "-B", "-c", code, os.path.join(sys.argv[2], f"par-{i}.out")]) for i in range(20)]
time.sleep(3)  # every process is waiting on the go-file
open(os.path.join(sys.argv[2], "par-go"), "w").close()
for p in ps:
    p.wait()
PY
swaps=$(cat "$TMP"/par-*.out | grep -c '"updatedInput"')
[ "$swaps" = 1 ] && ok "20 parallel tech calls before factory-core: exactly one auto-correction" || no "parallel auto-corrections: $swaps"
sk_all=$(python3 -B "$SESS" --skills par-tech | tr -d '\r')
[ "$(grep -c . <<<"$sk_all")" = 20 ] && [ "$(grep -cx factory-core <<<"$sk_all")" = 1 ] && [ "$(grep -cx go-backend <<<"$sk_all")" = 19 ] \
  && ok "parallel calls: all 20 loads recorded (1 factory-core, 19 go-backend)" || no "parallel SKILLS: $(tr '\n' ' ' <<<"$sk_all")"
adv_all=$(python3 -B "$SESS" --advisories par-tech | tr -d '\r')
[ "$(grep -c . <<<"$adv_all")" = 20 ] && [ "$(grep -cx 'go-backend autocorrect factory-core' <<<"$adv_all")" = 1 ] \
  && [ "$(grep -cx 'go-backend warn lead-missing' <<<"$adv_all")" = 19 ] && ok "parallel calls: all 20 advisories recorded, one autocorrect" \
  || no "parallel ADVISORIES: $(tr '\n' ';' <<<"$adv_all")"
for i in $(seq 1 30); do python3 -B "$SESS" --skill <<<"$(skpl rpg-factory:server-services par-many)" >/dev/null & done; wait
[ "$(python3 -B "$SESS" --skills par-many | grep -c .)" = 30 ] && ok "30 parallel lead calls: 30 records" || no "30 parallel: $(python3 -B "$SESS" --skills par-many | grep -c .) records"
# sequential order is kept; legacy one-file logs of older sessions are still read
mkdir -p "$TMP/rpg-factory/legacy"; printf 'factory-core\nserver-services\n' > "$TMP/rpg-factory/legacy/SKILLS"; echo "go-backend warn lead-missing" > "$TMP/rpg-factory/legacy/ADVISORIES"
python3 -B "$SESS" --skill <<<"$(skpl rpg-factory:go-backend legacy)" >/dev/null
[ "$(python3 -B "$SESS" --skills legacy | tr -d '\r' | tr '\n' ' ')" = "factory-core server-services go-backend " ] \
  && [ "$(python3 -B "$SESS" --advisories legacy | tr -d '\r')" = "go-backend warn lead-missing" ] \
  && ok "legacy SKILLS / ADVISORIES files read, a lead in them counts" || no "legacy: $(python3 -B "$SESS" --skills legacy | tr '\n' ' ')"
# the readers find a session whose hooks resolved the other scratch root (persistent()/tmp instead of $TMPDIR)
mkdir -p "$TMP/state/tmp/other-root"; printf 'unity-dots warn lead-missing\n' > "$TMP/state/tmp/other-root/ADVISORIES"
[ "$(python3 -B "$SESS" --advisories other-root | tr -d '\r')" = "unity-dots warn lead-missing" ] \
  && ok "--advisories reads a session written under the persistent()/tmp root" || no "other-root advisories: $(python3 -B "$SESS" --advisories other-root)"
# a bare registry skill name is this plugin's skill (recorded and gated); unknown bare names are ignored
o=$(python3 -B "$SESS" --skill <<<"$(skpl go-backend bare)")
jq -e '.hookSpecificOutput.updatedInput.skill == "rpg-factory:factory-core"' <<<"$o" >/dev/null && [ "$(python3 -B "$SESS" --skills bare | tr -d '\r')" = factory-core ] \
  && ok "bare 'go-backend': gated like rpg-factory:go-backend" || no "bare name: ${o:0:200}"
o=$(python3 -B "$SESS" --skill <<<"$(skpl no-such-skill bare2)"); [ -z "$o" ] && [ -z "$(python3 -B "$SESS" --skills bare2)" ] \
  && ok "bare unknown skill name: no opinion, nothing recorded" || no "bare unknown: $o"
# MODE is replaced atomically: concurrent writers and readers never see a torn value
python3 -B - "$ROOT/scripts" <<'PY' && ok "MODE: 4 writers x 150 + reader, no torn read" || no "MODE torn read"
import os, subprocess, sys
sys.path.insert(0, sys.argv[1]); import factory_session as fs
sd = fs.session_dir("mode-race")
code = ("import sys; sys.path.insert(0, %r); import factory_session as fs\nsd = fs.session_dir('mode-race')\n"
        "for i in range(150):\n    try: fs.write_mode(sd, sys.argv[1])\n    except OSError: pass\n") % sys.argv[1]
ps = [subprocess.Popen([sys.executable, "-B", "-c", code, m]) for m in ("plan", "analyze", "review", "implement")]
bad = set()
while any(p.poll() is None for p in ps):
    v = fs.read(os.path.join(sd, "MODE"))
    if v is not None and v not in fs.MODES:
        bad.add(v)
leftover = [f for f in os.listdir(sd) if f.endswith(".tmp")]
print("torn:", bad, "tmp left:", leftover) if bad or leftover else None
sys.exit(1 if bad or leftover else 0)
PY
# mode detection: only a command that RUNS the routing script declares a mode; a phrase that only says
# "do not implement" is no declaration
python3 -B - "$ROOT/scripts" "$SERVER" <<'PY' && ok "mode recorded only when factory-context.sh / context.py actually runs" || no "mode detection"
import sys; sys.path.insert(0, sys.argv[1]); import factory_session as fs
cases = [("grep -n factory-context.sh --mode review README.md", None), ("echo factory-context.sh --mode plan", None),
         ("cat scripts/factory-context.sh --mode plan", None), ("bash scripts/factory-context.sh --mode plan --repo server", "plan"),
         ("scripts/factory-context.sh --mode=review", "review"), ("python3 -B scripts/lib/context.py --mode analyze", "analyze"),
         ("cd /x && bash \"C:/p/scripts/factory-context.sh\" --repo server --mode validate", "validate")]
bad = []
for cmd, want in cases:
    got = fs.record_mode({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": sys.argv[2], "session_id": "mode-detect"})
    if got != want:
        bad.append((cmd, want, got))
for args, want in [("Do not implement anything yet, just look", None), ("don't implement it", None), ("plan only", "plan"),
                   ("mode: plan", "plan"), ("analyze only", "analyze"), ("review only", "review"), ("validate only", "validate")]:
    if fs.mode_from_text(args) != want:
        bad.append((args, want, fs.mode_from_text(args)))
print(bad) if bad else None
sys.exit(1 if bad else 0)
PY
# session ids: one safe path component, distinct ids stay distinct, a plain (UUID) id is unchanged
python3 -B - "$ROOT/scripts/lib" <<'PY' && ok "session_key: '..', '.', '', long, '/', unicode -> safe and distinct; UUID unchanged" || no "session_key"
import os, re, sys; sys.path.insert(0, sys.argv[1]); import fstate
uuid = "3f2b8c1e-9a4d-4e7b-8f00-123456789abc"
ids = ["..", ".", "", None, "x" * 300, "a/b", "a:b", "a_b", "s\u00e9", "s\u00e8", "../../etc", "C:\\x", "-rf"]
keys = [fstate.session_key(i) for i in ids]
ok = fstate.session_key(uuid) == uuid and fstate.session_key("default") == "default" == fstate.session_key("")
ok = ok and all(re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}", k) for k in keys)
ok = ok and len(set(k for i, k in zip(ids, keys) if i not in ("", None))) == len(ids) - 2
print(list(zip(ids, keys))) if not ok else None
sys.exit(0 if ok else 1)
PY
pl=$(jq -cn --arg d "$SERVER" '{tool_name:"Skill",tool_input:{skill:"rpg-factory:factory-core",args:"plan only"},cwd:$d,session_id:".."}')
python3 -B "$SESS" --skill <<<"$pl" >/dev/null
[ ! -e "$TMP/MODE" ] && [ -n "$(ls "$TMP"/rpg-factory/s-*/MODE 2>/dev/null)" ] && ok "session id '..': state stays inside the scratch root" || no "session id '..' escaped"
# the advisory and the correction are never lost because the session log cannot be written (L4)
mkdir -p "$TMP/rpg-factory/nolog/SKILLS" "$TMP/rpg-factory/nolog/ADVISORIES"; touch "$TMP/rpg-factory/nolog/SKILLS.d" "$TMP/rpg-factory/nolog/ADVISORIES.d"
o=$(python3 -B "$SESS" --skill <<<"$(skpl rpg-factory:go-backend nolog)"; echo "rc=$?")
jq -e '.hookSpecificOutput.updatedInput.skill == "rpg-factory:factory-core"' <<<"${o%rc=*}" >/dev/null && [ "${o##*rc=}" = 0 ] \
  && ok "logs unwritable: the auto-correction is still returned, exit 0" || no "logs unwritable: $o"
touch "$TMP/rpg-factory/nostate"
o=$(python3 -B "$SESS" --skill <<<"$(skpl rpg-factory:go-backend nostate)"; echo "rc=$?")
jq -e '(.hookSpecificOutput.additionalContext | startswith("rpg-factory advisory (high)")) and (.hookSpecificOutput | has("updatedInput") | not)' <<<"${o%rc=*}" >/dev/null \
  && [ "${o##*rc=}" = 0 ] && ok "session dir unusable: advisory still returned (no correction without state), exit 0" || no "no state: $o"
# scratch(): a candidate whose rpg-factory/ cannot be created is skipped (L5); persistent() is absolute with no HOME (L6)
mkdir -p "$TMP/blocked"; touch "$TMP/blocked/rpg-factory"
r=$(TMPDIR="$TMP/blocked" python3 -B -c "import sys; sys.path.insert(0,'$ROOT/scripts/lib'); import fstate, os; r=fstate.scratch(); assert os.path.isdir(r), r; print(r)" 2>&1)
is_abs "$r" && [ "$(fwd "$r")" != "$TMP/blocked/rpg-factory" ] && ok "scratch(): \$TMPDIR/rpg-factory is a file -> next candidate ($r)" || no "scratch fallback: $r"
r=$(env -u RPG_FACTORY_STATE_DIR -u XDG_STATE_HOME HOME=rel USERPROFILE=rel HOMEDRIVE= HOMEPATH= python3 -B -c "import sys; sys.path.insert(0,'$ROOT/scripts/lib'); import fstate; print(fstate.persistent())" 2>&1)
is_abs "$r" && ok "persistent(): relative HOME -> absolute ($r)" || no "persistent fallback: $r"
# atomic state files: a Windows sharing lock longer than the old fixed retry count (~0.36 s read, ~0.3 s replace)
# is waited out (time budget), never read as a missing record; elsewhere a PermissionError keeps the short count
mkdir -p "$TMP/lockt"
python3 -B - "$ROOT/scripts/lib" "$TMP/lockt" <<'PY' && ok "fstate: a 0.6 s Windows lock -> read_json gets the record, write_text succeeds; non-Windows unchanged" || no "fstate lock retry budget"
import builtins, os, sys, time; sys.path.insert(0, sys.argv[1]); import fstate
path = os.path.join(sys.argv[2], "rec.json"); fstate.write_json(path, {"state": "PASS"})
real_open, real_replace, bad = builtins.open, os.replace, []
def locked(fn, until, match):
    def f(*a, **k):
        if match(a) and time.monotonic() < until[0]:
            raise PermissionError(13, "sharing violation (simulated)")
        return fn(*a, **k)
    return f
until = [0.0]
fstate.open = locked(real_open, until, lambda a: a[0] == path)
os.replace = locked(real_replace, until, lambda a: a[1] == path)
try:
    for win in (True, False):
        fstate._WINDOWS = win
        until[0] = time.monotonic() + 0.6; r = fstate.read_json(path, default="MISSING")
        if (r != {"state": "PASS"}) if win else (r != "MISSING"): bad.append(("read", win, r))
        until[0] = time.monotonic() + 0.6
        try:
            fstate.write_json(path, {"state": "FAIL"}); w = "ok"
        except PermissionError:
            w = "raised"
        if w != ("ok" if win else "raised"): bad.append(("write", win, w))
    fstate._WINDOWS = True  # a lock that never ends is still bounded: default after the budget
    until[0] = time.monotonic() + 60; t0 = time.monotonic(); r = fstate.read_json(path, default="MISSING")
    if r != "MISSING" or not 1.5 < time.monotonic() - t0 < 5: bad.append(("endless", r, time.monotonic() - t0))
finally:
    del fstate.open; os.replace = real_replace
left = [f for f in os.listdir(sys.argv[2]) if f.endswith(".tmp")]
print(bad, left) if bad or left else None
sys.exit(1 if bad or left else 0)
PY

total=$((pass + fail))
echo "session-state tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
