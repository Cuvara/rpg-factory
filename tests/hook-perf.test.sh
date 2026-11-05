#!/usr/bin/env bash
# What a hook call costs before it does any work (lib/hookspeed.py, lib/workspace.py), in a throwaway workspace:
#   - a file-guard Read (and a plain Write) never loads the git guard
#   - git-guard.py is a small entry: every guard name stays importable from it; the helpers come from lib/workspace.py
#   - compiled bytecode goes to <state>/pycache, never into the plugin tree, and a second call reuses it
#   - the gitlinks of a repo are cached per index stat: used on the next write, recomputed when .git/index changes
#   - doctor names a `python3` that is the Windows Store alias (detection only)
# Timing is never asserted (machine dependent).
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
FG="$ROOT/scripts/file-guard.py"; GG="$ROOT/scripts/git-guard.py"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
export TMPDIR="$TMP" RPG_FACTORY_WORKSPACE="$TMP/ws" CLAUDE_PLUGIN_ROOT="$ROOT" RPG_FACTORY_STATE_DIR="$TMP/state"
unset RPG_FACTORY_PYCACHE
WS="$TMP/ws"; S="$WS/rpg-mmo-server"; C="$WS/IndieRPGMMOAdventure"
gc() { git -C "$1" -c user.email=t@t -c user.name=t "${@:2}"; }
mkdir -p "$S/backend" "$C/ProjectSettings" "$C/Assets"
touch "$S/backend/TEAM.md" "$C/ProjectSettings/ProjectVersion.txt" "$C/Assets/a.cs"
for r in "$S" "$C"; do git -C "$r" init -q -b develop; gc "$r" add -A; gc "$r" commit -qm init; done
SUB="$TMP/gdk"; git init -q -b main "$SUB"; echo s > "$SUB/s.cs"; gc "$SUB" add -A; gc "$SUB" commit -qm s
gc "$C" -c protocol.file.allow=always submodule add -q "$SUB" Packages/com.gdk.core >/dev/null 2>&1; gc "$C" commit -qm sub
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1${2:+: $2}"; }
level() { # tool path -> allow|warn|high
  local o; o=$(jq -cn --arg t "$1" --arg p "$2" --arg d "$C" '{tool_name:$t,tool_input:{file_path:$p,content:"x"},cwd:$d,session_id:"hp"}' | python3 -B "$FG")
  jq -r '(.hookSpecificOutput.additionalContext // "") | (capture("^rpg-factory advisory [(](?<l>[a-z]+)[)]") // {l: "allow"}) | .l' <<<"${o:-{\}}"; }

echo "-- the file guard does not load the git guard"
out=$(python3 -B - "$FG" "$C/Assets/a.cs" <<'PY'
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("file_guard", sys.argv[1]); fg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fg)
import factory_session
reg = factory_session.load_registry()
for tool in ("Read", "Write"):
    fg.evaluate({"tool_name": tool, "tool_input": {"file_path": sys.argv[2]}, "cwd": "/", "session_id": "hp"}, reg)
    print(tool, "loaded" if {"gitguard", "git_guard"} & set(sys.modules) else "not-loaded")
PY
)
grep -q '^Read not-loaded$' <<<"$out" && ok "file-guard Read does not import the git guard" || no "Read imports the git guard" "$out"
grep -q '^Write not-loaded$' <<<"$out" && ok "file-guard Write (no mode) does not import the git guard" || no "Write imports the git guard" "$out"

echo "-- git-guard.py is the entry, lib/gitguard.py the guard, lib/workspace.py the shared helpers"
out=$(python3 -B - "$GG" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("gg", sys.argv[1]); g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
import os; sys.path.append(os.path.dirname(os.path.abspath(sys.argv[1])))
import gitguard, workspace, factory_session
import context
names = ["find_workspace", "linked_worktree", "main_checkout", "native_path", "collect", "advisory", "expand", "prog",
         "parse_git", "classify_gh", "evaluate", "load_registry", "_needs_mode"]
missing = [n for n in names if getattr(g, n, None) is not getattr(gitguard, n, object())]
shared = [n for n in ("find_workspace", "linked_worktree", "main_checkout", "native_path") if getattr(gitguard, n) is not getattr(workspace, n)]
print("names", "ok" if not missing else missing)
print("shared", "ok" if not shared else shared)
print("session", "ok" if factory_session.guard() is gitguard else "other")
print("context", "ok" if context.native_abs is workspace.native_abs else "own copy")
PY
)
for k in names shared session context; do grep -q "^$k ok$" <<<"$out" && ok "git-guard $k" || no "git-guard $k" "$out"; done

echo "-- bytecode: state dir, never the plugin tree"
before=$(find "$ROOT" -name __pycache__ -not -path '*/.git/*' 2>/dev/null | sort)
level Read "$C/Assets/a.cs" >/dev/null
jq -cn --arg d "$C" '{tool_name:"Bash",tool_input:{command:"git status"},cwd:$d,session_id:"hp"}' | python3 -B "$GG" >/dev/null
jq -cn '{tool_name:"Skill",tool_input:{skill:"rpg-factory:factory-core"},session_id:"hp"}' | python3 -B "$ROOT/scripts/factory_session.py" --skill >/dev/null
after=$(find "$ROOT" -name __pycache__ -not -path '*/.git/*' 2>/dev/null | sort)
[ "$before" = "$after" ] && ok "no __pycache__ appears in the plugin tree" || no "__pycache__ in the plugin tree" "$(comm -13 <(echo "$before") <(echo "$after"))"
PC="$TMP/state/pycache"
for m in gitguard workspace factory_session pluginroot; do  # fstate and hookspeed load before the prefix is set
  [ -n "$(find "$PC" -name "$m.*.pyc" 2>/dev/null)" ] && ok "pycache holds $m" || no "pycache lacks $m" "$(find "$PC" -name '*.pyc' 2>/dev/null | head -5)"
