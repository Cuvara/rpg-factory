#!/usr/bin/env bash
# Tripwire tests: real commands between the real --pre and --post hooks, in a throwaway
# workspace (never the real repos). Each case: expected "trip" or "clean".
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TW="$ROOT/scripts/tripwire.py"; GUARD="$ROOT/scripts/git-guard.py"
TMP="$(mktemp -d -p /tmp)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
export TMPDIR="$TMP" RPG_FACTORY_WORKSPACE="$TMP/ws" CLAUDE_PLUGIN_ROOT="$ROOT" RPG_FACTORY_STATE_DIR="$TMP/state"
WS="$TMP/ws"; SERVER="$WS/rpg-mmo-server"; CLIENT="$WS/IndieRPGMMOAdventure"
mkdir -p "$SERVER/backend" "$CLIENT/ProjectSettings"
touch "$SERVER/backend/TEAM.md" "$CLIENT/ProjectSettings/ProjectVersion.txt"
gc() { git -C "$1" -c user.email=t@t -c user.name=t "${@:2}"; }
for r in "$SERVER" "$CLIENT"; do git -C "$r" init -q -b develop; gc "$r" add -A; gc "$r" commit -qm init; done
git init -q --bare "$TMP/remote.git"; git -C "$SERVER" remote add origin "$TMP/remote.git"; gc "$SERVER" push -q origin develop
echo "user work" > "$CLIENT/UserScene.unity"           # pre-existing untracked user file (baseline)
# a submodule with uncommitted user work inside it (like the client's com.gdk.*)
SUBSRC="$TMP/gdk-src"; git init -q -b main "$SUBSRC"; for i in 1 2 3 4 5; do echo "v$i" > "$SUBSRC/f$i.cs"; done; gc "$SUBSRC" add -A; gc "$SUBSRC" commit -qm s
gc "$CLIENT" -c protocol.file.allow=always submodule add -q "$SUBSRC" Packages/com.gdk.core >/dev/null 2>&1; gc "$CLIENT" commit -qam "add sub"
for i in 1 2 3 4 5; do echo "user edit $i" >> "$CLIENT/Packages/com.gdk.core/f$i.cs"; done
pass=0; fail=0; n=0

run_case() { # expected cwd command
  local expected="$1" cwd="$2" cmd="$3" sid out got
  n=$((n + 1)); sid="case$n"
  local payload; payload=$(jq -cn --arg c "$cmd" --arg d "$cwd" --arg s "$sid" '{tool_name:"Bash",tool_input:{command:$c},cwd:$d,session_id:$s}')
  python3 -B "$TW" --pre <<<"$payload"
  (cd "$cwd" && bash -c "$cmd") >/dev/null 2>&1
  out=$(python3 -B "$TW" --post <<<"$payload")
  got=$([ -n "$out" ] && echo trip || echo clean)
  if [ "$got" = "$expected" ]; then pass=$((pass + 1)); echo "PASS  $expected  $cmd"
  else fail=$((fail + 1)); echo "FAIL  expected=$expected got=$got  $cmd"; echo "      $out" | head -c 400; echo; fi
}

# a helper script the text guard cannot see into
cat > "$TMP/sneaky.sh" <<'EOF'
#!/usr/bin/env bash
case "$1" in
  tag)    git tag v9.9.9 ;;
  commit) git -c user.email=t@t -c user.name=t commit -q --allow-empty -m sneaky ;;
  push)   git -c user.email=t@t -c user.name=t commit -q --allow-empty -m p && git push -q origin develop ;;
  reset)  git reset -q --hard HEAD~1 ;;
  switch) git switch -q -c other ;;
  stash)  echo x >> README && git add README && git stash -q ;;
esac
EOF
chmod +x "$TMP/sneaky.sh"
printf '#!/usr/bin/env bash\nsleep 1; git -C Packages/com.gdk.core checkout -- .\n' > "$TMP/sneaky-sub.sh"; chmod +x "$TMP/sneaky-sub.sh"
gc "$SERVER" commit -q --allow-empty -m second

