---
name: server-realtime
description: Use when changing the C# realtime game server or the Shared.GameLogic package in rpg-mmo-server - tick loop, ECS systems and simulation phases, input handling, snapshot/replication/AOI/importance, scaffolding bots and enemies, GAMESERVER_* knobs, metrics and /status, content loading, NativeAOT, golden vectors. It is the server leg of wire and SGL-pin work. Not for wire.proto, protocol version or the Redis servers:id hash (wire-contract), persistence/migrations, gateway or Nakama (server-services), deploy manifests (server-ops), or benchmarks (measure).
argument-hint: "[task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*)
---
# Server realtime - C# game server + Shared.GameLogic

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first. Honour the declared Factory mode: in `analyze`, `plan` and `review` apply this skill's workflow, rules and checklist to produce the analysis, plan or findings - change nothing; in `validate` only run and grade checks.

Task: $ARGUMENTS

## Applies when / Not when

- **Applies:** code under `backend/gameserver-dotnet/` (except `GameServer/Persistence/`), `Shared.GameLogic/`, `backend/content/`, and the docs/CHANGELOGs of those modules.
- **Not when:** the change is only in a hand-off area (see Scope). If a task starts there and then needs server code, the driver skill calls this one as a leg.

## Scope

Repo `server`. Modules: `server.gameserver-dotnet`, `server.shared-gamelogic`, `server.content`.
`server.content` belongs here. The game server is its only reader: it loads and validates at boot and serves `/content` (ADR-19). Its schema and validator are in `Shared.GameLogic/Content/`, its loader is `GameServer/Content/`, and `ContentLoaderTests` validates the shipped `items.json`. Its changes go in `backend/gameserver-dotnet/CHANGELOG.md` (the ADR-19 commit cc217b9 did this).

Module rules, checks and obligations come from the registry (the snapshot prints them for touched
modules); architecture map and wiring recipes: `references/gameserver.md`.

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

0. **Tech skill.** Invoke `rpg-factory:dotnet-gameserver` (Skill tool) before implementing, debugging or reviewing C# here, and before answering how the code works or how to run or choose a test - in every mode, including analyze and plan. It is supporting context, not a follow-up.
1. **Classify before planning.** Each new number (HP, damage, cooldown, spawn rate, AI radius, knob default) is a gameplay rule. Stop and ask (`phase-plumbing-only`). Routing a value the user already gave is plumbing.
2. **Place the code.** See `references/gameserver.md`. Mechanics (tick order, inline work versus systems, EcsWorld locks, rates, zero-alloc idioms, fixtures, the one-test filter) come from `rpg-factory:dotnet-gameserver` (step 0). The core (Server, World, Net, Snapshot, Input) stays content-agnostic, and content goes behind `ISimulationPhase` in `Scaffolding/`, wired only in `Program.cs`. A new system implements `IEcsSystem` with `Group`, a unique `Order` and honest `ComponentAccess`. It keeps state on components, not in fields.
3. **Knob change = server-knobs obligation.** Follow `references/gameserver.md#knobs`. Declare the name as a `const string` and parse it strictly (exit 2). Then the passthrough lines must land in the **same commit**. The manifests belong to `server.deploy`, so for a single-repo server task this skill co-edits them (only the `environment:`/`env:` entries) and puts a `backend/deploy/CHANGELOG.md` entry in the same commit. Values (`.env.example`, ConfigMap keys) and anything else in those files are hand-offs to server-ops.
4. **Metric or /status change.** Update `docs/METRICS.md` in the same change. No test enforces parity. Then check the consumers: `deploy/monitoring/{prometheus,alerts}.yaml` and `dashboards/rpg-gameplay.json` (server-ops), and `/status` field names read by the client DOTS sample (client-integration).
5. **SGL change.** Registry rules apply (`.meta`, golden vectors, release). A signature or behaviour change is a two-repo contract (ADR-10): name the client impact and the `pin-bump` follow-up in the report.

