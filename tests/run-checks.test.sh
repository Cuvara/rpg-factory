#!/usr/bin/env bash
# run-checks.py state model, deterministically: a temp plugin copy whose registry gives the
# server.gateway module synthetic checks, run against a throwaway workspace.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
P="$TMP/plugin"; mkdir -p "$P"; cp -r "$ROOT/scripts" "$ROOT/.claude-plugin" "$P/"
RUNNER_SOURCE="${1:-${RUN_CHECKS_BASELINE:-}}"
if [ -n "$RUNNER_SOURCE" ]; then cp "$RUNNER_SOURCE" "$P/scripts/run-checks.py"; fi
WS="$TMP/work space"; S="$WS/rpg-mmo-server"; C="$WS/IndieRPGMMOAdventure"
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
      extended: [
        {id: "t-ext", cwd: ".", run: "echo --- PASS: TestX", parser: "go-test", trigger: "always", evidence: "e"},
        {id: "t-isolated-pollute", cwd: ".", run: "touch isolated-leftover.txt", evidence: "e"},
        {id: "t-isolated-clean", cwd: ".", run: "echo clean", evidence: "e"},
        {id: "t-isolated-clean2", cwd: ".", run: "echo clean again", evidence: "e"},
        {id: "t-dirty-edit", cwd: ".", run: "echo edited >> backend/gateway/x.go", evidence: "e"},
        {id: "t-large-untracked", cwd: ".", run: "echo clean", evidence: "e"},
        {id: "t-timeout-tree", cwd: ".", run: "(sleep 60) & echo $! > child.pid; cat /proc/$!/winpid > child.winpid 2>/dev/null || true; wait", evidence: "e"},
        {id: "t-env", cwd: ".", run: "env | grep '^RPG_FACTORY_'; pwd", evidence: "e"}
      ],
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
okk() { pass=$((pass + 1)); echo "PASS  $1"; }; nok() { fail=$((fail + 1)); echo "FAIL  $1"; }
rm -f "$S/leftover.txt"
out=$(python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/gateway/x.go --only t-isolated-pollute t-isolated-clean --approve t-isolated-pollute t-isolated-clean --json)
[ "$(jq -r '.results[] | select(.check == "t-isolated-pollute") | .state' <<<"$out")" = FAIL ] && okk "polluting check fails" || nok "polluting check state"
[ "$(jq -r '.results[] | select(.check == "t-isolated-clean") | .state' <<<"$out")" = PASS ] && okk "later clean check passes despite earlier leftover" || nok "later clean check was blamed"
rm -f "$S/isolated-leftover.txt"
out=$(python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/gateway/x.go --only t-isolated-clean t-isolated-clean2 --approve t-isolated-clean t-isolated-clean2 --json)
[ "$(jq -r '[.results[] | select(.check | startswith("t-isolated-clean")) | .state] | all(. == "PASS")' <<<"$out")" = true ] && okk "sequential clean checks both pass" || nok "sequential clean checks failed"
cp "$S/backend/gateway/x.go" "$TMP/x.go.bak"
echo 'pre-existing dirty content' >> "$S/backend/gateway/x.go"
out=$(python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/gateway/x.go --only t-dirty-edit --approve t-dirty-edit --json)
jq -e '.results[] | select(.check == "t-dirty-edit") | .state == "FAIL" and (.reason | test("backend/gateway/x.go"))' <<<"$out" >/dev/null && okk "edit to already-dirty path is detected" || nok "edit to already-dirty path missed"
cp "$TMP/x.go.bak" "$S/backend/gateway/x.go"
# A large untracked artifact is fingerprinted from one stat, without opening or hashing its contents.
dd if=/dev/zero of="$S/large-untracked.bin" bs=1M count=32 2>/dev/null
python3 -B - "$P/scripts/run-checks.py" "$S/large-untracked.bin" "$S" <<'PY'
import builtins, importlib.util, os, sys
runner, target, repo = sys.argv[1:]
spec = importlib.util.spec_from_file_location("runner_under_test", runner)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
real_open = builtins.open
def guarded_open(file, *args, **kwargs):
    if os.path.normcase(os.path.abspath(os.fspath(file))) == os.path.normcase(os.path.abspath(target)):
        raise AssertionError("worktree_state read the large untracked file")
    return real_open(file, *args, **kwargs)
