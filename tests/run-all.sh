#!/usr/bin/env bash
# run-all.sh — every local validation for the plugin. Read-only against the workspace.
# Prints one line per check and a final count; exits non-zero if anything failed.
#
# Usage: tests/run-all.sh [--no-workspace] [--no-claude] [--release]
#   --release       the installed plugin must equal the source (install-status CURRENT)
#   --no-workspace  skip checks that need the RPG MMO workspace on disk
#   --no-claude     skip `claude plugin validate`
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1
use_ws=true; use_claude=true; release=false
for a in "$@"; do
  case "$a" in --no-workspace) use_ws=false ;; --no-claude) use_claude=false ;; --release) release=true ;; esac
done

pass=0; fail=0; skip=0
ok()   { pass=$((pass + 1)); echo "PASS  $1"; }
bad()  { fail=$((fail + 1)); echo "FAIL  $1"; [ -n "${2:-}" ] && echo "$2" | sed 's/^/      /'; }
skp()  { skip=$((skip + 1)); echo "SKIP  $1 ($2)"; }
run()  { local name="$1"; shift; local out; if out=$("$@" 2>&1); then ok "$name"; else bad "$name" "$out"; fi; }

# ---- syntax
json_count=0
while IFS= read -r f; do json_count=$((json_count + 1)); run "json: $f" jq empty "$f"; done \
  < <(find . -name '*.json' -not -path './.git/*' | sort)
