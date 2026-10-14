---
name: unity-dots
description: How Unity Entities/Burst/Jobs code actually works in com.cuvara.dots (UnityDots) and the IndieRPGMMOAdventure client - the system group tree and bootstrap install, the package ECB singleton, measured Schedule vs ScheduleParallel thresholds, archetype-stable spawning, sync points, managed singletons, allocators, change filters, ECS tests - and when gameplay should NOT be ECS. Use when you write, review, debug or optimise an ISystem, job, component layout or ECS test, or decide ECS vs classic C# for a feature. Not for deciding where a change goes, which checks or gates apply (unity-package, client-integration), not for async/VContainer/asmdef/UI questions (unity-client-tech), and not for the server's Arch ECS (dotnet-gameserver).
argument-hint: "[task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*)
---
# Unity DOTS - Entities, Burst and Jobs as this workspace uses them

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first. Honour the declared Factory mode: in `analyze`, `plan` and `review` apply this skill's workflow, rules and checklist to produce the analysis, plan or findings - change nothing; in `validate` only run and grade checks.

> **Supporting skill, never the owner:** invoke the lead (and co-leads) from the snapshot's routing line
> first - here `unity-package`, `client-integration` or `measure`. If you have not, stop and invoke it now: rules, gates, validation and the
> report come only from it. This skill adds how the technology works; it decides nothing.

Task: $ARGUMENTS

Paths are relative to the `UnityDots/` repo unless prefixed `client:` (`IndieRPGMMOAdventure/`). Package
versions are registry facts (`entities-version`, `burst-version`, `collections-version`,
`unity-physics-version`) - check API advice against them, not against older Entities docs. Worked
examples: `references/dots-patterns.md`. Review checklist: `references/ecs-review.md`.

## Applies when / Not when

Applies: you are about to write or review a system, job, component, buffer, ECB use or ECS test in
`UnityDots/Runtime*`, the client's ECS code (`client:Assets/Scripts/**/Ecs/`, `client:Assets/Scripts/DI/Dots/`),
or you must choose between ECS and classic C# for gameplay. Not when: the question is module, scope,
check or gate (lead skill); async, VContainer, asmdefs, UI (`rpg-factory:unity-client-tech`); netcode
transport/prediction internals (`rpg-factory:netcode-client`); server simulation (`rpg-factory:dotnet-gameserver`).

## Scope

Repos `unitydots`, `client`. Owns no module, contract or check.

## ECS or not - decide first

- **ECS (unmanaged ISystem + Burst jobs):** many homogeneous entities updated every frame from data -
  replicated net entities and their interpolation, projectiles, transient effects, simulation
  scaffolding (`Runtime/Simulation/`). That is what the package is (`Documentation~/OVERVIEW.md:3-5`).
- **Classic C# + VContainer:** services, session/login, inventory and other request/response state,
  UI, flows that run once or rarely. Authority lives on the server; the client inventory is a
  server-authoritative service, not ECS (`client:Assets/Scripts/Gameplay/Inventory/InventoryService.cs`).
- **Hybrid, through the existing seams only:** ECS -> UI via a bridge system and a presenter
  (`unity-client-tech`, HUD path); net -> ECS via the enqueue-only `DotsEntityView` drained in
  `SnapshotApplyGroup` (`Runtime.Netcode/DotsEntityView.cs:20`); ECS -> GameObject views via the view
  groups. Do not invent a new bridge.
- Moving a feature across that line (or claiming ECS is faster) needs a `measure` record with a
  control - the package's own rule is "no capacity claim before" profiler markers and a baseline
  (`ROADMAP.md:88-89`). ECS is not faster by default: 1-2 managed objects per frame cost more in
  bridging than they save.

## Architecture

