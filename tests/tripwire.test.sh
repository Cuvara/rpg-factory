#!/usr/bin/env bash
# Tripwire tests: real commands between the real --pre and --post hooks, in a throwaway
# workspace (never the real repos). Each case: expected "trip" or "clean".
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TW="$ROOT/scripts/tripwire.py"; GUARD="$ROOT/scripts/git-guard.py"
TMP="$(mktemp -d -p /tmp)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
export TMPDIR="$TMP" RPG_FACTORY_WORKSPACE="$TMP/ws" CLAUDE_PLUGIN_ROOT="$ROOT"
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

# performance: pre+post overhead for a mutating command vs a read-only command, 2 repos
t0=$(date +%s%N); for i in 1 2 3 4 5; do p=$(jq -cn --arg d "$SERVER" --arg s perf '{tool_name:"Bash",tool_input:{command:"touch /tmp/rpgf-perf"},cwd:$d,session_id:$s}'); python3 -B "$TW" --pre <<<"$p"; python3 -B "$TW" --post <<<"$p" >/dev/null; done; t1=$(date +%s%N)
t2=$(date +%s%N); for i in 1 2 3 4 5; do p=$(jq -cn --arg d "$SERVER" --arg s perf '{tool_name:"Bash",tool_input:{command:"git status"},cwd:$d,session_id:$s}'); python3 -B "$TW" --pre <<<"$p"; python3 -B "$TW" --post <<<"$p" >/dev/null; done; t3=$(date +%s%N)
echo "perf: mutating pre+post avg $(( (t1 - t0) / 5000000 )) ms; read-only pre+post avg $(( (t3 - t2) / 5000000 )) ms (fixture, 2 repos)"

total=$((pass + fail))
echo "tripwire tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
