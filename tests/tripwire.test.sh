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
  local payload; payload=$(jq -cn --arg c "$cmd" --arg d "$cwd" --arg s "$sid" --arg t "tu$n" '{tool_name:"Bash",tool_input:{command:$c},cwd:$d,session_id:$s,tool_use_id:$t}')
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
python3 -B "$TW" --ack >/dev/null                                   # the trips above are separate open events
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
case "$ss" in *"never cleared"*"session crashed-A"*"--ack"*) pass=$((pass + 1)); echo "PASS  SessionStart reports the unresolved STOP from crashed-A";;
  *) fail=$((fail + 1)); echo "FAIL  SessionStart message: $ss";; esac
st=$(python3 -B "$TW" --status); case "$st" in *"OPEN event "*"[workspace $WS, session crashed-A"*) pass=$((pass + 1)); echo "PASS  --status lists the workspace latch";; *) fail=$((fail + 1)); echo "FAIL  status: $st";; esac
python3 -B "$TW" --ack >/dev/null
chk allow "touch y"
[ -z "$(ls "$TMP"/state/latch/*/*.json 2>/dev/null)" ] && [ -n "$(ls "$TMP"/state/latch/*/acked/*.json 2>/dev/null)" ]   && { pass=$((pass + 1)); echo "PASS  --ack closed the workspace event and archived it (evidence kept)"; } || { fail=$((fail + 1)); echo "FAIL  open event left or nothing archived"; }
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

# ==== latch lifecycle (snapshot per tool call, events, ack) =========================================
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; }
hook() { # mode session tool_use_id("" = none) cwd command
  local pl; pl=$(jq -cn --arg c "$5" --arg d "$4" --arg s "$2" --arg t "$3" \
    '{tool_name:"Bash",tool_input:{command:$c},cwd:$d,session_id:$s} + (if $t == "" then {} else {tool_use_id:$t} end)')
  python3 -B "$TW" "$1" <<<"$pl"
}
call() { local out; hook --pre "$1" "$2" "$3" "$4"; (cd "$3" && bash -c "$4") >/dev/null 2>&1; hook --post "$1" "$2" "$3" "$4"; }
nopen() { ls "$TMP"/state/latch/*/*.json "$TMP"/state/latch/*.json 2>/dev/null | wc -l; }
openids() { for f in "$TMP"/state/latch/*/*.json; do [ -f "$f" ] && basename "$f" .json; done; }
gdec() { local o; o=$(jq -cn --arg c "$3" --arg d "$2" --arg s "$1" '{tool_name:"Bash",tool_input:{command:$c},cwd:$d,session_id:$s}' \
  | python3 -B "$GUARD"); jq -r '.hookSpecificOutput.permissionDecision // "allow"' <<<"${o:-{\}}"; }
python3 -B "$TW" --ack >/dev/null; git -C "$SERVER" switch -q develop 2>/dev/null

# 1. R1 regression: a denied call's snapshot (PreToolUse ran, PostToolUse never does) is never consumed by a
#    later read-only call - here another session creates a branch in between (the 2026-10-14 false STOP)
hook --pre s-r1 tu-denied "$SERVER" "touch $TMP/denied.txt"                        # denied by the guard: no post
gc "$SERVER" branch backup/other-session-work                                      # another session / the user
out=$(hook --post s-r1 tu-status "$SERVER" "python3 $TW --status")
[ -z "$out" ] && [ "$(nopen)" -eq 0 ] && ok "R1: read-only --status after a denied call: no STOP, no event" \
  || no "R1: stale snapshot consumed: ${out:0:300}"