[ "$json_count" -ge 4 ] && ok "json files found: $json_count" || bad "json files found: $json_count (expected >= 4)"
for f in scripts/*.sh scripts/checks/*.sh tests/*.sh; do run "bash -n: $f" bash -n "$f"; done
for f in scripts/*.py scripts/checks/*.py; do run "py_compile: $f" python3 -B -c "import ast,sys; ast.parse(open(sys.argv[1]).read(), sys.argv[1])" "$f"; done
run "jq compile: scripts/lib/resolve.jq" \
  jq -e --arg repo server --argjson files '[]' --argjson subst '{}' --argjson tools '{}' -f scripts/lib/resolve.jq registry.json
find scripts tests -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null

# ---- executable bits (as recorded in git when available, else filesystem)
for f in scripts/factory-context.sh scripts/check-registry.sh scripts/git-guard.py scripts/checks/*.py scripts/checks/*.sh \
         tests/*.sh; do
  mode=$(git ls-files -s "$f" 2>/dev/null | awk '{print $1}')
  if [ "$mode" = "100755" ] || { [ -z "$mode" ] && [ -x "$f" ]; }; then ok "executable: $f"
  else bad "executable: $f" "git mode=${mode:-untracked}"; fi
done

# ---- manifest consistency
name=$(jq -r .name .claude-plugin/plugin.json)
mname=$(jq -r '.plugins[0].name' .claude-plugin/marketplace.json)
msrc=$(jq -r '.plugins[0].source' .claude-plugin/marketplace.json)
[ "$name" = "rpg-factory" ] && [ "$mname" = "$name" ] && [ "$msrc" = "./" ] \
  && ok "manifest: plugin.json name == marketplace entry, source ./" \
  || bad "manifest consistency" "plugin=$name marketplace=$mname source=$msrc"
[ -f "skills/factory-core/SKILL.md" ] && head -5 skills/factory-core/SKILL.md | grep -q '^name: factory-core$' \
  && ok "skill: factory-core frontmatter name" || bad "skill: factory-core frontmatter name"
for ref in $(grep -o 'references/[a-z-]*\.md' skills/factory-core/SKILL.md | sort -u); do
  [ -f "skills/factory-core/$ref" ] && ok "skill reference exists: $ref" || bad "skill reference missing: $ref"
done
jq -e '(.hooks.PreToolUse[0].matcher == "Bash|PowerShell")
        and ([.hooks.PreToolUse[0].hooks[].command] | any(test("git-guard.py")) and any(test("tripwire.py\" --pre")))
        and (.hooks.PostToolUse[0].matcher == "Bash|PowerShell") and (.hooks.PostToolUse[0].hooks[0].command | test("tripwire.py\" --post"))
        and ([.hooks.SessionStart[0].hooks[].command] | any(test("install-status.py\" --session")) and any(test("tripwire.py\" --session-start")))' hooks/hooks.json >/dev/null \
  && ok "hooks: guard+tripwire on Bash|PowerShell, tripwire post, session install check + baseline" || bad "hooks wiring"

# ---- registry
run "registry structure" scripts/check-registry.sh --structure-only
if $use_ws; then run "registry paths exist in workspace" scripts/check-registry.sh
else skp "registry paths exist in workspace" "--no-workspace"; fi

# ---- git guard, skill contract lint, routing (task + historical replay)
run "git-guard unit tests" tests/git-guard.test.sh
run "skills lint (contract)" tests/skills-lint.sh
run "tripwire (script-driven mutations, latch, submodule work)" env -u TMPDIR tests/tripwire.test.sh
run "worktree-aware context" tests/worktree.test.sh
run "check runner state model" tests/run-checks.test.sh
run "factory-status rollout / resume fixture" tests/factory-status.test.sh
run "install-status stale-install detection" tests/install-status.test.sh
if $use_ws; then run "routing properties over real history" python3 -B tests/routing-properties.test.py
else skp "routing properties over real history" "--no-workspace"; fi
if $use_ws; then run "registry facts re-probed in the repos" tests/facts.test.sh
else skp "registry facts re-probed in the repos" "--no-workspace"; fi
if $use_ws; then run "routing + history replay" tests/routing.test.sh
else run "routing (task scenarios only)" tests/routing.test.sh --no-history; fi

# ---- resolver behaviour (pure jq, no workspace needed)
resolve() { # repo files-json
  jq -c --arg repo "$1" --argjson files "$2" --argjson subst '{"{dotnet}":"dotnet.exe","{plugin_root}":"/p"}' \
    --argjson tools '{"go":"/usr/bin/go","dotnet":"/x/dotnet.exe","python3":"/usr/bin/python3","protoc":"/usr/bin/protoc","protoc-gen-go":"/x","jq":"/usr/bin/jq","docker":null}' \
    -f scripts/lib/resolve.jq registry.json
}
expect() { # name jq-predicate json
  if jq -e "$2" <<<"$3" >/dev/null 2>&1; then ok "resolve: $1"; else bad "resolve: $1" "$(jq -c '{touched,dependents,unmapped}' <<<"$3")"; fi
}
r=$(resolve server '[{"path":"backend/shared/proto/wire.proto","status":"--","source":"given"}]')
expect "wire.proto -> server.proto (longest prefix)" '.touched == ["server.proto"]' "$r"
expect "wire.proto dependents include C# server + integration" '(.dependents | index("server.gameserver-dotnet")) and (.dependents | index("server.integration-test"))' "$r"
expect "proto triggers proto-regen extended check" 'any(.checks[]; .id == "proto-regen" and .tier == "extended")' "$r"
r=$(resolve server '[{"path":"backend/gateway/internal/redirect.go","status":" M","source":"worktree"}]')
expect "gateway fast checks = vet+test+build" '[.checks[] | select(.tier=="fast" and .module=="server.gateway") | .id] == ["go-vet","go-test","go-build"]' "$r"
expect "gateway dependents = integration only" '.dependents == ["server.integration-test"]' "$r"
r=$(resolve server '[{"path":"backend/gameserver-dotnet/GameServer/Program.cs","status":" M","source":"worktree"}]')
expect "{dotnet} substituted" 'any(.checks[]; .run == "dotnet.exe build -c Release")' "$r"
r=$(resolve server '[{"path":"backend/gameserver-dotnet/GameServer/Net/Generated/Wire.cs","status":" M","source":"worktree"}]')
expect "generated path flagged" '.generated_hits | length == 1' "$r"
r=$(resolve client '[{"path":"Assets/Samples/Netcode/DOTS Sample/Scripts/A.cs","status":" M","source":"worktree"},{"path":"Assets/Samples/Cuvara UI Toolkit/","status":"??","source":"worktree"},{"path":"Packages/com.gdk.core","status":" M","source":"worktree"},{"path":"weird/file.txt","status":"??","source":"worktree"}]')
expect "DOTS Sample beats Assets/Samples" '.files[0].module == "client.dots-sample"' "$r"
expect "untracked sample dir -> samples-imported" '.files[1].module == "client.samples-imported"' "$r"
expect "submodule pointer -> gdk-submodules" '.files[2].module == "client.gdk-submodules"' "$r"
expect "unknown path -> repo-level (client.root), not unmapped" '.unmapped == [] and .repo_level == ["weird/file.txt"]' "$r"
expect "{plugin_root} substituted in package-pins" 'any(.checks[]; .run == "python3 /p/scripts/checks/unity-package-pins.py .")' "$r"
r=$(resolve server '[]')
expect "no files -> no checks" '.checks == [] and .touched == []' "$r"

# ---- live context script (read-only against the real workspace)
if $use_ws; then
  if out=$(scripts/factory-context.sh --json 2>&1) && jq -e --argjson n "$(jq '.repos | length' registry.json)" '.repos | length == $n' <<<"$out" >/dev/null; then
    ok "factory-context --json: every registered repo"
    jq -e 'all(.repos[]; .error == null and (.branch | length) > 0)' <<<"$out" >/dev/null \
      && ok "factory-context: branch resolved for each repo" || bad "factory-context: branch per repo" "$out"
    out2=$(scripts/factory-context.sh --repo server --json --paths backend/gameserver-dotnet/GameServer/Program.cs 2>&1)
    jq -e 'any(.toolchain[]; .tool == "dotnet" and .resolved != null)' <<<"$out2" >/dev/null \
      && ok "factory-context: dotnet resolved lazily for a .NET change ($(jq -r '.toolchain[] | select(.tool=="dotnet") | .resolved' <<<"$out2"))" \
      || bad "factory-context: dotnet not resolved (dotnet / dotnet.exe)"
  else
    bad "factory-context --json" "$out"
  fi
  out=$(scripts/factory-context.sh --repo server --json --paths backend/gateway/x.go 2>&1)
  jq -e '.repos[0].touched == ["server.gateway"] and (.repos[0].files | length == 1)' <<<"$out" >/dev/null \
    && ok "factory-context --paths ignores working tree" || bad "factory-context --paths" "$out"
  scripts/factory-context.sh --paths x >/dev/null 2>&1; [ $? -eq 2 ] \
    && ok "factory-context --paths without --repo is rejected" || bad "factory-context --paths without --repo"
  md=$(scripts/factory-context.sh --repo client 2>&1)
  grep -q "^## client:" <<<"$md" && ok "factory-context markdown renders" || bad "factory-context markdown" "$md"
else
  skp "factory-context live checks" "--no-workspace"
fi

# ---- Factory check scripts against the live workspace (read-only)
if $use_ws; then
  run "pin-status (client pins vs upstream tags)" python3 -B scripts/checks/pin-status.py
  run "wire-parity (Wire.cs bytes + protocol version)" bash scripts/checks/wire-parity.sh
  out=$(python3 -B scripts/checks/pin-plan.py com.cuvara.netcode v0.45.0 --client-ref 17b7737^ 2>&1)
  grep -q "hash=2eb6ddbc4e0c62544fa860b3a4f7e64071918f0b" <<<"$out" && grep -q "DOTSNetworkBridge.cs" <<<"$out" \
    && ok "pin-plan replays 17b7737 (lock hash + DOTS Sample file)" || bad "pin-plan replay of 17b7737" "$out"
  out=$(python3 -B scripts/checks/pin-plan.py com.cuvara.dots v99.0.0 2>&1); rc=$?
  [ $rc -eq 1 ] && grep -q "BLOCKED: tag v99.0.0 not found" <<<"$out" && ok "pin-plan blocks on a missing tag" || bad "pin-plan missing-tag gate" "$out"
  for p in Netcode UnityDots UIToolkit; do
    out=$(python3 -B scripts/checks/package-ready.py "${RPG_FACTORY_WORKSPACE:-/mnt/c/Workspaces/UnityIndie}/$p" 2>&1); rc=$?
    { [ $rc -eq 0 ] && grep -q "READY to tag" <<<"$out"; } || { [ $rc -eq 1 ] && grep -q "NOT READY" <<<"$out"; } \
      && ok "package-ready $p -> $(grep -m1 -oE 'NOT READY|READY to tag v[0-9.]+' <<<"$out")" || bad "package-ready $p" "$out"
  done
  if command -v dotnet >/dev/null 2>&1 || command -v dotnet.exe >/dev/null 2>&1; then
    out=$(bash scripts/checks/netcode-headless.sh 2>&1); rc=$?
    [ $rc -eq 0 ] && ok "netcode headless tests: $(grep -oE 'discovered=[0-9]+ executed=[0-9]+ passed=[0-9]+ failed=[0-9]+' <<<"$out")" || bad "netcode headless tests" "$(tail -5 <<<"$out")"
  else skp "netcode headless tests" "no dotnet/dotnet.exe"; fi
fi

# ---- live derived status + install state
if $use_ws; then
  run "factory-status on the real workspace (read-only)" python3 -B scripts/factory-status.py
fi
ist=$(python3 -B scripts/install-status.py --json 2>/dev/null | jq -r .state)
if $release; then
  [ "$ist" = "CURRENT" ] && ok "installed plugin == source (release gate)" || bad "installed plugin == source (release gate)" "$(python3 -B scripts/install-status.py)"
else
  skp "installed plugin == source" "install state $ist; required only with --release"
fi

# ---- package pins checker behaviour
T=$(mktemp -d); mkdir -p "$T/Packages"
echo '{"dependencies":{"a":"https://x/a.git#v1","b":"1.0.0"}}' > "$T/Packages/manifest.json"
echo '{"dependencies":{"a":{"version":"https://x/a.git#v1"}}}' > "$T/Packages/packages-lock.json"
python3 scripts/checks/unity-package-pins.py "$T" >/dev/null && ok "package-pins: agreeing pins pass" || bad "package-pins: agreeing pins pass"
echo '{"dependencies":{"a":{"version":"https://x/a.git#v0"}}}' > "$T/Packages/packages-lock.json"
python3 scripts/checks/unity-package-pins.py "$T" >/dev/null && bad "package-pins: mismatch must fail" || ok "package-pins: mismatch fails"
echo '{"dependencies":{"a":"file:/mnt/c/x"}}' > "$T/Packages/manifest.json"
python3 scripts/checks/unity-package-pins.py "$T" >/dev/null && bad "package-pins: file: must fail" || ok "package-pins: file: path fails"
echo '{"dependencies":{"b":"1.0.0"}}' > "$T/Packages/manifest.json"
python3 scripts/checks/unity-package-pins.py "$T" >/dev/null && bad "package-pins: empty selection must fail" || ok "package-pins: zero git deps fails"
rm -rf "$T"

# ---- Claude Code's own validator
if $use_claude && command -v claude >/dev/null 2>&1; then
  run "claude plugin validate --strict . (marketplace)" claude plugin validate --strict .
  run "claude plugin validate --strict .claude-plugin/plugin.json (plugin + skills)" claude plugin validate --strict .claude-plugin/plugin.json
else
  skp "claude plugin validate" "claude CLI unavailable or --no-claude"
fi

total=$((pass + fail + skip))
echo "----"
echo "run-all: $total checks, $pass passed, $fail failed, $skip skipped"
[ "$pass" -gt 0 ] && [ "$fail" -eq 0 ]
