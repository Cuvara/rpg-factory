#!/usr/bin/env bash
# Unit tests for scripts/git-guard.py. Builds a throwaway fake workspace in a temp
# dir (never touches the real repos), feeds hook payloads, and checks the decision.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GUARD="$ROOT/scripts/git-guard.py"
TMP="$(mktemp -d -p /tmp)" || exit 1; [ -d "$TMP" ] || exit 1
trap 'rm -rf "$TMP"' EXIT
export TMPDIR="$TMP" RPG_FACTORY_STATE_DIR="$TMP/state"   # tripwire latch/mode state stays inside this test

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
  got=$(jq -r '.hookSpecificOutput.permissionDecision // "allow"' <<<"${out:-{\}}" 2>/dev/null || echo "invalid-json")
  if [ "$got" = "$expected" ]; then pass=$((pass + 1))
  else fail=$((fail + 1)); printf 'FAIL expected=%s got=%s cwd=%s cmd=%q\n  out=%s\n' "$expected" "$got" "${cwd#$TMP/}" "$cmd" "$out"; fi
}

# read-only commands pass through
check allow "$SERVER" "git status"
check allow "$SERVER" "git diff --stat"
check allow "$SERVER" "git log --oneline -5"
check allow "$SERVER" "git stash list"
check allow "$SERVER" "git tag -l"
check allow "$SERVER" "git add backend/gateway/main.go"
check allow "$SERVER" "git restore --staged backend/gateway/main.go"
check allow "$SERVER" 'echo "git reset --hard"'
# destructive
check ask "$SERVER" "git reset --hard HEAD~1"
check ask "$SERVER" "git clean -fd"
check ask "$SERVER" "git checkout -- ."
check ask "$SERVER" "git restore backend/gateway/main.go"
check ask "$SERVER" "git stash"
check ask "$SERVER" "git stash drop"
check ask "$SERVER" "git branch -D feat/old"
check ask "$SERVER" "git push --force origin feat/x"
check ask "$SERVER" "git push origin feat/x"
check ask "$SERVER" "git rebase develop"
# staging everything
check ask "$SERVER" "git add -A"
check ask "$SERVER" "git add ."
check ask "$SERVER" "git commit -am wip"
# protected branches
check ask "$SERVER" "git commit -m 'fix(gateway): x'"
check ask "$WS" "git -C rpg-mmo-server commit -m x"
check ask "$WS" "cd IndieRPGMMOAdventure && git commit -m x"
check allow "$SERVER" "git checkout -b feat/gateway/y && git commit -m 'feat(gateway): y'"
check allow "$FEATURE" "git commit -m 'feat(gateway): x'"
check ask "$FEATURE" "git commit --amend --no-edit"
# tags + submodules
check deny "$SERVER" "git tag sgl-v0.7.0"
check deny "$SERVER" "git tag -a v1.2.3 -m release"
check deny "$SERVER" "git tag -d v0.1.0"
check deny "$SERVER" "git push origin --tags"
check deny "$SERVER" "git push origin v1.2.3"
check deny "$SERVER" "git push origin refs/tags/core-baseline-v2"
check deny "$SERVER" "git status && git tag v9.9.9"
check ask "$CLIENT" "git submodule update --init --recursive"
# registry human gates (ask) inside the workspace
check ask "$SERVER" "kubectl apply -f backend/deploy/k8s/app/50-fleet-map.yaml"
check ask "$SERVER" "helm upgrade x y"
check ask "$SERVER" "ssh deploy@vps.example"
check ask "$SERVER" "gh workflow run cd.yml --ref develop"
check ask "$SERVER" "gh pr create --fill"
check ask "$WS" "./toggle-packages.sh dev"
check ask "$SERVER" "cat backend/deploy/kubeconfig.local"
check ask "$SERVER" "make flow-up"
check ask "$CLIENT" "bash Tools/run-clients.sh 4"
check allow "$SERVER" "make flow-check"
check allow "$SERVER" "gh pr view 12"
check allow "$SERVER" "echo kubectl is gated"
check allow "$OUT" "kubectl get pods"
check ask "$SERVER" "sudo kubectl get pods -n rpg"
check ask "$SERVER" "KUBECONFIG=x kubectl apply -f a.yaml"
check ask "$SERVER" "bash backend/deploy/k8s/verify/verify.sh --target k8s-dev"
check ask "$SERVER" "bash backend/deploy/db/backup.sh"
check ask "$SERVER" "JWT_SECRET=x ./scripts/bench.sh 50 60s cluster out"
check ask "$CLIENT" "Unity.exe -batchmode -executeMethod PlayerBuilder.Build"
check ask "$SERVER" "psql -c 'DELETE FROM schema_migrations'"
check allow "$SERVER" "cat backend/deploy/.env.example"
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
check ask "$SERVER" "git status && git clean -fdx"
# outside the workspace and opt-out
check allow "$OUT" "git reset --hard"
check allow "$SERVER" "git reset --hard" "RPG_FACTORY_GUARD=off"
# a broken registry regex must not disable git protection (fail-open regression)
BROKEN="$TMP/broken-plugin"; mkdir -p "$BROKEN/scripts"
jq '.human_gates[1].match = "(("' "$ROOT/registry.json" > "$BROKEN/registry.json"
payload=$(jq -cn --arg d "$SERVER" '{tool_name:"Bash", tool_input:{command:"git reset --hard"}, cwd:$d}')
got=$(CLAUDE_PLUGIN_ROOT="$BROKEN" python3 "$GUARD" <<<"$payload" | jq -r '.hookSpecificOutput.permissionDecision // "allow"')
if [ "$got" = "ask" ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL broken regex disabled git protection (got $got)"; fi
# ---- v2: wrappers and nested shells (were ALLOW in the v0.2 audit)
check ask "$SERVER" 'bash -c "git reset --hard"'
check ask "$SERVER" "sh -c 'git push --force'"
check ask "$SERVER" 'bash -lc "cd backend && git clean -fdx"'
check allow "$SERVER" 'bash -lc "cd /tmp && git clean -fdx"'
check ask "$SERVER" 'eval "git reset --hard"'
check ask "$SERVER" "env git reset --hard"
check ask "$SERVER" "env -u X GIT_TRACE=1 git reset --hard"
check ask "$SERVER" "command git reset --hard"
check ask "$SERVER" "sudo git reset --hard"
check ask "$SERVER" "sudo -u root git clean -f"
check ask "$SERVER" "timeout 5 git push origin feat/x"
check ask "$SERVER" "timeout -s KILL 30 git stash"
check ask "$SERVER" "nohup git push &"
check ask "$SERVER" "nice -n 10 git gc --prune=now"
check ask "$SERVER" "xargs git reset --hard < /dev/null"
check deny "$SERVER" "echo v9 | xargs git tag"              # xargs appends the tag name (found by installed-safety)
check deny "$SERVER" "echo v9 | xargs -n1 git tag"
check deny "$SERVER" "printf a | xargs -I{} git tag {}"
check ask "$SERVER" "echo develop | xargs git push origin"
check allow "$SERVER" "xargs git tag -l < /dev/null"
check allow "$SERVER" "echo f | xargs git log --oneline"
check ask "$SERVER" 'find . -name x -exec git checkout -- {} \;'
check ask "$SERVER" "cmd.exe /c git reset --hard"
check ask "$SERVER" 'powershell.exe -c "git reset --hard"'
check ask "$SERVER" "powershell.exe -EncodedCommand ZwBpAHQA"
check ask "$SERVER" 'G=git; $G reset --hard'
check ask "$SERVER" '$(which git) reset --hard'
check ask "$SERVER" '`which git` push'
check ask "$SERVER" 'git -c alias.nuke="reset --hard" nuke'
check ask "$SERVER" 'python3 -c "import os; os.system(\"git reset --hard\")"'
check ask "$SERVER" 'node -e "require(\"child_process\").execSync(\"git push\")"'
check deny "$SERVER" 'bash -c "git tag v1.0.0"'
check deny "$SERVER" 'env GIT_DIR=.git git push origin --tags'
check deny "$SERVER" "sudo git tag sgl-v9.9.9"
# ---- v2: commit-creating / ref-destroying operations
check ask "$SERVER" "git merge feat/x"
check ask "$SERVER" "git merge --no-ff feat/x"
check ask "$SERVER" "git cherry-pick abc123"
check ask "$SERVER" "git revert HEAD"
check ask "$SERVER" "git am patch.mbox"
check ask "$SERVER" "git pull --rebase"
check ask "$SERVER" "git reset HEAD~3"
check ask "$SERVER" "git checkout -B develop origin/develop"
check ask "$SERVER" "git switch -C develop origin/develop"
check ask "$SERVER" "git branch -f develop HEAD~2"
check ask "$SERVER" "git update-ref -d refs/heads/x"
check deny "$SERVER" "git update-ref refs/tags/v9 HEAD"
check ask "$SERVER" "git gc --prune=now"
check ask "$SERVER" "git reflog expire --expire=now --all"
check ask "$SERVER" "git prune"
check deny "$SERVER" "git push origin HEAD:refs/tags/v2.0.0"
check deny "$SERVER" "git push --mirror origin"
check allow "$FEATURE" "git merge develop"
check allow "$FEATURE" "git cherry-pick abc123"
check ask "$SERVER" "git pull"                                # may merge into protected develop (v0.4)
check allow "$SERVER" "git pull --ff-only"
check allow "$FEATURE" "git pull"
check allow "$SERVER" "git merge --abort"
check allow "$SERVER" "git fetch --prune"
# ---- v2: gh API / releases
check deny "$SERVER" "gh api -X POST repos/Cuvara/x/git/refs -f ref=refs/tags/v9 -f sha=abc"
check deny "$SERVER" "gh api repos/Cuvara/x/git/tags -f tag=v9"
check deny "$SERVER" "gh release create v1.0.0"
check deny "$SERVER" "gh api -X POST repos/Cuvara/x/releases -f tag_name=v1"
check ask "$SERVER" "gh api -X POST repos/Cuvara/x/git/refs -f ref=refs/heads/x -f sha=abc"
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
check deny "$SERVER" "git tag v1.2.3" "" PowerShell
check ask "$SERVER" "git reset --hard; Get-ChildItem" "" PowerShell
check ask "$SERVER" "& 'git.exe' push --force" "" PowerShell
check ask "$SERVER" "Set-Location ..\\IndieRPGMMOAdventure; git commit -m x" "" PowerShell
check ask "$SERVER" "git merge feat/x" "" PowerShell
check allow "$SERVER" "git status; git log -1" "" PowerShell
check ask "$SERVER" "kubectl apply -f x.yaml" "" PowerShell
# ---- v2: repo git aliases are expanded
git -C "$SERVER" config alias.wipe "reset --hard"
git -C "$SERVER" config alias.shwipe '!git reset --hard'
check ask "$SERVER" "git wipe"
check ask "$SERVER" "git shwipe"
# ---- v2: worktree of a protected repo keeps protected-branch rules via the main checkout
git -C "$SERVER" worktree add -q "$TMP/ws/srv-wt" -b feat/server/wt 2>/dev/null
check allow "$TMP/ws/srv-wt" "git commit -m 'feat(server): x'"
git -C "$TMP/ws/srv-wt" switch -q -c release-9 2>/dev/null
check ask "$TMP/ws/srv-wt" "git commit -m x"
# ---- tripwire latch: guard denies mutating commands, allows read-only
mkdir -p "$TMP/rpg-factory/guardtest" && echo "test violation" > "$TMP/rpg-factory/guardtest/LATCH"
check deny "$FEATURE" "git commit -m x"
check deny "$SERVER" "touch newfile"
check allow "$SERVER" "git status"
check allow "$SERVER" "ls -la"
rm -f "$TMP/rpg-factory/guardtest/LATCH"
check allow "$FEATURE" "git commit -m 'feat(gateway): after ack'"
# non-Bash payloads are ignored
out=$(jq -cn '{tool_name:"Read", tool_input:{file_path:"x"}, cwd:"/"}' | CLAUDE_PLUGIN_ROOT="$ROOT" python3 "$GUARD")
if [ -z "$out" ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL non-Bash payload produced output: $out"; fi
# malformed stdin never breaks the session
out=$(echo 'not json' | CLAUDE_PLUGIN_ROOT="$ROOT" python3 "$GUARD"; echo "exit=$?")
if [ "$out" = "exit=0" ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL malformed stdin: $out"; fi

# ---- v0.4: execution modes - declared with factory-context.sh --mode, enforced per session
mcheck() { # expected command [tool]
  local out got; out=$(jq -cn --arg c "$2" --arg d "$SERVER" --arg t "${3:-Bash}" '{tool_name:$t,tool_input:{command:$c},cwd:$d,session_id:"modes"}' | CLAUDE_PLUGIN_ROOT="$ROOT" python3 "$GUARD")
  got=$(jq -r '.hookSpecificOutput.permissionDecision // "allow"' <<<"${out:-{\}}")
  if [ "$got" = "$1" ]; then pass=$((pass + 1)); else fail=$((fail + 1)); printf 'FAIL mode expected=%s got=%s cmd=%s\n  out=%s\n' "$1" "$got" "$2" "$out"; fi
}
CTX="$ROOT/scripts/factory-context.sh"; RC="$ROOT/scripts/run-checks.py"
mcheck allow "touch before-any-mode.txt"                                  # no mode declared: normal rules
mcheck allow "bash $CTX --mode plan --repo server --paths backend/x.go"    # declaring is read-only
mcheck deny  "touch plan.txt"
mcheck deny  "git switch -c feat/x/plan"
mcheck deny  "python3 $RC --repo server"
mcheck allow "git status 2>/dev/null"
mcheck allow "git log --oneline -3 2>&1 | head -3"
mcheck allow "python3 $ROOT/scripts/factory-status.py"
mcheck deny  "touch x" PowerShell
mcheck allow "bash $CTX --mode=validate --repo server"
mcheck allow "python3 $RC --repo server --paths backend/x.go"
mcheck allow "python3 $RC --repo server --status | head -20"
mcheck deny  "touch validate.txt"
mcheck allow "bash $CTX --mode analyze"
mcheck deny  "git commit -m x"
mcheck allow "bash $CTX --mode implement --repo server"
mcheck allow "touch implement.txt"
mcheck allow "git switch -c feat/x/impl"
mcheck allow "bash $CTX --mode nonsense"                                   # unknown modes are not recorded
mcheck allow "touch still-implement.txt"
# the mode can also be declared through the Skill tool's arguments (hook on Skill)
skill() { jq -cn --arg a "$1" --arg sk "${2:-rpg-factory:factory-core}" --arg d "$SERVER" '{tool_name:"Skill",tool_input:{skill:$sk,args:$a},cwd:$d,session_id:"modes"}' | CLAUDE_PLUGIN_ROOT="$ROOT" python3 "$ROOT/scripts/tripwire.py" --skill; }
skill "Plan-only task: add an AOI radius knob. No edits."
mcheck deny  "touch via-skill-plan.txt"
skill "Validate only, change nothing"
mcheck deny  "touch via-skill-validate.txt"
mcheck allow "python3 $RC --repo server"
skill "Add a knob to the server"                                         # no explicit mode: unchanged (validate)
mcheck deny  "touch still-validate.txt"
skill "mode: implement - the user approved the plan"
mcheck allow "touch via-skill-implement.txt"
skill "plan only" "other-plugin:skill"                                    # other plugins' skills never set a Factory mode
mcheck allow "touch other-plugin.txt"

# ---- v0.4: GitHub remote mutations (invisible to the tripwire - the guard is the only defence)
check deny "$SERVER" "gh api graphql -f query='mutation{createRef(input:{repositoryId:\"R\",name:\"refs/tags/v9\",oid:\"abc\"}){ref{name}}}'"
check deny "$SERVER" "gh api graphql -f query='mutation(\$n:String!){createRef(input:{name:\$n}){ref{name}}}' -f n=refs/tags/v9"
check deny "$SERVER" "gh api graphql -f query='mutation{createRelease(input:{tagName:\"v9\"}){release{id}}}'"
check ask "$SERVER" "gh api graphql -f query='mutation{updateBranchProtectionRule(input:{branchProtectionRuleId:\"x\"}){clientMutationId}}'"
check ask "$SERVER" "gh api graphql -F query=@mutation.graphql"
check ask "$SERVER" "gh api graphql --input body.json"
check allow "$SERVER" "gh api graphql -f query='query{viewer{login}}'"
check allow "$SERVER" "gh api repos/Cuvara/rpg-mmo-server/branches/develop/protection"
check ask "$SERVER" "gh api -X PUT repos/Cuvara/rpg-mmo-server/branches/develop/protection --input p.json"
check ask "$SERVER" "gh api -X DELETE repos/Cuvara/rpg-mmo-server/branches/develop/protection"
check ask "$SERVER" "gh api --method POST repos/Cuvara/rpg-mmo-server/rulesets -f name=x"
check deny "$SERVER" "gh api -X DELETE repos/Cuvara/rpg-mmo-server"
check deny "$SERVER" "gh api repos/Cuvara/rpg-mmo-server/git/tags -f tag=v9 -f object=abc"
check deny "$SERVER" "gh api -XPOST repos/Cuvara/rpg-mmo-server/releases -f tag_name=v9"
check ask "$SERVER" "gh api -X PATCH repos/Cuvara/rpg-mmo-server -f default_branch=main"
check ask "$SERVER" "gh api repos/Cuvara/rpg-mmo-server/issues -f title=x"
check allow "$SERVER" "gh api repos/Cuvara/rpg-mmo-server/pulls --jq '.[].number'"
check deny "$SERVER" "gh repo delete Cuvara/rpg-mmo-server --yes"
check deny "$SERVER" "gh repo archive Cuvara/rpg-mmo-server"
check ask "$SERVER" "gh repo edit --default-branch main"
check ask "$SERVER" "gh repo rename x"
check ask "$SERVER" "gh repo sync"
check ask "$SERVER" "gh secret set TOKEN"
check ask "$SERVER" "gh variable delete X"
check ask "$SERVER" "gh workflow disable ci.yml"
check ask "$SERVER" "gh run cancel 12"
check ask "$SERVER" "gh pr close 12"
check ask "$SERVER" "gh pr comment 12 -b hi"
check ask "$SERVER" "gh label create x"
check deny "$SERVER" "gh release edit v1 --draft=false"
check allow "$SERVER" "gh pr view 12"
check allow "$SERVER" "gh pr checks 12"
check allow "$SERVER" "gh run view 1 --log"
check allow "$SERVER" "gh repo view"
check allow "$SERVER" "gh release list"
check allow "$SERVER" "gh auth status"
check allow "$SERVER" "gh search prs --repo Cuvara/Netcode x"
check deny "$SERVER" "bash -c 'gh repo delete Cuvara/Netcode --yes'"
# outside the workspace, a command naming a registry repo is still checked; unrelated repos are not
check deny "$OUT" "gh repo delete Cuvara/Netcode --yes"
check deny "$OUT" "gh api -X DELETE repos/Cuvara/UnityDots"
check ask "$OUT" "gh api -X PUT repos/Cuvara/UIToolkit/branches/main/protection --input p.json"
check allow "$OUT" "gh repo delete someone/scratch --yes"

# ---- v0.4: local ref / remote / config mutations on protected branches
git -C "$SERVER" branch feat/x 2>/dev/null
check ask "$SERVER" "git branch -m develop old-develop"
check ask "$SERVER" "git branch -m renamed"                       # renames the current (protected) branch
check allow "$SERVER" "git branch -m feat/x feat/y"
check ask "$SERVER" "git branch -d develop"
check allow "$SERVER" "git branch -d feat/x"
check ask "$SERVER" "git fetch origin +refs/heads/develop:refs/heads/develop"
check ask "$SERVER" "git fetch origin develop:develop"
check deny "$SERVER" "git fetch origin v9:refs/tags/v9"
check allow "$SERVER" "git fetch origin"
check allow "$SERVER" "git fetch origin +refs/heads/*:refs/remotes/origin/*"
check allow "$SERVER" "git fetch --prune"
check ask "$SERVER" "git remote set-url origin https://evil.example/x.git"
check ask "$SERVER" "git remote add fork https://example/x.git"
check ask "$SERVER" "git remote remove origin"
check allow "$SERVER" "git remote -v"
check allow "$SERVER" "git remote get-url origin"
check ask "$SERVER" "git config alias.t tag"
check ask "$SERVER" "git config --global alias.p push"
check ask "$SERVER" "git config remote.origin.url https://evil.example/x.git"
check ask "$SERVER" "git config core.hooksPath /tmp/h"
check ask "$SERVER" "git config url.https://evil/.insteadOf https://github.com/"
check allow "$SERVER" "git config user.email a@b"
check allow "$SERVER" "git config --get remote.origin.url"
check allow "$SERVER" "git config -l"
check ask "$SERVER" "git symbolic-ref HEAD refs/heads/main"
check allow "$SERVER" "git symbolic-ref --short HEAD"
check ask "$SERVER" "git submodule add https://x/y.git sub"
check ask "$SERVER" "git submodule set-url sub https://evil/x.git"
check ask "$SERVER" "git pull origin develop" "" PowerShell
check ask "$SERVER" "git remote set-url origin x" "" PowerShell
check deny "$SERVER" "gh api graphql -f query='mutation{createRef(input:{name:\"refs/tags/v9\"}){ref{name}}}'" "" PowerShell

total=$((pass + fail))
echo "git-guard tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
