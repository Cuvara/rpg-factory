#!/usr/bin/env bash
# Safety through the INSTALLED plugin: runs the hook commands exactly as the installed hooks.json
# declares them (CLAUDE_PLUGIN_ROOT = the path installed sessions load: the marketplace directory
# for a directory marketplace, the version-keyed cache copy otherwise), with Claude-shaped payloads,
# against a disposable fake workspace (throwaway repos + a bare remote under mktemp). Nothing in the
# real workspace is touched: RPG_FACTORY_WORKSPACE points at the fake one.
#
# Commands the hooks allow are executed (as Claude would) and followed by any PostToolUse hook;
# asked/denied ones are not executed (nobody approves). At the end the fake repos and remote must
# hold no tag created by a blocked command.
#
# Usage: tests/installed-safety.sh [--plugin-root DIR]   (default: install-status.py loads_from)
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
PR=$(python3 -B "$ROOT/scripts/install-status.py" --json 2>/dev/null | jq -r '.installed.loads_from // empty')
[ "${1:-}" = "--plugin-root" ] && PR="$2"
REC=$(jq -r '.plugins["rpg-factory@rpg-factory"][0] | "\(.version) \(.gitCommitSha[0:7])"' "$HOME/.claude/plugins/installed_plugins.json" 2>/dev/null)
[ -n "$PR" ] && [ -f "$PR/hooks/hooks.json" ] || { echo "NOT_AVAILABLE  no installed rpg-factory (installPath '$PR')"; exit 2; }
VER=$(jq -r .version "$PR/.claude-plugin/plugin.json")
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
export TMPDIR="$TMP/tmpdir"; mkdir -p "$TMPDIR"
export RPG_FACTORY_WORKSPACE="$TMP/ws" CLAUDE_PLUGIN_ROOT="$PR" PYTHONDONTWRITEBYTECODE=1 RPG_FACTORY_STATE_DIR="$TMP/state"
WS="$RPG_FACTORY_WORKSPACE"; S="$WS/rpg-mmo-server"; C="$WS/IndieRPGMMOAdventure"; OTHER="$TMP/elsewhere"
gc() { git -C "$1" -c user.email=t@t -c user.name=t "${@:2}"; }
mkdir -p "$S/backend" "$C/ProjectSettings" "$OTHER"
echo team > "$S/backend/TEAM.md"; echo "m_EditorVersion: 6000" > "$C/ProjectSettings/ProjectVersion.txt"
git init -q --bare "$TMP/remote.git"
for r in "$S" "$C" "$OTHER"; do git -C "$r" init -q -b develop; echo a > "$r/a.txt"; gc "$r" add -A; gc "$r" commit -qm init; done
gc "$S" remote add origin "$TMP/remote.git"; gc "$S" push -q origin develop
gc "$S" branch feat/x; echo "user wip" > "$S/user-wip.txt"          # a pre-existing user file
SID="safety-$$"

