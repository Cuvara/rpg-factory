# Game server architecture map and wiring recipes

Verified 2026-09-30 against rpg-mmo-server `develop` @ 5023a3d. Every path is relative to
`backend/gameserver-dotnet/` unless it says otherwise. Re-check a line number before you cite it.

## Map

| Folder (`GameServer/`) | Holds | Hand-off |
|---|---|---|
| `Server/` | host (`GameServer.cs`), `TickLoop`, `SystemSchedule` (+`ComponentAccess`, `IEcsSystem`), `SimulationSchedule`, `SimulationRates` (`SimulationGroup`), `ReplicationSchedule`, `AoiSettings`, `ImportanceSettings`, `ServerDefaults`, handshake/JWT/admission | handshake and JWT semantics shared with the gateway go to wire-contract |
| `World/` | `EcsWorld` (Arch), `Components.cs`, `ArchAotHints.cs`, `SpatialGrid`, `WorldReader/Writer`, `SimChunk` | - |
| `Net/` | `Connection`, `ConnectionManager`, `WireProtocol`, `WireJson`, `Transport/`, `Sealed/`, `Security/`, `Generated/` (protoc output) | `Generated/` and the framing go to wire-contract |
| `Snapshot/` | `SnapshotEncoder`, `SnapshotFrameWriter`, `SnapshotDeltaState`, `ReplicationImportance`, `TickEventBuffer` | the normative wire semantics in `docs/API.md` go to wire-contract |
| `Input/` | `InputHandler`, `InputRejection`, `InputAnomalyTracker`, `AttackRateAudit` | - |
| `Scaffolding/` | all content: `EnemySpawner`, `EnemyAi*`, `EnemyCombatSystems`, `BotPlayerSpawner`, `LoadTestSpawner`, `CompositeSimulationPhase`, `BotSettings`, `EnemyAiSettings`, `EnemyAiTuning` | gameplay numbers need the user's decision |
| `Content/` | `ContentLoader`, `ContentJson` (source-gen STJ), serving `backend/content/*.json` at `/content` (ADR-19) | - |
| `Observability/` | `GameMetrics` (meter `rpg.gameserver`), `MetricsEndpoint` (`/metrics`, `/healthz`, `/status`, `/content`), `ServerStatus`, `FrameOrderProbe` | dashboards and alerts go to server-ops |
| `Registry/` | `RedisServerRegistry` (the `servers:id:{id}` writer) | wire-contract (cross-language contract) |
| `Events/` | `RedisEventStream` (`events:game`, ADR-5), `RedisKickConsumer` (`events:kick`, ADR-20) | the stream payload shape is cross-language with the gateway: co-edit with wire-contract |
| `Nakama/` | `NakamaClient` (`POST /v2/rpc/reward_kills`) | the RPC contract goes to server-services |
| `Agones/` | SDK over the HTTP sidecar (ADR-14) | fleet YAML goes to server-ops |
| `Persistence/` | Npgsql player store, migrations | **server-services** (`server.persistence`) |
| `Program.cs` | composition root: arg/env parsing, fail-fast validation, `ServerOptions`, `SimulationPhaseFactory` | - |
| `ServerEnv.cs` | the `GAMESERVER_*` names Program.cs reads directly, as `const string` | - |

`GameServer.Tests/` has the same folders as the code. The test-only folders are `Aot/` (reflection guard), `Bench/` (opt-in benches, owned by measure),
`Deploy/` (knob passthrough gates), `Golden/`, `Infrastructure/` (Docker/ports/proxy helpers), and
`Shared/` (SGL unit tests).

`Shared.GameLogic/`: `Components/` (EntityState, InputData, SnapshotData, Vec2, GameConstants,
MapBounds, ...), `Systems/` (Movement, Combat, Validation, AoiLogic, AbilityLogic,
ActionStateLogic, SnapshotMerger, SnapshotFieldBits), `Content/` (definitions + validation,
ADR-19 d4), `GoldenVectors/` (aoi, combat, movement, snapshot_merger, validation, vec2 `.json`),
`package.json` (`com.rpgmmo.shared-gamelogic`).

## Composition: how content reaches the tick

- `ISimulationPhase` (`Server/ISimulationPhase.cs:27`) has one member, `Tick(ulong)`. It runs after
  input and before snapshots, and takes its own write scope through `EcsWorld.UpdateComponents` or
  `ReadAll`.
- `ServerOptions.SimulationPhaseFactory` (`Server/GameServer.cs:388`) is invoked in the host
  constructor (`:883`) with `(world, loggerFactory, onGroupRan)`.
- `Program.cs:983` picks the factory. `LoadTestSpawner` is used when `loadTestEntities > 0` (it never
  composes: its entities are tagged `EnemyAi`). Otherwise `EnemySpawner` and/or `BotPlayerSpawner`
  are used, with enemies first and the two wrapped in `CompositeSimulationPhase` when both are on.
  Otherwise the factory is `null`.
  The `/status` counts (`StatusEntityCount`, `StatusBotCount`) are wired beside it, because only
  the composition root may know what the game is.
- **The deletability claim is not fully true today.** `ISimulationPhase` says that the core never
  names `Scaffolding`. It does: `World/EcsWorld.cs` references `Scaffolding.BotTag`, which
  persistence uses to exclude bots, and `World/ArchAotHints.cs` hints Scaffolding components,
  which AOT requires. Add no new reference of this kind.

## Recipe: a new system

1. Implement `IEcsSystem` (`Server/SystemSchedule.cs:75`) with `Name`, `Group`, `Order` and `Access`.
   `Group` defaults to `World`. `Order` must be unique within the schedule, or the
   constructor throws. `Run(WorldWriter, ulong)` gets the dt of its group at construction.