run_case trip  "$SERVER" "$TMP/sneaky.sh tag"
run_case trip  "$SERVER" "python3 -c 'import subprocess; subprocess.run([\"git\",\"tag\",\"v8\"])'"
run_case trip  "$SERVER" "$TMP/sneaky.sh commit"
run_case trip  "$SERVER" "$TMP/sneaky.sh push"
run_case trip  "$SERVER" "$TMP/sneaky.sh reset"
run_case trip  "$SERVER" "$TMP/sneaky.sh switch"
git -C "$SERVER" switch -q develop
run_case trip  "$SERVER" "$TMP/sneaky.sh stash"
run_case trip  "$CLIENT" "rm -f UserScene.unity"
echo "user work" > "$CLIENT/UserScene.unity"
run_case trip  "$CLIENT" "$TMP/sneaky-sub.sh"
# legitimate, visible git operations do not trip (the guard already judged them)
run_case clean "$SERVER" "git switch -q -c feat/server/x"
run_case clean "$SERVER" "git -c user.email=t@t -c user.name=t commit -q --allow-empty -m visible"
run_case clean "$SERVER" "git switch -q develop"
run_case clean "$SERVER" "echo hello > $TMP/scratch.txt"
run_case clean "$CLIENT" "ls -la"
# a worktree: the script commits inside it
git -C "$SERVER" worktree add -q "$WS/srv-wt" -b feat/server/wt
run_case trip  "$WS/srv-wt" "$TMP/sneaky.sh commit"
run_case clean "$WS/srv-wt" "git -c user.email=t@t -c user.name=t commit -q --allow-empty -m ok"

# latch: after a trip, the guard denies mutating commands but allows read-only ones
sid=latchcase
p=$(jq -cn --arg d "$SERVER" --arg s "$sid" '{tool_name:"Bash",tool_input:{command:"'"$TMP"'/sneaky.sh tag"},cwd:$d,session_id:$s}')
git -C "$SERVER" tag -d v9.9.9 >/dev/null 2>&1; git -C "$SERVER" tag -d v8 >/dev/null 2>&1
python3 -B "$TW" --pre <<<"$p"; (cd "$SERVER" && "$TMP/sneaky.sh" tag); python3 -B "$TW" --post <<<"$p" >/dev/null
dec() { local o; o=$(jq -cn --arg c "$1" --arg d "$SERVER" --arg s "$sid" '{tool_name:"Bash",tool_input:{command:$c},cwd:$d,session_id:$s}' | python3 -B "$GUARD"); jq -r '.hookSpecificOutput.permissionDecision // "allow"' <<<"${o:-{\}}"; }
chk() { local e="$1" c="$2" g; g=$(dec "$c"); if [ "$g" = "$e" ]; then pass=$((pass + 1)); echo "PASS  latch $e  $c"; else fail=$((fail + 1)); echo "FAIL  latch expected=$e got=$g  $c"; fi; }
chk deny  "touch x"
chk deny  "git -c user.email=t@t -c user.name=t commit --allow-empty -m y"
chk deny  "python3 $TW --ack"
chk allow "git status"
chk allow "git log --oneline -3"
python3 -B "$TW" --ack "$sid" >/dev/null
chk allow "touch x"

# ---- v0.4: a STOP survives the session (crash / closed terminal) until the user acks
python3 -B "$TW" --ack >/dev/null                                   # clean slate
p=$(jq -cn --arg d "$SERVER" '{tool_name:"Bash",tool_input:{command:"'"$TMP"'/sneaky.sh tag"},cwd:$d,session_id:"crashed-A"}')
git -C "$SERVER" tag -d v9.9.9 >/dev/null 2>&1
python3 -B "$TW" --pre <<<"$p"; (cd "$SERVER" && "$TMP/sneaky.sh" tag); python3 -B "$TW" --post <<<"$p" >/dev/null
rm -rf "$TMP/rpg-factory/crashed-A"                                  # session A's scratch is gone (crash, tmp cleaned)
sid=fresh-B
chk deny  "touch y"                                                  # new session B is still latched
chk allow "git status"
ss=$(jq -cn --arg d "$SERVER" '{cwd:$d,session_id:"fresh-B"}' | python3 -B "$TW" --session-start | jq -r '.hookSpecificOutput.additionalContext // ""')
case "$ss" in *"earlier session"*crashed-A*"--ack"*) pass=$((pass + 1)); echo "PASS  SessionStart reports the unresolved STOP from crashed-A";;
  *) fail=$((fail + 1)); echo "FAIL  SessionStart message: $ss";; esac
st=$(python3 -B "$TW" --status); case "$st" in *"workspace $WS: LATCHED"*) pass=$((pass + 1)); echo "PASS  --status lists the workspace latch";; *) fail=$((fail + 1)); echo "FAIL  status: $st";; esac
python3 -B "$TW" --ack >/dev/null
chk allow "touch y"
[ -z "$(ls "$TMP/state/latch" 2>/dev/null)" ] && { pass=$((pass + 1)); echo "PASS  --ack removed the workspace latch"; } || { fail=$((fail + 1)); echo "FAIL  latch file left"; }
git -C "$SERVER" tag -d v9.9.9 >/dev/null 2>&1

