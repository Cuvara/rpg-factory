#!/usr/bin/env bash
# Unit tests for scripts/git-guard.py. Builds a throwaway fake workspace in a temp
# dir (never touches the real repos), feeds hook payloads, and checks the decision.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
GUARD="$ROOT/scripts/git-guard.py"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1
trap 'rm -rf "$TMP"' EXIT
unset RPG_FACTORY_WORKSPACE   # the developer shell may point it at the real workspace; this test builds its own
export TMPDIR="$TMP" RPG_FACTORY_STATE_DIR="$TMP/state"   # mode state stays inside this test

WS="$TMP/ws"
OUT="$TMP/outside"
mkdir -p "$WS/rpg-mmo-server/backend" "$WS/IndieRPGMMOAdventure/ProjectSettings" "$OUT"
touch "$WS/rpg-mmo-server/backend/TEAM.md" "$WS/IndieRPGMMOAdventure/ProjectSettings/ProjectVersion.txt"
for r in "$WS/rpg-mmo-server" "$WS/IndieRPGMMOAdventure" "$OUT"; do
  git -C "$r" init -q -b develop
  git -C "$r" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
done
SERVER="$WS/rpg-mmo-server"
CLIENT="$WS/IndieRPGMMOAdventure"
FEATURE="$TMP/ws/feature-repo"
git init -q -b feat/gateway/x "$FEATURE"

pass=0; fail=0
check() { # expected cwd command [env] [tool]
  local expected="$1" cwd="$2" cmd="$3" envset="${4:-}" tool="${5:-Bash}" payload out got
  payload=$(jq -cn --arg c "$cmd" --arg d "$cwd" --arg t "$tool" '{hook_event_name:"PreToolUse", tool_name:$t, tool_input:{command:$c}, cwd:$d, session_id:"guardtest"}')
  if [ -n "$envset" ]; then out=$(env "$envset" CLAUDE_PLUGIN_ROOT="$ROOT" python3 "$GUARD" <<<"$payload")
  else out=$(CLAUDE_PLUGIN_ROOT="$ROOT" python3 "$GUARD" <<<"$payload"); fi
  got=$(jq -r 'if .hookSpecificOutput.permissionDecision then "DECISION" else ((.hookSpecificOutput.additionalContext // "") | (capture("^rpg-factory advisory [(](?<l>[a-z]+)[)]") // {l: "allow"}) | .l) end' <<<"${out:-{\}}" 2>/dev/null || echo "invalid-json")
  if [ "$got" = "$expected" ]; then pass=$((pass + 1))
  else fail=$((fail + 1)); printf 'FAIL expected=%s got=%s cwd=%s cmd=%q\n  out=%s\n' "$expected" "$got" "${cwd#$TMP/}" "$cmd" "$out"; fi
}

# read-only commands pass through
check allow "$SERVER" "git status"
check allow "$SERVER" "git diff --stat"
check allow "$SERVER" "git log --oneline -5"
check allow "$SERVER" "git stash list"
check allow "$SERVER" "git tag -l"
check allow "$SERVER" "git tag --sort=-v:refname"           # listing with sort/format options is a read
check allow "$SERVER" "git tag --format='%(refname)' --sort=-creatordate -n1"
check high "$SERVER" "git tag --sort=-v:refname v9.9.9"     # a name after listing options still creates
check high "$SERVER" "git tag --sort -v:refname"            # separated value form is ambiguous: not a listing
check allow "$SERVER" "git add backend/gateway/main.go"
check allow "$SERVER" "git restore --staged backend/gateway/main.go"
check allow "$SERVER" 'echo "git reset --hard"'
# destructive
check warn "$SERVER" "git reset --hard HEAD~1"
check warn "$SERVER" "git clean -fd"
check warn "$SERVER" "git checkout -- ."
check warn "$SERVER" "git restore backend/gateway/main.go"
check warn "$SERVER" "git stash"
check warn "$SERVER" "git stash drop"
check warn "$SERVER" "git branch -D feat/old"
check warn "$SERVER" "git push --force origin feat/x"
check warn "$SERVER" "git push origin feat/x"
check warn "$SERVER" "git rebase develop"
# staging everything
check warn "$SERVER" "git add -A"
check warn "$SERVER" "git add ."
check warn "$SERVER" "git commit -am wip"
# protected branches
check warn "$SERVER" "git commit -m 'fix(gateway): x'"
check warn "$WS" "git -C rpg-mmo-server commit -m x"
check warn "$WS" "cd IndieRPGMMOAdventure && git commit -m x"
check allow "$SERVER" "git checkout -b feat/gateway/y && git commit -m 'feat(gateway): y'"
check allow "$FEATURE" "git commit -m 'feat(gateway): x'"
check warn "$FEATURE" "git commit --amend --no-edit"
# tags + submodules
check high "$SERVER" "git tag sgl-v0.7.0"
check high "$SERVER" "git tag -a v1.2.3 -m release"
check high "$SERVER" "git tag -d v0.1.0"
check high "$SERVER" "git push origin --tags"
check high "$SERVER" "git push origin v1.2.3"
check high "$SERVER" "git push origin refs/tags/core-baseline-v2"
check high "$SERVER" "git status && git tag v9.9.9"
check warn "$CLIENT" "git submodule update --init --recursive"
# registry human gates (ask) inside the workspace
check warn "$SERVER" "kubectl apply -f backend/deploy/k8s/app/50-fleet-map.yaml"
check warn "$SERVER" "helm upgrade x y"
check warn "$SERVER" "ssh deploy@vps.example"
check warn "$SERVER" "gh workflow run cd.yml --ref develop"
check warn "$SERVER" "gh pr create --fill"
check warn "$WS" "./toggle-packages.sh dev"
check warn "$SERVER" "cat backend/deploy/kubeconfig.local"
check warn "$SERVER" "make flow-up"
check warn "$CLIENT" "bash Tools/run-clients.sh 4"
check allow "$SERVER" "make flow-check"
check allow "$SERVER" "gh pr view 12"
check allow "$SERVER" "echo kubectl is gated"
check allow "$OUT" "kubectl get pods"
check warn "$SERVER" "sudo kubectl get pods -n rpg"
check warn "$SERVER" "KUBECONFIG=x kubectl apply -f a.yaml"
check warn "$SERVER" "bash backend/deploy/k8s/verify/verify.sh --target k8s-dev"
check warn "$SERVER" "bash backend/deploy/db/backup.sh"
check warn "$SERVER" "JWT_SECRET=x ./scripts/bench.sh 50 60s cluster out"
check warn "$CLIENT" "Unity.exe -batchmode -executeMethod PlayerBuilder.Build"
check warn "$CLIENT" "Unity.exe -batchmode -executeMethod PlayClientBuilder.Build"      # _SampleBuild entries (client.buildscripts)
check warn "$CLIENT" "Unity.exe -batchmode -executeMethod SampleBuilder.Build"
check warn "$CLIENT" "Unity.exe -batchmode -projectPath . -runTests -testPlatform EditMode -testResults r.xml"
check allow "$CLIENT" "grep -rn runTests unity-build-workflows/.github/workflows"       # mentioning the flag is not a run
check warn "$SERVER" "psql -c 'DELETE FROM schema_migrations'"
check allow "$SERVER" "cat backend/deploy/.env.example"
# 1.0.2: a read_only_exempt gate never asks for read-only inspection of the gated script; running it still asks
check allow "$CLIENT" "sed -n 300,340p $CLIENT/Tools/verify-multiclient.sh"
check allow "$CLIENT" "sed -n '1,\$p' Tools/run-clients.sh"
check allow "$CLIENT" "sed -n -e 10q Tools/run-clients.sh"
check allow "$CLIENT" "cat Tools/run-clients.sh | grep -n Unity"
check allow "$CLIENT" "grep -n 'players' Tools/verify-multiclient.sh"
check allow "$CLIENT" "head -40 Tools/verify-multiclient.sh && wc -l Tools/run-clients.sh"
check allow "$SERVER" "cat backend/deploy/db/backup.sh"
check allow "$SERVER" "sed -n 1,30p scripts/bench.sh"
check allow "$WS" "cat toggle-packages.sh"
check allow "$SERVER" "git log --oneline -5 -- backend/deploy/k8s/verify/verify.sh"
check warn   "$CLIENT" "bash Tools/verify-multiclient.sh"
check warn   "$CLIENT" "./Tools/run-clients.sh 2"
check warn   "$CLIENT" "sed -n 1,5p Tools/run-clients.sh; bash Tools/run-clients.sh 2"   # inspect, then run
check warn   "$CLIENT" "cat Tools/run-clients.sh | bash"                                  # piped into a shell
check warn   "$CLIENT" "sed -n 1,5p Tools/run-clients.sh | sh"
check warn   "$CLIENT" "sed -i s/4/8/ Tools/run-clients.sh"                               # edits the script
check warn   "$CLIENT" "sed -n '1e bash Tools/run-clients.sh' x.txt"                      # sed e runs a command
check warn   "$CLIENT" "sed -n 1w/tmp/x Tools/run-clients.sh"                             # sed w writes a file
check warn   "$CLIENT" "sed -f prog.sed Tools/run-clients.sh"                             # script file: unknown
check warn   "$CLIENT" "sed -n 1,5p Tools/run-clients.sh > copy.sh"                       # redirect: a write
check warn   "$CLIENT" "find Tools -name run-clients.sh -exec {} \\;"
check warn   "$CLIENT" "xargs -a list.txt Tools/run-clients.sh"
check warn   "$SERVER" "sed -n 1,5p backend/deploy/kubeconfig.local"                      # secrets is not exempt
check warn   "$SERVER" "head -3 backend/deploy/.env"
# every gate with a match: exempt from read-only inspection except secrets (reading is what it guards)
jq -e '[.human_gates[] | select(.match != null and .id != "secrets") | .read_only_exempt == true] | all' "$ROOT/registry.json" >/dev/null \
  && jq -e '.human_gates[] | select(.id == "secrets") | (.read_only_exempt // false) == false' "$ROOT/registry.json" >/dev/null \
  && pass=$((pass + 1)) || { fail=$((fail + 1)); echo "FAIL read_only_exempt: every matching gate except secrets"; }
