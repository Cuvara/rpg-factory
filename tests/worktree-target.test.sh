#!/usr/bin/env bash
# run-checks.py must run in the worktree it is invoked from (never silently in the canonical checkout), write no
# .pyc anywhere, and fail loudly when anything changes in the canonical checkout during a run. Throwaway fixture only.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
P="$TMP/plugin"; mkdir -p "$P"; cp -r "$ROOT/scripts" "$ROOT/.claude-plugin" "$P/"
WS="$TMP/ws"; S="$WS/rpg-mmo-server"; C="$WS/IndieRPGMMOAdventure"; WT="$TMP/agent-wt/task1"
mkdir -p "$S/backend/gateway" "$S/.github/scripts" "$C/ProjectSettings" "$TMP/elsewhere"
touch "$S/backend/TEAM.md" "$S/backend/gateway/x.go" "$C/ProjectSettings/ProjectVersion.txt"
printf 'x = 1\n' > "$S/.github/scripts/a.py"; printf '__pycache__/\n' > "$S/.gitignore"
for r in "$S" "$C"; do git -C "$r" init -q -b develop; git -C "$r" -c user.email=t@t -c user.name=t add -A; git -C "$r" -c user.email=t@t -c user.name=t commit -qm init; done
git -C "$S" worktree add -q "$WT" -b feat/x/y
jq --arg ws "$WS" --arg poison "$S/poison.txt" '
  .workspace.root_default = $ws
  | (.modules[] | select(.id == "server.gateway")) |= (.tools = [] | .checks = {fast: [
      {id: "t-where", cwd: ".", run: "pwd", evidence: "e"},
      {id: "t-pyc", cwd: ".", run: "python3 -m py_compile .github/scripts/a.py && python3 -c \"import sys; sys.path.insert(0, \\\".github/scripts\\\"); import a\"", evidence: "e"},
      {id: "t-poison", cwd: ".", run: ("touch \"" + $poison + "\""), evidence: "e"}], extended: [], external: []})
' "$ROOT/registry.json" > "$P/registry.json"
export RPG_FACTORY_WORKSPACE="$WS" CLAUDE_PLUGIN_ROOT="$P" TMPDIR="$TMP" RPG_FACTORY_STATE_DIR="$TMP/state"
unset PYTHONDONTWRITEBYTECODE PYTHONPYCACHEPREFIX
RC="$P/scripts/run-checks.py"
pass=0; fail=0
okk() { pass=$((pass + 1)); echo "PASS  $1"; }; nok() { fail=$((fail + 1)); echo "FAIL  $1"; }
snap() { git -C "$S" status --porcelain=v1 --untracked-files=all --ignored=traditional; }
res() { jq -r --arg c "$2" '.results[] | select(.check == $c) | .'"$3" <<<"$1" | head -1; }

before=$(snap)
out=$(cd "$WT" && python3 -B "$RC" --repo server --paths backend/gateway/x.go --only t-where t-pyc --json); rc=$?
[ "$(jq -r .resolution.source <<<"$out")" = cwd-worktree ] && okk "invoked from a linked worktree: target is that worktree" || nok "resolution: $(jq -c .resolution <<<"$out")"
fwd() { sed 's#\\#/#g'; }
[ "$(jq -r .path <<<"$out" | fwd)" = "$(echo "$WT" | fwd)" ] && okk "record path is the worktree" || nok "record path $(jq -r .path <<<"$out")"
res "$out" t-where output_tail | grep -q "task1" && okk "check ran with the worktree as cwd" || nok "check cwd: $(res "$out" t-where output_tail)"
[ "$(res "$out" t-pyc state)" = PASS ] && okk "py_compile check passes" || nok "t-pyc: $(res "$out" t-pyc reason)"
[ "$(res "$out" canonical-checkout-guard state)" = PASS ] && okk "guard row PASS when the canonical checkout is untouched" || nok "guard: $(res "$out" canonical-checkout-guard reason)"
[ "$(snap)" = "$before" ] && okk "canonical git status unchanged (incl. ignored)" || nok "canonical changed: $(diff <(echo "$before") <(snap))"
[ -z "$(find "$S" "$WT" -name '*.pyc' -not -path '*/.git/*' 2>/dev/null)" ] && okk "no .pyc in the canonical checkout or the worktree" || nok "pyc found: $(find "$S" "$WT" -name '*.pyc')"