- **Systems are installed, never auto-created.** Every group and system carries `[DisableAutoCreation]`;
  static bootstraps add them: `DotsSimulationBootstrap.InstallSimulationSystems` (`Runtime/Simulation/DotsSimulationBootstrap.cs:42`,
  `GetOrCreateSystem` + `SortSystems` `:60-69`, `Uninstall` `:87`), `DotsViewBootstrap` (`Runtime/Views/DotsViewBootstrap.cs:58`),
  `DotsNetcodeBootstrap` (`Runtime.Netcode/DotsNetcodeBootstrap.cs:36`), `DotsPredictionBootstrap`
  (`Runtime.Netcode.Prediction/DotsPredictionBootstrap.cs:36`). Install is idempotent (`DotsSimulationBootstrap.cs:24-26`).
- **Group tree:** `NetcodeSystemGroup` (Initialization) > `SnapshotApplyGroup` > `PredictionSystemGroup`;
  `ProvisioningSystemGroup` after netcode; `GameplaySystemGroup` (Simulation, before `TransformSystemGroup`,
  `Runtime/Groups/GameplaySystemGroup.cs:30-32`) > Movement > Lifecycle > `DotsEndSimulationCommandBufferSystem`
  (OrderLast); `ViewSystemGroup` (Presentation) > ViewInterpolation > ViewLifecycle > ViewTransformSync.
- **Order is declared with `UpdateAfter`/`UpdateBefore`, not OrderFirst/OrderLast**
  (`Runtime/Views/EntityViewSpawnSystem.cs:27-32`), and proven by `SystemOrderVerifier.Verify(world)`
  (`Runtime/Modules/SystemOrderVerifier.cs:36-67`) - it reads the real update list and reports
  wrong-group members, violated relations and misplaced Order* members, none of which Entities throws for (`:20-22`).
- **One ECB for gameplay structural changes:** `DotsEndSimulationCommandBufferSystem` plays back at the end
  of `GameplaySystemGroup`, before transforms and views (`Runtime/Groups/DotsEndSimulationCommandBufferSystem.cs:14-19,34-63`).
- **Managed state reaches systems as managed singleton components** set by bootstraps
  (`AddComponentObject`, `DotsViewBootstrap.cs:70`) and read with `SystemAPI.ManagedAPI.GetSingleton`
  (`Runtime/Views/EntityViewTransformSyncSystem.cs:55`). Nothing is injected into a system.

## Idioms

- New simulation system: `[BurstCompile] partial struct : ISystem` with `[BurstCompile]` on the struct **and**
  `OnCreate`/`OnUpdate`, work in an `IJobEntity` (`Runtime/Simulation/TimeToLiveSystem.cs:25-78`). No `Entities.ForEach`.
- Structural changes from jobs: get the package ECB singleton, `AsParallelWriter()`, pass
  `[ChunkIndexInQuery]` as the sort key (`TimeToLiveSystem.cs:32-35,64-74`); `RequireForUpdate` the singleton (`:58`).
- Schedule vs ScheduleParallel: compare entity count to the measured threshold in `ParallelScheduling`
  (`Runtime/Simulation/ParallelScheduling.cs:50-68`; 12 cores, Burst on, 41 interleaved pairs, `:8`). New
  job kinds start at `Schedule` until the benchmark (`Tests/Runtime/ParallelSchedulingBenchmark.cs`) gets an arm for them.
- Spawn with the final component set: every component an entity will need at snapshot rate is added at
  spawn (`Runtime.Netcode/NetworkViewCommandSystem.cs:283-289`); add once-per-entity components lazily only
  when they are rare (`:405`).
- Write a singleton only when the value changed - a change filter fires on any write
  (`client:Assets/Scripts/UI/Hud/Ecs/HudStateSystem.cs:28-31,106-110`).
- `IJobChunk` only when per-chunk optional components matter (`Runtime/Views/MinimapCollectJob.cs:15-19`);
  otherwise `IJobEntity`.
- Allocators: `Allocator.Temp` inside one update; `state.WorldUpdateAllocator` for lists/ECBs that live one
  frame (`EntityViewTransformSyncSystem.cs:61-63`); `Persistent` only with `CompleteDependency()` then
  `Dispose` in `OnDestroy` (`Runtime/Views/ViewOverlaySystem.cs:90-95`).
