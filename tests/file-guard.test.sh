#!/usr/bin/env bash
# file-guard.py: the workspace rules applied to Claude's file tools (Write/Edit/MultiEdit/NotebookEdit/Read),
# in a throwaway workspace. Expected decision per payload.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
FG="$ROOT/scripts/file-guard.py"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
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
echo "user wip" >> "$C/Assets/Scripts/Net/Client.cs"                 # a pre-existing user change
mkdir -p "$C/Assets/Samples/Mine"; echo u > "$C/Assets/Samples/Mine/u.cs"  # untracked user dir
pass=0; fail=0
dec() { # tool path [session]
  local o; o=$(jq -cn --arg t "$1" --arg p "$2" --arg s "${3:-fg}" --arg d "$C" '{tool_name:$t,tool_input:{file_path:$p,content:"x"},cwd:$d,session_id:$s}' | python3 -B "$FG")
  jq -r 'if .hookSpecificOutput.permissionDecision then "DECISION" else ((.hookSpecificOutput.additionalContext // "") | (capture("^rpg-factory advisory [(](?<l>[a-z]+)[)]") // {l: "allow"}) | .l) end' <<<"${o:-{\}}"; }
t() { local g; g=$(dec "$2" "$3" "${4:-fg}"); if [ "$g" = "$1" ]; then pass=$((pass + 1)); echo "PASS  $1  $2 ${3#$TMP/}"; else fail=$((fail + 1)); echo "FAIL  expected $1 got $g  $2 ${3#$TMP/}"; fi; }
t allow Write "$C/Assets/Scripts/Net/NewFile.cs"
t allow Edit  "$S/backend/deploy/compose.yml"
t allow Edit  "$C/Assets/Scripts/Net/Client.cs"                         # pre-existing change: no session baseline any more
t warn   Write "$C/Assets/Samples/Mine/u.cs"                             # generated Assets/Samples/
t warn   Edit  "$C/Packages/com.cuvara.dots/a.cs"                        # embedded clone
t warn   Write "$C/Packages/com.gdk.core/s.cs"                           # submodule content
t warn   Edit  "$S/backend/shared/proto/gen/wire.pb.go"                  # generated (proto bindings)
t warn   Write "$C/Assets/Scripts/UI/Hud/Generated/HudView.uxml.g.cs"    # generated (uxml codegen)
t warn   MultiEdit "$C/Assets/Scripts/Foo.uxml.g.cs"                     # generated glob
t warn   Write "$S/backend/deploy/.env"                                   # secrets
t warn   Read  "$S/backend/deploy/kubeconfig.local"
t warn   Read  "$S/backend/deploy/.env.local"
t allow Read  "$S/backend/deploy/.env.example"                            # documentation, not a secret
t allow Edit  "$S/backend/deploy/.env.example"
t allow Read  "$S/backend/TEAM.md"
t warn  Read  "$ROOT/skills/game-design/SKILL.md"                      # load it with the Skill tool instead
t warn  Read  "$TMP/plugin-cache/rpg-factory/1.3.0/skills/art-3d/SKILL.md"  # any plugin location
t allow Read  "$ROOT/skills/game-design/references/x.md"               # references are plain reads
t allow Read  "$TMP/elsewhere/skills/nosuch/SKILL.md"                   # not a registered skill
t allow Read  "$C/Packages/com.cuvara.dots/a.cs"                         # reading user state is fine
t allow Write "$TMP/outside/file.txt"                                     # outside the workspace
t allow Edit  "Assets/Scripts/Net/Other.cs"                               # relative path resolved against cwd
t warn   Edit  "Assets/Scripts/UI/Hud/Generated/HudView.uxml.g.cs"      # relative generated path
# modes: analyze/plan/review/validate forbid file changes (declared through the shell guard, same session)
declare_mode() { jq -cn --arg c "bash $ROOT/scripts/factory-context.sh --mode $1" --arg d "$C" '{tool_name:"Bash",tool_input:{command:$c},cwd:$d,session_id:"fg"}' | python3 -B "$ROOT/scripts/git-guard.py" >/dev/null; }
declare_mode plan;      t high  Write "$C/Assets/Scripts/Net/NewFile.cs"; t allow Read "$C/Assets/Scripts/Net/Client.cs"
declare_mode validate;  t high  Edit  "$S/backend/deploy/compose.yml"
declare_mode review;    t high  MultiEdit "$C/Assets/Scripts/Net/NewFile.cs"
declare_mode implement; t allow Write "$C/Assets/Scripts/Net/NewFile.cs"

