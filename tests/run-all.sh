#!/usr/bin/env bash
# run-all.sh — every local validation for the plugin. Read-only against the workspace.
# Prints one line per check and a final count; exits non-zero if anything failed.
#
# Usage: tests/run-all.sh [--no-workspace] [--no-claude] [--release]
#   --release       the installed plugin must equal the source (install-status CURRENT), the source
#                   must be committed, and tests/installed-safety.sh must pass against the installed hooks
#   --no-workspace  skip checks that need the RPG MMO workspace on disk
#   --no-claude     skip `claude plugin validate`
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
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
for f in scripts/*.py scripts/checks/*.py scripts/lib/*.py testlab/*.py testlab/lab/*.py testlab/tests/*.py; do run "py_compile: $f" python3 -B -W error::SyntaxWarning -c "import ast,sys; ast.parse(open(sys.argv[1], encoding='utf-8').read(), sys.argv[1])" "$f"; done
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
ver=$(jq -r .version .claude-plugin/plugin.json); mver=$(jq -r '.plugins[0].version // empty' .claude-plugin/marketplace.json)
fver=$(tr -d '[:space:]' < VERSION 2>/dev/null)
rver=$(sed -n 's/^Version \([0-9][0-9.]*\) (see `VERSION`).*/\1/p' README.md)
{ [ "$ver" = "$fver" ] && [ -z "$mver" -o "$mver" = "$ver" ] && grep -q "^## \[$ver\]" CHANGELOG.md && [ "$rver" = "$ver" ]; } \
  && ok "version: VERSION == plugin.json == marketplace == CHANGELOG section == README ($ver)" \
  || bad "version consistency" "VERSION=$fver plugin=$ver marketplace=$mver README=${rver:-none} changelog section missing?"
# release policy wording: tags and releases are the lead's by default and the agent's only with explicit release
# authorization in the current task - no authoritative text may state the absolute "agents never tag" rule again
policy_files=(.claude/CLAUDE.md README.md registry.json skills/factory-core/SKILL.md skills/factory-core/references/git-safety.md
              skills/factory-core/references/skill-contract.md skills/unity-package/SKILL.md scripts/git-guard.py scripts/lib/context.py
              .claude-plugin/plugin.json .claude-plugin/marketplace.json)
absolute=$(grep -nE -i "agents never tag|never create the tag|tags are never (done|created) by agents|never tag, never publish|; never tag\b" "${policy_files[@]}" 2>/dev/null)
missing=$(for f in .claude/CLAUDE.md README.md registry.json skills/factory-core/references/git-safety.md skills/factory-core/references/skill-contract.md skills/unity-package/SKILL.md; do
  grep -qiE "explicit(ly)? (release authorization|authoriz)" "$f" || echo "$f"; done)
[ -z "$absolute$missing" ] && ok "release policy: default READY_TO_TAG, tag/release only with explicit authorization (${#policy_files[@]} files)" \
  || bad "release policy wording" "absolute 'never tag' text: ${absolute:-none}; no authorization rule in: ${missing:-none}"