done
pyc=$(find "$PC" -name 'gitguard.*.pyc' | head -1); m1=$(python3 -B -c 'import os,sys; print(os.stat(sys.argv[1]).st_mtime_ns)' "$pyc" 2>/dev/null)
jq -cn --arg d "$C" '{tool_name:"Bash",tool_input:{command:"git status"},cwd:$d,session_id:"hp"}' | python3 -B "$GG" >/dev/null
m2=$(python3 -B -c 'import os,sys; print(os.stat(sys.argv[1]).st_mtime_ns)' "$pyc" 2>/dev/null)
[ -n "$m1" ] && [ "$m1" = "$m2" ] && ok "a second git-guard call reuses the compiled guard" || no "gitguard pyc rewritten" "$m1 vs $m2"
rm -rf "$TMP/state2"
jq -cn --arg d "$C" '{tool_name:"Bash",tool_input:{command:"git status"},cwd:$d,session_id:"hp"}' \
  | RPG_FACTORY_PYCACHE=off RPG_FACTORY_STATE_DIR="$TMP/state2" python3 -B "$GG" >/dev/null
[ -z "$(find "$TMP/state2" -name '*.pyc' 2>/dev/null)" ] && ok "RPG_FACTORY_PYCACHE=off writes no bytecode" || no "pyc written with RPG_FACTORY_PYCACHE=off"
out=$(jq -cn --arg d "$C" '{tool_name:"Bash",tool_input:{command:"git tag v9"},cwd:$d,session_id:"hp"}' \
  | RPG_FACTORY_STATE_DIR="relative/state" python3 -B "$GG" | jq -r '.hookSpecificOutput.additionalContext // ""')
grep -q '^rpg-factory advisory (high)' <<<"$out" && [ ! -e relative ] && ok "unusable state dir: no cache, same advisory" || no "relative state dir" "$out"

echo "-- gitlinks cache (per work tree and .git/index stat)"
GL="$TMP/state/cache/gitlinks"
rm -rf "$GL"
[ "$(level Write "$C/Packages/com.gdk.core/s.cs")" = warn ] && ok "first write into the submodule warns" || no "submodule write"
cf=$(find "$GL" -name '*.json' 2>/dev/null | head -1)
[ -n "$cf" ] && jq -e '.gitlinks == ["Packages/com.gdk.core"] and (.index | length == 2)' "$cf" >/dev/null && ok "gitlinks cached in the state dir" || no "no gitlinks cache" "$cf"
jq '.gitlinks += ["Assets/Fake"]' "$cf" > "$cf.new" && mv "$cf.new" "$cf"   # a marker only the cache knows
[ "$(level Write "$C/Assets/Fake/x.cs")" = warn ] && ok "second write uses the cache (no git ls-files)" || no "cache not used"
echo b > "$C/Assets/b.cs"; gc "$C" add Assets/b.cs                          # .git/index changes
[ "$(level Write "$C/Assets/Fake/x.cs")" = allow ] && ok "changed .git/index recomputes the gitlinks" || no "stale gitlinks after an index change"
jq -e '.gitlinks == ["Packages/com.gdk.core"]' "$cf" >/dev/null && ok "cache rewritten from git" || no "cache not rewritten" "$(cat "$cf")"
echo 'not json' > "$cf"
[ "$(level Write "$C/Packages/com.gdk.core/s.cs")" = warn ] && ok "unreadable cache: recomputed" || no "unreadable cache"
[ "$(GIT_INDEX_FILE="$TMP/none" level Write "$C/Packages/com.gdk.core/s.cs")" = allow ] && ok "GIT_INDEX_FILE set: no cache (git reads that index)" || no "GIT_INDEX_FILE ignored"

echo "-- doctor: python3 as the Windows Store alias (detection only)"
alias_path='C:\Users\u\AppData\Local\Microsoft\WindowsApps\python3.exe'
out=$(RPG_FACTORY_PYTHON3="$alias_path" python3 -B "$ROOT/scripts/factory-cmd.py" doctor --json 2>/dev/null)
jq -e '.tools.python3.windows_store_alias == true and (.tools.python3.advice | test("70 ms"))' <<<"$out" >/dev/null && ok "doctor --json names the alias" || no "doctor alias" "$(jq -c .tools.python3 <<<"$out" 2>&1 | head -c 300)"
out=$(RPG_FACTORY_PYTHON3="$alias_path" python3 -B "$ROOT/scripts/factory-cmd.py" doctor 2>/dev/null)
grep -q '^- python3: .*Windows Store alias.*70 ms slower' <<<"$out" && ok "doctor text names the alias" || no "doctor text"
out=$(RPG_FACTORY_PYTHON3="/usr/bin/python3" python3 -B "$ROOT/scripts/factory-cmd.py" doctor --json 2>/dev/null)
jq -e '.tools.python3.windows_store_alias == false and .tools.python3.advice == null' <<<"$out" >/dev/null && ok "doctor: a real python3 is no alias" || no "doctor false alias"

total=$((pass + fail)); echo "hook-perf tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
