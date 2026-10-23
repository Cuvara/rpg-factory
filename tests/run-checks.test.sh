#!/usr/bin/env bash
# run-checks.py state model, deterministically: a temp plugin copy whose registry gives the
# server.gateway module synthetic checks, run against a throwaway workspace.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
P="$TMP/plugin"; mkdir -p "$P"; cp -r "$ROOT/scripts" "$ROOT/.claude-plugin" "$P/"
WS="$TMP/ws"; S="$WS/rpg-mmo-server"; C="$WS/IndieRPGMMOAdventure"
mkdir -p "$S/backend/gateway" "$S/backend/shared" "$S/backend/deploy" "$C/ProjectSettings"; touch "$S/backend/TEAM.md" "$S/backend/gateway/x.go" "$S/backend/shared/s.go" "$S/backend/deploy/d.yaml" "$C/ProjectSettings/ProjectVersion.txt"
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
        {id: "t-root",     cwd: ".", run: "test -f {plugin_root}/registry.json && echo \"OK: 1\"", parser: "regex:^OK: \\d+", evidence: "e"},
        {id: "t-needs",   cwd: ".", run: "echo should-not-run", evidence: "e", needs: ["t-fail"]},
        {id: "t-regex",    cwd: ".", run: "echo nothing-useful", parser: "regex:^OK: \\d+", evidence: "e"},
        {id: "t-elsewhere", cwd: "backend/deploy", run: "echo elsewhere", evidence: "e"},
        {id: "t-needs-ok", cwd: ".", run: "echo needs-ok", evidence: "e", needs: ["t-pass"]},
        {id: "t-needs-late", cwd: ".", run: "echo needs-late", evidence: "e", needs: ["t-late"]},
        {id: "t-late",     cwd: ".", run: "echo late-prereq", evidence: "e"},
        {id: "t-pollute",  cwd: ".", run: "touch leftover.txt", evidence: "e"},
        {id: "t-scoped",   cwd: "backend/gateway", run: "printf \"=== RUN TestS\\n--- PASS: TestS\\nok  s 0.1s\\n\"", parser: "go-test", evidence: "e"}
      ],
      extended: [{id: "t-ext", cwd: ".", run: "echo --- PASS: TestX", parser: "go-test", trigger: "always", evidence: "e"}],
      external: [{id: "t-ci", run: "CI job", evidence: "e"}]})
  | (.modules[] | select(.id == "server.gateway") | .checks.fast[0].run) as $tpass
  | (.modules[] | select(.id == "server.shared")) |= (.tools = [] | .checks = {
      fast: [{id: "t-dup", cwd: ".", run: $tpass, parser: "go-test", evidence: "other text, same command"}], extended: [], external: []})
  | (.modules[] | select(.id == "server.nakama")) |=(.tools = ["nosuchtool"] | .checks.fast = [{id: "t-tool", cwd: ".", run: "no-such-tool-xyz", evidence: "e"}])
' "$ROOT/registry.json" > "$P/registry.json"
export RPG_FACTORY_WORKSPACE="$WS" CLAUDE_PLUGIN_ROOT="$P" TMPDIR="$TMP" RPG_FACTORY_STATE_DIR="$TMP/state"
pass=0; fail=0
out=$(python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/gateway/x.go --json); rc=$?
st() { jq -r --arg c "$1" '.results[] | select(.check == $c) | .state' <<<"$out" | head -1; }
expect() { local c="$1" e="$2" g; g=$(st "$c"); if [ "$g" = "$e" ]; then pass=$((pass + 1)); echo "PASS  $c -> $e"; else fail=$((fail + 1)); echo "FAIL  $c expected $e got ${g:-none}"; jq -c --arg c "$c" '.results[] | select(.check == $c) | {state,reason,counts}' <<<"$out"; fi; }
expect t-pass PASS
expect t-zero FAIL
expect t-fail FAIL
expect t-skipall FAIL
expect t-dotnet PASS
expect t-root PASS
if [ -n "$RPGF_WINDOWS" ]; then   # the plugin root as Windows reports it (C:\...): {plugin_root} must survive bash -c
  full="$out"
  out=$(CLAUDE_PLUGIN_ROOT="$(cygpath -w "$P")" python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/gateway/x.go --only t-root --json)
  expect t-root PASS
  out="$full"