## Rules

Module rules are in the registry. These are the additions, each with its source:

- Systems declare frequency only through `IEcsSystem.Group`. Never count ticks, test `tick % n` or read Hz. Group order Critical, World, Background is fixed (ADR-13; `Server/SimulationSchedule.cs`).
- Rates that do not divide the critical rate are rejected at startup, not rounded (ADR-13 d2; `Server/SimulationRates.cs` `TryCreate`). Replication stays gated to the World rate (ADR-13 d7): the base rate would break the `< 50 KB/s` per-client mobile budget (ADR-7). A change to snapshot cadence or size needs a measure leg.
- `Net/Transport/` (KCP PSK, ADR-8) and `Net/Sealed/` (X25519 + ChaCha20-Poly1305, nonce as replay counter, ADR-22; per-pod Ed25519 identity, ADR-25) have Go twins in `backend/shared/transport` and `backend/shared/sealed`. Changing framing, handshake or crypto bytes is wire-contract work; turning `GAMESERVER_SEALED` on in manifests is the `transport-security` contract (server-ops).
- An under-declared `ComponentAccess` is a latent race: `IsDisjointFrom` is the future parallel predicate (`Server/SystemSchedule.cs`). Structural changes go through the world's deferred phase (ADR-11 d3, ADR-12 d2).
- Never add `NoWarn` for the audited Collections.Pooled AOT warnings (`GameServer.csproj`); reflection JSON is caught by `Aot/JsonReflectionGuardTests.cs`.
- ECS staging must not change the wire, and snapshot output stays byte-identical (ADR-12 d6; `Snapshot/SnapshotByteIdentityTests.cs`). Importance orders what is sent. It does not budget or gate interest. It is off by default (ADR-27).
- No synchronous I/O on the tick loop. Persistence is an async background task (`gameserver-dotnet/CLAUDE.md`).
- Read `docs/BENCHMARK.md` Part XI (AOI gate and sort) and Parts XIII-XIV (importance baseline and cost) before changing AOI, gather or replication. Parts X and earlier are superseded for AOI ratios.

## Generated & protected paths

| Path | Generator |
|---|---|
| `GameServer/Net/Generated/` | `backend/shared/proto/generate.sh` (wire-contract; never hand-edit) |
| `Shared.GameLogic/GoldenVectors/*.json` | `GameServer.Tests/Golden/GoldenVectorGenerator.cs` `Regenerate` (registry `golden-regen`) |
| `Shared.GameLogic/**/*.meta` | hand-written here (no Unity Editor in this repo): copy a sibling's `.meta` (`MonoImporter` for `.cs`, `folderAsset: yes` for folders) with a fresh random 32-hex `guid`; `check_metas.py` checks presence only, not GUID uniqueness |
| `ServerEnv.cs` constant values | protected: renaming one needs every manifest changed in the same commit |

## Validation delta

- **fast:** `run-checks.py` runs the registry's `dotnet-build`, `dotnet-test`, `verify-test-counters`, `check-metas`. The dotnet-test skip count is **non-zero by design**. `Regenerate` skips without `GOLDEN_REGEN`, benches skip without `BENCH_TICK`/`BENCH_AOI`/`MEASURE_TIERING`, and the Docker fixtures skip without Docker. Name each skip family. Anything else that skipped is a finding. While iterating, `{dotnet} test GameServer.Tests --filter "FullyQualifiedName~<Namespace.Class[.Method]>"` is the only selector (no `[Trait]`s); e.g. `~GameServer.Tests.Deploy` for knobs. It never replaces the full run.
- **zero-alloc guard:** `GameServer.Tests/Snapshot/SnapshotAllocationTests.cs` runs in every `dotnet-test` and guards the snapshot path. It does not cover input/combat: for a change there, also run `Bench/TickAllocationBench.cs` (`BENCH_TICK=1`) as a local check; a number written into a doc is measure's.
- **extended `golden-regen`:** run only for an intended behaviour change. Evidence: the `git diff --stat` of `GoldenVectors/`, with every changed case explained, and the non-regen suite passing afterwards.
- **extended `aot-publish`:** triggered by a new component, serialization, a new package or a csproj change. Evidence: the publish succeeds and the only AOT/trim warnings are the audited `Collections.Pooled.PooledEnumerableJsonConverter` set (IL2026/IL3050 warnings, count = fact `aot-audited-warnings`, plus the IL3053/IL2104 summary lines, `docs/DESIGN.md`) - any new warning is a finding. The native interop run is Linux-only, so from WSL report it HUMAN_REQUIRED (external) (covered by `ci-dotnet.yml`).
- **extended `integration-e2e`:** for a handshake, join or snapshot framing change (registry trigger).
- **external:** `ci-dotnet.yml`. Count its two jobs (Test & Build, Publish AOT), and then `ci.yml` integration when a wire change is involved.

