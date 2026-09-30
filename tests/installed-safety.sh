#!/usr/bin/env bash
# Safety through the INSTALLED plugin: runs the hook commands exactly as the installed hooks.json
# declares them (CLAUDE_PLUGIN_ROOT = the path installed sessions load: the marketplace directory
# for a directory marketplace, the version-keyed cache copy otherwise), with Claude-shaped payloads,
# against a disposable fake workspace (throwaway repos + a bare remote under mktemp). Nothing in the
# real workspace is touched: RPG_FACTORY_WORKSPACE points at the fake one.
#
# Commands the hooks allow are executed (as Claude would) and followed by the PostToolUse hook;
# asked/denied ones are not executed (nobody approves). At the end the fake repos and remote must
# hold no tag created by a blocked command.
#
# Usage: tests/installed-safety.sh [--plugin-root DIR]   (default: install-status.py loads_from)
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PR=$(python3 -B "$ROOT/scripts/install-status.py" --json 2>/dev/null | jq -r '.installed.loads_from // empty')
[ "${1:-}" = "--plugin-root" ] && PR="$2"
REC=$(jq -r '.plugins["rpg-factory@rpg-factory"][0] | "\(.version) \(.gitCommitSha[0:7])"' "$HOME/.claude/plugins/installed_plugins.json" 2>/dev/null)
[ -n "$PR" ] && [ -f "$PR/hooks/hooks.json" ] || { echo "NOT_AVAILABLE  no installed rpg-factory (installPath '$PR')"; exit 2; }
VER=$(jq -r .version "$PR/.claude-plugin/plugin.json")
TMP="$(mktemp -d -p /tmp)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
export TMPDIR="$TMP/tmpdir"; mkdir -p "$TMPDIR"
export RPG_FACTORY_WORKSPACE="$TMP/ws" CLAUDE_PLUGIN_ROOT="$PR" PYTHONDONTWRITEBYTECODE=1
WS="$RPG_FACTORY_WORKSPACE"; S="$WS/rpg-mmo-server"; C="$WS/IndieRPGMMOAdventure"; OTHER="$TMP/elsewhere"
gc() { git -C "$1" -c user.email=t@t -c user.name=t "${@:2}"; }
mkdir -p "$S/backend" "$C/ProjectSettings" "$OTHER"
echo team > "$S/backend/TEAM.md"; echo "m_EditorVersion: 6000" > "$C/ProjectSettings/ProjectVersion.txt"
git init -q --bare "$TMP/remote.git"
for r in "$S" "$C" "$OTHER"; do git -C "$r" init -q -b develop; echo a > "$r/a.txt"; gc "$r" add -A; gc "$r" commit -qm init; done
gc "$S" remote add origin "$TMP/remote.git"; gc "$S" push -q origin develop
gc "$S" branch feat/x; echo "user wip" > "$S/user-wip.txt"          # a baseline (user) file
SID="safety-$$"

hooks() { # event matcher-tool -> hook commands (one per line)
  jq -r --arg e "$1" --arg t "$2" '.hooks[$e][]? | select((.matcher // "") as $m | $m == "" or ($t | test("^(" + $m + ")$"))) | .hooks[].command' "$PR/hooks/hooks.json"
}
payload() { jq -nc --arg s "$SID" --arg e "$1" --arg t "$2" --arg c "$3" --arg d "$4" '{session_id:$s, hook_event_name:$e, tool_name:$t, tool_input:{command:$c}, tool_response:{}, cwd:$d}'; }
decide() { # tool command cwd -> allow|ask|deny (+ reason in $REASON)
  local d=allow out; REASON=""
  while IFS= read -r h; do
    out=$(payload PreToolUse "$1" "$2" "$3" | (cd "$3" && bash -c "$h") 2>/dev/null)
    local pd; pd=$(jq -r '.hookSpecificOutput.permissionDecision // empty' <<<"${out:-{\}}" 2>/dev/null)
    [ -n "$pd" ] && REASON=$(jq -r '.hookSpecificOutput.permissionDecisionReason // ""' <<<"$out" | head -c 90)
    case "$pd" in deny) d=deny;; ask) [ "$d" = allow ] && d=ask;; esac
  done < <(hooks PreToolUse "$1")
  echo "$d $REASON"
}
post() { # tool command cwd -> prints STOP text if any
  while IFS= read -r h; do
    payload PostToolUse "$1" "$2" "$3" | (cd "$3" && bash -c "$h") 2>/dev/null | jq -r '.hookSpecificOutput.additionalContext // .reason // empty' 2>/dev/null
  done < <(hooks PostToolUse "$1")
}
# SessionStart (baseline) exactly as installed
while IFS= read -r h; do payload SessionStart "" "" "$S" | (cd "$S" && bash -c "$h") >/dev/null 2>&1; done < <(jq -r '.hooks.SessionStart[]?.hooks[].command' "$PR/hooks/hooks.json")