out=$(call s-r1 tu-next "$SERVER" "touch $TMP/next.txt")
[ -z "$out" ] && ok "R1: the next mutating call compares only its own window" || no "R1: next call tripped: ${out:0:200}"
# the same without tool_use_id (older Claude Code): a snapshot of another command is discarded
hook --pre s-r1b "" "$SERVER" "touch $TMP/denied2.txt"
gc "$SERVER" branch backup/other-session-work-2
out=$(hook --post s-r1b "" "$SERVER" "git status")
[ -z "$out" ] && [ "$(nopen)" -eq 0 ] && ok "R1 (no tool_use_id): a mismatched command's snapshot is discarded" || no "R1 nokey: ${out:0:200}"
# unconsumed snapshots are pruned after SNAP_TTL
touch -d '3 hours ago' "$TMP/rpg-factory/s-r1/pre-tu-denied.json"
hook --pre s-r1 tu-prune "$SERVER" "touch $TMP/p.txt"
[ ! -e "$TMP/rpg-factory/s-r1/pre-tu-denied.json" ] && [ -e "$TMP/rpg-factory/s-r1/pre-tu-prune.json" ] \
  && ok "stale snapshot of a denied call pruned after 2 h" || no "stale snapshot not pruned: $(ls "$TMP/rpg-factory/s-r1")"
hook --post s-r1 tu-prune "$SERVER" "touch $TMP/p.txt" >/dev/null

# 2. overlapping calls of one session keep distinct snapshots; each compares its own window
hook --pre s-ov tu-A "$SERVER" "touch $TMP/a.txt"
hook --pre s-ov tu-B "$SERVER" "touch $TMP/b.txt"
[ -e "$TMP/rpg-factory/s-ov/pre-tu-A.json" ] && [ -e "$TMP/rpg-factory/s-ov/pre-tu-B.json" ] \
  && ok "overlapping calls: two snapshot files (pre-tu-A, pre-tu-B)" || no "overlap files: $(ls "$TMP/rpg-factory/s-ov")"
outA=$(hook --post s-ov tu-A "$SERVER" "touch $TMP/a.txt")
(cd "$SERVER" && "$TMP/sneaky.sh" tag)                                              # inside B's window only
outB=$(hook --post s-ov tu-B "$SERVER" "touch $TMP/b.txt")
[ -z "$outA" ] && [ ! -e "$TMP/rpg-factory/s-ov/pre-tu-A.json" ] && case "$outB" in *"tag v9.9.9 created"*) true;; *) false;; esac \
  && ok "overlapping calls: A clean, B (whose window held the tag) trips" || no "overlap: A=${outA:0:120} B=${outB:0:200}"
python3 -B "$TW" --ack >/dev/null; gc "$SERVER" tag -d v9.9.9 >/dev/null

# 3. two concurrent sessions: two events, nothing overwritten; acking one leaves the other open
call s-c1 tu-1 "$SERVER" "$TMP/sneaky.sh tag" >/dev/null
call s-c2 tu-2 "$CLIENT" "$TMP/sneaky.sh commit" >/dev/null
ids=$(openids); id1=$(grep -l '"session": "s-c1"' "$TMP"/state/latch/*/*.json | xargs -n1 basename | sed 's/\.json$//')
[ "$(nopen)" -eq 2 ] && [ -n "$id1" ] && ok "two sessions -> two open events (no overwrite)" || no "events: $ids"
out=$(python3 -B "$TW" --ack "$id1"); rc=$?
[ $rc -eq 1 ] && case "$out" in *"still LATCHED"*) true;; *) false;; esac && [ "$(nopen)" -eq 1 ] \
  && grep -q '"session": "s-c2"' "$TMP"/state/latch/*/*.json && ok "ack of event A leaves B open (exit 1, still LATCHED)" \
  || no "ack A: rc=$rc ${out:0:300}"
[ "$(gdec s-c1 "$SERVER" "touch q")" = deny ] && ok "session A still denied while B's event is open (global scope)" || no "A not denied"
out=$(python3 -B "$TW" --ack); rc=$?
[ $rc -eq 0 ] && case "$out" in *"latch is now CLEAR"*) true;; *) false;; esac && ok "ack of the rest: exit 0, CLEAR" || no "ack rest: rc=$rc ${out:0:200}"
gc "$SERVER" tag -d v9.9.9 >/dev/null