# quoted / heredoc content is data, not commands
check allow "$FEATURE" "git commit -m \"\$(cat <<'EOF'
docs: explain why git reset --hard is guarded
EOF
)\""
check allow "$FEATURE" "git commit -F - <<'EOF'
chore: mention git push --force in docs
EOF"
check allow "$FEATURE" "git commit -m 'docs: explain that agents never git tag'"
# chained commands: one dangerous segment is enough
check warn "$SERVER" "git status && git clean -fdx"
# outside the workspace and opt-out
check allow "$OUT" "git reset --hard"
check allow "$SERVER" "git reset --hard" "RPG_FACTORY_GUARD=off"
# a broken registry regex must not disable git protection (fail-open regression)
BROKEN="$TMP/broken-plugin"; mkdir -p "$BROKEN/scripts"
jq '.human_gates[1].match = "(("' "$ROOT/registry.json" > "$BROKEN/registry.json"
payload=$(jq -cn --arg d "$SERVER" '{tool_name:"Bash", tool_input:{command:"git reset --hard"}, cwd:$d}')
got=$(CLAUDE_PLUGIN_ROOT="$BROKEN" python3 "$GUARD" <<<"$payload" | jq -r 'if .hookSpecificOutput.permissionDecision then "DECISION" else ((.hookSpecificOutput.additionalContext // "") | (capture("^rpg-factory advisory [(](?<l>[a-z]+)[)]") // {l: "allow"}) | .l) end')
if [ "$got" = "warn" ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL broken regex disabled git protection (got $got)"; fi
# ---- v2: wrappers and nested shells (were ALLOW in the v0.2 audit)
check warn "$SERVER" 'bash -c "git reset --hard"'
check warn "$SERVER" "sh -c 'git push --force'"
check warn "$SERVER" 'bash -lc "cd backend && git clean -fdx"'
check allow "$SERVER" 'bash -lc "cd /tmp && git clean -fdx"'
check warn "$SERVER" 'eval "git reset --hard"'
check warn "$SERVER" "env git reset --hard"
check warn "$SERVER" "env -u X GIT_TRACE=1 git reset --hard"
check warn "$SERVER" "command git reset --hard"
check warn "$SERVER" "sudo git reset --hard"
check warn "$SERVER" "sudo -u root git clean -f"
check warn "$SERVER" "timeout 5 git push origin feat/x"
check warn "$SERVER" "timeout -s KILL 30 git stash"
check warn "$SERVER" "nohup git push &"
check warn "$SERVER" "nice -n 10 git gc --prune=now"
check warn "$SERVER" "xargs git reset --hard < /dev/null"
check high "$SERVER" "echo v9 | xargs git tag"              # xargs appends the tag name (found by installed-safety)
check high "$SERVER" "echo v9 | xargs -n1 git tag"
check high "$SERVER" "printf a | xargs -I{} git tag {}"
check warn "$SERVER" "echo develop | xargs git push origin"
check allow "$SERVER" "xargs git tag -l < /dev/null"
check allow "$SERVER" "echo f | xargs git log --oneline"
check warn "$SERVER" 'find . -name x -exec git checkout -- {} \;'
check warn "$SERVER" "cmd.exe /c git reset --hard"
check warn "$SERVER" 'powershell.exe -c "git reset --hard"'
check warn "$SERVER" "powershell.exe -EncodedCommand ZwBpAHQA"
check warn "$SERVER" 'G=git; $G reset --hard'
check warn "$SERVER" '$(which git) reset --hard'
check warn "$SERVER" '`which git` push'
check warn "$SERVER" 'git -c alias.nuke="reset --hard" nuke'
check warn "$SERVER" 'python3 -c "import os; os.system(\"git reset --hard\")"'
check warn "$SERVER" 'node -e "require(\"child_process\").execSync(\"git push\")"'
check high "$SERVER" 'bash -c "git tag v1.0.0"'
check high "$SERVER" 'env GIT_DIR=.git git push origin --tags'
check high "$SERVER" "sudo git tag sgl-v9.9.9"
# ---- v2: commit-creating / ref-destroying operations
check warn "$SERVER" "git merge feat/x"
check warn "$SERVER" "git merge --no-ff feat/x"
check warn "$SERVER" "git cherry-pick abc123"
check warn "$SERVER" "git revert HEAD"
check warn "$SERVER" "git am patch.mbox"
check warn "$SERVER" "git pull --rebase"
check warn "$SERVER" "git reset HEAD~3"
check warn "$SERVER" "git checkout -B develop origin/develop"
check warn "$SERVER" "git switch -C develop origin/develop"
check warn "$SERVER" "git branch -f develop HEAD~2"
check warn "$SERVER" "git update-ref -d refs/heads/x"
check high "$SERVER" "git update-ref refs/tags/v9 HEAD"
check warn "$SERVER" "git gc --prune=now"
check warn "$SERVER" "git reflog expire --expire=now --all"
check warn "$SERVER" "git prune"
check high "$SERVER" "git push origin HEAD:refs/tags/v2.0.0"
check high "$SERVER" "git push --mirror origin"
check allow "$FEATURE" "git merge develop"
check allow "$FEATURE" "git cherry-pick abc123"
check warn "$SERVER" "git pull"                                # may merge into protected develop (v0.4)
check allow "$SERVER" "git pull --ff-only"
check allow "$SERVER" "git merge --ff-only origin/develop"          # a fast-forward creates no commit
check warn "$SERVER" "git merge origin/develop"
check allow "$SERVER" "git pull --rebase=false --ff-only"           # --rebase=false|no is not a rebase
check allow "$SERVER" "git pull --rebase=no --ff-only"
check warn "$SERVER" "git pull --rebase=false"                      # still may merge
check warn "$SERVER" "git pull --rebase=merges"
check allow "$FEATURE" "git pull"
check allow "$SERVER" "git merge --abort"
check allow "$SERVER" "git fetch --prune"
# ---- v2: gh API / releases
check high "$SERVER" "gh api -X POST repos/Cuvara/x/git/refs -f ref=refs/tags/v9 -f sha=abc"
check high "$SERVER" "gh api repos/Cuvara/x/git/tags -f tag=v9"
check high "$SERVER" "gh release create v1.0.0"
check high "$SERVER" "gh api -X POST repos/Cuvara/x/releases -f tag_name=v1"
check warn "$SERVER" "gh api -X POST repos/Cuvara/x/git/refs -f ref=refs/heads/x -f sha=abc"
check allow "$SERVER" "gh api repos/Cuvara/x/git/refs/tags"
check allow "$SERVER" "gh release list"
# ---- v2: read-only wrapped commands stay allowed (no false positives)
check allow "$SERVER" 'bash -c "git status"'
check allow "$SERVER" "env git log --oneline -3"
check allow "$SERVER" "timeout 5 git fetch origin"
check allow "$SERVER" "find . -name '*.cs' -type f"
check allow "$SERVER" "sudo ls /root"
check allow "$SERVER" 'python3 -c "print(1)"'
check allow "$SERVER" 'echo $HOME && ls'
# ---- v2: PowerShell tool
check high "$SERVER" "git tag v1.2.3" "" PowerShell
check warn "$SERVER" "git reset --hard; Get-ChildItem" "" PowerShell
check warn "$SERVER" "& 'git.exe' push --force" "" PowerShell
check warn "$SERVER" "Set-Location ..\\IndieRPGMMOAdventure; git commit -m x" "" PowerShell
check warn "$SERVER" "git merge feat/x" "" PowerShell
check allow "$SERVER" "git status; git log -1" "" PowerShell
check warn "$SERVER" "kubectl apply -f x.yaml" "" PowerShell
# ---- v2: repo git aliases are expanded
git -C "$SERVER" config alias.wipe "reset --hard"
git -C "$SERVER" config alias.shwipe '!git reset --hard'
check warn "$SERVER" "git wipe"
check warn "$SERVER" "git shwipe"
# ---- v2: worktree of a protected repo keeps protected-branch rules via the main checkout
git -C "$SERVER" worktree add -q "$TMP/ws/srv-wt" -b feat/server/wt 2>/dev/null
check allow "$TMP/ws/srv-wt" "git commit -m 'feat(server): x'"
git -C "$TMP/ws/srv-wt" switch -q -c release-9 2>/dev/null
check warn "$TMP/ws/srv-wt" "git commit -m x"
# ---- linked worktrees OUTSIDE the workspace root (Orca worktrees, sibling dirs) are classified as their main
# checkout when it lies in the workspace (registry repo or not); a main checkout outside it stays silent
OWT="$TMP/orca/server-wt"; OPW="$TMP/orca/server-release"; OFW="$TMP/orca/rpgf-wt"; OXW="$TMP/orca/other-wt"
git -C "$SERVER" worktree add -q "$OWT" -b feat/server/outside 2>/dev/null
git -C "$SERVER" worktree add -q "$OPW" -b release-7 2>/dev/null
git -C "$WS" init -q -b main rpg-factory && git -C "$WS/rpg-factory" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
git -C "$WS/rpg-factory" worktree add -q "$OFW" -b feat/core/outside 2>/dev/null
git -C "$OUT" worktree add -q "$OXW" -b feat/other 2>/dev/null
check allow "$OWT" "git commit -m 'feat(server): x'"
check allow "$OWT" "git status"
check high "$OWT" "git tag -a v9.9.9 -m x"
check high "$OWT" "git push origin --tags"
check warn "$OWT" "git push --force origin main"
check warn "$OWT" "git reset --hard HEAD~3"
check high "$SERVER" "git -C $OWT tag -a v9.9.9 -m x"            # from inside the workspace via -C
check high "$OUT" "git -C $OWT push origin --tags"                # from outside the workspace via -C
check warn "$OUT" "git -C $OWT push --force origin feat/server/outside"
check warn "$OPW" "git commit -m x"                               # protected branch in the outside worktree
check warn "$OPW" "git merge feat/x"
check high "$OFW" "git tag -a v9.9.9 -m x"                        # non-registry repo whose main checkout is in the workspace
check warn "$OFW" "git push --force origin main"
check allow "$OFW" "git commit -m 'feat(core): x'"
check allow "$OXW" "git tag -a v9.9.9 -m x"                       # main checkout outside the workspace: no opinion
check allow "$OXW" "git push --force origin main"
check allow "$SERVER" "git -C $OXW tag v9.9.9"
check allow "$TMP/orca/missing" "git tag v9.9.9"                  # not a repo / missing dir: no opinion
# ---- 1.0.1: the tripwire latch is gone - state files left by older versions (a session LATCH, open workspace
# events, a legacy single-file latch) never block anything
mkdir -p "$TMP/rpg-factory/guardtest" && echo "test violation" > "$TMP/rpg-factory/guardtest/LATCH"
python3 -B - "$TMP/state" "$TMP/ws" <<'PY'
import hashlib, json, os, sys
key = hashlib.sha1(os.path.abspath(sys.argv[2]).encode()).hexdigest()[:12]
os.makedirs(os.path.join(sys.argv[1], "latch", key), exist_ok=True)
for p in (os.path.join(sys.argv[1], "latch", key, "20261014T000000Z-abc123.json"), os.path.join(sys.argv[1], "latch", key + ".json")):
    json.dump({"workspace": sys.argv[2], "session": "other", "message": "[client] pre-existing user file changed"}, open(p, "w"))
PY
check allow "$SERVER" "git fetch --tags"
check allow "$SERVER" "git fetch origin --tags --prune"
check allow "$SERVER" "touch newfile"
check allow "$FEATURE" "git commit -m 'feat(gateway): x'"
check allow "$SERVER" "git switch -c feat/server/after-latch"
check allow "$SERVER" "python3 build.py"
check allow "$SERVER" "git status"
check warn   "$SERVER" "git stash drop"                       # the unrelated git safety rules still apply
check high  "$SERVER" "git push origin --tags"
rm -rf "$TMP/rpg-factory/guardtest/LATCH" "$TMP/state/latch"
# non-Bash payloads are ignored
out=$(jq -cn '{tool_name:"Read", tool_input:{file_path:"x"}, cwd:"/"}' | CLAUDE_PLUGIN_ROOT="$ROOT" python3 "$GUARD")
if [ -z "$out" ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL non-Bash payload produced output: $out"; fi
# malformed stdin never breaks the session
out=$(echo 'not json' | CLAUDE_PLUGIN_ROOT="$ROOT" python3 "$GUARD"; echo "exit=$?")
if [ "$out" = "exit=0" ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL malformed stdin: $out"; fi

# ---- v0.4: execution modes - declared with factory-context.sh --mode, enforced per session
mcheck() { # expected command [tool]
  local out got; out=$(jq -cn --arg c "$2" --arg d "$SERVER" --arg t "${3:-Bash}" '{tool_name:$t,tool_input:{command:$c},cwd:$d,session_id:"modes"}' | CLAUDE_PLUGIN_ROOT="$ROOT" python3 "$GUARD")
  got=$(jq -r 'if .hookSpecificOutput.permissionDecision then "DECISION" else ((.hookSpecificOutput.additionalContext // "") | (capture("^rpg-factory advisory [(](?<l>[a-z]+)[)]") // {l: "allow"}) | .l) end' <<<"${out:-{\}}")
  if [ "$got" = "$1" ]; then pass=$((pass + 1)); else fail=$((fail + 1)); printf 'FAIL mode expected=%s got=%s cmd=%s\n  out=%s\n' "$1" "$got" "$2" "$out"; fi
}
CTX="$ROOT/scripts/factory-context.sh"; RC="$ROOT/scripts/run-checks.py"
mcheck allow "touch before-any-mode.txt"                                  # no mode declared: normal rules
mcheck allow "bash $CTX --mode plan --repo server --paths backend/x.go"    # declaring is read-only
mcheck high  "touch plan.txt"
mcheck high  "git switch -c feat/x/plan"
mcheck high  "python3 $RC --repo server"
mcheck allow "git status 2>/dev/null"
mcheck allow "git log --oneline -3 2>&1 | head -3"
mcheck allow "sed -n 10,40p backend/x.go"                                 # print-only sed is read-only
mcheck high  "sed -i s/a/b/ backend/x.go"
mcheck high  "sed -n 's/a/b/w out.txt' backend/x.go"
mcheck allow "python3 $ROOT/scripts/factory-status.py"
mcheck high  "touch x" PowerShell
mcheck allow "bash $CTX --mode=validate --repo server"
mcheck allow "python3 $RC --repo server --paths backend/x.go"
mcheck allow "python3 $RC --repo server --status | head -20"
mcheck high  "touch validate.txt"
mcheck allow "bash $CTX --mode analyze"
mcheck high  "git commit -m x"
# the switch command in the denial pastes into bash: no backslashes, also when Windows reports C:\... as the root
winroot=$(cygpath -w "$ROOT" 2>/dev/null || echo "$ROOT")
reason=$(jq -cn --arg d "$SERVER" '{tool_name:"Bash",tool_input:{command:"git commit -m y"},cwd:$d,session_id:"modes"}' \
  | CLAUDE_PLUGIN_ROOT="$winroot" python3 "$GUARD" | jq -r '.hookSpecificOutput.additionalContext // ""')
bs='\'
case "$reason" in *"$bs"*|"") fail=$((fail + 1)); echo "FAIL mode denial command is not bash-safe: $reason";;
  *'/scripts/factory-context.sh" --mode implement'*) pass=$((pass + 1));;
  *) fail=$((fail + 1)); echo "FAIL mode denial names no switch command: $reason";; esac