pass=0; fail=0; REASON=""; LASTPOST=""
row() { printf '%-5s %-10s %-58s expected %-6s got %-6s %s\n' "$1" "$2" "$3" "$4" "$5" "$6"; }
t() { # tool expected cwd command
  LASTPOST=""; local got; got=$(decide "$1" "$4" "$3"); REASON=${got#* }; got=${got%% *}
  if [ "$got" = "$2" ]; then pass=$((pass + 1)); row PASS "$1" "$4" "$2" "$got" ""
  else fail=$((fail + 1)); row FAIL "$1" "$4" "$2" "$got" "$REASON"; fi
  if [ "$got" = allow ] && [ "${EXEC:-1}" = 1 ]; then
    (cd "$3" && if [ "$1" = PowerShell ]; then bash -c "$4"; else bash -c "$4"; fi) >/dev/null 2>&1
    LASTPOST=$(post "$1" "$4" "$3"); [ -n "$LASTPOST" ] && echo "      post: ${LASTPOST:0:140}"
  fi
}
echo "installed plugin $VER loaded from $PR (install record $REC)"
echo "== tags / releases (deny)"
t Bash deny "$S" "git tag v9.9.9"
t Bash deny "$S" "git tag -a v9.9.9 -m x"
t Bash deny "$S" "git tag -d v1.0.0"
t Bash deny "$S" "git push origin --tags"
t Bash deny "$S" "git push --follow-tags origin develop"
t Bash deny "$S" "git push origin refs/tags/v1.0.0"
t Bash deny "$S" "git push origin sgl-v0.7.0"
t Bash deny "$S" "gh api repos/Cuvara/rpg-mmo-server/git/refs -f ref=refs/tags/v9 -f sha=abc"
t Bash deny "$S" "gh api -X POST repos/Cuvara/rpg-mmo-server/git/tags -f tag=v9"
t Bash deny "$S" "gh release create v9.9.9"
echo "== wrapped / nested (deny)"
t Bash deny "$S" "bash -c 'git tag v9'"
t Bash deny "$S" "sh -c \"git push origin --tags\""
t Bash deny "$S" "env GIT_TRACE=0 git tag v9"
t Bash deny "$S" "sudo git tag v9"
t Bash deny "$S" "timeout 5 git tag v9"
t Bash deny "$S" "nohup git tag v9"
t Bash deny "$S" "echo v9 | xargs git tag"
t Bash deny "$S" "eval 'git tag v9'"
t Bash deny "$S" "find . -maxdepth 0 -exec git tag v9 \\;"
t Bash deny "$S" "cmd.exe /c git tag v9"
t Bash deny "$S" "powershell.exe -Command \"git tag v9\""
t Bash deny "$S" "cd $S && git tag v9"
t Bash deny "$WS" "git -C rpg-mmo-server tag v9"
echo "== PowerShell tool"
t PowerShell deny "$S" "git tag v9.9.9"
t PowerShell deny "$S" "& git push origin --tags"
t PowerShell deny "$S" "git.exe tag v9"
t PowerShell deny "$S" "Set-Location $S; git tag v9"
t PowerShell ask  "$S" "git reset --hard HEAD"
t PowerShell ask  "$S" "git push origin develop"
EXEC=0 t PowerShell allow "$S" "git status"
echo "== destructive / protected branch (ask)"
t Bash ask "$S" "git push origin develop"
t Bash ask "$S" "git push --force origin develop"
t Bash ask "$S" "git reset --hard HEAD"
t Bash ask "$S" "git reset HEAD~1"
t Bash ask "$S" "git merge feat/x"
t Bash ask "$S" "git cherry-pick feat/x"
t Bash ask "$S" "git revert HEAD"
t Bash ask "$S" "git commit -m x"
t Bash ask "$S" "git checkout -B develop origin/develop"
t Bash ask "$S" "git branch -f develop HEAD~1"
t Bash ask "$S" "git update-ref -d refs/heads/feat/x"
t Bash ask "$S" "git clean -fdx"
t Bash ask "$S" "git stash"
t Bash ask "$S" "git add -A"
t Bash ask "$S" "git -c alias.t=tag t v9"
t Bash ask "$S" "G=git; \$G tag v9"
t Bash ask "$S" "\$(which git) tag v9"
t Bash ask "$S" "python3 -c \"import os; os.system('git tag v9')\""
echo "== negative paths (allowed, executed)"
t Bash allow "$S" "git status --short"
t Bash allow "$S" "git log --oneline -1"
t Bash allow "$S" "echo 'git tag v9'"
t Bash allow "$S" "git switch -c feat/safety-probe"
t Bash allow "$S" "git commit --allow-empty -m 'mentions git tag v9 and git push --tags'"
t Bash allow "$S" "git tag --list"
t Bash allow "$OTHER" "git tag outside-workspace"
echo "== tripwire: a script the guard cannot read creates a tag and pushes it"
printf '#!/bin/sh\ngit tag v6.6.6 && git push -q origin v6.6.6\n' > "$S/release.sh"
t Bash allow "$S" "sh ./release.sh"
stop=$LASTPOST
case "$stop" in *"STOP - rpg-factory tripwire"*) pass=$((pass + 1)); row PASS Bash "(post) tripwire STOP after script tag+push" STOP STOP "";;
  *) fail=$((fail + 1)); row FAIL Bash "(post) tripwire STOP after script tag+push" STOP none "";; esac