# guard bites: a check that writes into the canonical checkout fails the run
out=$(cd "$WT" && python3 -B "$RC" --repo server --paths backend/gateway/x.go --only t-poison --json); rc=$?
[ "$(res "$out" canonical-checkout-guard state)" = FAIL ] && res "$out" canonical-checkout-guard reason | grep -q poison.txt && okk "guard FAILs and names the file" || nok "guard did not bite: $(res "$out" canonical-checkout-guard reason)"
[ $rc -eq 1 ] && okk "run exits 1 when the canonical checkout changed" || nok "exit $rc"
rm -f "$S/poison.txt"

# a stray .pyc (gitignored) in the canonical checkout is caught too
jq --arg d "$S/.github/scripts/__pycache__" '(.modules[] | select(.id == "server.gateway") | .checks.fast[] | select(.id == "t-poison") | .run) = ("mkdir -p \"" + $d + "\" && touch \"" + $d + "/a.cpython-312.pyc\"")' "$P/registry.json" > "$P/r2.json" && mv "$P/r2.json" "$P/registry.json"
out=$(cd "$WT" && python3 -B "$RC" --repo server --paths backend/gateway/x.go --only t-poison --json); rc=$?
[ "$(res "$out" canonical-checkout-guard state)" = FAIL ] && okk "guard catches a gitignored .pyc in the canonical checkout" || nok "pyc guard: $(res "$out" canonical-checkout-guard reason)"
rm -rf "$S/.github/scripts/__pycache__"

# cwd outside every worktree: canonical fallback, announced
o=$(cd "$TMP/elsewhere" && python3 -B "$RC" --repo server --paths backend/gateway/x.go --only t-where 2>&1)
grep -q "canonical-fallback" <<<"$o" && grep -q "NOTE: .*outside every checkout and worktree" <<<"$o" && okk "cwd outside the repo: canonical fallback is announced" || nok "fallback: $o"
# --repo-path targets a worktree from anywhere
out=$(cd "$TMP/elsewhere" && python3 -B "$RC" --repo server --repo-path "$WT" --paths backend/gateway/x.go --only t-where --json)
[ "$(jq -r .resolution.source <<<"$out")" = repo-path ] && res "$out" t-where output_tail | grep -q task1 && okk "--repo-path runs in the named worktree" || nok "--repo-path: $(jq -c .resolution <<<"$out")"
[ "$(snap)" = "$before" ] && okk "canonical untouched after --repo-path run" || nok "canonical changed after --repo-path"
o=$(cd "$TMP/elsewhere" && python3 -B "$RC" --repo server --repo-path "$TMP/elsewhere" --dry-run 2>&1); r=$?
[ $r -eq 2 ] && okk "--repo-path outside any registered repo: exit 2" || nok "--repo-path outside: rc=$r $o"
o=$(cd "$WT" && python3 -B "$RC" --repo client --repo-path "$WT" --dry-run 2>&1); r=$?
[ $r -eq 2 ] && grep -q "belongs to repo 'server'" <<<"$o" && okk "--repo-path of another repo than --repo: exit 2" || nok "--repo mismatch: rc=$r $o"
# factory-context honours the same rules
j=$(cd "$WT" && bash "$P/scripts/factory-context.sh" --repo server --json)
[ "$(jq -r '.repos[0].resolution.source' <<<"$j")" = cwd-worktree ] && okk "factory-context: worktree cwd resolves to the worktree" || nok "factory-context resolution"
j=$(cd "$TMP/elsewhere" && bash "$P/scripts/factory-context.sh" --repo server --json)
[ "$(jq -r '.repos[0].resolution.source' <<<"$j")" = canonical-fallback ] && okk "factory-context: outside cwd announces the fallback" || nok "factory-context fallback"

echo "worktree-target tests: $((pass + fail)) run, $pass passed, $fail failed"
[ "$fail" -eq 0 ]