fdecide() { # tool path -> allow|warn|high (advisory level) through the installed file-tool hooks
  local d=allow out pd
  while IFS= read -r h; do
    out=$(jq -nc --arg s "$SID" --arg t "$1" --arg p "$2" --arg d "$S" '{session_id:$s,hook_event_name:"PreToolUse",tool_name:$t,tool_input:{file_path:$p,content:"x"},cwd:$d}' | (cd "$S" && bash -c "$h") 2>/dev/null)
    pd=$(jq -r 'if .hookSpecificOutput.permissionDecision then "DECISION" else ((.hookSpecificOutput.additionalContext // "") | (capture("^rpg-factory advisory [(](?<l>[a-z]+)[)]") | .l) // empty) end' <<<"${out:-{\}}" 2>/dev/null)
    case "$pd" in DECISION) d=DECISION;; high) [ "$d" != DECISION ] && d=high;; warn) [ "$d" = allow ] && d=warn;; esac
  done < <(hooks PreToolUse "$1")
  echo "$d"
}
hooks() { # event matcher-tool -> hook commands (one per line)
  jq -r --arg e "$1" --arg t "$2" '.hooks[$e][]? | select((.matcher // "") as $m | $m == "" or ($t | test("^(" + $m + ")$"))) | .hooks[].command' "$PR/hooks/hooks.json"
}
payload() { jq -nc --arg s "$SID" --arg e "$1" --arg t "$2" --arg c "$3" --arg d "$4" '{session_id:$s, hook_event_name:$e, tool_name:$t, tool_input:{command:$c}, tool_response:{}, cwd:$d}'; }
decide() { # tool command cwd -> allow|warn|high (advisory level) (+ reason in $REASON)
  local d=allow out; REASON=""
  while IFS= read -r h; do
    out=$(payload PreToolUse "$1" "$2" "$3" | (cd "$3" && bash -c "$h") 2>/dev/null)
    local pd; pd=$(jq -r 'if .hookSpecificOutput.permissionDecision then "DECISION" else ((.hookSpecificOutput.additionalContext // "") | (capture("^rpg-factory advisory [(](?<l>[a-z]+)[)]") | .l) // empty) end' <<<"${out:-{\}}" 2>/dev/null)
    [ -n "$pd" ] && REASON=$(jq -r '.hookSpecificOutput.additionalContext // ""' <<<"$out" | head -c 90)
    case "$pd" in DECISION) d=DECISION;; high) [ "$d" != DECISION ] && d=high;; warn) [ "$d" = allow ] && d=warn;; esac
  done < <(hooks PreToolUse "$1")
  echo "$d $REASON"
}
post() { # tool command cwd -> prints STOP text if any
  while IFS= read -r h; do
    payload PostToolUse "$1" "$2" "$3" | (cd "$3" && bash -c "$h") 2>/dev/null | jq -r '.hookSpecificOutput.additionalContext // .reason // empty' 2>/dev/null
  done < <(hooks PostToolUse "$1")
}
# SessionStart exactly as installed
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
echo "== tags / releases (advisory high)"
t Bash high "$S" "git tag v9.9.9"
t Bash high "$S" "git tag -a v9.9.9 -m x"
t Bash high "$S" "git tag -d v1.0.0"
t Bash high "$S" "git push origin --tags"
t Bash high "$S" "git push --follow-tags origin develop"
t Bash high "$S" "git push origin refs/tags/v1.0.0"
t Bash high "$S" "git push origin sgl-v0.7.0"
t Bash high "$S" "gh api repos/Cuvara/rpg-mmo-server/git/refs -f ref=refs/tags/v9 -f sha=abc"
t Bash high "$S" "gh api -X POST repos/Cuvara/rpg-mmo-server/git/tags -f tag=v9"
t Bash high "$S" "gh release create v9.9.9"
echo "== wrapped / nested (advisory high)"
t Bash high "$S" "bash -c 'git tag v9'"
t Bash high "$S" "sh -c \"git push origin --tags\""
# git -C into the workspace from outside it, with no RPG_FACTORY_WORKSPACE to fall back on (allowed before 1.0.0)
RPG_FACTORY_WORKSPACE= t Bash high "$OTHER" "git -C $S tag v9.9.9"
t Bash high "$S" "env GIT_TRACE=0 git tag v9"
t Bash high "$S" "sudo git tag v9"
t Bash high "$S" "timeout 5 git tag v9"
t Bash high "$S" "nohup git tag v9"
t Bash high "$S" "echo v9 | xargs git tag"
t Bash high "$S" "eval 'git tag v9'"
t Bash high "$S" "find . -maxdepth 0 -exec git tag v9 \\;"
t Bash high "$S" "cmd.exe /c git tag v9"
t Bash high "$S" "powershell.exe -Command \"git tag v9\""
t Bash high "$S" "cd $S && git tag v9"
t Bash high "$WS" "git -C rpg-mmo-server tag v9"
# 1.0.5: reserved words, a heredoc fed to a shell, gh repository selectors (allowed before)
t Bash high "$S" "if true; then git tag v9; fi"
t Bash high "$S" "{ git tag v9; }"
t Bash high "$S" "f() { git tag v9; }; f"
t Bash high "$S" "bash <<'EOF'
git tag v9
EOF"
t Bash high "$S" "gh --repo Cuvara/rpg-mmo-server release create v9.9.9"
echo "== PowerShell tool"
t PowerShell high "$S" 'if ($true) { git tag v9 }'
t PowerShell high "$S" "git tag v9.9.9"
t PowerShell high "$S" "& git push origin --tags"
t PowerShell high "$S" "git.exe tag v9"
t PowerShell high "$S" "Set-Location $S; git tag v9"
t PowerShell warn  "$S" "git reset --hard HEAD"
t PowerShell warn  "$S" "git push origin develop"
EXEC=0 t PowerShell allow "$S" "git status"
echo "== GitHub remote mutations (remote-only: the guard is the only control)"
t Bash high "$S" "gh api graphql -f query='mutation{createRef(input:{name:\"refs/tags/v9\"}){ref{name}}}'"
t Bash high "$S" "gh repo delete Cuvara/rpg-mmo-server --yes"
t Bash high "$OTHER" "gh repo delete Cuvara/Netcode --yes"
t Bash warn  "$S" "gh api -X PUT repos/Cuvara/rpg-mmo-server/branches/develop/protection --input p.json"
t Bash warn  "$S" "gh api graphql -f query='mutation{updateBranchProtectionRule(input:{}){clientMutationId}}'"
t Bash warn  "$S" "gh repo edit --default-branch main"
EXEC=0 t Bash allow "$S" "gh pr view 1"
echo "== local ref / remote / config mutations"
t Bash warn  "$S" "git fetch origin +refs/heads/develop:refs/heads/develop"
t Bash warn  "$S" "git remote set-url origin https://evil.example/x.git"
t Bash warn  "$S" "git config alias.t tag"
t Bash warn  "$S" "git branch -m develop old"
t Bash warn  "$S" "git pull origin develop"
echo "== destructive / protected branch (advisory warn)"
t Bash warn "$S" "git push origin develop"
t Bash warn "$S" "git push --force origin develop"
t Bash warn "$S" "git reset --hard HEAD"
t Bash warn "$S" "git reset HEAD~1"
t Bash warn "$S" "git merge feat/x"
t Bash warn "$S" "git cherry-pick feat/x"
t Bash warn "$S" "git revert HEAD"
t Bash warn "$S" "git commit -m x"
t Bash warn "$S" "git checkout -B develop origin/develop"
t Bash warn "$S" "git branch -f develop HEAD~1"
t Bash warn "$S" "git update-ref -d refs/heads/feat/x"
t Bash warn "$S" "git clean -fdx"
t Bash warn "$S" "git stash"
t Bash warn "$S" "git add -A"
t Bash warn "$S" "git -c alias.t=tag t v9"
t Bash warn "$S" "G=git; \$G tag v9"
t Bash warn "$S" "\$(which git) tag v9"
t Bash warn "$S" "python3 -c \"import os; os.system('git tag v9')\""
echo "== negative paths (allowed, executed)"
t Bash allow "$S" "git status --short"
t Bash allow "$S" "git log --oneline -1"
t Bash allow "$S" "echo 'git tag v9'"
t Bash allow "$S" "git switch -c feat/safety-probe"
t Bash allow "$S" "git commit --allow-empty -m 'mentions git tag v9 and git push --tags'"
t Bash allow "$S" "git tag --list"
t Bash allow "$OTHER" "git tag outside-workspace"
echo "== human gates: read-only inspection passes, running still asks (1.0.2)"
EXEC=0 t Bash allow "$S" "sed -n 300,340p Tools/verify-multiclient.sh"
EXEC=0 t Bash allow "$S" "cat scripts/bench.sh"
t Bash warn "$S" "bash Tools/verify-multiclient.sh"
t Bash warn "$S" "cat Tools/run-clients.sh | bash"
t Bash warn "$S" "head -3 backend/deploy/.env"
echo "== no tripwire (removed in 1.0.1): a script's effect is never latched, the next command still runs"
printf '#!/bin/sh\ngit tag v6.6.6 && git push -q origin v6.6.6\n' > "$S/release.sh"
t Bash allow "$S" "sh ./release.sh"
[ -z "$LASTPOST" ] && { pass=$((pass + 1)); row PASS Bash "(post) no STOP after a script's tag+push" none none ""; } \
  || { fail=$((fail + 1)); row FAIL Bash "(post) no STOP after a script's tag+push" none STOP "${LASTPOST:0:80}"; }