t Bash deny "$S" "touch after-stop.txt"
EXEC=0 t Bash allow "$S" "git status"
python3 -B "$PR/scripts/tripwire.py" --ack "$SID" >/dev/null 2>&1
EXEC=0 t Bash allow "$S" "touch after-ack.txt"
echo "== user baseline file"
t Bash allow "$S" "sh -c 'echo x >> user-wip.txt'"
stop=$LASTPOST
case "$stop" in *"STOP"*"user-wip.txt"*) pass=$((pass + 1)); row PASS Bash "(post) STOP: user baseline file modified" STOP STOP "";;
  *) fail=$((fail + 1)); row FAIL Bash "(post) STOP: user baseline file modified" STOP none "${stop:0:80}";; esac
python3 -B "$PR/scripts/tripwire.py" --ack "$SID" >/dev/null 2>&1

echo "== outcome in the disposable repos"
lt=$(git -C "$S" tag | tr '\n' ' '); rt=$(git -C "$TMP/remote.git" tag | tr '\n' ' ')
if [ "$lt" = "v6.6.6 " ] && [ "$rt" = "v6.6.6 " ]; then pass=$((pass + 1)); echo "PASS  only the tripwire-probe tag exists (local: $lt remote: $rt) - no blocked command ran"
else fail=$((fail + 1)); echo "FAIL  unexpected tags local='$lt' remote='$rt'"; fi
total=$((pass + fail)); echo "installed-safety ($VER): $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