# ---- v0.4: state paths never resolve relative to the cwd, whatever TMPDIR is
PROBE="$TMP/cwdprobe"; mkdir -p "$PROBE"
for td in "" "relative/dir" "/nonexistent/x" "$TMP/tmpok"; do
  mkdir -p "$TMP/tmpok"
  pl=$(jq -cn --arg d "$SERVER" '{tool_name:"Bash",tool_input:{command:"touch /tmp/rpgf-x"},cwd:$d,session_id:"tmpdir-case"}')
  (cd "$PROBE" && TMPDIR="$td" python3 -B "$TW" --pre <<<"$pl" && TMPDIR="$td" python3 -B "$TW" --post <<<"$pl" >/dev/null
   TMPDIR="$td" python3 -B -c "import sys; sys.path.insert(0,'$ROOT/scripts/lib'); import fstate, os; r=fstate.scratch(); assert os.path.isabs(r), r; print(r)" > "$TMP/root.txt")
  root=$(cat "$TMP/root.txt")
  if [ -z "$(ls -A "$PROBE")" ] && [ "${root:0:1}" = "/" ]; then pass=$((pass + 1)); echo "PASS  TMPDIR='$td' -> $root (nothing written in the cwd)"
  else fail=$((fail + 1)); echo "FAIL  TMPDIR='$td' root=$root cwd has: $(ls -A "$PROBE")"; fi
done
rm -rf /tmp/rpg-factory/tmpdir-case                                   # fallback cases used the real /tmp: clean up
(cd "$PROBE" && env -u TMPDIR python3 -B -c "import sys; sys.path.insert(0,'$ROOT/scripts/lib'); import fstate; print(fstate.scratch())") | grep -q '^/' && { pass=$((pass + 1)); echo "PASS  TMPDIR unset -> absolute"; } || { fail=$((fail + 1)); echo "FAIL  TMPDIR unset"; }

# ---- v0.4: embedded package clones (gitignored nested repos inside the client) are user state
CLONE="$CLIENT/Packages/com.cuvara.dots"
echo "Packages/com.cuvara.*/" >> "$CLIENT/.gitignore"; gc "$CLIENT" add .gitignore; gc "$CLIENT" commit -qm ignore
git init -q -b main "$CLONE"; for i in $(seq 1 30); do echo "v$i" > "$CLONE/f$i.cs"; done; gc "$CLONE" add -A; gc "$CLONE" commit -qm c
for i in $(seq 1 30); do echo "user wip $i" >> "$CLONE/f$i.cs"; done          # 30 dirty files of user work
printf '#!/usr/bin/env bash\ngit -C Packages/com.cuvara.dots checkout -q -- .\n' > "$TMP/sneaky-clone.sh"; chmod +x "$TMP/sneaky-clone.sh"
cstart() { jq -cn --arg d "$CLIENT" --arg s "$1" '{cwd:$d,session_id:$s}' | python3 -B "$TW" --session-start >/dev/null; }
cstart clone1
run_clone() { # expected command
  local pl out got; pl=$(jq -cn --arg c "$2" --arg d "$CLIENT" '{tool_name:"Bash",tool_input:{command:$c},cwd:$d,session_id:"clone1"}')
  python3 -B "$TW" --pre <<<"$pl"; (cd "$CLIENT" && bash -c "$2") >/dev/null 2>&1; out=$(python3 -B "$TW" --post <<<"$pl")
  got=$([ -n "$out" ] && echo trip || echo clean)
  if [ "$got" = "$1" ]; then pass=$((pass + 1)); echo "PASS  clone $1  $2"; else fail=$((fail + 1)); echo "FAIL  clone expected=$1 got=$got  $2 :: ${out:0:300}"; fi
}
echo "more user wip" >> "$CLONE/f3.cs"                                     # the user edits in Unity between commands
run_clone clean "ls Packages"
run_clone trip  "$TMP/sneaky-clone.sh"
python3 -B "$TW" --ack >/dev/null
for i in $(seq 1 30); do echo "user wip $i" >> "$CLONE/f$i.cs"; done
cstart clone2
run_clone2() { local pl out; pl=$(jq -cn --arg c "$1" --arg d "$CLIENT" '{tool_name:"Bash",tool_input:{command:$c},cwd:$d,session_id:"clone2"}')
  python3 -B "$TW" --pre <<<"$pl"; (cd "$CLIENT" && bash -c "$1") >/dev/null 2>&1; python3 -B "$TW" --post <<<"$pl"; }
