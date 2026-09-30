---
name: server-realtime
description: Use when changing the C# realtime game server or the Shared.GameLogic package in rpg-mmo-server - tick loop, ECS systems and simulation phases, input handling, snapshot/replication/AOI/importance, scaffolding bots and enemies, GAMESERVER_* knobs, metrics and /status, content loading, NativeAOT, golden vectors. It is the server leg of wire and SGL-pin work. Not for wire.proto, protocol version or the Redis servers:id hash (wire-contract), persistence/migrations, gateway or Nakama (server-services), deploy manifests (server-ops), or benchmarks (measure).
argument-hint: "[task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*)
---
# Server realtime - C# game server + Shared.GameLogic

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first.

Task: $ARGUMENTS

## Applies when / Not when

- **Applies:** code under `backend/gameserver-dotnet/` (except `GameServer/Persistence/`), `Shared.GameLogic/`, `backend/content/`, and the docs/CHANGELOGs of those modules.
- **Not when:** the change is only in a hand-off area (see Scope). If a task starts there and then needs server code, the driver skill calls this one as a leg.

## Scope

Repo `server`. Modules: `server.gameserver-dotnet`, `server.shared-gamelogic`, `server.content`.
`server.content` belongs here. The game server is its only reader: it loads and validates at boot and serves `/content` (ADR-19). Its schema and validator are in `Shared.GameLogic/Content/`, its loader is `GameServer/Content/`, and `ContentLoaderTests` validates the shipped `items.json`. Its changes go in `backend/gameserver-dotnet/CHANGELOG.md` (the ADR-19 commit cc217b9 did this).

Facts come from the registry:
`jq '.modules[]|select(.id|test("gameserver-dotnet|shared-gamelogic|content"))' ${CLAUDE_PLUGIN_ROOT}/registry.json`.
The architecture map and wiring recipes are in `references/gameserver.md`.

| Touches | Owner | This skill |
|---|---|---|
| `wire.proto`, `Net/Generated/`, `protocol_version`, normative `docs/API.md` sections | wire-contract (driver) | server leg: encoder/handler code + tests |
| `Registry/RedisServerRegistry.cs` field set (servers:id:{id}) | wire-contract | never alone |
| join-token claims (`sid`, `jti`): `Server/JwtValidator.cs` <-> gateway `transfer/join_token.go` + `shared/jwt` | wire-contract | C# side as a leg, never alone |
| `backend/integration_test/` | server-services (Go flows), wire-contract on contract change | cases driven by game server behaviour |
| `GameServer/Persistence/` (Migrator, AsyncSaver, PlayerSpawn, PostgresPlayerStore), `deploy/db/`, gateway, nakama plugin | server-services (hands back PlayerSpawn changes that alter spawn/movement behaviour) | `Nakama/NakamaClient.cs` caller side; RPC shape co-edited with server-services |
| compose, fleet manifests, `gameserver-config` ConfigMap, `deploy/monitoring/` | server-ops | knob passthrough lines: see Workflow step 3 |
| `Bench/*`, `docs/BENCHMARK.md`, any capacity/latency claim | measure | may add a bench but never quotes a number |
| SGL tag, client `manifest.json` pin | pin-bump (lead tags) | stops at "ready to tag server sgl-vX.Y.Z" |

## Workflow delta