# 4. visible git of another session explains ref changes in that repo; unseen git and tags never do
hook --pre s-x1 tu-x1 "$SERVER" "touch $TMP/x1.txt"
out2=$(call s-x2 tu-x2 "$SERVER" "git branch feat/server/other-session")
out1=$(hook --post s-x1 tu-x1 "$SERVER" "touch $TMP/x1.txt")
[ -z "$out1$out2" ] && [ "$(nopen)" -eq 0 ] && ok "concurrent session's visible git branch: no STOP in either session" || no "cross-session: ${out1:0:200}"
hook --pre s-x1 tu-x3 "$SERVER" "touch $TMP/x3.txt"
hook --pre s-x4 tu-x4 "$SERVER" "git branch feat/server/in-flight"; (cd "$SERVER" && git branch feat/server/in-flight)  # not finished yet
out1=$(hook --post s-x1 tu-x3 "$SERVER" "touch $TMP/x3.txt")
case "$out1" in *"in-flight created"*) ok "an unfinished (possibly denied) call of another session explains nothing";; *) no "in-flight: ${out1:0:200}";; esac
hook --post s-x4 tu-x4 "$SERVER" "git branch feat/server/in-flight" >/dev/null; python3 -B "$TW" --ack >/dev/null
hook --pre s-x1 tu-x5 "$SERVER" "touch $TMP/x5.txt"
call s-x6 tu-x6 "$SERVER" "git branch feat/server/x6 && $TMP/sneaky.sh tag" >/dev/null
out1=$(hook --post s-x1 tu-x5 "$SERVER" "touch $TMP/x5.txt")
case "$out1" in *"tag v9.9.9 created"*) ok "tags are never explained by another session's git";; *) no "tag excused: ${out1:0:200}";; esac
python3 -B "$TW" --ack >/dev/null; gc "$SERVER" tag -d v9.9.9 >/dev/null

# 5. independent worktrees: the event names the worktree; the latch stays global for the workspace (by design)
out=$(call s-wt1 tu-wt1 "$WS/srv-wt" "$TMP/sneaky.sh commit")
ev=$(cat "$TMP"/state/latch/*/*.json)
jq -e '([.repos[]] | any(. == "worktree:srv-wt")) and (.refs | length > 0) and (.command | test("sneaky"))' <<<"$ev" >/dev/null \
  && ok "worktree incident: event names worktree:srv-wt, the command and the ref values" || no "worktree event: ${ev:0:300}"
[ "$(gdec s-wt2 "$CLIENT" "touch y")" = deny ] && ok "a session in another repo/worktree is blocked too (global workspace latch)" || no "global scope"
python3 -B "$TW" --ack >/dev/null

# 6. approved stash path: a visible `git stash` is audited, not latched
gc "$SERVER" switch -q develop; echo "wip" >> "$SERVER/backend/TEAM.md"
out=$(call s-st tu-st1 "$SERVER" "git -c user.email=t@t -c user.name=t stash push -m 'rpg-factory: test' -- backend/TEAM.md")
sha=$(git -C "$SERVER" rev-parse -q --verify refs/stash)
[ -z "$out" ] && [ "$(nopen)" -eq 0 ] && grep -q "\"stash_after\": \"$sha\"" "$TMP"/state/audit/*.jsonl \
  && ok "visible git stash push: no STOP, audit line with the stash SHA" || no "stash audit: ${out:0:200} $(cat "$TMP"/state/audit/*.jsonl 2>/dev/null)"
out=$(call s-st tu-st2 "$SERVER" "git stash pop")
[ -z "$out" ] && grep -q "\"stash_before\": \"$sha\"" "$TMP"/state/audit/*.jsonl && grep -q wip "$SERVER/backend/TEAM.md" \
  && ok "visible git stash pop: audited (before SHA kept), change restored" || no "stash pop audit"
gc "$SERVER" checkout -q -- backend/TEAM.md
n0=$(cat "$TMP"/state/audit/*.jsonl | wc -l); echo "wt wip" >> "$WS/srv-wt/backend/TEAM.md"
out=$(call s-st tu-st3 "$WS/srv-wt" "git -c user.email=t@t -c user.name=t stash push -m 'rpg-factory: wt' -- backend/TEAM.md")
[ -z "$out" ] && [ "$(cat "$TMP"/state/audit/*.jsonl | wc -l)" -eq $((n0 + 1)) ] && ok "stash in a worktree: one audit line (shared refs/stash not doubled)" \
  || no "worktree stash audit: ${out:0:200} lines=$(cat "$TMP"/state/audit/*.jsonl | wc -l) n0=$n0"
call s-st tu-st4 "$WS/srv-wt" "git stash pop" >/dev/null; gc "$WS/srv-wt" checkout -q -- backend/TEAM.md

# 7. unexpected stash: event with the stash SHA and a recovery hint; then a sneaky drop stays recoverable
out=$(call s-us tu-us "$SERVER" "$TMP/sneaky.sh stash")
sha=$(git -C "$SERVER" rev-parse -q --verify refs/stash)
ev=$(cat "$TMP"/state/latch/*/*.json)
jq -e --arg s "$sha" '(.refs[] | .["refs/stash"][1] == $s) and (.recovery | any(test("stash show -p " + $s)))' <<<"$ev" >/dev/null \
  && ok "unexpected stash: event records the new stash SHA and how to inspect it" || no "stash event: ${ev:0:300}"
