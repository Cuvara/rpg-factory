#!/usr/bin/env bash
# Unit tests for scripts/git-guard.py. Builds a throwaway fake workspace in a temp
# dir (never touches the real repos), feeds hook payloads, and checks the decision.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GUARD="$ROOT/scripts/git-guard.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

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
check() { # expected cwd command [env]
  local expected="$1" cwd="$2" cmd="$3" envset="${4:-}" payload out got
  payload=$(jq -cn --arg c "$cmd" --arg d "$cwd" '{hook_event_name:"PreToolUse", tool_name:"Bash", tool_input:{command:$c}, cwd:$d}')
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
# non-Bash payloads are ignored
out=$(jq -cn '{tool_name:"Read", tool_input:{file_path:"x"}, cwd:"/"}' | CLAUDE_PLUGIN_ROOT="$ROOT" python3 "$GUARD")
if [ -z "$out" ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL non-Bash payload produced output: $out"; fi
# malformed stdin never breaks the session
out=$(echo 'not json' | CLAUDE_PLUGIN_ROOT="$ROOT" python3 "$GUARD"; echo "exit=$?")
if [ "$out" = "exit=0" ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL malformed stdin: $out"; fi

total=$((pass + fail))
echo "git-guard tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