# since 1.0.3 the hooks are advisory only: agent-facing text must not claim they deny, block or enforce
advisory_files=(.claude/CLAUDE.md README.md scripts/lib/context.py scripts/factory-context.sh commands/*.md skills/*/SKILL.md skills/*/references/*.md)
blocking=$(grep -nE -i "denied by the guard|hooks enforce|\(deny\)|enforced by (both|the) (guards?|hooks)" "${advisory_files[@]}" 2>/dev/null)
[ -z "$blocking" ] && ok "advisory wording: no 'denied by the guard' / 'hooks enforce' / '(deny)' in agent-facing text (${#advisory_files[@]} files)" \
  || bad "advisory wording (hooks never block since 1.0.3)" "$blocking"
[ -f "skills/factory-core/SKILL.md" ] && head -5 skills/factory-core/SKILL.md | grep -q '^name: factory-core$' \
  && ok "skill: factory-core frontmatter name" || bad "skill: factory-core frontmatter name"
for ref in $(grep -o 'references/[a-z-]*\.md' skills/factory-core/SKILL.md | sort -u); do
  [ -f "skills/factory-core/$ref" ] && ok "skill reference exists: $ref" || bad "skill reference missing: $ref"
done
jq -e '(.hooks.PreToolUse[0].matcher == "Bash|PowerShell")
        and ([.hooks.PreToolUse[0].hooks[].command] | any(test("git-guard.py")))
        and ([.hooks.PreToolUse[] | select(.matcher == "Skill") | .hooks[].command] | any(test("factory_session.py\" --skill")))
        and ([.hooks.SessionStart[0].hooks[].command] | any(test("install-status.py\" --session")))
        and ([.. | .command? // empty] | all(test("tripwire") | not))
        and ([.. | .command? // empty] | length >= 4 and all(endswith("; exit 0")))' hooks/hooks.json >/dev/null \
  && ok "hooks: guard on Bash|PowerShell, skill order on Skill, session install check, no tripwire, every command fail-safe (; exit 0)" || bad "hooks wiring"
# exit 2 is Claude Code's blocking code (python exits 2 on a missing script): a missing or crashing hook script
# must exit 0 and its stdout must still reach Claude Code
HT=$(mktemp_win); mkdir -p "$HT/missing/scripts" "$HT/broken/scripts"
for f in $(jq -r '[.. | .command? // empty | capture("scripts/(?<f>[a-z_-]+\\.py)").f] | unique[]' hooks/hooks.json); do
  printf 'import sys\nprint("{\\"marker\\": \\"%s\\"}")\nsys.exit(2)\n' "$f" > "$HT/broken/scripts/$f"
done
hfail=""
while IFS= read -r h; do
  out=$(CLAUDE_PLUGIN_ROOT="$HT/missing" bash -c "$h" </dev/null 2>/dev/null); rc=$?
  [ $rc -eq 0 ] && [ -z "$out" ] || hfail+="missing script rc=$rc: $h"$'\n'
  out=$(CLAUDE_PLUGIN_ROOT="$HT/broken" bash -c "$h" </dev/null 2>/dev/null); rc=$?
  [ $rc -eq 0 ] && grep -q '"marker"' <<<"$out" || hfail+="exit-2 script rc=$rc stdout='$out': $h"$'\n'
done < <(jq -r '.. | .command? // empty' hooks/hooks.json)
rm -rf "$HT"
[ -z "$hfail" ] && ok "hooks: a missing or exit-2 script never blocks (exit 0, stdout passes through)" || bad "hooks fail-safe" "$hfail"

# ---- testlab (pure parts: scenarios, plan expansion, analysis checks; no stack, no Unity)
run "testlab: unit tests" python3 -B testlab/tests/test_lab.py
run "testlab: scenarios load" python3 -B testlab/testlab.py list
find testlab -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null

# ---- registry
run "registry structure" scripts/check-registry.sh --structure-only
if $use_ws; then run "registry paths exist in workspace" scripts/check-registry.sh
else skp "registry paths exist in workspace" "--no-workspace"; fi

# ---- git guard, skill contract lint, routing (task + historical replay)
run "cross-platform helpers + UTF-8 output (Linux, WSL, Windows git-bash)" env -u TMPDIR tests/compat.test.sh
run "git-guard unit tests" tests/git-guard.test.sh
run "skills lint (contract)" tests/skills-lint.sh
run "session state + tripwire removed (state paths, stale latch files inert)" env -u TMPDIR tests/session-state.test.sh
run "file guard (Write/Edit/MultiEdit/NotebookEdit/Read)" env -u TMPDIR tests/file-guard.test.sh
run "slash commands (files, parsing, invocation)" env -u TMPDIR tests/commands.test.sh
run "dev tools + services (probes, snapshot, doctor, no secrets, registry checks)" env -u TMPDIR tests/devtools.test.sh
run "worktree-aware context" tests/worktree.test.sh
run "check runner state model" tests/run-checks.test.sh
run "factory-status rollout / resume fixture" tests/factory-status.test.sh
run "install-status stale-install detection" tests/install-status.test.sh
run "release-check gate (throwaway repo, local bare origin)" env -u TMPDIR tests/release-check.test.sh
if $use_ws; then run "routing properties over real history" python3 -B tests/routing-properties.test.py
else skp "routing properties over real history" "--no-workspace"; fi
if $use_ws; then run "registry facts re-probed in the repos" tests/facts.test.sh
else skp "registry facts re-probed in the repos" "--no-workspace"; fi
run "skill citation checker (fixture repos)" env -u TMPDIR tests/skill-citations.test.sh
run "netcode-headless server resolution (fixture repos)" env -u TMPDIR tests/netcode-headless.test.sh
run "skill scaffolder + touchpoints (throwaway plugin copy)" env -u TMPDIR tests/new-skill.test.sh
run "parallel-work policy lint bites (throwaway plugin copy)" env -u TMPDIR tests/parallel-policy.test.sh
if ! $use_ws; then skp "orca commands cited in parallel-work.md" "--no-workspace"
elif ! command -v orca >/dev/null 2>&1; then skp "orca commands cited in parallel-work.md" "orca not on PATH"
else run "orca commands cited in parallel-work.md exist in orca --help" tests/orca-commands.test.sh; fi
if $use_ws; then run "skill line citations point at their symbols (integration branches)" python3 -B scripts/checks/skill-citations.py
else skp "skill line citations against the repos" "--no-workspace"; fi
if $use_ws; then run "routing + history replay" tests/routing.test.sh
else
  # task scenarios resolve --paths only, but factory-context still needs the workspace markers and a git
  # work tree per registry repo: a throwaway stand-in (empty repos), never the real workspace
  SW=$(mktemp_win)
  while IFS= read -r p; do
    git init -q "$SW/$p" && git -C "$SW/$p" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
  done < <(jq -r '.repos[].path' registry.json)
  while IFS= read -r m; do mkdir -p "$SW/$(dirname "$m")"; touch "$SW/$m"; done < <(jq -r '.workspace.root_markers[]' registry.json)
  run "routing (task scenarios only, stand-in workspace)" env RPG_FACTORY_WORKSPACE="$SW" tests/routing.test.sh --no-history
  rm -rf "$SW"
fi

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

# ---- sgl-determinism (ADR-10) against fixtures: banned calls fail, comments/strings/allowed MathF pass
dt=$(mktemp_win)
printf '%s\n' 'class A {' '  float F(float x) => MathF.Sqrt(x) + MathF.Abs(x); // MathF.Sin(x) in a comment' \
  '  string S = "Math.Pow(1, 2)";' '}' > "$dt/Ok.cs"
out=$(python3 -B scripts/checks/sgl-determinism.py "$dt" 2>&1); rc=$?
[ $rc -eq 0 ] && grep -q "^OK: sgl-determinism files=1 banned=0" <<<"$out" \
  && ok "sgl-determinism: allowed MathF, comments and strings pass" || bad "sgl-determinism allowed fixture" "$out"
printf '%s\n' 'class B {' '  float G(float x) => MathF.Atan2(x, 1f);' '  double H(double y) => System.Math.Pow(y, 2);' '}' > "$dt/Bad.cs"
out=$(python3 -B scripts/checks/sgl-determinism.py "$dt" 2>&1); rc=$?
[ $rc -eq 1 ] && grep -q "Bad.cs:2: MathF.Atan2" <<<"$out" && grep -q "Bad.cs:3: Math.Pow" <<<"$out" \
  && ok "sgl-determinism: banned calls fail with path:line" || bad "sgl-determinism banned fixture" "$out"
rm -f "$dt"/*.cs
python3 -B scripts/checks/sgl-determinism.py "$dt" >/dev/null 2>&1; [ $? -eq 2 ] \
  && ok "sgl-determinism: empty directory is an error, not a pass" || bad "sgl-determinism empty dir"
rm -rf "$dt"

# ---- Factory check scripts against the live workspace (read-only)
if $use_ws; then
  run "sgl-determinism on Shared.GameLogic" python3 -B scripts/checks/sgl-determinism.py \
    "${RPG_FACTORY_WORKSPACE:-/mnt/c/Workspaces/UnityIndie}/rpg-mmo-server/backend/gameserver-dotnet/Shared.GameLogic"
  # pin-status reads the client's working tree. When the user has uncommitted pin files (the local file:
  # toggle is a human gate and their state), a live FAIL says nothing about this plugin: then verify the
  # committed HEAD through a read-only export and report SKIP with the reason - never PASS.
  wsr="${RPG_FACTORY_WORKSPACE:-/mnt/c/Workspaces/UnityIndie}"; cl="$wsr/IndieRPGMMOAdventure"
  pin_files=(Packages/manifest.json Packages/packages-lock.json "Assets/Samples/Netcode/DOTS Sample/.sample-source")
  if out=$(python3 -B scripts/checks/pin-status.py 2>&1); then ok "pin-status (client pins vs upstream tags)"
  elif [ -n "$(git -C "$cl" status --porcelain -- "${pin_files[@]}" 2>/dev/null)" ]; then
    ph=$(mktemp_win); mkdir -p "$ph/ws/IndieRPGMMOAdventure"
    git -C "$cl" archive HEAD -- "${pin_files[@]}" | tar -x -C "$ph/ws/IndieRPGMMOAdventure"
    for r in Netcode UnityDots UIToolkit rpg-mmo-server; do
      [ -d "$wsr/$r/.git" ] && git clone -q --shared --no-checkout "$wsr/$r" "$ph/ws/$r"; done
    if hout=$(python3 -B scripts/checks/pin-status.py --workspace "$ph/ws" 2>&1); then
      skp "pin-status on the live tree" "client pin files have uncommitted user changes; committed HEAD: $(tail -1 <<<"$hout")"
    else bad "pin-status (committed HEAD, live tree also has user changes)" "$hout"; fi
    rm -rf "$ph"
  else bad "pin-status (client pins vs upstream tags)" "$out"; fi
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
  [ -z "$(git status --porcelain)" ] && ok "source is committed (release gate)" || bad "source is committed (release gate)" "uncommitted changes"
  run "safety through the installed hooks (disposable workspace)" env -u TMPDIR tests/installed-safety.sh
else
  skp "installed plugin == source" "install state $ist; required only with --release"
fi

# ---- package pins checker behaviour
T=$(mktemp_win); mkdir -p "$T/Packages"
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

# ---- package-ready: when git cannot read the tree, readiness is unknown (exit 2), never READY
T=$(mktemp_win)
printf '{"name":"com.cuvara.netcode","version":"9.9.9"}\n' > "$T/package.json"; printf '## [9.9.9] - 2026-01-01\n' > "$T/CHANGELOG.md"
out=$(GIT_CEILING_DIRECTORIES="$T" python3 -B scripts/checks/package-ready.py "$T" 2>&1); rc=$?
[ $rc -eq 2 ] && grep -q "readiness unknown" <<<"$out" && ! grep -q "READY to tag" <<<"$out" \
  && ok "package-ready: unreadable git tree is an error, not READY" || bad "package-ready on a non-repo (rc=$rc)" "$out"
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