[ "$(gdec s-us "$SERVER" "git -c user.email=t@t -c user.name=t commit --allow-empty -m z")" = deny ] && ok "real incident: git commit denied" || no "commit not denied"
[ "$(gdec s-us "$SERVER" "git stash drop")" = deny ] && ok "real incident: git stash drop denied" || no "stash drop not denied"
for c in "git reflog show develop" "git stash show -p" "git branch --list 'backup/*'" "git stash list"; do
  [ "$(gdec s-us "$SERVER" "$c")" = allow ] && ok "investigation allowed while latched: $c" || no "denied while latched: $c"; done
[ "$(gdec s-us "$SERVER" "git reflog expire --expire=now --all")" = deny ] && ok "reflog expire denied while latched" || no "reflog expire allowed"
python3 -B "$TW" --ack >/dev/null
printf '#!/usr/bin/env bash\ngit stash drop -q\n' > "$TMP/sneaky-drop.sh"; chmod +x "$TMP/sneaky-drop.sh"
out=$(call s-dr tu-dr "$SERVER" "$TMP/sneaky-drop.sh")
old=$(jq -r '.refs[] | .["refs/stash"][0]' "$TMP"/state/latch/*/*.json)
[ "$old" = "$sha" ] && [ "$(git -C "$SERVER" rev-parse -q --verify refs/stash)" != "$sha" ] && ok "sneaky stash drop: event keeps the dropped SHA" || no "drop event old=$old"
gc "$SERVER" stash apply -q "$old" >/dev/null 2>&1; grep -q x "$SERVER/README" && ok "dropped stash recoverable from the event: git stash apply <sha>" || no "not recoverable"
python3 -B "$TW" --ack >/dev/null; gc "$SERVER" reset -q; rm -f "$SERVER/README"

# 8. an unrelated pre-existing stash: no false positive, and it stays
echo "user stash" >> "$SERVER/backend/TEAM.md"; gc "$SERVER" stash push -q -m "user's own"
out=$(call s-pe tu-pe1 "$SERVER" "ls")$(call s-pe tu-pe2 "$SERVER" "touch $TMP/pe.txt")$(call s-pe tu-pe3 "$SERVER" "git -c user.email=t@t -c user.name=t commit -q --allow-empty -m pe")
[ -z "$out" ] && [ "$(nopen)" -eq 0 ] && git -C "$SERVER" stash list | grep -q "user's own" \
  && ok "pre-existing user stash: no STOP, stash untouched" || no "pre-existing stash: ${out:0:200}"

# 9. ack failures are reported, never claimed as success
call s-af tu-af "$SERVER" "$TMP/sneaky.sh tag" >/dev/null
kd=$(dirname "$(ls "$TMP"/state/latch/*/*.json | head -1)")
if [ "$(id -u)" != 0 ]; then
  chmod 555 "$kd"; out=$(python3 -B "$TW" --ack); rc=$?; chmod 755 "$kd"
  [ $rc -eq 1 ] && case "$out" in *"NOT cleared"*"still LATCHED"*) true;; *) false;; esac && [ "$(nopen)" -eq 1 ] \
    && [ "$(gdec s-af "$SERVER" "touch f")" = deny ] && ok "unwritable latch dir: ack exits 1, NOT cleared, still latched" || no "ack failure: rc=$rc ${out:0:300}"