mcheck allow "bash $CTX --mode implement --repo server"
mcheck allow "touch implement.txt"
mcheck allow "git switch -c feat/x/impl"
mcheck allow "bash $CTX --mode nonsense"                                   # unknown modes are not recorded
mcheck allow "touch still-implement.txt"
# the mode can also be declared through the Skill tool's arguments (hook on Skill)
skill() { jq -cn --arg a "$1" --arg sk "${2:-rpg-factory:factory-core}" --arg d "$SERVER" '{tool_name:"Skill",tool_input:{skill:$sk,args:$a},cwd:$d,session_id:"modes"}' | CLAUDE_PLUGIN_ROOT="$ROOT" python3 "$ROOT/scripts/factory_session.py" --skill; }
skill "Plan-only task: add an AOI radius knob. No edits."
mcheck high  "touch via-skill-plan.txt"
skill "Validate only, change nothing"
mcheck high  "touch via-skill-validate.txt"
mcheck allow "python3 $RC --repo server"
skill "Add a knob to the server"                                         # no explicit mode: unchanged (validate)
mcheck high  "touch still-validate.txt"
skill "mode: implement - the user approved the plan"
mcheck allow "touch via-skill-implement.txt"
skill "plan only" "other-plugin:skill"                                    # other plugins' skills never set a Factory mode
mcheck allow "touch other-plugin.txt"
# a session id that is not a plain UUID: git-guard must find the MODE factory_session wrote (same fstate.session_key)
jq -cn --arg d "$SERVER" '{tool_name:"Skill",tool_input:{skill:"rpg-factory:factory-core",args:"plan only"},cwd:$d,session_id:"odd/id:1"}' \
  | CLAUDE_PLUGIN_ROOT="$ROOT" python3 "$ROOT/scripts/factory_session.py" --skill >/dev/null