fi
expect t-needs BLOCKED
expect t-needs-ok PASS        # its prerequisite t-pass passed earlier in this run
expect t-needs-late BLOCKED   # its prerequisite t-late is listed after it: not PASS in this run yet
expect t-late PASS
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
ls "$TMP"/state/evidence/*/runs/server-*.json >/dev/null 2>&1 && { pass=$((pass + 1)); echo "PASS  run record written to the state root (outside the repo)"; } || { fail=$((fail + 1)); echo "FAIL  no run record"; }
lg=$(jq -r '.results[] | select(.check == "t-pass") | .log' <<<"$out")
grep -q -- "--- PASS: TestB" "$lg" 2>/dev/null && { pass=$((pass + 1)); echo "PASS  full log kept ($lg)"; } || { fail=$((fail + 1)); echo "FAIL  full log missing: $lg"; }
jq -e '.results[] | select(.check == "t-pass") | .identity.tree and .identity.head' <<<"$out" >/dev/null && { pass=$((pass + 1)); echo "PASS  result carries the tree identity"; } || { fail=$((fail + 1)); echo "FAIL  no identity"; }
rm -f "$S/leftover.txt"
out=$(python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/gateway/x.go --only t-ext --approve t-ext --json)
expect t-ext PASS
out=$(python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/nakama/main.go --json); rc=$?
expect t-tool NOT_AVAILABLE
out=$(python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/gateway/x.go --only t-pass --json); rc=$?
[ $rc -eq 0 ] && { pass=$((pass + 1)); echo "PASS  exit 0 when every executed check passes"; } || { fail=$((fail + 1)); echo "FAIL  exit $rc with --only t-pass"; }

# ---- v0.4 evidence: --status grades stored evidence against the CURRENT tree, running nothing
sts() { python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/gateway/x.go --status --json; }
sget() { jq -r --arg c "$1" '.checks[] | select(.check == $c) | .state' <<<"$sout" | head -1; }
sexp() { local g; g=$(sget "$1"); if [ "$g" = "$2" ]; then pass=$((pass + 1)); echo "PASS  status $1 -> $2 ($3)"; else fail=$((fail + 1)); echo "FAIL  status $1 expected $2 got ${g:-none} ($3)"; jq -c --arg c "$1" '.checks[] | select(.check == $c)' <<<"$sout"; fi; }
sout=$(sts); src=$?
sexp t-pass PASS "tree unchanged since the run"
sexp t-fail FAIL "a stored FAIL stays FAIL"
sexp t-needs NOT_RUN "declared, blocked, never executed"
sexp t-ci HUMAN_REQUIRED "external"
[ $src -eq 1 ] && { pass=$((pass + 1)); echo "PASS  --status exits 1 while a fast check is not PASS"; } || { fail=$((fail + 1)); echo "FAIL  --status exit $src"; }
[ -z "$(git -C "$S" status --porcelain)" ] && { pass=$((pass + 1)); echo "PASS  --status ran nothing in the repo"; } || { fail=$((fail + 1)); echo "FAIL  --status touched the repo"; }
echo "package x // edited" > "$S/backend/gateway/x.go"
sout=$(sts)
sexp t-pass STALE "tracked file edited after the PASS"
jq -e '.checks[] | select(.check == "t-pass") | .detail | test("working tree changed")' <<<"$sout" >/dev/null && { pass=$((pass + 1)); echo "PASS  STALE names the reason"; } || { fail=$((fail + 1)); echo "FAIL  STALE reason"; }
python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/gateway/x.go --only t-pass --json >/dev/null
sout=$(sts); sexp t-pass PASS "re-run on the edited tree"
git -C "$S" -c user.email=t@t -c user.name=t commit -qam edit
sout=$(sts); sexp t-pass STALE "HEAD moved (commit) - identity includes HEAD"
touch "$S/new-untracked.txt"; python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/gateway/x.go --only t-pass --json >/dev/null
rm -f "$S/new-untracked.txt"; sout=$(sts); sexp t-pass STALE "untracked file removed after the run"

# the identity covers the module's dependencies: gateway depends on shared -> a shared edit makes it STALE
python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/gateway/x.go --only t-scoped --json >/dev/null
sout=$(sts); sexp t-scoped PASS "scoped check fresh"
echo "# unrelated" >> "$S/backend/deploy/d.yaml"; sout=$(sts); sexp t-scoped PASS "edit outside the check's dependency closure"
echo "package shared // dependency edit" > "$S/backend/shared/s.go"; sout=$(sts); sexp t-scoped STALE "edit in a module the check's module depends on"

# ---- 1.0.5 robustness
okk() { pass=$((pass + 1)); echo "PASS  $1"; }; nok() { fail=$((fail + 1)); echo "FAIL  $1"; }
snap() { find "$TMP/state" -type f | sort; }
# --dry-run records nothing: no run record, no evidence, no log
before=$(snap); python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/gateway/x.go --dry-run --json >/dev/null
[ "$before" = "$(snap)" ] && okk "--dry-run writes nothing to the state root" || nok "--dry-run wrote: $(diff <(echo "$before") <(snap) | head -5)"
# valid JSON of the wrong shape is no evidence: NOT_RUN, never a crash
EV=$(python3 -B -c "import sys; sys.path.insert(0, sys.argv[1]); import evidence; print(evidence.repo_dir_for(sys.argv[2], 'server', create=False))" "$P/scripts/lib" "$WS")
for bad in '{"identity":"x"}' '[1]' '{"identity":{"tree":"x"}}' '"str"' '{"identity":{},"state":7}'; do
  printf '%s' "$bad" > "$EV/server.gateway__t-pass.json"
  sout=$(sts 2>&1); src=$?
  if jq -e . >/dev/null 2>&1 <<<"$sout" && [ "$(sget t-pass)" = NOT_RUN ] && [ $src -le 1 ]; then okk "wrong-shape evidence $bad -> NOT_RUN, no crash"
  else nok "wrong-shape evidence $bad: rc=$src ${sout:0:200}"; fi
done
# a stored record is replaced atomically: a reader polling during 40 rewrites never sees a missing or half record
python3 -B - "$P/scripts/lib" "$WS" <<'PY' && okk "evidence store vs concurrent reader: never a torn record" || nok "torn evidence record"
import os, subprocess, sys, time
sys.path.insert(0, sys.argv[1]); import evidence
res = {"module": "server.gateway", "check": "t-race", "state": "PASS", "timestamp": "20260101T000000", "identity": {"tree": "t", "head": "h"}}
evidence.store(sys.argv[2], "server", res, "x" * 20000)
code = ("import sys; sys.path.insert(0, %r); import evidence\nres = %r\n"
        "for i in range(40): evidence.store(%r, 'server', res, 'y' * 200000)\n") % (sys.argv[1], res, sys.argv[2])
w = subprocess.Popen([sys.executable, "-B", "-c", code])
misses = 0
while w.poll() is None:
    if evidence.latest(sys.argv[2], "server", "server.gateway", "t-race") is None:
        misses += 1
w.wait()
print("misses", misses) if misses else None
sys.exit(1 if misses or w.returncode else 0)
PY
# log names are unique per run (same second, parallel) and only the newest 20 per check are kept
python3 -B - "$P/scripts/lib" "$WS" <<'PY' && okk "logs: unique per store, pruned to the newest 20, latest log kept" || nok "log naming / pruning"
import os, sys
sys.path.insert(0, sys.argv[1]); import evidence
res = {"module": "server.gateway", "check": "t-prune", "state": "PASS", "timestamp": "20260101T000000", "identity": {"tree": "t"}}
logs = [evidence.store(sys.argv[2], "server", res, f"run {i}") for i in range(25)]
d = os.path.dirname(logs[-1])
mine = [f for f in os.listdir(d) if f.startswith("server.gateway__t-prune-")]
other = [f for f in os.listdir(d) if f.startswith("server.gateway__t-pass-")]
rec = evidence.latest(sys.argv[2], "server", "server.gateway", "t-prune")
ok = len(set(logs)) == 25 and len(mine) == 20 and os.path.exists(rec["log"]) and rec["log"] == logs[-1] and other
print(len(set(logs)), len(mine), rec and rec.get("log"), len(other)) if not ok else None
sys.exit(0 if ok else 1)
PY
ls "$TMP"/state/evidence/*/runs/server-*-*-*.json >/dev/null 2>&1 && okk "run record names carry a unique suffix" || nok "run record name"
# the workspace key is the case-folded real path: C:/X and c:\x share evidence on Windows
if [ -n "$RPGF_WINDOWS" ]; then
  python3 -B -c "import sys; sys.path.insert(0, sys.argv[1]); import fstate; w = sys.argv[2]; sys.exit(0 if fstate.workspace_key(w) == fstate.workspace_key(w.upper().replace('/', '\\\\')) else 1)" "$P/scripts/lib" "$WS" \
    && okk "workspace key ignores case and slash style" || nok "workspace key is case-sensitive"
  sout=$(RPG_FACTORY_WORKSPACE="$(tr '[:lower:]' '[:upper:]' <<<"$WS")" sts); sexp t-scoped STALE "same evidence through an upper-cased RPG_FACTORY_WORKSPACE"
