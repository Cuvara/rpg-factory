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
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WS="${RPG_FACTORY_WORKSPACE:-/mnt/c/Workspaces/UnityIndie}"
CTX="$ROOT/scripts/factory-context.sh"
history=true; [ "${1:-}" = "--no-history" ] && history=false
pass=0; fail=0; skip=0

# assert <name> <repo> <jq-predicate over .repos[0]> <paths...>
assert() {
  local name="$1" repo="$2" pred="$3"; shift 3
  local out
  out=$(bash "$CTX" --repo "$repo" --json --paths "$@" 2>&1)
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
history "toolkit submodule auto-bump (#137)"  client IndieRPGMMOAdventure  285a5a2 "(.routing.lead == \"pin-bump\")"
history "toolkit v5.7.0 gitlink + CHANGELOG"  client IndieRPGMMOAdventure  525cf5b "(.routing.lead == \"pin-bump\") and $(nolead client-integration)"

total=$((pass + fail + skip))
echo "routing tests: $total run, $pass passed, $fail failed, $skip skipped"
[ "$pass" -gt 0 ] && [ "$fail" -eq 0 ]