## Human gates

- **SGL release (lead-only).** Bumping `Shared.GameLogic/package.json` `version`, creating `sgl-v*` tags and dispatching `publish-shared-gamelogic.yml` all need the user. The skill stops at "ready to tag server sgl-vX.Y.Z".
- **Gameplay numbers.** `phase-plumbing-only`: see Workflow step 1.
- Otherwise the global gates apply.

## Review checklist

- [ ] Hot paths (tick, input, snapshot, gather) allocate nothing new: no LINQ, no closures, no boxing, no per-tick `new`. The buffers are `[SimulationScratch]` or caller-provided `Span<T>`.
- [ ] Registry rules for the touched modules hold (systems, ArchAotHints, knob passthrough, SGL constraints, `[SkippableFact]`, live socket-path test for movement).
- [ ] The core added no new reference to `GameServer.Scaffolding`, and content wiring lives in `Program.cs`.
- [ ] Every knob is a `const string` and strictly parsed (exit 2). The value in force is on `/status` when an operator must confirm it (the pattern is `aoi_radius`, `enemy_ai`). It is in the `docs/README.md` configuration table and in all 5 gated manifests, or excluded with a reason.
- [ ] Every new or renamed metric or `/status` field is in `docs/METRICS.md`. The monitoring and client consumers are checked.
- [ ] Behaviour change: golden fixtures are committed and each diff is explained. No change means an unchanged `GoldenVectors/`.
- [ ] CHANGELOG `[Unreleased]` entries exist: `gameserver-dotnet/CHANGELOG.md` and/or `Shared.GameLogic/CHANGELOG.md`, plus `deploy/CHANGELOG.md` when manifests changed. The `docs/DESIGN.md` note is dated for an architecture change.

## Report additions

- The skip families with counts (golden, bench, docker), and any skip outside them.
- Knob table: name, default, parse rule, and the manifests edited or excluded.
- Golden diff summary, or "GoldenVectors unchanged".
- SGL: the API or behaviour change and its client impact, or "no SGL change". Whether it is ready to tag.
- AOT: the warning set compared with the audited baseline, or HUMAN_REQUIRED with the trigger.

## Tools

- `dotnet`: build, `dotnet-test` and single-test runs, `aot-publish`. Not OK: CI `ci-dotnet.yml` is the evidence, reported as external.
- `lsp-csharp`: find callers before changing an ECS component, an `EcsWorld` API, an `IEcsSystem`/`ISimulationPhase` member or a phase order. Not OK (today MISSING): `grep -rn` the symbol over `GameServer/`, `GameServer.Tests/`, `Shared.GameLogic/`, then `{dotnet} build`.
- `context-mode`: keep `dotnet test` / `dotnet publish` logs out of context; return only the summary, failures and IL warning codes. Not OK: `tail`/`grep` the summary lines.
- `codex`: a second diagnosis through `codex:rescue` when a tick, lock or race bug is stuck after one honest attempt; its output is reviewed like any diff and runs outside the Factory hooks. Not OK: no fallback needed.