# secrets are matched case-insensitively (Windows file systems are)
t warn  Write "$S/backend/deploy/.ENV"
t warn  Read  "$S/backend/deploy/KubeConfig.Local"
t allow Read  "$S/backend/deploy/.ENV.EXAMPLE"
# a linked worktree of a workspace repo outside the repo directory gets that repo's rules (git common dir)
WT="$WS/.wt-client-cleanup"; gc "$C" worktree add -q -b cleanup "$WT" >/dev/null 2>&1
mkdir -p "$WT/Assets/Scripts/UI/Hud/Generated"
t warn  Write "$WT/Assets/Scripts/UI/Hud/Generated/HudView.uxml.g.cs"   # generated, via the worktree's main checkout
t warn  Write "$WT/Assets/Samples/Mine/x.cs"                            # generated Assets/Samples/ in the worktree
t warn  Write "$WT/Packages/com.gdk.core/s.cs"                          # submodule content in the worktree
t allow Write "$WT/Assets/Scripts/Net/NewFile.cs"
t warn  Write "$WT/Assets/Scripts/New/Deep/Missing.uxml.g.cs"          # target directory does not exist yet
# the gitlinks are cached per work tree and index stat (state dir): a submodule added or removed after a write is
# seen at the next write, in the main checkout and (own index) in the worktree
t allow Write "$C/Packages/com.gdk.extra/s.cs"
gc "$C" -c protocol.file.allow=always submodule add -q "$SUB" Packages/com.gdk.extra >/dev/null 2>&1
t warn  Write "$C/Packages/com.gdk.extra/s.cs"                          # added after the first write
t allow Write "$WT/Packages/com.gdk.extra/s.cs"                         # not in the worktree's index
gc "$C" rm -q --cached Packages/com.gdk.extra >/dev/null 2>&1
t allow Write "$C/Packages/com.gdk.extra/s.cs"                          # removed from the index
t warn  Write "$WT/Packages/com.gdk.core/s.cs"                          # the worktree's cache entry is its own
# a linked worktree OUTSIDE the workspace root (Orca worktree) whose main checkout is in the workspace gets its rules
OWS="$TMP/orca/server-wt"; gc "$S" worktree add -q -b feat/outside "$OWS" >/dev/null 2>&1; mkdir -p "$OWS/backend/shared/proto/gen"
t warn  Read  "$OWS/backend/.env"                                        # secrets
t warn  Write "$OWS/backend/deploy/.env"
t warn  Edit  "$OWS/backend/shared/proto/gen/wire.pb.go"                 # generated, via the main checkout
t allow Edit  "$OWS/backend/deploy/compose.yml"
OXW="$TMP/orca/other-wt"; git init -q -b main "$TMP/other"; gc "$TMP/other" commit -q --allow-empty -m i
gc "$TMP/other" worktree add -q -b feat/o "$OXW" >/dev/null 2>&1
t allow Read  "$OXW/.env"                                                # main checkout outside the workspace
t allow Read  "$TMP/orca/missing/.env"                                   # not a repo: no opinion
# finding an outside worktree runs no git (it reads the worktree's .git file): a Read outside the workspace stays
# cheap. subprocess is patched in-process, so the count is exact on every platform.
nogit() { jq -cn --arg p "$1" --arg d "$C" '{tool_name:"Read",tool_input:{file_path:$p},cwd:$d,session_id:"fg"}' | python3 -B -c '
import runpy, subprocess, sys
calls = []
real = subprocess.run
def spy(*a, **k):
    calls.append(a[0] if a else k.get("args"))
    return real(*a, **k)
subprocess.run = spy
try:
    runpy.run_path(sys.argv[1], run_name="__main__")
except SystemExit:
    pass
print("", file=sys.stdout)
print("GITCALLS", len([c for c in calls if c and "git" in str(c[0])]))' "$FG"; }
o=$(nogit "$OWS/backend/.env"); grep -q "holds secrets" <<<"$o" && grep -q "^GITCALLS 0$" <<<"$o"   && { pass=$((pass + 1)); echo "PASS  outside-worktree secrets advisory with no git call"; }   || { fail=$((fail + 1)); echo "FAIL  outside-worktree Read ran git or lost its advisory: $(tr '
' ' ' <<<"$o" | cut -c1-200)"; }
o=$(nogit "$TMP/outside/plain.txt"); grep -q "^GITCALLS 0$" <<<"$o"   && { pass=$((pass + 1)); echo "PASS  Read outside the workspace runs no git"; }   || { fail=$((fail + 1)); echo "FAIL  Read outside the workspace ran git: $(tail -1 <<<"$o")"; }
# outside the workspace: silent even with RPG_FACTORY_WORKSPACE set and a read-only mode declared
declare_mode plan
t allow Write "$TMP/outside/file.txt"
t allow Write "$TMP/outside/.env"
t allow Read  "$TMP/outside/.ENV"
# the mode advisory names a bash-pasteable command: forward slashes, quoted
o=$(jq -cn --arg p "$C/Assets/Scripts/Net/NewFile.cs" --arg d "$C" '{tool_name:"Write",tool_input:{file_path:$p,content:"x"},cwd:$d,session_id:"fg"}' | python3 -B "$FG" | jq -r '.hookSpecificOutput.additionalContext // ""')
cmd=$(grep -o '`bash [^`]*`' <<<"$o")
if [ -n "$cmd" ] && ! grep -q '\\' <<<"$cmd" && grep -q '^`bash "[^"]*/scripts/factory-context.sh" --mode implement`$' <<<"$cmd"; then
  pass=$((pass + 1)); echo "PASS  mode advisory command is quoted with forward slashes: $cmd"
else fail=$((fail + 1)); echo "FAIL  mode advisory command: ${cmd:-none} ($o)"; fi
declare_mode implement

# 1.0.1: the tripwire latch is gone - stale latch files from older versions never deny a write
python3 -B - "$TMP/state" "$WS" <<'PY2'
import hashlib, json, os, sys
key = hashlib.sha1(os.path.abspath(sys.argv[2]).encode()).hexdigest()[:12]
os.makedirs(os.path.join(sys.argv[1], "latch", key), exist_ok=True)
for p in (os.path.join(sys.argv[1], "latch", key, "20261014T000000Z-fg0001.json"), os.path.join(sys.argv[1], "latch", key + ".json")):
    json.dump({"workspace": sys.argv[2], "session": "old", "message": "[client] pre-existing user file changed"}, open(p, "w"))
PY2
mkdir -p "$TMP/rpg-factory/stale-session" && echo "old STOP" > "$TMP/rpg-factory/stale-session/LATCH"
t allow Write "$C/Assets/Scripts/Net/NewFile.cs" stale-session
t allow Edit  "$S/backend/deploy/compose.yml" fresh-session
# rule english-only: non-English text written into a governed path (registered repo, plugin checkout, docs/plans, harness
# plan or memory directory) gives a warn advisory; English text, a Read and a localisation path give none
VI='"Xin ch\u00e0o c\u00e1c b\u1ea1n, \u0111\u00e2y l\u00e0 t\u00e0i li\u1ec7u ti\u1ebfng Vi\u1ec7t cho d\u1ef1 \u00e1n"'
EN='"Hello everyone, this is the English document for the project"'
lang() { # expected tool path text-json [tool_input-jq-builder]
  local o g; o=$(jq -cn --arg t "$2" --arg p "$3" --argjson x "$4" --arg d "$C" \
    '{tool_name:$t,cwd:$d,session_id:"fg",tool_input:({file_path:$p} + (if $t=="Write" then {content:$x} elif $t=="Edit" then {old_string:"a",new_string:$x} elif $t=="MultiEdit" then {edits:[{old_string:"a",new_string:"b"},{old_string:"c",new_string:$x}]} elif $t=="NotebookEdit" then {notebook_path:$p,new_source:$x} else {} end))}' | python3 -B "$FG")
  g=$(jq -r 'if .hookSpecificOutput.permissionDecision then "DECISION" elif ((.hookSpecificOutput.additionalContext // "") | test("^rpg-factory advisory [(]warn[)].*rule english-only")) then "warn" else "none" end' <<<"${o:-{\}}")
  if [ "$g" = "$1" ]; then pass=$((pass + 1)); echo "PASS  english-only $1  $2 ${3#$TMP/}"; else fail=$((fail + 1)); echo "FAIL  english-only expected $1 got $g  $2 ${3#$TMP/}: $o"; fi; }
HOME_DIR="$TMP/home"
lang warn Write "$C/Assets/Scripts/Net/NewFile.cs" "$VI"                       # a registered repo file
lang warn Edit  "$S/backend/deploy/compose.yml" "$VI"
lang warn Write "$HOME_DIR/.claude/plans/x.md" "$VI"                           # a harness plan file (outside the workspace)
lang warn Write "$HOME_DIR/.claude/projects/p/memory/m.md" "$VI"               # a harness memory file
lang warn Write "$TMP/other/docs/plans/plan.md" "$VI"                          # a docs/plans/ directory
lang warn Write "$ROOT/docs/some-new-doc.md" "$VI"                             # the plugin checkout
lang warn MultiEdit "$C/Assets/Scripts/Net/NewFile.cs" "$VI"                   # each edits[].new_string
lang warn NotebookEdit "$C/Assets/Scripts/Net/nb.ipynb" "$VI"                  # new_source
lang none Write "$C/Assets/Scripts/Net/NewFile.cs" "$EN"                       # English
lang none Edit  "$HOME_DIR/.claude/plans/x.md" "$EN"
lang none MultiEdit "$C/Assets/Scripts/Net/NewFile.cs" "$EN"
lang none Read  "$C/Assets/Scripts/Net/NewFile.cs" "$VI"                       # a Read never triggers it
lang none Write "$C/Assets/Localization/vi.json" "$VI"                         # localisation data (workspace.language_allow)
lang none Write "$C/Assets/Locales/vi/strings.po" "$VI"
lang none Write "$C/Assets/i18n/vi.txt" "$VI"
lang none Write "$S/backend/deploy/messages.po" "$VI"
lang none Write "$TMP/outside/vi.txt" "$VI"                                    # not governed: no opinion
lang none Write "$HOME_DIR/.claude/projects/p/notes.md" "$VI"                  # only the memory directory of a project is governed
o=$(jq -cn --arg p "$C/Assets/Scripts/Net/NewFile.cs" --arg d "$C" --argjson x "$VI" '{tool_name:"Write",tool_input:{file_path:$p,content:$x},cwd:$d,session_id:"fg"}' | python3 -B "$FG")
jq -e '.hookSpecificOutput | (has("permissionDecision") | not) and (.additionalContext | test("line 1:"))' >/dev/null <<<"$o" \
  && { pass=$((pass + 1)); echo "PASS  english-only advisory names the first offending line, no permissionDecision"; } || { fail=$((fail + 1)); echo "FAIL  english-only advisory shape: $o"; }
# combined with another advisory (a generated path) both are reported
o=$(jq -cn --arg p "$S/backend/shared/proto/gen/wire.pb.go" --arg d "$C" --argjson x "$VI" '{tool_name:"Write",tool_input:{file_path:$p,content:$x},cwd:$d,session_id:"fg"}' | python3 -B "$FG")
jq -e '.hookSpecificOutput.additionalContext | test("generated") and test("english-only")' >/dev/null <<<"$o" \
  && { pass=$((pass + 1)); echo "PASS  english-only combines with the generated-path advisory"; } || { fail=$((fail + 1)); echo "FAIL  combined advisory: $o"; }
out=$(echo 'garbage' | python3 -B "$FG"; echo "rc=$?"); [ "$out" = "rc=0" ] && { pass=$((pass + 1)); echo "PASS  malformed input -> no opinion"; } || { fail=$((fail + 1)); echo "FAIL  malformed: $out"; }
out=$(jq -cn --arg p "$C/Packages/com.cuvara.dots/a.cs" '{tool_name:"Edit",tool_input:{file_path:$p},cwd:"/"}' | RPG_FACTORY_GUARD=off python3 -B "$FG")
[ -z "$out" ] && { pass=$((pass + 1)); echo "PASS  RPG_FACTORY_GUARD=off disables it"; } || { fail=$((fail + 1)); echo "FAIL  guard off: $out"; }
total=$((pass + fail)); echo "file-guard tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