fi
echo '{not json' > "$kd/corrupt.json"
st=$(python3 -B "$TW" --status); case "$st" in *"UNREADABLE event file"*) ok "--status shows an unreadable event as open";; *) no "corrupt status: ${st:0:200}";; esac
python3 -B "$TW" --ack corrupt >/dev/null; [ -e "$kd/acked/corrupt.json" ] && ok "unreadable event acked by id is archived, not lost" || no "corrupt not archived"
out=$(python3 -B "$TW" --ack); rc=$?; [ $rc -eq 0 ] && ok "remaining event acked: exit 0" || no "ack rc=$rc"
gc "$SERVER" tag -d v9.9.9 >/dev/null
out=$(python3 -B - "$ROOT" <<'PY'
import sys, os
sys.path.insert(0, sys.argv[1] + "/scripts"); sys.argv = ["tripwire.py", "--ack"]
import tripwire
tripwire.open_events = lambda ws=None: (_ for _ in ()).throw(RuntimeError("disk on fire"))
sys.exit(tripwire.main())
PY
); rc=$?
[ $rc -eq 1 ] && case "$out" in "NOT cleared: RuntimeError: disk on fire") true;; *) false;; esac && ok "an ack that crashes exits 1 and says NOT cleared" || no "crash: rc=$rc $out"

# 10. repeated ack, unknown and invalid ids
out=$(python3 -B "$TW" --ack); rc=$?; [ $rc -eq 0 ] && [ "$out" = "no open tripwire events; latch is CLEAR" ] && ok "repeated ack: exit 0, CLEAR" || no "repeat: rc=$rc $out"
out=$(python3 -B "$TW" --ack 20990101T000000Z-abcdef); rc=$?; [ $rc -eq 1 ] && case "$out" in *"unknown event"*) true;; *) false;; esac && ok "unknown event id: exit 1" || no "unknown: rc=$rc $out"
out=$(python3 -B "$TW" --ack '../../etc'); rc=$?; [ $rc -eq 2 ] && ok "invalid id: exit 2" || no "invalid: rc=$rc $out"

# 11. an event created while an ack runs stays open (controlled interleaving, no timing)
call s-r1x tu-ra "$SERVER" "$TMP/sneaky.sh tag" >/dev/null
out=$(python3 -B - "$ROOT" "$SERVER" <<'PY'
import sys, json, os
sys.path.insert(0, sys.argv[1] + "/scripts"); sys.path.insert(0, sys.argv[1] + "/scripts/lib")
import tripwire, fstate
real = tripwire.archive_event
def racing(e):  # another session's STOP lands while this ack archives its snapshot of open events
    ws = e["data"]["workspace"]
    fstate.write_json(os.path.join(fstate.latch_dir(ws), "29990101T000000Z-racing.json"),
                      {"id": "29990101T000000Z-racing", "workspace": ws, "session": "s-late", "message": "late STOP"})
    tripwire.archive_event = real
    real(e)
tripwire.archive_event = racing
sys.exit(tripwire.ack([]))
PY
); rc=$?
[ $rc -eq 1 ] && case "$out" in *"still LATCHED: 29990101T000000Z-racing"*) true;; *) false;; esac && [ "$(openids)" = "29990101T000000Z-racing" ] \
  && ok "ack race: the event created during the ack stays open (exit 1)" || no "race: rc=$rc ${out:0:300}"
python3 -B "$TW" --ack >/dev/null; gc "$SERVER" tag -d v9.9.9 >/dev/null

