#!/usr/bin/env bash
# file-guard.py: the workspace rules applied to Claude's file tools (Write/Edit/MultiEdit/NotebookEdit/Read),
# in a throwaway workspace. Expected decision per payload.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FG="$ROOT/scripts/file-guard.py"; TW="$ROOT/scripts/tripwire.py"
TMP="$(mktemp -d -p /tmp)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
export TMPDIR="$TMP" RPG_FACTORY_WORKSPACE="$TMP/ws" CLAUDE_PLUGIN_ROOT="$ROOT" RPG_FACTORY_STATE_DIR="$TMP/state"
WS="$TMP/ws"; S="$WS/rpg-mmo-server"; C="$WS/IndieRPGMMOAdventure"
gc() { git -C "$1" -c user.email=t@t -c user.name=t "${@:2}"; }
mkdir -p "$S/backend/shared/proto/gen" "$S/backend/deploy" "$C/ProjectSettings" "$C/Assets/Scripts/UI/Hud/Generated" "$C/Assets/Scripts/Net"
touch "$S/backend/TEAM.md" "$C/ProjectSettings/ProjectVersion.txt" "$S/backend/shared/proto/gen/wire.pb.go" "$C/Assets/Scripts/Net/Client.cs"
for r in "$S" "$C"; do git -C "$r" init -q -b develop; gc "$r" add -A; gc "$r" commit -qm init; done
echo "Packages/com.cuvara.*/" > "$C/.gitignore"; gc "$C" add .gitignore; gc "$C" commit -qm ignore
git init -q -b main "$C/Packages/com.cuvara.dots"; echo x > "$C/Packages/com.cuvara.dots/a.cs"; gc "$C/Packages/com.cuvara.dots" add -A; gc "$C/Packages/com.cuvara.dots" commit -qm c
SUB="$TMP/gdk"; git init -q -b main "$SUB"; echo s > "$SUB/s.cs"; gc "$SUB" add -A; gc "$SUB" commit -qm s
gc "$C" -c protocol.file.allow=always submodule add -q "$SUB" Packages/com.gdk.core >/dev/null 2>&1; gc "$C" commit -qm sub
echo "user wip" >> "$C/Assets/Scripts/Net/Client.cs"                 # the user's pre-existing change (baseline)
mkdir -p "$C/Assets/Samples/Mine"; echo u > "$C/Assets/Samples/Mine/u.cs"  # untracked user dir
jq -cn --arg d "$C" '{cwd:$d,session_id:"fg"}' | python3 -B "$TW" --session-start >/dev/null
pass=0; fail=0
dec() { # tool path [session]
  local o; o=$(jq -cn --arg t "$1" --arg p "$2" --arg s "${3:-fg}" --arg d "$C" '{tool_name:$t,tool_input:{file_path:$p,content:"x"},cwd:$d,session_id:$s}' | python3 -B "$FG")
  jq -r '.hookSpecificOutput.permissionDecision // "allow"' <<<"${o:-{\}}"; }
t() { local g; g=$(dec "$2" "$3" "${4:-fg}"); if [ "$g" = "$1" ]; then pass=$((pass + 1)); echo "PASS  $1  $2 ${3#$TMP/}"; else fail=$((fail + 1)); echo "FAIL  expected $1 got $g  $2 ${3#$TMP/}"; fi; }
t allow Write "$C/Assets/Scripts/Net/NewFile.cs"
t allow Edit  "$S/backend/deploy/compose.yml"
t ask   Edit  "$C/Assets/Scripts/Net/Client.cs"                         # baseline (user's modified file)
t ask   Write "$C/Assets/Samples/Mine/u.cs"                             # inside an untracked user dir + generated Assets/Samples/
t ask   Edit  "$C/Packages/com.cuvara.dots/a.cs"                        # embedded clone
t ask   Write "$C/Packages/com.gdk.core/s.cs"                           # submodule content
t ask   Edit  "$S/backend/shared/proto/gen/wire.pb.go"                  # generated (proto bindings)
t ask   Write "$C/Assets/Scripts/UI/Hud/Generated/HudView.uxml.g.cs"    # generated (uxml codegen)
t ask   MultiEdit "$C/Assets/Scripts/Foo.uxml.g.cs"                     # generated glob
t ask   Write "$S/backend/deploy/.env"                                   # secrets
t ask   Read  "$S/backend/deploy/kubeconfig.local"
t allow Read  "$S/backend/TEAM.md"
t allow Read  "$C/Packages/com.cuvara.dots/a.cs"                         # reading user state is fine
t allow Write "$TMP/outside/file.txt"                                     # outside the workspace
t allow Edit  "Assets/Scripts/Net/Other.cs"                               # relative path resolved against cwd
t ask   Edit  "Assets/Scripts/Net/Client.cs"
# latch: an unresolved STOP (even from an earlier session) denies every write
mkdir -p "$TMP/state/latch"
python3 -B - "$ROOT" "$WS" <<'PY'
import json, os, sys; sys.path.insert(0, sys.argv[1] + "/scripts/lib"); import fstate
json.dump({"workspace": sys.argv[2], "session": "old", "at": "t", "message": "[server] tag v9 created"},
          open(os.path.join(fstate.persistent(), "latch", fstate.workspace_key(sys.argv[2]) + ".json"), "w"))
PY
t deny  Write "$C/Assets/Scripts/Net/NewFile.cs" other-session
t allow Read  "$C/Assets/Scripts/Net/Client.cs" other-session
python3 -B "$TW" --ack >/dev/null
t allow Write "$C/Assets/Scripts/Net/NewFile.cs" other-session
out=$(echo 'garbage' | python3 -B "$FG"; echo "rc=$?"); [ "$out" = "rc=0" ] && { pass=$((pass + 1)); echo "PASS  malformed input -> no opinion"; } || { fail=$((fail + 1)); echo "FAIL  malformed: $out"; }
out=$(jq -cn --arg p "$C/Packages/com.cuvara.dots/a.cs" '{tool_name:"Edit",tool_input:{file_path:$p},cwd:"/"}' | RPG_FACTORY_GUARD=off python3 -B "$FG")
[ -z "$out" ] && { pass=$((pass + 1)); echo "PASS  RPG_FACTORY_GUARD=off disables it"; } || { fail=$((fail + 1)); echo "FAIL  guard off: $out"; }
total=$((pass + fail)); echo "file-guard tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
