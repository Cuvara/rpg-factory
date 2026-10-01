---
name: dotnet-gameserver
description: How the C# .NET 10 realtime game server and Shared.GameLogic actually work in rpg-mmo-server - the tick thread and the order of one tick, the three simulation rates, EcsWorld locking over Arch, the zero-allocation idioms, the C# 9 limits on shared code, the Net layer, xUnit idioms and how to run one test, and what breaks NativeAOT. Use when you implement, debug or review code there and need to know how the technology behaves, not where the change belongs. Not for deciding scope, rules, checks or gates (server-realtime, wire-contract, measure own those), and not for Go services or the Unity client.
argument-hint: "[task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*)
---
# .NET game server - how it works

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first. Honour the declared Factory mode: in `analyze`, `plan` and `review` apply this skill's workflow, rules and checklist to produce the analysis, plan or findings - change nothing; in `validate` only run and grade checks.

> **Supporting skill, never the owner:** invoke the lead (and co-leads) from the snapshot's routing line
> first - here `server-realtime`, `wire-contract` or `measure`. If you have not, stop and invoke it now: rules, gates, validation and the
> report come only from it. This skill adds how the technology works; it decides nothing.

Task: $ARGUMENTS

## Applies when / Not when

- **Applies:** you are writing, debugging or reviewing C# under `backend/gameserver-dotnet/`
  (`GameServer/`, `GameServer.Tests/`, `Shared.GameLogic/`) and need the mechanics: what runs on
  which thread, under which lock, at which rate, and how to prove it with one test.
- **Not when:** you need to know where a change goes, which rules, checks and human gates apply,
  or what the report must contain. That is the calling skill (`rpg-factory:server-realtime`,
  `rpg-factory:wire-contract`, `rpg-factory:measure`) and the registry. This skill restates none of it.

## Scope

Repo `server`, read through the modules of the calling skill. All paths below are relative to
`backend/gameserver-dotnet/` (rpg-mmo-server). Folder map, content composition, new-system recipe,
knobs, metrics, golden vectors and the AOT warning baseline:
`gameserver.md` in the server-realtime skill's references. Line-level detail of one tick:
`references/tick-and-world.md`. Decisions: `backend/docs/ARCHITECTURE-DECISIONS.md` (ADR-n below).

## Architecture