# 12. legacy (<= 0.5.0) single-file latch: still blocks, migrates on ack without losing evidence
key=$(python3 -B -c "import sys; sys.path.insert(0,'$ROOT/scripts/lib'); import fstate; print(fstate.workspace_key('$WS'))")
mkdir -p "$TMP/state/latch"
jq -cn --arg w "$WS" '{workspace:$w,session:"old-0.5.0",at:"2026-10-14T22:29:09+0700",message:"[server] branch x moved"}' > "$TMP/state/latch/$key.json"
[ "$(gdec s-lg "$SERVER" "touch l")" = deny ] && ok "legacy latch file still blocks" || no "legacy not blocking"
st=$(python3 -B "$TW" --status); case "$st" in *"legacy-$key (legacy latch): [server] branch x moved"*) ok "--status lists the legacy latch";; *) no "legacy status: ${st:0:200}";; esac
out=$(python3 -B "$TW" --ack); rc=$?
[ $rc -eq 0 ] && [ ! -e "$TMP/state/latch/$key.json" ] && jq -e '.session == "old-0.5.0" and .message == "[server] branch x moved" and .acked_at' \
  "$TMP/state/latch/$key/acked/legacy-$key.json" >/dev/null && ok "legacy latch migrated into acked/ with its evidence" || no "legacy migrate: rc=$rc $out"
mkdir -p "$TMP/rpg-factory/s-lg"; printf 'old plain text latch' > "$TMP/rpg-factory/s-lg/LATCH"
[ "$(gdec s-lg "$SERVER" "touch l")" = deny ] && python3 -B "$TW" --ack >/dev/null && [ ! -e "$TMP/rpg-factory/s-lg/LATCH" ] \
  && ok "legacy plain-text session LATCH blocks and is cleared by ack" || no "legacy session LATCH"

# 13. the printed ack command: quoted, forward slashes, works from bash
call s-cmd tu-cmd "$SERVER" "$TMP/sneaky.sh tag" >/dev/null
msg=$(jq -cn --arg d "$SERVER" '{cwd:$d,session_id:"s-cmd2"}' | python3 -B "$TW" --session-start | jq -r '.hookSpecificOutput.additionalContext')
cmd=$(grep -o 'python3 "[^"]*" --ack' <<<"$msg" | head -1)
[ -n "$cmd" ] && ! grep -q '\\' <<<"$cmd" && ok "ack command quoted, no backslash: $cmd" || no "ack command: $msg"
out=$(bash -c "$cmd"); rc=$?; [ $rc -eq 0 ] && case "$out" in *"latch is now CLEAR"*) true;; *) false;; esac && ok "printed ack command runs from bash and clears" || no "printed cmd: rc=$rc $out"
w=$(python3 -B -c "import sys; sys.path.insert(0,'$ROOT/scripts/lib'); import fstate; print(fstate.ack_command('C:\\\\Workspaces\\\\Unity Indie\\\\rpg-factory'))")
[ "$w" = 'python3 "C:/Workspaces/Unity Indie/rpg-factory/scripts/tripwire.py" --ack' ] && ok "Windows plugin root -> $w" || no "windows ack command: $w"
gc "$SERVER" tag -d v9.9.9 >/dev/null
[ "$(gdec s-cmd "$SERVER" "python3 \"$TW\" --ack")" = deny ] && ok "agent --ack denied even when nothing is latched" || no "agent ack allowed"

# ==== review findings (PR #1) =======================================================================
python3 -B "$TW" --ack >/dev/null; gc "$SERVER" switch -q develop
# F1: another session's git explains only the refs it changed itself, never a read-only git and never another ref
gc "$SERVER" commit -q --allow-empty -m "keep me"; keep=$(git -C "$SERVER" rev-parse develop)
printf '#!/usr/bin/env bash\ngit reset -q --hard HEAD~1\n' > "$TMP/build.sh"; chmod +x "$TMP/build.sh"
hook --pre s-f1a tu-f1a "$SERVER" "$TMP/build.sh"
hook --pre s-f1b tu-f1b "$SERVER" "git log -1 >/dev/null && touch $TMP/f1b"
(cd "$SERVER" && "$TMP/build.sh")                                                   # hidden reset of protected develop
outB=$(hook --post s-f1b tu-f1b "$SERVER" "git log -1 >/dev/null && touch $TMP/f1b")
outA=$(hook --post s-f1a tu-f1a "$SERVER" "$TMP/build.sh")
case "$outA" in *"branch develop moved"*"PROTECTED"*) ok "F1: a read-only git of another session does not excuse a hidden reset of develop";;
  *) no "F1 read-only excuse: A=${outA:0:200}";; esac
