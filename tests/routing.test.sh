#!/usr/bin/env bash
# Routing regression tests: does Factory Core pick the right specialised skill, contracts,
# cross-repo follow-ups and human gates?
#
#  - "task" scenarios: the files a typical request would touch, resolved with --paths.
#  - "history" scenarios: REAL commits from the workspace repos, replayed read-only
#    (`git show --name-only` -> --paths). They prove Factory would have routed work that
#    actually happened. Skipped (not failed) when a repo or commit is absent.
#
# Usage: tests/routing.test.sh [--no-history]
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
WS="${RPG_FACTORY_WORKSPACE:-/mnt/c/Workspaces/UnityIndie}"
CTX="$ROOT/scripts/factory-context.sh"
history=true; [ "${1:-}" = "--no-history" ] && history=false
pass=0; fail=0; skip=0

# assert <name> <repo> <jq-predicate over .repos[0]> <paths...>
assert() {
  local name="$1" repo="$2" pred="$3"; shift 3
  local out
  out=$(bash "$CTX" --repo "$repo" --json --paths "$@" 2>&1)
  # ROUTING_GOLDEN_OUT=<file>: also record the routing contract of this scenario (tests/routing-golden.test.sh)
  if [ -n "${ROUTING_GOLDEN_OUT:-}" ]; then
    jq -c --arg name "$name" --arg repo "$repo" '.repos[0] | {name: $name, repo: $repo,
        routing: (.routing | {lead, co_leads, legs, follow_ups, tech, ambiguous}),
        touched, checks: [.checks[].id]}' <<<"$out" >> "$ROUTING_GOLDEN_OUT" 2>/dev/null       || printf '{"name":%s,"error":true}
' "$(jq -Rn --arg n "$name" '$n')" >> "$ROUTING_GOLDEN_OUT"
  fi
  if jq -e ".repos[0] | $pred" <<<"$out" >/dev/null 2>&1; then
    pass=$((pass + 1)); echo "PASS  $name"
  else
    fail=$((fail + 1)); echo "FAIL  $name"
    jq -c '.repos[0] | {touched, skills: [.suggested_skills[] | "\(.role):\(.skill)"], contracts: [.contracts[].id], gates: [.gates[].gate], unmapped}' <<<"$out" 2>/dev/null | sed 's/^/      /' || echo "      $out" | head -3
  fi
}
lead()     { echo "any(.suggested_skills[]; .role == \"lead\" and .skill == \"$1\")"; }
leg()      { echo "any(.suggested_skills[]; .role == \"leg\" and .skill == \"$1\")"; }
followup() { echo "any(.suggested_skills[]; .role == \"follow-up\" and .skill == \"$1\")"; }
contract() { echo "any(.contracts[]; .id == \"$1\")"; }
gate()     { echo "any(.gates[]; .gate == \"$1\")"; }
nolead()   { echo "(any(.suggested_skills[]; .role == \"lead\" and .skill == \"$1\") | not)"; }
tech()     { echo "(.routing.tech | index(\"$1\"))"; }
notech()   { echo "(.routing.tech | index(\"$1\") | not)"; }

# history <name> <repo-key> <repo-dir> <sha> <predicate>
history() {
  local name="$1" key="$2" dir="$WS/$3" sha="$4" pred="$5" files
  if ! $history; then skip=$((skip + 1)); echo "SKIP  $name (--no-history)"; return; fi
  if ! git -C "$dir" cat-file -e "$sha^{commit}" 2>/dev/null; then
    skip=$((skip + 1)); echo "SKIP  $name ($3@$sha not available)"; return
  fi
  mapfile -t files < <(git -C "$dir" show --name-only --format= "$sha" | sed '/^$/d')
  assert "history $3@$sha: $name" "$key" "$pred" "${files[@]}"
}

echo "== task scenarios"
assert "tick-rate knob -> server-realtime leads, server-ops leg, server-knobs contract" server \
  "$(lead server-realtime) and $(leg server-ops) and $(contract server-knobs)" \
  backend/gameserver-dotnet/GameServer/ServerEnv.cs backend/gameserver-dotnet/GameServer/Server/ServerDefaults.cs \
  backend/gameserver-dotnet/GameServer/Observability/GameMetrics.cs backend/gameserver-dotnet/docs/METRICS.md
assert "wire field -> wire-contract leads; server legs; Netcode + client follow-ups; tag gate" server \
  "$(lead wire-contract) and $(leg server-realtime) and $(leg server-services) and $(followup unity-package) and $(followup pin-bump) and $(contract wire-generated) and $(gate tag) and (.cross_repo_dependents | map(.repo) | index(\"netcode\"))" \
  backend/shared/proto/wire.proto