fi

# ---- truthful evidence (audit TC-EVIDENCE)
rc_of() { "$@" >"$TMP/rc.out" 2>&1; echo $?; }
# the scope covers the check's OWN module even when the check runs elsewhere (t-elsewhere: module gateway, cwd backend/deploy)
python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/gateway/x.go --only t-elsewhere --json >/dev/null
sout=$(sts); sexp t-elsewhere PASS "check running outside its module, fresh"
echo "package x // own-module edit" > "$S/backend/gateway/x.go"; sout=$(sts)
sexp t-elsewhere STALE "edit in the check's own module path, outside its cwd"
# evidence recorded under an older (narrower) scope is STALE: the registry now gives the check another scope
EVF="$EV/server.gateway__t-elsewhere.json"
python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/gateway/x.go --only t-elsewhere --json >/dev/null
jq '.scopes = ["backend/deploy"]' "$EVF" > "$EVF.tmp" && mv "$EVF.tmp" "$EVF"
sout=$(sts); sexp t-elsewhere STALE "record made with an older scope"
jq -e '.checks[] | select(.check == "t-elsewhere") | .detail | test("scope changed")' <<<"$sout" >/dev/null && okk "STALE names the scope change" || nok "scope-change reason"
# needs: a prerequisite skipped by --only does not count as passed
out=$(python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/gateway/x.go --only t-needs-ok --json); rc=$?
expect t-needs-ok BLOCKED
jq -e '.results[] | select(.check == "t-needs-ok") | .reason | test("t-pass \\(SKIPPED\\)")' <<<"$out" >/dev/null && okk "BLOCKED names the prerequisite and its state" || nok "needs reason: $(jq -c '.results[] | select(.check == "t-needs-ok") | .reason' <<<"$out")"
[ $rc -eq 1 ] && okk "--only a check whose prerequisite was skipped: exit 1" || nok "--only t-needs-ok exit $rc"
out=$(python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/gateway/x.go --only t-pass t-needs-ok --json)
expect t-needs-ok PASS
# two modules share one command (dedup): each gets a record for its OWN definition and identity
out=$(python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/shared/s.go --only t-pass t-dup --json); rc=$?
expect t-pass PASS
expect t-dup PASS
[ $rc -eq 0 ] && okk "shared command: exit 0" || nok "shared command exit $rc"
sout=$(python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/shared/s.go --status --json)
sexp t-pass PASS "first module of a shared command, right after the run"
sexp t-dup PASS "second module of a shared command (other evidence text), right after the run"
# a changed registry command: STALE in run-checks --status AND in factory-status
cp "$P/registry.json" "$TMP/registry.bak"
jq '(.modules[] | select(.id == "server.gateway") | .checks.fast[] | select(.id == "t-pass") | .run) += " # changed"' "$TMP/registry.bak" > "$P/registry.json"
sout=$(python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/shared/s.go --status --json)
sexp t-pass STALE "registry changed the check command"
fs=$(python3 -B "$P/scripts/factory-status.py" --json 2>/dev/null)
jq -e '.evidence.server[] | select(.check == "server.gateway/t-pass") | .state == "STALE" and (.detail | test("definition changed"))' <<<"$fs" >/dev/null \
  && okk "factory-status: changed registry command -> STALE (same grade as run-checks --status)" || nok "factory-status grade: $(jq -c '.evidence.server[]? | select(.check == "server.gateway/t-pass")' <<<"$fs")"