o=$(jq -cn --arg d "$SERVER" '{tool_name:"Bash",tool_input:{command:"touch odd-id.txt"},cwd:$d,session_id:"odd/id:1"}' | CLAUDE_PLUGIN_ROOT="$ROOT" python3 "$GUARD")
case "$o" in *"Factory mode is \`plan\`"*) pass=$((pass + 1));; *) fail=$((fail + 1)); echo "FAIL mode for a non-UUID session id not seen by git-guard: ${o:-none}";; esac

# ---- 1.0.0: a tech skill (registry kind "tech") is denied until one of its used_by leads ran in the session
sk() { local o; o=$(jq -cn --arg sk "$1" --arg s "$2" --arg d "$SERVER" '{tool_name:"Skill",tool_input:{skill:$sk,args:"how do I run one test"},cwd:$d,session_id:$s}' \
  | CLAUDE_PLUGIN_ROOT="$ROOT" python3 "$ROOT/scripts/factory_session.py" --skill); jq -r 'if .hookSpecificOutput.permissionDecision then "DECISION" elif .hookSpecificOutput.updatedInput then "swap:" + .hookSpecificOutput.updatedInput.skill else ((.hookSpecificOutput.additionalContext // "") | (capture("^rpg-factory advisory [(](?<l>[a-z]+)[)]") // {l: "allow"}) | .l) end' <<<"${o:-{\}}"; }