2. `Access = new ComponentAccess(reads: [...], writes: [...], structural: <spawns/reaps>)`.
3. Mutable fields are allowed only as `[SimulationScratch]` buffers
   (`Server/SimulationScratchAttribute.cs`). `SimulationStateArchitectureTests` scans every
   `ISimulationPhase`/`IEcsSystem` and its nested types.
4. A new component struct goes in `World/Components.cs`, or in `Scaffolding/` if it is content. It also
   needs a `new T[1]` line in `ArchAotHints.KeepAlive`, which `World/ArchAotHintTests` enforces.
5. Tests: `Server/SystemScheduleTests.cs`, `SimulationScheduleTests.cs` and `MultiRateSimulationTests.cs` show the
   patterns. For movement-adjacent systems also add a live-path test like `Server/SlowClientMovementTests.cs`.

## Knobs

A knob is two things: the name the server parses, and a line in every gated manifest.
`ServerEnv.cs` and `docs/README.md` "Adding a knob" record seven incidents where the second half was missing.

1. **Name.** Declare it as a `const string` in `ServerEnv.cs`, or as `EnvVar` in its Settings class
   (`Server/AoiSettings.cs`, `Server/ImportanceSettings.cs`, `Scaffolding/BotSettings.cs`,
   `Scaffolding/EnemyAiSettings.cs`). A compile-time concat such as `EnvVar + "_W_X"` is fine. A runtime concat
   or an inline literal is invisible to the gates.
2. **Parse.** Use `TryCreate(..., out settings, out error)` and exit 2 before the startup banner
   (`Program.cs` ~225-250). Never fall back to the default on a bad value. Use InvariantCulture.
3. **Default.** Put a server default in `Server/ServerDefaults.cs` or in the Settings class. A new
   number needs the user's decision (`phase-plumbing-only`).
4. **Passthrough.** The gates reflect over every `GAMESERVER_*` const (`Tests/Deploy/DeclaredKnobs.cs`)
   and require each knob in all five manifests, or an entry in the gate's exclusion dictionary with a reason:
   - `ComposeEnvPassthroughTests.GatedServices`: `backend/deploy/docker-compose.yml` service
     `gameserver-dotnet` and `backend/deploy/docker-compose.override.yml` service
     `gameserver-dotnet-map02` (map02 inherits nothing). Write the entry as `NAME: ${NAME:-}`.
     Exclusions: `Excluded`.
   - `FleetEnvPassthroughTests.GatedFleets`: `backend/deploy/agones/fleet-map-dotnet-dev.yaml`,
     `backend/deploy/k8s/app/50-fleet-map.yaml`, `backend/deploy/k8s/app/60-fleet-dungeon.yaml`.
     Tuning knobs are `configMapKeyRef` to `gameserver-config` with `optional: true`.
     Exclusions: `ExcludedEverywhere` + `MapFleetExclusions` / `DungeonFleetExclusions`.
   - **Not checked by any gate:** `backend/deploy/k8s/app/20-configmaps.yaml`, which defines
     `gameserver-config` with kebab-case keys, and `backend/deploy/.env.example`. Setting a
     non-default value on a cluster or in compose is a server-ops change.
5. **Observe.** Publish the value in force on `/status` when an operator must confirm it, because an
   allocated Agones pod keeps its creation-time environment. Document it in the `docs/README.md`
   configuration table (flag, env, default, meaning) and in `docs/METRICS.md` if `/status` changed.
6. **Changelog.** Add an entry to `gameserver-dotnet/CHANGELOG.md`, and to `backend/deploy/CHANGELOG.md` for the manifest lines.

## Metrics

- Instruments are in `Observability/GameMetrics.cs` (meter `rpg.gameserver`) and are scraped as `gameserver_*`.
- `docs/METRICS.md` "Metric reference (scraped names)" is the table to update. The `/status` section
  documents the JSON fields. **No test compares the doc with the code**, so review it by hand.
- `Observability/GameMetricsTests.cs` uses the OTel in-memory reader. Add a point-level assertion
  for a new instrument, and show that it can read non-zero.
- Consumers outside this module: `backend/deploy/monitoring/prometheus.yaml`, `alerts.yaml`, and
  `dashboards/rpg-gameplay.json`. The client `Assets/Samples/Netcode/DOTS Sample/DOTSNetworkBridge.cs`
  reads `/status` `enemies_alive`.

## Golden vectors

- Generator: `GameServer.Tests/Golden/GoldenVectorGenerator.cs` `Regenerate`. It is a `[SkippableFact]` that runs only
  with `GOLDEN_REGEN=1` (from WSL you also need `WSLENV=GOLDEN_REGEN`).
- Replayed by `GoldenVectorTests`, `AoiGoldenVectorTests` and `SnapshotMergerGoldenVectorTests`, and by
  the client's Unity Test Runner against the pinned SGL tag (ADR-10).
- A stale fixture fails with "regenerate with: GOLDEN_REGEN=1 dotnet test --filter Regenerate".
  Regenerate only for an intended behaviour change, and never to turn a red test green.

## AOT

- `GameServer.csproj` has `PublishAot=true`. It shows 37 audited IL2026/IL3050 warnings in
  `Collections.Pooled.PooledEnumerableJsonConverter` plus IL3053/IL2104 summary lines. They are **not suppressed** on
  purpose (`docs/DESIGN.md` "Collections.Pooled AOT warnings"). A new warning outside that set is a finding.
- A clean publish proves nothing. Missing Arch hints throw only on the first archetype creation.
  CI (`ci-dotnet.yml` "Publish AOT") runs `TestDotnetInterop` against the native binary
  (`GAMESERVER_NATIVE_BIN`) (ADR-11 d4).
