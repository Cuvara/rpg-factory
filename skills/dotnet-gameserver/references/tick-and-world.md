# Tick and world internals

Verified 2026-10-01 against rpg-mmo-server `develop` @ 5023a3d. Paths are relative to
`backend/gameserver-dotnet/`. Line numbers drift: re-check one before you cite it. The folder map,
the content composition and the new-system recipe are in
`../server-realtime/references/gameserver.md`; this file only covers how one tick runs.

## The tick thread

- `TickLoop.RunAsync` (`GameServer/Server/TickLoop.cs:357`) starts a dedicated thread named
  `tick-loop`, `IsBackground`, `ThreadPriority.AboveNormal`. The remark above it explains why it is
  not an async loop: `await Task.Delay` resumed on a ThreadPool that every connection also uses
  (three long-lived items per connection), so a connection storm delayed ticks (#248).
- `RunOnDedicatedThread` (`:384`) paces in `Stopwatch` ticks, `Stopwatch.Frequency / BaseHz`,
  because `1000/60` in integer milliseconds is a 4% fast clock. It sleeps to just before the
  deadline on the cancellation wait handle, then spins with `SpinWait`.
- An overrun is a metric (`RecordTickOverrun`); above twice the budget it is also a warning log.
  A late loop advances the deadline without sleeping; past `MaxLagTicks` (`:339`) the backlog is
  dropped in one step and logged ("Simulation time is now behind real time").

## One base tick: `TickOnce` (`TickLoop.cs:494`)

| Step | Lines | What happens | Lock |
|---|---|---|---|
| 1 | 507 | `_world.ApplyStructuralChanges()` - spawns/despawns raised during an iteration (ADR-11: Arch's `CommandBuffer` throws under NativeAOT) | write |
| 2 | 517-579 | Critical group **inline in the loop body**, not an `IEcsSystem`: `DrainInputs`, `RebindStale`, coalesce to the newest input per entity (`_newestInputIndex`), then one `UpdateComponents` scope that runs `InputHandler.ProcessInput` (movement and attack/combat) and `ApplyHeldMovement`. With no input, held movement still runs. Timed under `group="critical"` by hand. | one write scope |
| 3 | 584 | `_simulationPhase?.Tick(_currentTick)` - the declared systems of every group due on this base tick (Critical, World, Background order); a no-op on ticks where none are due | the phase takes its own scopes |
| 4 | 610 | Return here unless the World group is due: snapshots ship at the World rate, not the base rate (ADR-13; bandwidth reason ADR-7) | - |
| 5 | 659-670 | Reset every per-tick snapshot counter, unconditionally, before the gather (#401) | - |
| 6 | 674-686 | Phase A, gather: `ReadAll` or, at `>= GatherParallelMinViewers` (`:136`) with `GAMESERVER_GATHER_WORKERS > 1`, `ReadAllParallel`. Each connection stages its own view and its write task is signalled. | one read lock |
| 7 | 689-729 | Collect each connection's counters (`TakeSnapshotCounters`, `TakeScheduleCounters`), clear the viewer scratch array | - |
| 8 | 747 | `_tickEvents?.Clear()` - only after the gather, never at the top of the base tick | - |
| 9 | 751-769 | Metrics, once per tick | - |

**Correction to the older description.** There is no Phase B on the tick thread any more. Encoding
and sending happen on each connection's write task: `Connection.GatherSnapshotView`
(`GameServer/Net/Connection.cs:314`) stages the view and writes `SendItem.Snapshot` into a bounded
`DropOldest` channel; `WriteLoopAsync` (`:841`) encodes against the last snapshot actually sent, so
back-pressure coalesces to the newest snapshot and one channel per connection keeps frame order.

## Rates

- Defaults: `SimulationRates.DefaultCriticalHz` / `DefaultWorldHz` / `DefaultBackgroundHz`
  (`GameServer/Server/SimulationRates.cs:59-65`, values in registry fact `tick-rates-default`), configured by `SIM_CRITICAL_HZ`, `SIM_WORLD_HZ`,
  `SIM_BACKGROUND_HZ`. `BaseHz` is the critical rate; the others are integer divisors of it.
- `TryCreate` (`:208`) rejects a slower group that does not divide the base rate (`:256`, `:266`)
  and a rate above `MaxHz`. A group is due when `baseTick % every == 0` (`RunsOn`, `:183`), so the
  schedule is identical on every run - never replace it with a float accumulator.
- `MovementHz` is what `JoinTokenResponse.tick_rate` publishes (doc comment above it in the
  same file): a change to how movement is scheduled is a wire change (wire-contract).

## EcsWorld threading (`GameServer/World/EcsWorld.cs`)

- One `ReaderWriterLockSlim` (`:178`) guards the Arch world, because network threads spawn,
  despawn and push input while the tick reads. Input is queued under a separate `_inputLock`.
- Read API: `ReadAll(Action<WorldReader>)` (`:943`), `ReadAllParallel(int, Action<WorldReader,int>)`
  (`:1100`). Write API: `UpdateComponents<TState>(state, Action<TState, WorldWriter>)` (`:1177`),
  the non-generic overload (`:1192`), `UpdateComponentsParallel` (`:1239`). Every write scope ends
  with `ApplyStructuralChangesLocked` and `ExitWriteScope` (`:559`).
- **Arch's read path writes** (issue #176): it resolves queries through a shared dictionary and
  rebuilds archetype lists lazily. A read path may only iterate a query from `_readQueries`
  (`:383`), refreshed by the preceding write scope. Concurrent raw Arch queries corrupted the
  enumerator and twice the heap.
- `ReadAllParallel`: the owner holds the read lock for the whole region and rebuilds the spatial
  grid before any worker wakes; per-worker scratch is thread-static. The callback must not share
  mutable state between workers.
- `UpdateComponentsParallel` is **not called by the tick loop**. It exists to prove the ADR-12
  preconditions (per-slot structural queues replayed in slot order). Using it needs disjoint
  `ComponentAccess` and is a schedule decision, not a local optimisation.
- No `Arch.Core` type crosses into `Shared.GameLogic`: the world composes `EntityState` on the way
  out (class doc above `EcsWorld`).

## Allocation evidence

- The `static (self, writer) => ...` form at `TickLoop.cs:560` and `:570`; the comment above it
  records the capturing form at ~104 B/tick and the static form at 0 B/call.
- `GameServer.Tests/Snapshot/SnapshotAllocationTests.cs` (always on): a paired A/B of the old
  allocating snapshot path against the pooled one, with generous thresholds, plus byte-identity of
  the two paths. It does not measure the input/combat path.
- `GameServer.Tests/Bench/TickAllocationBench.cs` (`BENCH_TICK=1`): `TickOnce` whole and per phase,
  inputs carry attacks, plus the off-tick encode path. Its doc names the defect class #249 found:
  interpolated rejection strings and unguarded debug logs on the combat branch.