skchk() { local got; got=$(sk "$2" "$3"); if [ "$got" = "$1" ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL skill order expected=$1 got=$got skill=$2 session=$3"; fi; }
advs() { CLAUDE_PLUGIN_ROOT="$ROOT" python3 -B "$ROOT/scripts/factory_session.py" --advisories "$1" | tr -d '\r'; }
skchk allow rpg-factory:factory-core tech-a                 # core skill: never gated
skchk high  rpg-factory:go-backend tech-a                   # tech before its lead: warned, the call still runs
skchk high  rpg-factory:go-backend tech-a                   # warned again: a warning does not count as a lead
skchk allow rpg-factory:server-realtime tech-a              # a lead of another tech skill does not satisfy go-backend
skchk high  rpg-factory:go-backend tech-a
skchk allow rpg-factory:dotnet-gameserver tech-a            # ...but it satisfies its own tech skill
skchk allow rpg-factory:server-services tech-a
skchk allow rpg-factory:go-backend tech-a                   # after a used_by lead: no advisory
skchk swap:rpg-factory:factory-core rpg-factory:go-backend tech-b   # before factory-core: auto-corrected to factory-core
skchk allow other-plugin:go-backend tech-b                  # other plugins are not Factory skills
# every registry tech skill (new ones included, nothing to edit here): auto-corrected first, warned before a
# lead (no second swap: no loop), quiet after its first lead
while IFS=$'\t' read -r t lead; do
  skchk "swap:rpg-factory:factory-core" "rpg-factory:$t" "every-$t"; skchk high "rpg-factory:$t" "every-$t"
  skchk allow "rpg-factory:$lead" "every-$t"; skchk allow "rpg-factory:$t" "every-$t"
done < <(jq -r '.skills | to_entries[] | select(.value.kind == "tech") | "\(.key)\t\(.value.used_by[0])"' "$ROOT/registry.json")
# regression (1.0.3 dogfood tech-go / tech-dots): early tech skills are advisory or auto-corrected, never a
# decision, the hook always exits 0, and the session state says what happened
o_all=""
for step in "rpg-factory:factory-core ord-go" "rpg-factory:go-backend ord-go" "rpg-factory:server-services ord-go" "rpg-factory:go-backend ord-go" \
            "rpg-factory:unity-dots ord-dots" "rpg-factory:unity-package ord-dots" "rpg-factory:unity-dots ord-dots" \
            "rpg-factory:factory-core ord-normal" "rpg-factory:unity-package ord-normal" "rpg-factory:unity-dots ord-normal"; do
  set -- $step
  o=$(jq -cn --arg sk "$1" --arg s "$2" --arg d "$SERVER" '{tool_name:"Skill",tool_input:{skill:$sk,args:"x"},cwd:$d,session_id:$s}' \
      | CLAUDE_PLUGIN_ROOT="$ROOT" python3 "$ROOT/scripts/factory_session.py" --skill); rc=$?
  [ $rc -eq 0 ] || { fail=$((fail + 1)); echo "FAIL skill hook exited $rc for $step"; }
  o_all="$o_all$o"
done
grep -q permissionDecision <<<"$o_all" && { fail=$((fail + 1)); echo "FAIL skill hook returned a permission decision"; } || pass=$((pass + 1))
[ "$(advs ord-go)" = "go-backend warn lead-missing" ] && pass=$((pass + 1)) || { fail=$((fail + 1)); echo "FAIL early go-backend after factory-core: advisories '$(advs ord-go)'"; }
[ "$(advs ord-dots)" = "unity-dots autocorrect factory-core" ] && pass=$((pass + 1)) || { fail=$((fail + 1)); echo "FAIL early unity-dots before factory-core: advisories '$(advs ord-dots)'"; }
[ -z "$(advs ord-normal)" ] && pass=$((pass + 1)) || { fail=$((fail + 1)); echo "FAIL normal order produced advisories '$(advs ord-normal)'"; }
seen=$(CLAUDE_PLUGIN_ROOT="$ROOT" python3 -B "$ROOT/scripts/factory_session.py" --skills ord-dots | tr -d '\r' | tr '\n' ' ' | sed 's/ $//')
[ "$seen" = "factory-core unity-package unity-dots" ] && pass=$((pass + 1)) || { fail=$((fail + 1)); echo "FAIL session records what loaded (factory-core for the corrected call): '$seen'"; }
reason=$(jq -cn --arg d "$SERVER" '{tool_name:"Skill",tool_input:{skill:"rpg-factory:unity-dots"},cwd:$d,session_id:"tech-c"}' \
  | CLAUDE_PLUGIN_ROOT="$ROOT" python3 "$ROOT/scripts/factory_session.py" --skill | jq -r '.hookSpecificOutput.additionalContext // ""')
case "$reason" in *'/scripts/factory-context.sh"'*"rpg-factory:unity-package"*) pass=$((pass + 1));;
  *) fail=$((fail + 1)); echo "FAIL tech-skill denial names no lead / route command: $reason";; esac