assert "replication/snapshot code -> server-realtime, no contract" server \
  "$(lead server-realtime) and (.contracts | length == 0)" backend/gameserver-dotnet/GameServer/Snapshot/SnapshotEncoder.cs backend/gameserver-dotnet/GameServer.Tests/Snapshot/SnapshotPipelineTests.cs
assert "Redis servers:id -> wire-contract leads" server "$(lead wire-contract) and $(contract redis-server-registry)" \
  backend/gameserver-dotnet/GameServer/Registry/RedisServerRegistry.cs
assert "Netcode transport fix -> unity-package leads, not wire-contract" netcode \
  "$(lead unity-package) and $(nolead wire-contract) and (.contracts | length == 0)" Runtime/Transport/TcpTransport.cs
assert "Netcode Wire.cs copy -> wire-contract leads, unity-package leg" netcode \
  "$(lead wire-contract) and $(leg unity-package) and $(contract wire-generated)" Runtime/Protocol/Generated/Wire.cs
assert "Nakama session flow in client -> client-integration" client \
  "$(lead client-integration) and (.contracts | length == 0)" Assets/Scripts/Session/MainSessionFlow.cs Assets/Scripts/Nakama/NakamaSessionService.cs
assert "move client to Netcode vX -> pin-bump leads; tag gate" client \
  "$(lead pin-bump) and $(contract package-pins) and $(gate tag)" Packages/manifest.json Packages/packages-lock.json