1. **Classify before planning.** Each new number (HP, damage, cooldown, spawn rate, AI radius, knob default) is a gameplay rule. Stop and ask (`phase-plumbing-only`). Routing a value the user already gave is plumbing.
2. **Place the code.** See `references/gameserver.md`. The core (Server, World, Net, Snapshot, Input) stays content-agnostic, and content goes behind `ISimulationPhase` in `Scaffolding/`, wired only in `Program.cs`. A new system implements `IEcsSystem` with `Group`, a unique `Order` and honest `ComponentAccess`. It keeps state on components, not in fields.
3. **Knob change = server-knobs obligation.** Follow `references/gameserver.md#knobs`. Declare the name as a `const string` and parse it strictly (exit 2). Then the passthrough lines must land in the **same commit**. The manifests belong to `server.deploy`, so for a single-repo server task this skill co-edits them (only the `environment:`/`env:` entries) and puts a `backend/deploy/CHANGELOG.md` entry in the same commit. Values (`.env.example`, ConfigMap keys) and anything else in those files are hand-offs to server-ops.
4. **Metric or /status change.** Update `docs/METRICS.md` in the same change. No test enforces parity. Then check the consumers: `deploy/monitoring/{prometheus,alerts}.yaml` and `dashboards/rpg-gameplay.json` (server-ops), and `/status` field names read by the client DOTS sample (client-integration).
5. **SGL change.** Add a `.meta` for every new file or folder. An intended behaviour change regenerates the golden vectors in the same commit (extended tier). A signature or behaviour change is a two-repo contract (ADR-10), so name the client impact in the report. Do not bump `package.json` unless the user asks for a release (Human gates).
6. **Movement-adjacent change.** Add a live socket-path test alongside the unit tests, modelled on `GameServer.Tests/Server/SlowClientMovementTests.cs` (TEAM.md).

## Rules

Module rules are in the registry. These are the additions, each with its source:

- Systems declare frequency only through `IEcsSystem.Group`. Never count ticks, test `tick % n` or read Hz. Group order Critical, World, Background is fixed (ADR-13; `Server/SimulationSchedule.cs`).
- `ComponentAccess` must list every type a system reads or writes. Set `structural: true` when it creates or destroys entities. `IsDisjointFrom` is the future parallel predicate, so an under-declared set is a latent race (`Server/SystemSchedule.cs`).
- Phases and systems keep no mutable instance fields. The exception is a `[SimulationScratch]` buffer that holds nothing across ticks, enforced by `SimulationStateArchitectureTests` (ADR-12).
- Never use `CommandBuffer`. Structural changes go through the world's deferred phase (ADR-11 d3, ADR-12 d2). A new component type gets its `World/ArchAotHints.cs` line in the same commit, enforced by `ArchAotHintTests` (ADR-12 d3).
- JSON goes through source-generated `JsonTypeInfo` only, guarded by `Aot/JsonReflectionGuardTests.cs`. Never add `NoWarn` for the audited Collections.Pooled AOT warnings (`GameServer.csproj`).
- ECS staging must not change the wire, and snapshot output stays byte-identical (ADR-12 d6; `Snapshot/SnapshotByteIdentityTests.cs`). Importance orders what is sent. It does not budget or gate interest. It is off by default (ADR-27).
- No synchronous I/O on the tick loop. Persistence is an async background task (`gameserver-dotnet/CLAUDE.md`).
- Run the server with space-separated flags (`--addr :9000`). `--addr=:9000` is silently ignored (`docs/README.md`, `Program.cs` `GetArg`).
- Read `docs/BENCHMARK.md` Part XI (AOI gate and sort) and Parts XIII-XIV (importance baseline and cost) before changing AOI, gather or replication. Parts X and earlier are superseded for AOI ratios.

## Generated & protected paths

| Path | Generator |
|---|---|
| `GameServer/Net/Generated/` | `backend/shared/proto/generate.sh` (wire-contract; never hand-edit) |
| `Shared.GameLogic/GoldenVectors/*.json` | `GameServer.Tests/Golden/GoldenVectorGenerator.cs` `Regenerate` (registry `golden-regen`) |
| `Shared.GameLogic/**/*.meta` | hand-written here (no Unity Editor in this repo): copy a sibling's `.meta` (`MonoImporter` for `.cs`, `folderAsset: yes` for folders) with a fresh random 32-hex `guid`; `check_metas.py` checks presence only, not GUID uniqueness |
| `ServerEnv.cs` constant values | protected: renaming one needs every manifest changed in the same commit |

## Validation delta