out=$(jq -cn --arg d "$SERVER" '{tool_name:"Skill",tool_input:{skill:"rpg-factory:go-backend"},cwd:$d,session_id:"tech-d"}' \
  | CLAUDE_PLUGIN_ROOT="$TMP/no-such-plugin" python3 "$ROOT/scripts/factory_session.py" --skill; echo "rc=$?")
[ "$out" = "rc=0" ] && pass=$((pass + 1)) || { fail=$((fail + 1)); echo "FAIL skill hook without a registry must fail open: $out"; }

# ---- v0.4: GitHub remote mutations (remote-only: the guard is the only defence)
check high "$SERVER" "gh api graphql -f query='mutation{createRef(input:{repositoryId:\"R\",name:\"refs/tags/v9\",oid:\"abc\"}){ref{name}}}'"
check high "$SERVER" "gh api graphql -f query='mutation(\$n:String!){createRef(input:{name:\$n}){ref{name}}}' -f n=refs/tags/v9"
check high "$SERVER" "gh api graphql -f query='mutation{createRelease(input:{tagName:\"v9\"}){release{id}}}'"
check warn "$SERVER" "gh api graphql -f query='mutation{updateBranchProtectionRule(input:{branchProtectionRuleId:\"x\"}){clientMutationId}}'"
check warn "$SERVER" "gh api graphql -F query=@mutation.graphql"
check warn "$SERVER" "gh api graphql --input body.json"
check allow "$SERVER" "gh api graphql -f query='query{viewer{login}}'"
check allow "$SERVER" "gh api repos/Cuvara/rpg-mmo-server/branches/develop/protection"
check warn "$SERVER" "gh api -X PUT repos/Cuvara/rpg-mmo-server/branches/develop/protection --input p.json"
check warn "$SERVER" "gh api -X DELETE repos/Cuvara/rpg-mmo-server/branches/develop/protection"
check warn "$SERVER" "gh api --method POST repos/Cuvara/rpg-mmo-server/rulesets -f name=x"
check high "$SERVER" "gh api -X DELETE repos/Cuvara/rpg-mmo-server"
check high "$SERVER" "gh api repos/Cuvara/rpg-mmo-server/git/tags -f tag=v9 -f object=abc"
check high "$SERVER" "gh api -XPOST repos/Cuvara/rpg-mmo-server/releases -f tag_name=v9"
check warn "$SERVER" "gh api -X PATCH repos/Cuvara/rpg-mmo-server -f default_branch=main"
check warn "$SERVER" "gh api repos/Cuvara/rpg-mmo-server/issues -f title=x"
check allow "$SERVER" "gh api repos/Cuvara/rpg-mmo-server/pulls --jq '.[].number'"
check high "$SERVER" "gh repo delete Cuvara/rpg-mmo-server --yes"
check high "$SERVER" "gh repo archive Cuvara/rpg-mmo-server"
check warn "$SERVER" "gh repo edit --default-branch main"
check warn "$SERVER" "gh repo rename x"
check warn "$SERVER" "gh repo sync"
check warn "$SERVER" "gh secret set TOKEN"
check warn "$SERVER" "gh variable delete X"
check warn "$SERVER" "gh workflow disable ci.yml"
check warn "$SERVER" "gh run cancel 12"
check warn "$SERVER" "gh pr close 12"
check warn "$SERVER" "gh pr comment 12 -b hi"
check warn "$SERVER" "gh label create x"
check high "$SERVER" "gh release edit v1 --draft=false"
check allow "$SERVER" "gh pr view 12"
check allow "$SERVER" "gh pr checks 12"
check allow "$SERVER" "gh run view 1 --log"
check allow "$SERVER" "gh repo view"
check allow "$SERVER" "gh release list"
check allow "$SERVER" "gh auth status"
check allow "$SERVER" "gh search prs --repo Cuvara/Netcode x"
check high "$SERVER" "bash -c 'gh repo delete Cuvara/Netcode --yes'"
# outside the workspace, a command naming a registry repo is still checked; unrelated repos are not
check high "$OUT" "gh repo delete Cuvara/Netcode --yes"
check high "$OUT" "gh api -X DELETE repos/Cuvara/UnityDots"
check warn "$OUT" "gh api -X PUT repos/Cuvara/UIToolkit/branches/main/protection --input p.json"
check allow "$OUT" "gh repo delete someone/scratch --yes"

# ---- v0.4: local ref / remote / config mutations on protected branches
git -C "$SERVER" branch feat/x 2>/dev/null
check warn "$SERVER" "git branch -m develop old-develop"
check warn "$SERVER" "git branch -m renamed"                       # renames the current (protected) branch
check allow "$SERVER" "git branch -m feat/x feat/y"
check warn "$SERVER" "git branch -d develop"
check allow "$SERVER" "git branch -d feat/x"
check warn "$SERVER" "git fetch origin +refs/heads/develop:refs/heads/develop"
check warn "$SERVER" "git fetch origin develop:develop"
check high "$SERVER" "git fetch origin v9:refs/tags/v9"
check allow "$SERVER" "git fetch origin"
check allow "$SERVER" "git fetch origin +refs/heads/*:refs/remotes/origin/*"
check allow "$SERVER" "git fetch --prune"
check warn "$SERVER" "git remote set-url origin https://evil.example/x.git"
check warn "$SERVER" "git remote add fork https://example/x.git"
check warn "$SERVER" "git remote remove origin"
check allow "$SERVER" "git remote -v"
check allow "$SERVER" "git remote get-url origin"
check warn "$SERVER" "git config alias.t tag"
check warn "$SERVER" "git config --global alias.p push"
check warn "$SERVER" "git config remote.origin.url https://evil.example/x.git"
check warn "$SERVER" "git config core.hooksPath /tmp/h"
check warn "$SERVER" "git config url.https://evil/.insteadOf https://github.com/"
check allow "$SERVER" "git config user.email a@b"
check allow "$SERVER" "git config --get remote.origin.url"
check allow "$SERVER" "git config -l"
check warn "$SERVER" "git symbolic-ref HEAD refs/heads/main"
check allow "$SERVER" "git symbolic-ref --short HEAD"
check warn "$SERVER" "git submodule add https://x/y.git sub"
check warn "$SERVER" "git submodule set-url sub https://evil/x.git"
check warn "$SERVER" "git pull origin develop" "" PowerShell
check warn "$SERVER" "git remote set-url origin x" "" PowerShell
check high "$SERVER" "gh api graphql -f query='mutation{createRef(input:{name:\"refs/tags/v9\"}){ref{name}}}'" "" PowerShell