builtins.open = guarded_open
state = mod.worktree_state(repo)
assert "large-untracked.bin" in state
assert state["large-untracked.bin"].startswith("size=")
PY
[ $? -eq 0 ] && okk "large untracked file fingerprint does not read contents" || nok "large untracked file was read"
rm -f "$S/large-untracked.bin"
out=$(python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/gateway/x.go --only t-env --approve t-env --json)
head=$(git -C "$S" rev-parse HEAD)
jq -e --arg ws "$WS" --arg repo "$S" --arg head "$head" '.results[] | select(.check == "t-env") | .state == "PASS" and (.output_tail | contains("work space") and contains("rpg-mmo-server") and contains("server") and contains($head))' <<<"$out" >/dev/null && okk "bash receives workspace, repo, repo key and head; cwd is correct" || { nok "environment contract"; jq -c '.results[] | select(.check == "t-env") | {state,reason,output_tail}' <<<"$out"; }
out=$(RPG_FACTORY_WORKSPACE="$TMP/missing workspace" python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/gateway/x.go --only t-env --approve t-env --json)
[ "$(jq -r '.results[] | select(.check == "t-env") | .state' <<<"$out")" = BLOCKED ] && okk "missing workspace blocks the check" || nok "missing workspace did not block"
if [ -n "$RPGF_WINDOWS" ]; then
  python3 -B - "$P/scripts/run-checks.py" "$WS" "$(command -v bash)" <<'PY'
import importlib.util, sys, shutil
from unittest.mock import patch
spec = importlib.util.spec_from_file_location("runner_under_test", sys.argv[1])
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
real_which = shutil.which
shutil.which = lambda name: None if name == "cygpath" else real_which(name)
converted = mod.bash_env_path(sys.argv[2], sys.argv[3])
assert converted.startswith(sys.argv[2][:2] + "/") and "\\" not in converted, converted
with patch.object(mod.subprocess, "run", return_value=__import__("subprocess").CompletedProcess([], 0, "/mnt/c/Work Space", "")):
    assert mod.bash_env_path(r"C:\Work Space", "bash.exe", "wsl") == "/mnt/c/Work Space"
alias = __import__("os").path.join(__import__("os").environ.get("LOCALAPPDATA", ""), "Microsoft", "WindowsApps", "bash.exe")
mod._BASH_SELECTION = None
with patch.object(mod.os, "name", "nt"), patch.object(mod.shutil, "which", side_effect=lambda n: alias if n == "bash" else None), \
     patch.object(mod.os.path, "isfile", side_effect=lambda p: "WindowsApps" in str(p)), \
     patch.object(mod.subprocess, "run", return_value=__import__("subprocess").CompletedProcess([], 0, "Linux\n6.6-microsoft-standard-WSL2", "")):
    assert mod.select_bash() == (alias, "wsl")
env = mod.wsl_environment({"WSLENV": "EXISTING", "RPG_FACTORY_WORKSPACE": "/mnt/c/work space"})
assert all(n in env["WSLENV"].split(":") for n in ("RPG_FACTORY_WORKSPACE", "RPG_FACTORY_REPO_DIR", "RPG_FACTORY_REPO_KEY", "RPG_FACTORY_HEAD", "PYTHONDONTWRITEBYTECODE")), env
assert "/p" not in env["WSLENV"]
PY
  [ $? -eq 0 ] && okk "Git Bash and WSL path/environment probes pass" || nok "bash path/environment probe failed"