t Bash allow "$S" "touch after-script.txt"
t Bash allow "$S" "git fetch --tags"
t Bash allow "$S" "sh -c 'echo x >> user-wip.txt'"
[ -z "$LASTPOST" ] && { pass=$((pass + 1)); row PASS Bash "(post) no STOP: user file modified" none none ""; } \
  || { fail=$((fail + 1)); row FAIL Bash "(post) no STOP: user file modified" none STOP "${LASTPOST:0:80}"; }

echo "== file tools and execution modes (installed file-guard + git-guard)"
mkdir -p "$S/backend/shared/proto/gen"; touch "$S/backend/shared/proto/gen/wire.pb.go"
f=$(fdecide Edit "$S/backend/shared/proto/gen/wire.pb.go"); [ "$f" = warn ] && { pass=$((pass + 1)); row PASS Edit "generated path" warn warn ""; } || { fail=$((fail + 1)); row FAIL Edit "generated path" warn "$f" ""; }
f=$(fdecide Edit "$S/user-wip.txt"); [ "$f" = allow ] && { pass=$((pass + 1)); row PASS Edit "pre-existing user file" allow allow ""; } || { fail=$((fail + 1)); row FAIL Edit "pre-existing user file" allow "$f" ""; }
f=$(fdecide Write "$S/new.txt"); [ "$f" = allow ] && { pass=$((pass + 1)); row PASS Write "ordinary new file" allow allow ""; } || { fail=$((fail + 1)); row FAIL Write "ordinary new file" allow "$f" ""; }
EXEC=0 t Bash allow "$S" "bash $PR/scripts/factory-context.sh --mode plan --repo server"
t Bash high "$S" "touch plan-mode.txt"
f=$(fdecide Write "$S/new.txt"); [ "$f" = high ] && { pass=$((pass + 1)); row PASS Write "plan mode: advisory high" high high ""; } || { fail=$((fail + 1)); row FAIL Write "plan mode" high "$f" ""; }
EXEC=0 t Bash allow "$S" "bash $PR/scripts/factory-context.sh --mode implement --repo server"
EXEC=0 t Bash allow "$S" "touch implement-mode.txt"

echo "== outcome in the disposable repos"
lt=$(git -C "$S" tag | tr '\n' ' '); rt=$(git -C "$TMP/remote.git" tag | tr '\n' ' ')
if [ "$lt" = "v6.6.6 " ] && [ "$rt" = "v6.6.6 " ]; then pass=$((pass + 1)); echo "PASS  only the script-probe tag exists (local: $lt remote: $rt) - no blocked command ran"
else fail=$((fail + 1)); echo "FAIL  unexpected tags local='$lt' remote='$rt'"; fi
total=$((pass + fail)); echo "installed-safety ($VER): $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