# Windows: a non-ASCII branch name (U+0410 is d0 90 in UTF-8; cp1252 cannot decode 0x90) once made the
# guard's git calls raise, and an exception means "no opinion" - the tag went through
git -C "$SERVER" checkout -q -b "feat/gateway/$(printf '\xd0\x90')"
check high "$SERVER" "git tag v1.2.3"
check warn "$SERVER" "git push --force origin HEAD"
git -C "$SERVER" checkout -q develop
# the payload cwd uses the other separator style than the workspace path the guard finds
if [ -n "$RPGF_WINDOWS" ]; then
  check high "$(cygpath -w "$SERVER")" "git tag v1.2.3"
  check warn "$(cygpath -w "$SERVER")" "git reset --hard HEAD~1"
  check high "$(fwd "$(cygpath -w "$SERVER")")" "git push origin --tags"
fi
# a developer shell exporting RPG_FACTORY_WORKSPACE for a different (real, complete) workspace must not
# open this one, and a `cd` from one workspace into the other is checked against the second
WS2="$TMP/ws2"; mkdir -p "$WS2/rpg-mmo-server/backend" "$WS2/IndieRPGMMOAdventure/ProjectSettings"
touch "$WS2/rpg-mmo-server/backend/TEAM.md" "$WS2/IndieRPGMMOAdventure/ProjectSettings/ProjectVersion.txt"
git -C "$WS2/rpg-mmo-server" init -q -b develop
check high "$SERVER" "git tag v1.2.3" "RPG_FACTORY_WORKSPACE=$OUT"
check high "$SERVER" "git tag v1.2.3" "RPG_FACTORY_WORKSPACE=$WS2"
check warn "$SERVER" "git reset --hard HEAD~1" "RPG_FACTORY_WORKSPACE=$WS2"
check high "$SERVER" "cd $WS2/rpg-mmo-server && git tag v1.2.3"
check allow "$OUT" "git reset --hard" "RPG_FACTORY_WORKSPACE=$WS2"   # a repo outside every workspace stays not ours
check high "$OUT" "git -C $WS2/rpg-mmo-server tag v1.2.3" "RPG_FACTORY_WORKSPACE=$WS2"   # the env root still covers git -C into it
# `git -C` decides by the directory git works in: from another workspace, and from outside every workspace
check high "$WS2/rpg-mmo-server" "git -C $SERVER tag v1.2.3" "RPG_FACTORY_WORKSPACE=$WS"
check high "$WS2/rpg-mmo-server" "git -C $SERVER tag v1.2.3"
check high "$OUT" "git -C $SERVER tag v1.2.3"
check warn "$OUT" "git -C $SERVER reset --hard HEAD~1"
check allow "$OUT" "git -C $OUT reset --hard"

# ---- 1.0.5: guard classification gaps
# (1) git-bash paths: on Windows `/c/ws` and `/mnt/c/ws` once resolved to C:\c\ws (no workspace: no advisory)
nt=$(python3 -B - "$GUARD" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("gg", sys.argv[1]); g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
cases = [("/c/Workspaces/UnityIndie/Netcode", True, "C:/Workspaces/UnityIndie/Netcode"), ("/mnt/c/ws/x", True, "C:/ws/x"),
         ("/d", True, "D:/"), ("/tmp/x", True, "/tmp/x"), ("C:\\ws\\x", True, "C:\\ws\\x"), ("backend", True, "backend"),
         ("/c/ws", False, "/c/ws"), ("/mnt/c/ws", False, "/mnt/c/ws")]
bad = [c for c in cases if g.native_path(c[0], nt=c[1]) != c[2]]
print("ok" if not bad else f"bad {bad}")
PY
)
[ "$nt" = ok ] && pass=$((pass + 1)) || { fail=$((fail + 1)); echo "FAIL native_path mapping: $nt"; }
check high "$OUT" "cd $SERVER && git tag v1.0.0"          # every platform: the native form
check high "$OUT" "git -C $SERVER/backend tag v1.0.0"
if [ -n "$RPGF_WINDOWS" ]; then
  d="${SERVER:0:1}"; u="/${d,,}${SERVER:2}"   # C:/Users/... -> /c/Users/... (cygpath -u would print /tmp/...)
  check high "$OUT" "cd $u && git tag v1.0.0"
  check high "$OUT" "git -C $u tag v1.0.0"
  check high "$OUT" "git -C /mnt$u tag v1.0.0"
  check warn "$OUT" "cd /mnt$u/backend && git reset --hard"
  check high "$CLIENT" "cd $u && git push origin --tags"
  check warn "$OUT" "kubectl apply -f $u/backend/x.yaml"      # human gate path scan maps the path too
