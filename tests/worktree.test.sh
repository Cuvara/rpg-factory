#!/usr/bin/env bash
# Worktree awareness: factory-context run inside a git worktree must report THAT worktree
# (branch, HEAD, changed files, routing), not the main checkout. Throwaway fixture only.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d -p /tmp)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
export RPG_FACTORY_WORKSPACE="$TMP/ws" CLAUDE_PLUGIN_ROOT="$ROOT"
WS="$TMP/ws"; S="$WS/rpg-mmo-server"; C="$WS/IndieRPGMMOAdventure"
mkdir -p "$S/backend/gateway" "$C/ProjectSettings"; touch "$S/backend/TEAM.md" "$C/ProjectSettings/ProjectVersion.txt"
gc() { git -C "$1" -c user.email=t@t -c user.name=t "${@:2}"; }
for r in "$S" "$C"; do git -C "$r" init -q -b develop; gc "$r" add -A; gc "$r" commit -qm init; done
gc "$S" worktree add -q "$WS/wt-a" -b feat/gateway/a
gc "$S" worktree add -q "$WS/wt-b" -b feat/server/b
mkdir -p "$WS/wt-a/backend/gateway"; echo "package x" > "$WS/wt-a/backend/gateway/x.go"                  # uncommitted in worktree A
mkdir -p "$WS/wt-b/backend/deploy/k8s"; echo "kind: X" > "$WS/wt-b/backend/deploy/k8s/y.yaml"
gc "$WS/wt-b" add -A; gc "$WS/wt-b" commit -qm "deploy change"          # committed on worktree B's branch
echo "main edit" > "$S/backend/TEAM.md"                                # main checkout has its own change
pass=0; fail=0
ctx() { (cd "$1" && bash "$ROOT/scripts/factory-context.sh" --json "${@:2}"); }
expect() { if jq -e "$2" <<<"$3" >/dev/null 2>&1; then pass=$((pass + 1)); echo "PASS  $1"; else fail=$((fail + 1)); echo "FAIL  $1"; jq -c '.repos[] | {repo,path,branch,worktree,files:[.files[].path],lead:.routing.lead}' <<<"$3" 2>/dev/null | head -3; fi; }

a=$(ctx "$WS/wt-a")
expect "worktree A: single repo auto-detected from cwd" '.repos | length == 1 and .[0].repo == "server"' "$a"
expect "worktree A: path is the worktree" ".repos[0].path == \"$WS/wt-a\" and .repos[0].worktree == true" "$a"
expect "worktree A: branch feat/gateway/a, not develop" '.repos[0].branch == "feat/gateway/a" and .repos[0].protected == false' "$a"
expect "worktree A: sees its own uncommitted file only" '[.repos[0].files[].path] | length == 1 and (.[0] | startswith("backend/gateway"))' "$a"
expect "worktree A: routes to server-services" '.repos[0].routing.lead == "server-services"' "$a"
b=$(ctx "$WS/wt-b")
expect "worktree B: committed branch diff vs develop" '[.repos[0].files[] | select(.source == "branch") | .path] == ["backend/deploy/k8s/y.yaml"]' "$b"
expect "worktree B: routes to server-ops" '.repos[0].routing.lead == "server-ops"' "$b"
m=$(ctx "$S")
expect "main checkout: develop, protected, its own change" '.repos[0].branch == "develop" and .repos[0].protected and ([.repos[0].files[].path] == ["backend/TEAM.md"]) and .repos[0].worktree == false' "$m"
w=$(ctx "$WS")
expect "workspace root: all registered repos present in the fixture" '[.repos[] | select(.error == null) | .repo] | index("server") != null and index("client") != null' "$w"
p=$(ctx "$WS/wt-a" --paths backend/shared/proto/wire.proto)
expect "worktree + --paths: contract routing still works" '.repos[0].routing.lead == "wire-contract"' "$p"

total=$((pass + fail)); echo "worktree tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