fi
start=$(python3 -c 'import time; print(time.monotonic())')
out=$(python3 -B "$P/scripts/run-checks.py" --repo server --paths backend/gateway/x.go --only t-timeout-tree --approve t-timeout-tree --timeout 1 --json)
elapsed=$(python3 -c 'import time,sys; print(time.monotonic()-float(sys.argv[1]))' "$start")
[ "$(awk -v e="$elapsed" 'BEGIN {print (e <= 8) ? "yes" : "no"}')" = yes ] && okk "timeout runner returned within timeout plus cleanup grace (${elapsed}s)" || nok "timeout runner exceeded bound (${elapsed}s)"
[ "$(jq -r '.results[] | select(.check == "t-timeout-tree") | .state' <<<"$out")" = FAIL ] && jq -e '.results[] | select(.check == "t-timeout-tree") | .reason | test("(?i)timeout.*cleanup")' <<<"$out" >/dev/null && okk "timeout is a FAIL with cleanup diagnostics" || nok "timeout state/diagnostics"
if [ -f "$S/child.pid" ]; then pid=$(cat "$S/child.pid"); kill -0 "$pid" 2>/dev/null && nok "timeout grandchild survived (pid $pid)" || okk "timeout grandchild was killed"; else nok "timeout check did not create pid file"; fi
if [ -s "$S/child.winpid" ]; then wpid=$(cat "$S/child.winpid"); tasklist //FI "PID eq $wpid" 2>/dev/null | grep -q "$wpid" && nok "timeout Windows grandchild survived (pid $wpid)" || okk "timeout Windows grandchild was killed"; fi
rm -f "$S/child.pid" "$S/child.winpid"
python3 -B "$ROOT/tests/fixtures/run-checks-cleanup-failure.py" "$P/scripts/run-checks.py" && okk "simulated timeout cleanup failure is reported" || nok "simulated cleanup failure was hidden"
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
python3 -B "$ROOT/tests/fixtures/run-checks-evidence-race.py" "$P/scripts/lib" "$WS" && okk "evidence store vs concurrent reader: never a torn record" || nok "torn evidence record"
# log names are unique per run (same second, parallel) and only the newest 20 per check are kept
python3 -B "$ROOT/tests/fixtures/run-checks-log-prune.py" "$P/scripts/lib" "$WS" && okk "logs: unique per store, pruned to newest 20, latest log kept" || nok "log naming / pruning"
ls "$TMP"/state/evidence/*/runs/server-*-*-*.json >/dev/null 2>&1 && okk "run record names carry a unique suffix" || nok "run record name"
# the workspace key is the case-folded real path: C:/X and c:\x share evidence on Windows
if [ -n "$RPGF_WINDOWS" ]; then
  python3 -B - "$P/scripts/lib" "$WS" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import fstate
w = sys.argv[2]
sys.exit(0 if fstate.workspace_key(w) == fstate.workspace_key(w.upper().replace('/', '\\')) else 1)
PY
  [ $? -eq 0 ] && okk "workspace key ignores case and slash style" || nok "workspace key is case-sensitive"
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
for args in "--paths $TMP/elsewhere/f.go" "--paths $TMP/elsewhere/f.go --status" "--paths ../elsewhere/f.go"             "--paths backend/../../elsewhere/f.go" "--paths backend/gateway/x.go $TMP/elsewhere/f.go"; do
  # shellcheck disable=SC2086
  [ "$(rc_of python3 -B "$RC" --repo server $args)" = 2 ] && grep -q "outside the server checkout" "$TMP/rc.out" && okk "path outside the repo ($args): exit 2" || nok "outside path ($args): $(tail -2 "$TMP/rc.out")"
done
git -C "$S" worktree add -q "$TMP/wt-server" 2>/dev/null
# checks run in the checkout run-checks runs in: a file of another linked worktree is a usage error, not
# evidence from the wrong tree; from inside that worktree the same absolute path is fine
[ "$(rc_of python3 -B "$RC" --repo server --paths "$TMP/wt-server/backend/gateway/x.go" --dry-run)" = 2 ] && grep -q "another checkout of server" "$TMP/rc.out"   && okk "path in another linked worktree of the repo: exit 2, run from that worktree" || nok "worktree path from main checkout: $(tail -2 "$TMP/rc.out")"
out=$(cd "$TMP/wt-server" && python3 -B "$RC" --repo server --paths "$TMP/wt-server/backend/gateway/x.go" --dry-run --json); rc=$?
[ $rc -eq 0 ] && [ "$(st t-pass)" = SKIPPED ] && okk "path inside the worktree run-checks runs in routes like the repo path" || nok "worktree path from the worktree: rc=$rc t-pass=$(st t-pass)"
git -C "$S" worktree remove --force "$TMP/wt-server"
o=$(python3 -B "$RC" --repo server --paths backend/TEAM.md 2>&1); rc=$?
[ $rc -eq 0 ] && grep -q "none registered" <<<"$o" && okk "no check registered for the paths: says so (exit 0)" || nok "none registered: rc=$rc $o"
o=$(python3 -B "$RC" --repo server --paths backend/TEAM.md --status 2>&1)
grep -q "none registered" <<<"$o" && okk "--status: no check registered says so" || nok "--status none registered: $o"

total=$((pass + fail)); echo "run-checks tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