fi
check warn "$OUT" "kubectl apply -f $SERVER/backend/x.yaml"   # native form (C:/... on Windows) on every platform
# (2) shell reserved words in front of git
check high "$SERVER" '{ git tag v1; }'
check high "$SERVER" '! git tag v1'
check high "$SERVER" 'if true; then git tag v1; fi'
check high "$SERVER" 'if false; then :; else git tag v1; fi'
check high "$SERVER" 'if false; then :; elif true; then git tag v1; fi'
check high "$SERVER" 'if git tag v1; then :; fi'
check high "$SERVER" 'for i in 1; do git tag v$i; done'
check high "$SERVER" 'while false; do git push --tags; done'
check high "$SERVER" 'until false; do git tag v1; done'
check high "$SERVER" 'f() { git tag v1; }; f'
check high "$SERVER" 'function f { git tag v1; }; f'
check warn "$SERVER" '{ git reset --hard; } 2>/dev/null'
check allow "$SERVER" 'if true; then git status; fi'
check allow "$SERVER" '{ git log -1; }'
check allow "$SERVER" 'for f in a b; do echo $f; done'
check high "$SERVER" 'if ($true) { git tag v1 }' "" PowerShell
check high "$SERVER" 'foreach ($t in $tags) { git tag $t }' "" PowerShell
check warn "$SERVER" 'try { git reset --hard } finally { Write-Host x }' "" PowerShell
check allow "$SERVER" 'if ($x) { git status } else { git log -1 }' "" PowerShell
check allow "$SERVER" 'if ($x) { git tag -l }' "" PowerShell
# (3) a heredoc read by a shell is commands; by an interpreter, opaque code; otherwise data
check high "$SERVER" "bash <<'EOF2'
git tag v1
EOF2"
check high "$SERVER" "bash -s <<EOF
git tag v1
EOF"
check high "$SERVER" "cat <<EOF | sh
git push --tags
EOF"
check high "$SERVER" "sh - <<'X'
cd backend && git tag v2
X"
check warn "$SERVER" "python3 - <<'PY'
import os; os.system('git reset --hard')
PY"
check warn "$SERVER" "node <<'JS'
require('child_process').execSync('gh release create v1')
JS"
check allow "$SERVER" "python3 - <<'PY'
print(1)
PY"
check allow "$SERVER" "cat > notes.txt <<'EOF'
git tag v1
EOF"
check allow "$SERVER" "cat <<'EOF' > notes.txt
git push --tags
EOF"
check allow "$SERVER" "bash -c 'cat' <<'EOF'
git tag v1
EOF"
check allow "$SERVER" "bash <<'O'
cat > f <<'I'
git tag v1
I
git status
O"
check high "$SERVER" "bash <<'O'
cat > f <<'I'
x
I
git tag v1
O"
check allow "$FEATURE" "git commit -F - <<'EOF'
chore: git tag v1 and git push --tags are release actions
EOF"
# (4) gh repository / host selectors never hide the group and verb (also for the human gates)
check high "$SERVER" "gh --repo Cuvara/x release create v1"
check high "$SERVER" "gh -R Cuvara/x release create v1"
check high "$SERVER" "gh --repo=Cuvara/x release create v1"
check high "$SERVER" "gh -RCuvara/x release create v1"
check high "$SERVER" "gh --hostname github.com release create v1"
check high "$SERVER" "gh release --repo Cuvara/x create v1"
check warn "$SERVER" "gh -R Cuvara/x pr merge 1"
check allow "$SERVER" "gh -R Cuvara/x pr view 1"
check allow "$SERVER" "gh --repo Cuvara/x release list"
reason_has() { # cwd command needle
  local r; r=$(jq -cn --arg c "$2" --arg d "$1" '{tool_name:"Bash",tool_input:{command:$c},cwd:$d,session_id:"guardtest"}' \
    | CLAUDE_PLUGIN_ROOT="$ROOT" python3 "$GUARD" | jq -r '.hookSpecificOutput.additionalContext // ""')
  case "$r" in *"$3"*) pass=$((pass + 1));; *) fail=$((fail + 1)); echo "FAIL reason for '$2' lacks '$3': $r";; esac
}
reason_has "$SERVER" "gh -R Cuvara/x pr merge 1" "human gate 'publish'"
reason_has "$SERVER" "gh --repo Cuvara/x pr create --fill" "human gate 'publish'"
# (5) interpreter one-liners that invoke gh
check warn "$SERVER" 'python3 -c "import os; os.system(\"gh release create v1\")"'
check warn "$SERVER" 'node -e "require(\"child_process\").execSync(\"gh release create v1\")"'
check allow "$SERVER" 'python3 -c "print(\"github\")"'
# (6) payloads that are not objects, and non-ASCII paths decoded as UTF-8
for p in '[]' 'null' '"s"' '42' '{"tool_name":"Bash","tool_input":"x"}' '{"tool_name":"Bash","tool_input":{"command":42}}'; do
  out=$(printf '%s' "$p" | CLAUDE_PLUGIN_ROOT="$ROOT" python3 "$GUARD" 2>&1; echo "exit=$?")
  [ "$out" = "exit=0" ] && pass=$((pass + 1)) || { fail=$((fail + 1)); echo "FAIL payload $p: $out"; }
done
NA="$SERVER/backend/d$(printf '\xc3\x84\xd0\x90')"; mkdir -p "$NA"
check high "$NA" "git tag v1.2.3"
check warn "$OUT" "git -C $NA reset --hard"
# (7) tag listings with --merged / --no-merged / --no-contains / separate --sort and --format values
check allow "$SERVER" "git tag --merged"
check allow "$SERVER" "git tag --no-merged HEAD"
check allow "$SERVER" "git tag --merged=HEAD 'v*'"
check allow "$SERVER" "git tag --no-contains HEAD"
check allow "$SERVER" "git tag --sort -version:refname"
check allow "$SERVER" "git tag --sort creatordate --format '%(refname:short)'"
check high "$SERVER" "git tag --sort -version:refname v9.9.9"
check high "$SERVER" "git tag --sort version:refname v9"
check high "$SERVER" "git tag --format x v9"
# (8) many read-only git calls stay quiet; an oversized command is one warn
cmd30=$(for i in $(seq 30); do printf 'git -C backend status; '; done)
check allow "$SERVER" "$cmd30"
check warn "$SERVER" "$(for i in $(seq 30); do printf 'git -C backend status; '; done)git commit -m x"
{ printf 'echo '; printf '%0200000d' 0; } > "$TMP/big.txt"   # too large for a jq --arg: read from a file
out=$(jq -cn --rawfile c "$TMP/big.txt" --arg d "$SERVER" '{tool_name:"Bash",tool_input:{command:$c},cwd:$d,session_id:"guardtest"}' \
  | CLAUDE_PLUGIN_ROOT="$ROOT" python3 "$GUARD"; echo "rc=$?")
case "$out" in *'rpg-factory advisory (warn)'*'command too large to check'*rc=0) pass=$((pass + 1));;
  *) fail=$((fail + 1)); echo "FAIL oversized command: ${out:0:300}";; esac
# (10) a mode switch counts wherever it runs, and only when the script really runs
mx() { # expected cwd command
  local out got; out=$(jq -cn --arg c "$3" --arg d "$2" '{tool_name:"Bash",tool_input:{command:$c},cwd:$d,session_id:"modes-x"}' | CLAUDE_PLUGIN_ROOT="$ROOT" python3 "$GUARD")
  got=$(jq -r 'if .hookSpecificOutput.permissionDecision then "DECISION" else ((.hookSpecificOutput.additionalContext // "") | (capture("^rpg-factory advisory [(](?<l>[a-z]+)[)]") // {l: "allow"}) | .l) end' <<<"${out:-{\}}")
  if [ "$got" = "$1" ]; then pass=$((pass + 1)); else fail=$((fail + 1)); printf 'FAIL mode-x expected=%s got=%s cwd=%s cmd=%s\n  out=%s\n' "$1" "$got" "${2#$TMP/}" "$3" "$out"; fi
}
mx allow "$SERVER" "bash $CTX --mode plan"
mx high  "$SERVER" "touch a.txt"
mx allow "$OUT"    "bash $CTX --mode implement --repo server"     # switched from outside the workspace
mx allow "$SERVER" "touch b.txt"
mx allow "$OUT"    "bash $CTX --mode review"
mx high  "$SERVER" "touch c.txt"
mx allow "$OUT"    "$CTX --mode=implement"
mx allow "$SERVER" "touch d.txt"
mx allow "$SERVER" "grep -n factory-context.sh --mode review README.md"   # mentions the script, does not run it
mx allow "$SERVER" "echo factory-context.sh --mode plan"
mx allow "$SERVER" "touch e.txt"
mx allow "$SERVER" "bash -x $CTX --mode analyze"
mx high  "$SERVER" "touch f.txt"
mx allow "$SERVER" "bash $CTX --mode implement"


total=$((pass + fail))
echo "git-guard tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