- **Tick thread.** `TickLoop.RunAsync` (`GameServer/Server/TickLoop.cs:357`) runs a dedicated
  `AboveNormal` thread, not an async loop on the ThreadPool (#248), paced in `Stopwatch` ticks with
  sleep-then-spin (`RunOnDedicatedThread` `:384`, loop `:426-442`). Overruns are metrics; a backlog past `MaxLagTicks` is dropped, not chased.
- **One base tick** (`TickOnce`, `:494`), in order:
  1. `ApplyStructuralChanges` - deferred spawns/despawns (ADR-11: no Arch `CommandBuffer` under AOT).
  2. Critical work **inline in the loop body**, not `IEcsSystem` classes: drain inputs, rebind
     stale handles, coalesce to the newest input per entity, then one `UpdateComponents` scope for
     `InputHandler.ProcessInput` (movement and attack) and held movement (`:517-579`).
  3. `_simulationPhase?.Tick` - the declared systems of the groups due this tick (`:584`).
  4. Only on World-rate ticks (`:610`): reset counters, then gather under **one** read lock
     (`ReadAll`, or `ReadAllParallel` at >= `GatherParallelMinViewers` viewers, `:136`, and only
     with `GAMESERVER_GATHER_WORKERS` > 1). Each connection stages its view and signals its write task.
  5. Encode and send happen **off the tick**, on each connection's write task
     (`GameServer/Net/Connection.cs:314` `GatherSnapshotView`, `:841` `WriteLoopAsync`, bounded
     `DropOldest` channel). Tick events are cleared only after the gather (`TickLoop.cs:747`).
- **Rates** (ADR-13). Three groups, `Critical`/`World`/`Background`, defaults in
  `GameServer/Server/SimulationRates.cs:59-65`. Base rate = critical rate; the others must divide it
  or `TryCreate` rejects the config at startup (`:256`, `:266`). Snapshots ship at the World rate,
  because the base rate would break the ADR-7 mobile bandwidth budget. `MovementHz` is the value the
  join reply advertises as `tick_rate` - moving movement to another group is a wire change.
- **ECS world** (`GameServer/World/EcsWorld.cs`). Arch behind one `ReaderWriterLockSlim` (`:178`),
  because network threads spawn/despawn and enqueue input while the tick runs. API: `ReadAll`
  (`:943`), `ReadAllParallel` (`:1100`), `UpdateComponents<TState>` (`:1177`),
  `UpdateComponentsParallel` (`:1239`, not used by the tick; proves the ADR-12 preconditions).
  Every write scope applies deferred structural changes on exit. No Arch type reaches SGL.
- **Shared.GameLogic.** `Shared.GameLogic/Shared.GameLogic.csproj` targets registry fact `sgl-target-frameworks`,
  pins `LangVersion` (fact `sgl-langversion`, Unity 6's C#), disables implicit usings and unsafe code to match the asmdef.
  Unity compiles it as **source** (ADR-10), so the server build is the first place a C# 10 feature
  or a missing `using` must fail.
- **Net layer.** `GameServer/Net/WireProtocol.cs` (4-byte BE length, Protobuf or legacy JSON per
  connection, ADR-9); `Net/Transport/` (TCP/KCP, `KcpCrypto` = kcp-go AES PSK, ADR-8);
  `Net/Sealed/` (X25519 + ChaCha20-Poly1305 sealed session with `SequenceValidator` as the replay
  counter, ADR-22; per-pod Ed25519 `ServerIdentity`, ADR-25); `Net/Security/SessionKey.cs` is
  superseded as an encryption key. `Net/Generated/` is protoc output (wire-contract).

## Idioms

- **Static lambda + state overload** for every world scope on a hot path:
  `_world.UpdateComponents(this, static (self, writer) => self.ProcessInputBatch(writer));`
  (`TickLoop.cs:560`). The capturing form measured ~104 B/tick (comment above it).
- Reused scratch, never per-tick `new`: `_inputs`, `_newestInputIndex`, `_viewers` grow once and are
  cleared (`TickLoop.cs`). In systems, mutable fields only as `[SimulationScratch]`
  (`GameServer/Server/SimulationScratchAttribute.cs`).
- Group membership, never tick arithmetic: `RunsOn(group, baseTick)` (`SimulationRates.cs:183`) is
  integer and replayable; never a float accumulator.
- AOT-safe JSON only: source-generated `JsonSerializerContext` (`GameServer/Content/ContentJson.cs`,
  `Observability/ServerStatus.cs`); every `JsonSerializer` call passes a `JsonTypeInfo`.
- Time is `Stopwatch`, never `DateTime.UtcNow` - this host's realtime clock runs fast and has
  stepped backwards (#153, `gameserver-dotnet/CLAUDE.md`).

## Pitfalls

- **Arch's read path writes** (#176). Iterate only queries from `_readQueries`
  (`EcsWorld.cs:383`); a raw Arch query under the read lock corrupted the enumerator and the heap.
- **Allocations that look harmless:** a capturing lambda, an interpolated rejection string, an
  unguarded debug log on the combat branch (#249, `GameServer.Tests/Bench/TickAllocationBench.cs`).
  The always-on guard covers the snapshot path only, so input/combat changes need the opt-in bench.
- **Counter and event lifetimes span two rates.** Input runs every base tick, broadcast every
  World tick: clearing tick events at the top of the base tick lost 3 of 4 damage events
  (`TickLoop.cs:731-747`, `Server/TickEventBroadcastTests.cs`); resetting counters inside the
  viewer guard replayed stale values forever (#401, `TickLoop.cs:628-670`).
- **A clean AOT publish proves nothing.** Arch allocates chunk arrays with
  `Array.CreateInstance`; a component without an `ArchAotHints` line publishes with no warning and
  throws on the first spawn (ADR-11 d4). Reflection JSON, `MakeGenericType`, `Activator`, dynamic
  assembly loading and `System.Reflection.Emit` all break or warn under `PublishAot=true`
  (`GameServer/GameServer.csproj`). Unit tests run on the JIT: only reflection JSON has a test
  (`GameServer.Tests/Aot/JsonReflectionGuardTests.cs`); the rest shows only in the CI
  "Publish AOT" job's native join (`.github/workflows/ci-dotnet.yml`, `TestDotnetInterop`).
- **Shared.GameLogic multi-targets** `netstandard2.1`: a .NET-only API compiles for `net10.0` and
  fails on the other target - read both target errors.
- `gameserver-dotnet/CLAUDE.md` still says "4-byte BE length + JSON"; the wire is Protobuf with JSON
  legacy (ADR-9, `WireProtocol.cs`).

## Testing

- xUnit, one project `GameServer.Tests/` mirroring `GameServer/`; SGL tests are in
  `GameServer.Tests/Shared/`. No `[Trait]` categories, so `--filter "FullyQualifiedName~X"` is the
  only selector. Run from `backend/gameserver-dotnet/`; `{dotnet}` is the resolved binary
  (Windows `dotnet.exe` on WSL, registry known issue `dotnet-wsl`):
  - one class: `{dotnet} test GameServer.Tests --filter "FullyQualifiedName~GameServer.Tests.Snapshot.SnapshotAllocationTests"`
  - one method: `{dotnet} test GameServer.Tests --filter "FullyQualifiedName~SnapshotAllocationTests.WriteFrame_IsByteIdenticalToTheAllocatingPath"`
  - env-gated (bench, golden regen) from WSL: `BENCH_TICK=1 WSLENV=BENCH_TICK${WSLENV:+:$WSLENV} {dotnet} test GameServer.Tests --filter "FullyQualifiedName~TickAllocationBench"`
- Fixtures: `TestHelpers.CreatePlayer` / `CreateMob` / `CreateTestJwt` (`GameServer.Tests/TestHelpers.cs`).
  Ports only from `Infrastructure/TestPorts.cs`: `StartServerAsync` (reads back the bound port)
  first, `Lease` only when the binder needs a number up front.
- Wall-clock assertions (distance over real seconds through a socket) go in
  `[Collection(WallClockCollection.Name)]` (`Server/WallClockCollection.cs`). A test that only
  waits polls for the condition instead of sleeping.
- Dependency-gated tests use `[SkippableFact]`: skip when Docker is absent, fail when Docker
  answered but the container never became ready (`gameserver-dotnet/CLAUDE.md`).
- `TickLoop.TickOnce()` is public for tests: drive ticks deterministically instead of starting
  the thread (`Server/TickLoopTests.cs`).

## Tools

- `dotnet`: build, single-test runs and the AOT publish above. Not OK: CI `ci-dotnet.yml`
  (Test & Build, Publish AOT with the native interop run) is the fallback, and say so.
- `lsp-csharp`: find callers and implementations before changing an `EcsWorld` API, a component
  or an `IEcsSystem`/`ISimulationPhase` member. Currently MISSING (known issue `no-csharp-lsp`):
  fall back to `grep -rn` for the symbol over `GameServer/`, `GameServer.Tests/` and
  `Shared.GameLogic/`, then `{dotnet} build` of `GameServer.sln` to catch what grep missed.
- `context-mode`: run `{dotnet} test` / `{dotnet} publish` through `ctx_execute` and return only
  the summary line, failures and IL warning codes. Not OK: pipe through `tail` / `grep -E 'Passed!|Failed|error|IL[0-9]{4}'`.