python3 -B "$TW" --ack >/dev/null; gc "$SERVER" reset -q --hard "$keep"
hook --pre s-f1a tu-f1c "$SERVER" "$TMP/build.sh"
hook --pre s-f1b tu-f1d "$SERVER" "git switch -q -c feat/server/f1 && git switch -q develop"
(cd "$SERVER" && git switch -q -c feat/server/f1 && git switch -q develop && "$TMP/build.sh")
outB=$(hook --post s-f1b tu-f1d "$SERVER" "git switch -q -c feat/server/f1 && git switch -q develop")
outA=$(hook --post s-f1a tu-f1c "$SERVER" "$TMP/build.sh")
case "$outA" in *"branch develop moved"*) case "$outA" in *"feat/server/f1"*) no "F1: B's own branch blamed on A: ${outA:0:200}";; *) ok "F1: B's visible branch explained, the hidden develop reset still trips";; esac;;
  *) no "F1 other-ref excuse: A=${outA:0:200}";; esac
python3 -B "$TW" --ack >/dev/null; gc "$SERVER" reset -q --hard "$keep"
# F2: a failing command (PostToolUseFailure) is still checked, and the STOP names that hook event
pl=$(jq -cn --arg d "$SERVER" --arg c "$TMP/sneaky.sh commit; exit 1" '{tool_name:"Bash",tool_input:{command:$c},cwd:$d,session_id:"s-f2",tool_use_id:"tu-f2"}')
python3 -B "$TW" --pre <<<"$pl"; (cd "$SERVER" && bash -c "$TMP/sneaky.sh commit; exit 1"); \
out=$(jq -c '. + {hook_event_name:"PostToolUseFailure"}' <<<"$pl" | python3 -B "$TW" --post)
[ "$(jq -r '.hookSpecificOutput.hookEventName' <<<"$out" 2>/dev/null)" = PostToolUseFailure ] && case "$out" in *"branch develop moved"*) true;; *) false;; esac \
  && ok "F2: failing command checked through PostToolUseFailure" || no "F2: ${out:0:200}"
jq -e '.hooks.PostToolUseFailure[0].matcher == "Bash|PowerShell" and (.hooks.PostToolUseFailure[0].hooks[0].command | test("tripwire.py\" --post"))' \
  "$ROOT/hooks/hooks.json" >/dev/null && ok "F2: hooks.json wires PostToolUseFailure to tripwire --post" || no "F2: hooks.json"
# F4 + F6 while latched: reflog rewrites denied; every ack form denied to the agent; grep of the script allowed
for c in "git reflog drop --all" "git reflog write refs/heads/develop HEAD x" "git reflog expire --expire=now --all" "git reflog delete develop@{0}"; do
  [ "$(gdec s-f2 "$SERVER" "$c")" = deny ] && ok "F4: denied while latched: $c" || no "F4: allowed while latched: $c"; done
python3 -B "$TW" --ack >/dev/null; gc "$SERVER" reset -q --hard "$keep"
for c in "python3 -B -X utf8 $TW --ack" "T=$TW; python3 \$T --ack" "python3 -c \"import runpy,sys; sys.argv=['tripwire.py','--ack']; runpy.run_path('$TW')\"" \
         "py -3 $TW --ack 20261014T000000Z-abc123" "cd /tmp && python3 $TW --ack"; do
  [ "$(gdec s-f6 "$SERVER" "$c")" = deny ] && ok "F6: agent ack denied: ${c:0:60}" || no "F6: agent ack allowed: $c"; done
for c in "grep -- --ack $TW" "grep -n -- --ack $TW" "python3 $TW --status"; do
  [ "$(gdec s-f6 "$SERVER" "$c")" = allow ] && ok "F6: allowed: ${c:0:60}" || no "F6: denied: $c"; done