- A system that touches a managed object says so and stays un-Bursted, with the reason in its doc
  (`NetworkViewCommandSystem.cs:54-55`, `EntityPoseViewSystem.cs:24-25`).

## Pitfalls

- **Sync points.** `state.Dependency.Complete()` in `OnUpdate` stalls the main thread on every job before it.
  Four view systems do it every frame by design (`EntityViewTransformSyncSystem.cs:31-32,70`,
  `Runtime/Views/MinimapDataSystem.cs:97`, `ViewOverlaySystem.cs:76`, `client:Assets/Scripts/DI/Dots/EntityElevationSystem.cs:92-93`);
  unprofiled (`EntityViewTransformSyncSystem.cs:24-28`). Do not add another without a marker and a measurement.
- **Archetype churn.** `EntityManager.Add/RemoveComponent` moves the entity to another chunk.
  `ApplySpawn` does 8-10 adds per entity (`NetworkViewCommandSystem.cs:250-316`); `LocalPredictionSystem`
  adds/removes the `PredictedTransform` tag at runtime (`Runtime.Netcode.Prediction/LocalPredictionSystem.cs:146-160`).
  For toggled state prefer an `IEnableableComponent` (none exist yet) or a prebuilt `EntityArchetype`
  (`ArchetypeFactory` is Add-chains despite its name, `Runtime/Configuration/ArchetypeFactory.cs:34-82`) - measured first.
- **Burst on the method only does nothing for an ISystem:** `PhysicsMovementBridge` has it on `OnUpdate`,
  not on the struct (`Runtime.Physics/PhysicsMovementBridge.cs:32-34`). The physics event jobs have none
  (`Runtime.Physics/PhysicsEventCollectorSystem.cs:58,82`).
- **Managed allocations in systems:** a method group passed as `Func<>` allocates a delegate per call
  (`PhysicsEventCollectorSystem.cs:147-148`); `ToString()` per snapshot (`LocalPredictionSystem.cs:185-188`, accepted).
- **Exactly one predicted entity, main thread only** - never parallelise prediction (`LocalPredictionSystem.cs:60-66`).
- A system added to the parent group instead of its declared subgroup runs in the wrong place silently
  (`Runtime/Modules/SystemOrderVerifier.cs:20-22`): run `SystemOrderVerifier` in the install test.
- `Persistent` containers disposed without `CompleteDependency()` are safe only if no job ever touches them
  (`NetworkViewCommandSystem.cs:124,133`).

## Testing

- EditMode, throwaway world: `new World(...)` in `[SetUp]`, install through the production bootstrap, assert
  `SystemOrderVerifier.Verify(world)` is empty, `DotsModules.UninstallAll` + `Dispose` in `[TearDown]`
  (`Tests/Editor/DotsSimulationBootstrapTests.cs:16-44`).
- Drive time and groups directly: `world.SetTime(new TimeData(...))`, then `group.Update()`
  (`Tests/Runtime/SimulationSystemsTests.cs:41-45`); ECB playback and `EntityManager` reads complete the jobs,
  no explicit `Complete()` needed (`:128-154`).
- Templates and the client's ECS test rules (PlayMode cannot see ECS): `rpg-factory:unity-client-tech`.
- Performance: `ParallelSchedulingBenchmark` is the pattern (Burst forced synchronous, interleaved pairs, no
  timing assertions, bit-identical check, `Tests/Runtime/ParallelSchedulingBenchmark.cs:138-148,186-206,283`).
  Numbers it prints are `measure` work.

## Tools

- `unity-mcp`: `tests-run` for one EditMode fixture (`testClass`), console for Burst/compile errors, the
  `profiler-*` tools for a point sample. DOWN: tests are HUMAN_REQUIRED (gate `unity-batch`) or CI.
- `lsp-csharp`: callers of a component or system before changing it (MISSING here: grep `UnityDots/`, the
  client `Assets/` and the DOTS Sample copy, then an Editor compile).
- `context-mode`: Editor logs and test `results.xml` - only totals, failures and Burst errors enter context
  (fallback: `grep` the summary lines).