- **fast:** Core's `dotnet-build`, `dotnet-test`, `verify-test-counters`, `check-metas`. The dotnet-test skip count is **non-zero by design**. `Regenerate` skips without `GOLDEN_REGEN`, benches skip without `BENCH_TICK`/`BENCH_AOI`/`MEASURE_TIERING`, and the Docker fixtures skip without Docker. Name each skip family. Anything else that skipped is a finding. While iterating on knobs, `--filter "FullyQualifiedName~GameServer.Tests.Deploy"` is a quick targeted run, but it does not replace the full run.
- **extended `golden-regen`:** run only for an intended behaviour change. Evidence: the `git diff --stat` of `GoldenVectors/`, with every changed case explained, and the non-regen suite passing afterwards.
- **extended `aot-publish`:** triggered by a new component, serialization, a new package or a csproj change. Evidence: the publish succeeds and the only AOT/trim warnings are the audited `Collections.Pooled.PooledEnumerableJsonConverter` set (37 IL2026/IL3050 warnings plus the IL3053/IL2104 summary lines, `docs/DESIGN.md`) - any new warning is a finding. The native interop run is Linux-only, so from WSL report it `not-run:external` (covered by `ci-dotnet.yml`).
- **extended `integration-e2e`:** for a handshake, join or snapshot framing change (registry trigger).
- **external:** `ci-dotnet.yml`. Count its two jobs (Test & Build, Publish AOT), and then `ci.yml` integration when a wire change is involved.

## Human gates

- **SGL release (lead-only).** Bumping `Shared.GameLogic/package.json` `version`, creating `sgl-v*` tags and dispatching `publish-shared-gamelogic.yml` all need the user. The skill stops at "ready to tag server sgl-vX.Y.Z".
- **Gameplay numbers.** `phase-plumbing-only`: see Workflow step 1.
- Otherwise the global gates apply.

## Review checklist

- [ ] Hot paths (tick, input, snapshot, gather) allocate nothing new: no LINQ, no closures, no boxing, no per-tick `new`. The buffers are `[SimulationScratch]` or caller-provided `Span<T>`.
- [ ] Every new or changed system has `Group`, a unique `Order` and a complete `ComponentAccess` (with `structural` if it spawns or reaps). There are no mutable fields.
- [ ] Every new component is in `ArchAotHints`. There is no reflection JSON and no `CommandBuffer`.
- [ ] The core added no new reference to `GameServer.Scaffolding`, and content wiring lives in `Program.cs`.
- [ ] Every knob is a `const string` and strictly parsed (exit 2). The value in force is on `/status` when an operator must confirm it (the pattern is `aoi_radius`, `enemy_ai`). It is in the `docs/README.md` configuration table and in all 5 gated manifests, or excluded with a reason.
- [ ] Every new or renamed metric or `/status` field is in `docs/METRICS.md`. The monitoring and client consumers are checked.
- [ ] SGL: `netstandard2.1;net10.0`, no ECS or Unity types, allowed float ops only, integer entity handles, `.meta` present.
- [ ] Behaviour change: golden fixtures are committed and each diff is explained. No change means an unchanged `GoldenVectors/`.
- [ ] Movement-adjacent change: there is a live socket-path test.
- [ ] Tests use `[SkippableFact]` for dependencies and `Stopwatch` for deadlines.
- [ ] CHANGELOG `[Unreleased]` entries exist: `gameserver-dotnet/CHANGELOG.md` and/or `Shared.GameLogic/CHANGELOG.md`, plus `deploy/CHANGELOG.md` when manifests changed. The `docs/DESIGN.md` note is dated for an architecture change.

## Report additions

- The skip families with counts (golden, bench, docker), and any skip outside them.
- Knob table: name, default, parse rule, and the manifests edited or excluded.
- Golden diff summary, or "GoldenVectors unchanged".
- SGL: the API or behaviour change and its client impact, or "no SGL change". Whether it is ready to tag.
- AOT: the warning set compared with the audited baseline, or `not-run` with the trigger.