# F5: a failed cache write (here: fpcache.json is a directory) never costs the comparison
mkdir -p "$TMP/rpg-factory/s-f5/fpcache.json"
out=$(call s-f5 tu-f5 "$SERVER" "$TMP/sneaky.sh tag")
case "$out" in *"tag v9.9.9 created"*) ok "F5: STOP still raised when the fingerprint cache cannot be written";; *) no "F5: ${out:0:200}";; esac
ls "$TMP/rpg-factory/s-f5"/*.tmp >/dev/null 2>&1 && no "F5: temp files leaked" || ok "F5: no temp files left behind"
python3 -B "$TW" --ack >/dev/null; gc "$SERVER" tag -d v9.9.9 >/dev/null
# F7: a commit in a worktree is reported once (the worktree and its main checkout share refs)
out=$(call s-f7 tu-f7 "$WS/srv-wt" "$TMP/sneaky.sh commit")
n7=$(jq -r '.violations[]' "$TMP"/state/latch/*/*.json | grep -c "branch feat/server/wt moved")
[ "$n7" -eq 1 ] && jq -e '.violations[0] | startswith("[worktree:srv-wt]")' "$TMP"/state/latch/*/*.json >/dev/null \
  && ok "F7: worktree ref change reported once, under the worktree" || no "F7: $n7 lines: $(jq -c .violations "$TMP"/state/latch/*/*.json)"
python3 -B "$TW" --ack >/dev/null
# F8: parallel calls without tool_use_id keep separate snapshots; both are checked
hook --pre s-f8 "" "$SERVER" "touch $TMP/f8a"; hook --pre s-f8 "" "$SERVER" "touch $TMP/f8b"
(cd "$SERVER" && "$TMP/sneaky.sh" tag)
oa=$(hook --post s-f8 "" "$SERVER" "touch $TMP/f8a"); ob=$(hook --post s-f8 "" "$SERVER" "touch $TMP/f8b")
[ -n "$oa" ] && [ -n "$ob" ] && ok "F8: two parallel calls without tool_use_id are both checked" || no "F8 nokey: a=${oa:0:80} b=${ob:0:80}"
python3 -B "$TW" --ack >/dev/null; gc "$SERVER" tag -d v9.9.9 >/dev/null
# F8: a second legacy latch never overwrites the first archived one
for i in 1 2; do jq -cn --arg w "$WS" --arg m "legacy $i" '{workspace:$w,session:"old",at:"t",message:$m}' > "$TMP/state/latch/$key.json"; python3 -B "$TW" --ack >/dev/null; done
msgs=$(cat "$TMP/state/latch/$key/acked/"legacy-*.json | jq -r .message)
grep -qx "legacy 1" <<<"$msgs" && grep -qx "legacy 2" <<<"$msgs" && grep -qx "\[server\] branch x moved" <<<"$msgs" \
  && ok "F8: two legacy latches archived side by side" || no "F8 legacy: $(ls "$TMP/state/latch/$key/acked/")"

# performance: pre+post overhead for a mutating command vs a read-only command, 2 repos
t0=$(date +%s%N); for i in 1 2 3 4 5; do p=$(jq -cn --arg d "$SERVER" --arg s perf '{tool_name:"Bash",tool_input:{command:"touch /tmp/rpgf-perf"},cwd:$d,session_id:$s}'); python3 -B "$TW" --pre <<<"$p"; python3 -B "$TW" --post <<<"$p" >/dev/null; done; t1=$(date +%s%N)
t2=$(date +%s%N); for i in 1 2 3 4 5; do p=$(jq -cn --arg d "$SERVER" --arg s perf '{tool_name:"Bash",tool_input:{command:"git status"},cwd:$d,session_id:$s}'); python3 -B "$TW" --pre <<<"$p"; python3 -B "$TW" --post <<<"$p" >/dev/null; done; t3=$(date +%s%N)
echo "perf: mutating pre+post avg $(( (t1 - t0) / 5000000 )) ms; read-only pre+post avg $(( (t3 - t2) / 5000000 )) ms (fixture, 2 repos)"

total=$((pass + fail))
echo "tripwire tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