out=$(run_clone2 "git -C Packages/com.cuvara.dots -c user.email=t@t -c user.name=t commit -qam wip")
[ -z "$out" ] && { pass=$((pass + 1)); echo "PASS  clone clean  visible git commit inside the clone"; } || { fail=$((fail + 1)); echo "FAIL  visible clone commit tripped: ${out:0:200}"; }
out=$(run_clone2 "cd Packages/com.cuvara.dots && python3 -c 'import subprocess; subprocess.run([\"git\",\"tag\",\"v1\"])'")
case "$out" in *"tag v1 created"*) pass=$((pass + 1)); echo "PASS  clone trip   tag created in the clone by a script";; *) fail=$((fail + 1)); echo "FAIL  clone tag: ${out:0:200}";; esac
python3 -B "$TW" --ack >/dev/null

# ---- v0.4 regression: the FIRST modified tracked file and paths with spaces are part of the baseline
# (v0.3 stripped the first porcelain line's leading space and lost the first character of its path)
python3 -B "$TW" --ack >/dev/null
echo "readme" > "$SERVER/README"; mkdir -p "$SERVER/My Folder"; echo a > "$SERVER/My Folder/a b.txt"
gc "$SERVER" add README "My Folder"; gc "$SERVER" commit -qm files
echo "user edit" >> "$SERVER/README"; echo "user edit" >> "$SERVER/My Folder/a b.txt"
jq -cn --arg d "$SERVER" '{cwd:$d,session_id:"firstfile"}' | python3 -B "$TW" --session-start >/dev/null
bl=$(cat "$TMP/rpg-factory/firstfile/baseline.json")
jq -e --arg t "$SERVER" '.[$t] | has("README") and has("My Folder/a b.txt") and (.["README"] | type == "array")' <<<"$bl" >/dev/null \
  && { pass=$((pass + 1)); echo "PASS  baseline keeps the first modified file and a path with spaces exactly"; } \
  || { fail=$((fail + 1)); echo "FAIL  baseline keys: $(jq -c --arg t "$SERVER" '.[$t] | keys' <<<"$bl")"; }
pl=$(jq -cn --arg d "$SERVER" '{tool_name:"Bash",tool_input:{command:"sh -c \"echo x > README\""},cwd:$d,session_id:"firstfile"}')
python3 -B "$TW" --pre <<<"$pl"; (cd "$SERVER" && sh -c "echo x > README"); out=$(python3 -B "$TW" --post <<<"$pl")
case "$out" in *"pre-existing user file README was modified"*) pass=$((pass + 1)); echo "PASS  overwriting the first baseline file trips";; *) fail=$((fail + 1)); echo "FAIL  first-file overwrite: ${out:0:200}";; esac
python3 -B "$TW" --ack >/dev/null
[ -f "$TMP/rpg-factory/firstfile/baseline.json" ] && jq -e --arg t "$SERVER" '.[$t] | has("README")' "$TMP/rpg-factory/firstfile/baseline.json" >/dev/null \
  && { pass=$((pass + 1)); echo "PASS  --ack rebuilds the baseline immediately (reviewed state protected before the next command)"; } \
  || { fail=$((fail + 1)); echo "FAIL  no baseline after --ack"; }
gc "$SERVER" checkout -q -- README "My Folder"

# performance: pre+post overhead for a mutating command vs a read-only command, 2 repos
t0=$(date +%s%N); for i in 1 2 3 4 5; do p=$(jq -cn --arg d "$SERVER" --arg s perf '{tool_name:"Bash",tool_input:{command:"touch /tmp/rpgf-perf"},cwd:$d,session_id:$s}'); python3 -B "$TW" --pre <<<"$p"; python3 -B "$TW" --post <<<"$p" >/dev/null; done; t1=$(date +%s%N)
t2=$(date +%s%N); for i in 1 2 3 4 5; do p=$(jq -cn --arg d "$SERVER" --arg s perf '{tool_name:"Bash",tool_input:{command:"git status"},cwd:$d,session_id:$s}'); python3 -B "$TW" --pre <<<"$p"; python3 -B "$TW" --post <<<"$p" >/dev/null; done; t3=$(date +%s%N)
echo "perf: mutating pre+post avg $(( (t1 - t0) / 5000000 )) ms; read-only pre+post avg $(( (t3 - t2) / 5000000 )) ms (fixture, 2 repos)"

total=$((pass + fail))
echo "tripwire tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