assert "repo-prefixed path routes like repo-relative" server "(.routing.lead == \"server-ops\")" rpg-mmo-server/backend/deploy/k8s/app/40-gateway.yaml
assert "comma-joined paths are split" server "(.routing.lead == \"server-services\") and ([.files[].path] | length == 2)" "backend/gateway/server/server.go,backend/nakama/main.go"
# absolute and glob --paths: repo-relative forward-slash files on every platform (Windows relpath gave backslashes)
sdir=$(bash "$CTX" --repo server --json --paths backend/docs/BENCHMARK.md 2>/dev/null | jq -r '.repos[0].path // empty')
if [ -n "$sdir" ]; then
  fwd="${sdir//\\//}"
  wirefiles='([.files[].path] == ["backend/shared/proto/wire.proto"])'
  assert "absolute path (native form) routes like repo-relative" server "$(lead wire-contract) and $wirefiles" "$sdir/backend/shared/proto/wire.proto"
  assert "absolute path (forward slashes) routes like repo-relative" server "$(lead wire-contract) and $wirefiles" "$fwd/backend/shared/proto/wire.proto"
  assert "absolute path (backslashes) routes like repo-relative" server "$(lead wire-contract) and $wirefiles" "${fwd//\//\\}\\backend\\shared\\proto\\wire.proto"
  if command -v cygpath >/dev/null 2>&1; then
    assert "absolute path (git-bash /c/ form) routes like repo-relative" server "$(lead wire-contract) and $wirefiles" "$(cygpath -u "$fwd")/backend/shared/proto/wire.proto"
  fi
  case "$fwd" in [A-Za-z]:/*)
    drv=$(printf '%s' "${fwd:0:1}" | tr 'A-Z' 'a-z')
    assert "absolute path (WSL /mnt/c/ form) routes like repo-relative" server "$(lead wire-contract) and $wirefiles" "/mnt/$drv${fwd:2}/backend/shared/proto/wire.proto" ;;
  esac
  assert "glob path expands to repo-relative forward-slash files" server \
    "$(lead wire-contract) and ([.files[].path] | length > 0 and all(test(\"^backend/shared/proto/[^/\\\\\\\\]+\\\\.proto$\")))" './backend/shared/proto/*.proto'
else
  skip=$((skip + 1)); echo "SKIP  absolute/glob --paths (server repo not found)"
fi
assert "benchmark docs -> measure is the lead" server "(.routing.lead == \"measure\")" backend/docs/BENCHMARK.md
assert "client end of nakama-rpc names the upstream driver" client "any(.contracts[]; .id == \"nakama-rpc\" and .driver == \"server-services\")" Assets/Scripts/Nakama/Social/PartyService.cs
assert "bench harness only -> measure leads, server-realtime co-leads" server "(.routing.lead == \"measure\") and (.routing.co_leads | index(\"server-realtime\"))" backend/gameserver-dotnet/GameServer.Tests/Bench/TickAllocationBench.cs
assert "netcode measurement test -> unity-package leads, measure co-leads" netcode "(.routing.lead == \"unity-package\") and (.routing.co_leads | index(\"measure\"))" Tests/Runtime/PredictionLatencyMeasurement.cs
assert "gateway TLS/sealed manifest -> server-ops drives transport-security; client + netcode follow up" server "(.routing.lead == \"server-ops\") and $(contract transport-security) and $(followup client-integration) and $(followup unity-package)" backend/deploy/k8s/app/40-gateway.yaml
assert "client pin loader is an end of transport-security" client "$(contract transport-security) and (.routing.lead == \"client-integration\")" Assets/Scripts/DI/TransportSecurityReport.cs
# ADR-10: game rules live only in Shared.GameLogic. Every consumer of a game rule carries the rule in its snapshot.
sgl_rule() { echo "any(.obligations[]; .module == \"$1\" and any(.rules[]; test(\"Shared.GameLogic\") and test(\"ADR-10\")))"; }
assert "client game code carries the SGL-only game-rule rule" client "$(sgl_rule client.scripts)" Assets/Scripts/Session/MainSessionFlow.cs
assert "game server carries the SGL placement rule" server "$(sgl_rule server.gameserver-dotnet)" backend/gameserver-dotnet/GameServer/Program.cs
assert "Netcode runtime carries the SGL-only game-rule rule" netcode "$(sgl_rule netcode.runtime)" Runtime/Client/NetworkClient.cs
assert "UnityDots runtime carries the SGL-only game-rule rule" unitydots "$(sgl_rule unitydots.runtime)" Runtime/Simulation/SimConstants.cs
assert "wire change: cross-repo dependents add only their PRIMARY owner as follow-up (no measure noise)" server "$(followup unity-package) and ($(followup measure) | not)" backend/shared/proto/wire.proto
assert "submodule gitlink bump -> pin-bump is the primary lead" client "(.routing.lead == \"pin-bump\") and (.routing.ambiguous | not)" unity-build-workflows
assert "DOTS Sample recopy -> pin-bump" client "$(lead pin-bump)" "Assets/Samples/Netcode/DOTS Sample/DOTSNetworkBridge.cs"
assert "k8s deployment -> server-ops; shared-infra gate" server \
  "$(lead server-ops) and $(gate shared-infra) and $(nolead server-realtime)" backend/deploy/k8s/app/40-gateway.yaml
assert "monitoring alert -> server-ops" server "$(lead server-ops)" backend/deploy/monitoring/alerts.yaml
assert "replication throughput measurement -> measure" server \
  "$(lead measure)" backend/loadtest/scripts/bench.sh backend/docs/BENCHMARK.md
assert "new Nakama RPC -> server-services" server "$(lead server-services)" backend/nakama/main.go backend/nakama/social/party.go
assert "gateway JoinToken claims -> wire-contract leads (join-token), server-services leg" server \
  "$(lead wire-contract) and $(leg server-services) and $(contract join-token)" backend/gateway/transfer/join_token.go
assert "gateway allocator internals -> server-services, no contract" server \
  "$(lead server-services) and (.contracts | length == 0)" backend/gateway/registry/allocator.go
assert "Nakama party RPC payload -> server-services leads (nakama-rpc), client follow-up" server \
  "$(lead server-services) and $(contract nakama-rpc) and $(followup client-integration)" backend/nakama/main.go
assert "new migration -> server-services; gamestate-migrations contract" server \
  "$(lead server-services) and $(contract gamestate-migrations)" backend/gameserver-dotnet/GameServer/Persistence/Migrations/002_new.sql
assert "Shared.GameLogic system -> server-realtime; client pin follow-up" server \
  "$(lead server-realtime) and $(followup pin-bump)" backend/gameserver-dotnet/Shared.GameLogic/Systems/MovementLogic.cs
assert "UnityDots runtime behaviour -> unity-package" unitydots "$(lead unity-package)" Runtime/Simulation/SimulationGroups.cs
assert "UIToolkit screen flow -> unity-package" uitoolkit "$(lead unity-package)" Runtime/Flow/ScreenNavigator.cs
assert "UIToolkit codegen core -> unity-package, generated files noted" uitoolkit "$(lead unity-package)" Editor/Codegen/Core/UxmlParser.cs
assert "client HUD -> client-integration" client "$(lead client-integration)" Assets/Scripts/UI/Hud/HudView.uxml
assert "client build config -> client-integration" client "$(lead client-integration)" BuildConfig/production.json
assert "content items.json -> server-realtime; gameplay gate" server \
  "$(lead server-realtime) and $(gate gameplay-rules)" backend/content/items.json
assert "docs-only ADR edit -> no specialised lead" server "(.suggested_skills | length == 0)" backend/docs/ARCHITECTURE-DECISIONS.md

assert "SGL change -> server-realtime leads, tech dotnet-gameserver listed, never routed" server \
  "$(lead server-realtime) and $(tech dotnet-gameserver) and $(notech go-backend) and (any(.suggested_skills[]; .skill == \"dotnet-gameserver\") | not)" \
  backend/gameserver-dotnet/Shared.GameLogic/Shared.GameLogic.csproj
assert "gateway change -> tech go-backend, not dotnet-gameserver" server \
  "$(lead server-services) and $(tech go-backend) and $(notech dotnet-gameserver)" backend/gateway/server/server.go
assert "wire field -> both server tech skills (wire-contract uses both)" server \
  "$(lead wire-contract) and $(tech dotnet-gameserver) and $(tech go-backend)" backend/shared/proto/wire.proto
assert "client HUD ECS code -> tech unity-client-tech" client \
  "$(lead client-integration) and $(tech unity-client-tech) and $(notech dotnet-gameserver)" Assets/Scripts/UI/Hud/Ecs/HudEcsBootstrap.cs
assert "Netcode package code -> tech unity-client-tech via unity-package" netcode \
  "$(lead unity-package) and $(tech unity-client-tech)" Runtime/Transport/ITransport.cs
assert "sample build scripts -> client.buildscripts with build gates" client \
  "$(lead client-integration) and (.touched == [\"client.buildscripts\"]) and $(gate unity-batch)" Assets/_SampleBuild/Editor/SampleBuilder.cs
assert "UnityDots simulation system -> tech unity-dots (and unity-client-tech), unity-package leads" unitydots   "$(lead unity-package) and $(tech unity-dots) and $(tech unity-client-tech) and $(notech dotnet-gameserver)" Runtime/Simulation/TimeToLiveSystem.cs
assert "Netcode prediction code -> tech netcode-client, unity-package leads" netcode   "$(lead unity-package) and $(tech netcode-client)" Runtime/Prediction/LocalMovePredictor.cs
assert "client ECS bridge code -> tech unity-dots and netcode-client via client-integration" client   "$(lead client-integration) and $(tech unity-dots) and $(tech netcode-client)" Assets/Scripts/DI/Dots/DotsWorldBridge.cs
assert "wire field in server repo -> no client tech skill (the Netcode leg gets it in its repo)" server   "$(lead wire-contract) and $(notech netcode-client) and $(notech unity-dots)" backend/shared/proto/wire.proto
assert "server loadtest (measure) -> server tech only, no Unity tech skill" server   "$(lead measure) and $(tech dotnet-gameserver) and $(notech unity-dots) and $(notech netcode-client)" backend/loadtest/cmd/loadtest/main.go
assert "client measurement tools (measure) -> Unity tech, not dotnet-gameserver" client   "$(lead measure) and $(tech unity-dots) and $(notech dotnet-gameserver)" Tools/run-clients.sh
assert "server tick change -> no Unity tech skill" server   "$(lead server-realtime) and $(notech unity-dots) and $(notech netcode-client)" backend/gameserver-dotnet/GameServer/Server/TickLoop.cs
assert "deploy-only change -> no tech skill" server \
  "$(lead server-ops) and (.routing.legs == []) and (.routing.tech == [])" backend/deploy/monitoring/prometheus.yaml

# a tech skill can never be forced into ownership, and --explain names it as supporting context
for t in $(jq -r '.skills | to_entries[] | select(.value.kind == "tech") | .key' "$ROOT/registry.json"); do
  if bash "$CTX" --repo server --paths backend/gameserver-dotnet/GameServer/Server/TickLoop.cs --lead "$t" >/dev/null 2>&1; then
    fail=$((fail + 1)); echo "FAIL  --lead $t accepted (tech skills are never lead)"
  else pass=$((pass + 1)); echo "PASS  --lead $t rejected (tech skills are never lead)"; fi
done
out=$(bash "$CTX" --repo server --explain --paths backend/gameserver-dotnet/GameServer/Server/TickLoop.cs 2>&1)
if grep -q '^- dotnet-gameserver: tech (supporting) - .*(server-realtime)' <<<"$out" && grep -q '^- go-backend: not selected - tech skill: none of its users' <<<"$out"; then
  pass=$((pass + 1)); echo "PASS  --explain marks tech skills as supporting / unused"
else fail=$((fail + 1)); echo "FAIL  --explain tech rows: $(grep -E '^- (dotnet-gameserver|go-backend):' <<<"$out")"; fi

echo "== task scope (throwaway fixture workspace)"
. "$ROOT/scripts/lib/compat.sh"
FX="$(mktemp_win)" && [ -d "$FX" ] && trap 'rm -rf "$FX"' EXIT
FW="$FX/ws"; FS="$FW/rpg-mmo-server"; FC="$FW/IndieRPGMMOAdventure"
fgc() { git -C "$1" -c user.email=t@t -c user.name=t "${@:2}"; }
mkdir -p "$FS/backend/gateway/server" "$FS/backend/shared/proto" "$FC/ProjectSettings"
touch "$FS/backend/TEAM.md" "$FS/backend/gateway/server/server.go" "$FS/backend/shared/proto/wire.proto" "$FC/ProjectSettings/ProjectVersion.txt"
for r in "$FS" "$FC"; do git -C "$r" init -q -b develop; fgc "$r" add -A; fgc "$r" commit -qm init; done
echo "// user edit" >> "$FS/backend/gateway/server/server.go"           # pre-existing user change = baseline
fctx() { (cd "$1" && RPG_FACTORY_WORKSPACE="$FW" bash "$CTX" "${@:2}" 2>&1); }
fexpect() { if eval "$2"; then pass=$((pass + 1)); echo "PASS  $1"; else fail=$((fail + 1)); echo "FAIL  $1"; head -c 600 <<<"$out" | sed 's/^/      /'; fi; }
out=$(fctx "$FS")
fexpect "dirty tree, no --paths: baseline listed with modules, not routed" \
  'grep -q "server.go\` -> server.gateway" <<<"$out" && grep -q "Baseline only - not routed" <<<"$out" && grep -q -- "--paths <files the task will write>" <<<"$out"'
fexpect "dirty tree, no --paths: no Routing lead, no Next, no gates, no checks" \
  '! grep -qE "\*\*Routing\*\*|\*\*Next:\*\*|Gates for this change|^Validation" <<<"$out"'
out=$(fctx "$FS" --json)
fexpect "dirty tree, no --paths: JSON task_scope is baseline (full resolution kept for run-checks)" \
  'jq -e ".repos[0].task_scope == {scope: \"baseline\", lead: null, baseline_paths: [\"backend/gateway/server/server.go\"]} and .repos[0].routing.lead == \"server-services\"" <<<"$out" >/dev/null'
out=$(fctx "$FS" --paths backend/gateway/server/server.go)
fexpect "dirty tree, with --paths: routed as before (lead + Next)" \
  'grep -q "\*\*Routing\*\* lead \`rpg-factory:server-services\`" <<<"$out" && grep -q "\*\*Next:\*\* invoke the Skill tool with \`rpg-factory:server-services\`" <<<"$out" && ! grep -q "Baseline only" <<<"$out"'
fgc "$FS" worktree add -q "$FX/elsewhere/srv-wt" -b feat/wire/x
echo "message X {}" >> "$FX/elsewhere/srv-wt/backend/shared/proto/wire.proto"; fgc "$FX/elsewhere/srv-wt" commit -qam "wire"
echo "// wt user edit" >> "$FX/elsewhere/srv-wt/backend/gateway/server/server.go"
out=$(fctx "$FX/elsewhere/srv-wt")
fexpect "feature branch, no --paths: commits routed, uncommitted paths stay baseline" \
  'grep -q "\*\*Routing\*\* lead \`rpg-factory:wire-contract\`" <<<"$out" && grep -q "covers only the 1 path(s) committed on this branch" <<<"$out" && ! grep -q "lead \`rpg-factory:server-services\`" <<<"$out"'
out=$(fctx "$FW" --repo server --paths backend/docs/ARCHITECTURE-DECISIONS.md)
fexpect "module without skills: explicit no-lead fallback line" \
  'grep -q "\*\*Routing\*\* no specialised lead - factory-core only; follow \`rpg-mmo-server/CLAUDE.md\`" <<<"$out" && ! grep -q "\*\*Next:\*\*" <<<"$out"'
out=$(fctx "$FW" --repo server --json --paths "$FX/elsewhere/srv-wt/backend/shared/proto/wire.proto")
fexpect "absolute path in a linked worktree elsewhere -> repo-relative, server.proto, wire-contract" \
  'jq -e "([.repos[0].files[] | .path + \"=\" + .module] == [\"backend/shared/proto/wire.proto=server.proto\"]) and .repos[0].routing.lead == \"wire-contract\"" <<<"$out" >/dev/null'
out=$(fctx "$FC" --json --paths "$FS/backend/shared/proto/wire.proto" ProjectSettings/ProjectVersion.txt)
fexpect "absolute path in another registry repo -> rejected with a warning, never client.root" \
  'jq -e "(.repos[0].rejected_paths | length == 1 and .[0].repo == \"server\") and ([.repos[0].files[].path] == [\"ProjectSettings/ProjectVersion.txt\"])" <<<"$out" >/dev/null'
out=$(fctx "$FC" --paths "$FS/backend/shared/proto/wire.proto" ProjectSettings/ProjectVersion.txt)
fexpect "cross-repo absolute path: warning line in the snapshot" 'grep -q "\*\*Warning: not routed\*\* .*in repo server: use --repo server" <<<"$out"'
out=$(fctx "$FC" --paths "$FX/nowhere/x.cs"); rc=$?
fexpect "only paths outside every repo -> exit 2, nothing routed" '[ $rc -eq 2 ] && grep -q "no path left to route" <<<"$out"'
out=$(fctx "$FW" --repo server --json --paths backend/gateway/server/server.go --mode=plan)
fexpect "--paths a --mode=plan: the flag ends the path list" \
  'jq -e ".mode == \"plan\" and ([.repos[0].files[].path] == [\"backend/gateway/server/server.go\"])" <<<"$out" >/dev/null'
out=$(fctx "$FW" --repo server --json --paths backend/gateway/server/server.go --lead=server-services)
fexpect "--paths a --lead=x: --flag=value ends the path list and applies" \
  'jq -e "([.repos[0].files[].path] == [\"backend/gateway/server/server.go\"]) and .repos[0].routing.override" <<<"$out" >/dev/null'

echo "== history (real commits, replayed read-only)"
history "action_seq wire change"              server rpg-mmo-server       2b1418c "$(lead wire-contract) and $(leg server-realtime)"
history "Netcode Wire.cs resync (649f078)"    netcode Netcode              649f078 "$(lead wire-contract)"
history "netcode v0.45.0 pin + DOTS recopy"   client IndieRPGMMOAdventure  17b7737 "$(lead pin-bump) and $(contract package-pins)"
history "tiering gauge + METRICS + bench"     server rpg-mmo-server       4647b44 "$(lead server-realtime) and $(lead measure)"
history "fleet knobs gated (deploy+knobs)"    server rpg-mmo-server       3b0211d "$(lead server-realtime) and $(leg server-ops) and $(contract server-knobs)"
history "re-baseline v1.1"                    server rpg-mmo-server       a154f18 "$(lead measure)"
history "measurement write-up"                server rpg-mmo-server       d314b94 "$(lead measure)"
history "Nakama party RPCs"                   server rpg-mmo-server       ee1240c "$(lead server-services)"
history "gateway party_get classification"    server rpg-mmo-server       fae2761 "$(lead server-services)"
history "Nakama TLS pinning in client"        client IndieRPGMMOAdventure  a949b42 "$(lead client-integration) and $(nolead pin-bump)"
history "Netcode TCP transport cancellation"  netcode Netcode              c38c763 "$(lead unity-package) and $(nolead wire-contract)"
history "UnityDots entity pose / events"      unitydots UnityDots          77f671c "$(lead unity-package)"
history "UIToolkit SettingsModel fix"         uitoolkit UIToolkit          24161a2 "$(lead unity-package)"
history "meta-hop TLS broke dungeon entry"      server rpg-mmo-server       ed090ab "$(contract transport-security)"
history "verify pinned the wrong cluster cert"   server rpg-mmo-server       437a3db "(.routing.lead == \"server-ops\") and $(contract transport-security)"
history "toolkit submodule auto-bump (#137)"  client IndieRPGMMOAdventure  285a5a2 "(.routing.lead == \"pin-bump\")"
history "toolkit v5.7.0 gitlink + CHANGELOG"  client IndieRPGMMOAdventure  525cf5b "(.routing.lead == \"pin-bump\") and $(nolead client-integration)"

total=$((pass + fail + skip))
echo "routing tests: $total run, $pass passed, $fail failed, $skip skipped"
[ "$pass" -gt 0 ] && [ "$fail" -eq 0 ]