jq -e '.evidence.server[] | select(.check == "server.shared/t-dup") | .state == "PASS"' <<<"$fs" >/dev/null \
  && okk "factory-status: unchanged check stays PASS" || nok "factory-status t-dup: $(jq -c '.evidence.server[]? | select(.check == "server.shared/t-dup")' <<<"$fs")"
cp "$TMP/registry.bak" "$P/registry.json"
# nothing verified is never a silent success: unknown names and outside paths are usage errors (exit 2)
RC="$P/scripts/run-checks.py"
[ "$(rc_of python3 -B "$RC" --repo server --paths backend/gateway/x.go --tier bogus)" = 2 ] && grep -q "unknown --tier" "$TMP/rc.out" && okk "--tier bogus: exit 2" || nok "--tier bogus: $(cat "$TMP/rc.out" | tail -2)"
[ "$(rc_of python3 -B "$RC" --repo server --paths backend/gateway/x.go --only t-typo)" = 2 ] && grep -q "t-typo" "$TMP/rc.out" && okk "--only typo: exit 2" || nok "--only typo: $(tail -2 "$TMP/rc.out")"
[ "$(rc_of python3 -B "$RC" --repo server --paths backend/gateway/x.go --timeout abc)" = 2 ] && ! grep -q Traceback "$TMP/rc.out" && okk "--timeout abc: exit 2, no traceback" || nok "--timeout abc: $(tail -2 "$TMP/rc.out")"
mkdir -p "$TMP/elsewhere"; touch "$TMP/elsewhere/f.go"
for args in "--paths $TMP/elsewhere/f.go" "--paths $TMP/elsewhere/f.go --status" "--paths ../elsewhere/f.go"; do
  # shellcheck disable=SC2086
  [ "$(rc_of python3 -B "$RC" --repo server $args)" = 2 ] && grep -q "outside the server checkout" "$TMP/rc.out" && okk "path outside the repo ($args): exit 2" || nok "outside path ($args): $(tail -2 "$TMP/rc.out")"
done
git -C "$S" worktree add -q "$TMP/wt-server" 2>/dev/null
out=$(python3 -B "$RC" --repo server --paths "$TMP/wt-server/backend/gateway/x.go" --dry-run --json); rc=$?
[ $rc -eq 0 ] && [ "$(st t-pass)" = SKIPPED ] && okk "path inside a linked worktree of the repo routes like the repo path" || nok "worktree path: rc=$rc t-pass=$(st t-pass)"
git -C "$S" worktree remove --force "$TMP/wt-server"
o=$(python3 -B "$RC" --repo server --paths backend/TEAM.md 2>&1); rc=$?
[ $rc -eq 0 ] && grep -q "none registered" <<<"$o" && okk "no check registered for the paths: says so (exit 0)" || nok "none registered: rc=$rc $o"
o=$(python3 -B "$RC" --repo server --paths backend/TEAM.md --status 2>&1)
grep -q "none registered" <<<"$o" && okk "--status: no check registered says so" || nok "--status none registered: $o"

total=$((pass + fail)); echo "run-checks tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
