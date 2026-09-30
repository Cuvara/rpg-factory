#!/usr/bin/env bash
# run-checks.py state model, deterministically: a temp plugin copy whose registry gives the
# server.gateway module synthetic checks, run against a throwaway workspace.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d -p /tmp)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
P="$TMP/plugin"; mkdir -p "$P"; cp -r "$ROOT/scripts" "$ROOT/.claude-plugin" "$P/"
WS="$TMP/ws"; S="$WS/rpg-mmo-server"; C="$WS/IndieRPGMMOAdventure"
mkdir -p "$S/backend/gateway" "$C/ProjectSettings"; touch "$S/backend/TEAM.md" "$S/backend/gateway/x.go" "$C/ProjectSettings/ProjectVersion.txt"
for r in "$S" "$C"; do git -C "$r" init -q -b develop; git -C "$r" -c user.email=t@t -c user.name=t add -A; git -C "$r" -c user.email=t@t -c user.name=t commit -qm init; done
jq --arg ws "$WS" '
  .workspace.root_default = $ws
  | .tools.nosuchtool = {candidates: ["no-such-tool-xyz"], version_args: "--version"}
  | (.modules[] | select(.id == "server.gateway")) |= (.tools = [] | .checks = {
      fast: [
        {id: "t-pass",     cwd: ".", run: "printf \"=== RUN TestA\\n--- PASS: TestA (0.00s)\\n--- PASS: TestB\\nok  x 0.1s\\n\"", parser: "go-test", evidence: "e"},
        {id: "t-zero",     cwd: ".", run: "echo \"ok  x [no test files]\"", parser: "go-test", evidence: "e"},
        {id: "t-fail",     cwd: ".", run: "echo \"--- FAIL: TestC\"; exit 1", parser: "go-test", evidence: "e"},
        {id: "t-skipall",  cwd: ".", run: "echo \"Passed!  - Failed:     0, Passed:     0, Skipped:     3, Total:     3\"", parser: "dotnet-test", evidence: "e"},
        {id: "t-dotnet",   cwd: ".", run: "echo \"Passed!  - Failed:     0, Passed:    12, Skipped:     1, Total:    13\"", parser: "dotnet-test", evidence: "e"},
        {id: "t-needs",    cwd: ".", run: "echo should-not-run", evidence: "e", needs: ["t-fail"]},
        {id: "t-regex",    cwd: ".", run: "echo nothing-useful", parser: "regex:^OK: \\d+", evidence: "e"},
        {id: "t-pollute",  cwd: ".", run: "touch leftover.txt", evidence: "e"}
      ],
      extended: [{id: "t-ext", cwd: ".", run: "echo --- PASS: TestX", parser: "go-test", trigger: "always", evidence: "e"}],
      external: [{id: "t-ci", run: "CI job", evidence: "e"}]})
  | (.modules[] | select(.id == "server.nakama")) |= (.tools = ["nosuchtool"] | .checks.fast = [{id: "t-tool", cwd: ".", run: "no-such-tool-xyz", evidence: "e"}])
' "$ROOT/registry.json" > "$P/registry.json"
export RPG_FACTORY_WORKSPACE="$WS" CLAUDE_PLUGIN_ROOT="$P" TMPDIR="$TMP"
pass=0; fail=0
out=$(python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/gateway/x.go --json); rc=$?
st() { jq -r --arg c "$1" '.results[] | select(.check == $c) | .state' <<<"$out" | head -1; }
expect() { local c="$1" e="$2" g; g=$(st "$c"); if [ "$g" = "$e" ]; then pass=$((pass + 1)); echo "PASS  $c -> $e"; else fail=$((fail + 1)); echo "FAIL  $c expected $e got ${g:-none}"; jq -c --arg c "$c" '.results[] | select(.check == $c) | {state,reason,counts}' <<<"$out"; fi; }
expect t-pass PASS
expect t-zero FAIL
expect t-fail FAIL
expect t-skipall FAIL
expect t-dotnet PASS
expect t-needs BLOCKED
expect t-regex FAIL
expect t-pollute FAIL
expect t-ext HUMAN_REQUIRED
expect t-ci HUMAN_REQUIRED
expect go-vet-integration BLOCKED   # dependent module dir absent: BLOCKED, never a crash
c=$(jq -r '.results[] | select(.check == "t-pass") | "\(.counts.passed)/\(.counts.discovered)"' <<<"$out")
[ "$c" = "2/2" ] && { pass=$((pass + 1)); echo "PASS  go-test counts 2/2"; } || { fail=$((fail + 1)); echo "FAIL  go-test counts $c"; }
c=$(jq -r '.results[] | select(.check == "t-dotnet") | "\(.counts.passed)/\(.counts.skipped)/\(.counts.total)"' <<<"$out")
[ "$c" = "12/1/13" ] && { pass=$((pass + 1)); echo "PASS  dotnet counts 12/1/13"; } || { fail=$((fail + 1)); echo "FAIL  dotnet counts $c"; }
jq -e '.results[] | select(.check == "t-pollute") | .reason | test("leftover.txt")' <<<"$out" >/dev/null && { pass=$((pass + 1)); echo "PASS  pollution names the leftover file"; } || { fail=$((fail + 1)); echo "FAIL  pollution reason"; }
[ $rc -eq 1 ] && { pass=$((pass + 1)); echo "PASS  exit 1 when a fast check fails"; } || { fail=$((fail + 1)); echo "FAIL  exit $rc"; }
ls "$TMP"/rpg-factory/results/server-*.json >/dev/null 2>&1 && { pass=$((pass + 1)); echo "PASS  evidence JSON written outside the repo"; } || { fail=$((fail + 1)); echo "FAIL  no evidence file"; }
rm -f "$S/leftover.txt"
out=$(python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/gateway/x.go --only t-ext --approve t-ext --json)
expect t-ext PASS
out=$(python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/nakama/main.go --json); rc=$?
expect t-tool NOT_AVAILABLE
out=$(python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/gateway/x.go --only t-pass --json); rc=$?
[ $rc -eq 0 ] && { pass=$((pass + 1)); echo "PASS  exit 0 when every executed check passes"; } || { fail=$((fail + 1)); echo "FAIL  exit $rc with --only t-pass"; }
total=$((pass + fail)); echo "run-checks tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
