# DOTS worked patterns

Verified 2026-10-21 against UnityDots `origin/main` @ `c3be200` and the client `origin/develop` @ `c2cf32c`. Paths are relative to
`UnityDots/` unless prefixed `client:`. Line numbers drift: re-read the file before you copy a pattern.

## 1. A Burst simulation system with a structural change (the reference shape)

`Runtime/Simulation/TimeToLiveSystem.cs`, the whole file is the template:

```csharp
[BurstCompile]                                   // :25 the job
internal partial struct TimeToLiveJob : IJobEntity
{
    public float DeltaTime;
    public EntityCommandBuffer.ParallelWriter CommandBuffer;
    private void Execute([ChunkIndexInQuery] int chunkIndex, Entity entity, ref TimeToLive ttl) { ... }  // :32
}

[BurstCompile, DisableAutoCreation]              // :45-46 struct attribute is required for Burst on an ISystem
[UpdateInGroup(typeof(LifecycleSystemGroup))]
[UpdateAfter(typeof(HealthDeathSystem))]
internal partial struct TimeToLiveSystem : ISystem
{
    [BurstCompile] public void OnCreate(ref SystemState state)   // :53-59
    {   _query = SystemAPI.QueryBuilder().WithAll<TimeToLive>().Build();
        state.RequireForUpdate<TimeToLive>();
        state.RequireForUpdate<DotsEndSimulationCommandBufferSystem.Singleton>(); }

    [BurstCompile] public void OnUpdate(ref SystemState state)   // :61-79
    {   var ecb = SystemAPI.GetSingleton<DotsEndSimulationCommandBufferSystem.Singleton>()
                           .CreateCommandBuffer(state.WorldUnmanaged);
        var job = new TimeToLiveJob { DeltaTime = SystemAPI.Time.DeltaTime, CommandBuffer = ecb.AsParallelWriter() };
        state.Dependency = _query.CalculateEntityCount() >= ParallelScheduling.TimeToLiveMinimum
            ? job.ScheduleParallel(state.Dependency) : job.Schedule(state.Dependency); }
}
```

Then add it to `DotsSimulationBootstrap.InstallSimulationSystems` (`Runtime/Simulation/DotsSimulationBootstrap.cs:42-72`)
and to the install test, which asserts `SystemOrderVerifier.Verify` is empty.

Why the sort key is `[ChunkIndexInQuery]` and not a counter: `TimeToLiveSystem.cs:17-22` (playback
order must be deterministic across runs and worker counts).

## 2. Choosing Schedule vs ScheduleParallel

`ParallelScheduling` (`Runtime/Simulation/ParallelScheduling.cs:1-68`). Each job has its own crossover from a benchmark, not a
shared guess. Cheap per-entity work (one comparison plus an ECB write) barely gains even at 65,536
(1.16x-1.24x) and lost (0.45x-0.88x) when scheduled at 16,384. To add a threshold for a new job:

1. Add an arm to `Tests/Runtime/ParallelSchedulingBenchmark.cs` (PlayMode; Burst forced on and
   synchronous `RequireBurst` `:186-206`; 41 interleaved `Pairs` `:148`; bit-identical check
   `BothSchedules_ProduceBitIdenticalResults` `:283`).
2. Run it under the `measure` workflow (record, control, run id). It asserts no timing (`ParallelSchedulingBenchmark` doc, `Tests/Runtime/ParallelSchedulingBenchmark.cs:138-140`).
3. Put the first count where parallel won into `ParallelScheduling` with the table row.

## 3. Spawning without archetype churn

- Snapshot-driven spawn adds the full component set up front, including the sample buffer, because an
  entity whose archetype changes at snapshot rate moves chunks every snapshot
  (`AddBuffer<SnapshotSample>`, `Runtime.Netcode/NetworkViewCommandSystem.cs:303-310`).
- Cost today: `CreateEntity` + 7 unconditional adds + 1 `AddBuffer` + 2 conditional adds
  (`ApplySpawn`, `Runtime.Netcode/NetworkViewCommandSystem.cs:229-321`), i.e. up to 10 chunk moves per spawn. A prebuilt `EntityArchetype`
  (`EntityManager.CreateArchetype` once in `OnCreate`, then `CreateEntity(archetype)` + `SetComponentData`)
  removes the moves. Only the benchmarks call `CreateArchetype` today: `CreateArchetype` in
  `Tests/Runtime/ParallelSchedulingBenchmark.cs:228`, `CreateArchetype` in
  `Samples~/StressBenchmark/StressBenchmarkBase.cs:160,173` and `CreateArchetype` in
  `client:Assets/Scripts/Benchmark/Dots/DotsStressBenchmark.cs:175,188`.
- Toggled state (local player predicted or not) is a candidate for `IEnableableComponent`
  (`SetComponentEnabled` is not a structural change). Today `PredictedTransform` is added/removed
  (`Runtime.Netcode.Prediction/LocalPredictionSystem.cs:146-160`) and queries exclude it with
  `[WithNone(typeof(PredictedTransform))]` (`Runtime.Netcode/RemoteInterpolationJob.cs:49-51`); switching
  it changes every such query, so it is a package change with a measurement, not a drive-by.

## 4. Job -> managed apply (the view sync shape)

`EntityViewTransformSyncSystem.OnUpdate` (`Runtime/Views/EntityViewTransformSyncSystem.cs:53-73`): a Burst job collects into a
`NativeList` on `state.WorldUpdateAllocator` sized exactly (`AddNoResize`, a ParallelWriter cannot grow,
`:61-63`), `state.Dependency.Complete()` (`:70`), then a flat main-thread loop writes `Transform`s.
The `Complete()` is the price of touching managed objects; keep the managed part as one tight loop
and never call it from more systems than needed.

## 5. ECS -> UI (client)

`client:Assets/Scripts/UI/Hud/Ecs/HudStateSystem.cs` (unmanaged, Simulation) aggregates into a
`HudState` singleton and writes it only on change (`:106-110`; position quantised with `math.round` `:97-102`) ->
`HudBridgeSystem : EcsViewModelBridge<HudState, HudSnapshot>` (`client:Assets/Scripts/UI/Hud/Ecs/HudBridgeSystem.cs:25`)
disables itself with no sink and uses a changed-version filter (`SetChangedVersionFilter`,
`UIToolkit/Runtime/Ecs/EcsViewModelBridge.cs:133-145`)
-> presenter -> view model -> bound view. The ECS side never sees a `VisualElement`.

## 6. Physics queries

`SpatialQuery` (`Runtime.Physics/SpatialQuery.cs:11-42`): `OverlapSphere`, `Raycast`, `RaycastAll`, `ClosestBody`,
all over `in CollisionWorld`. Use these (Unity Physics broadphase) before writing a custom grid on the client;
the server has its own AOI grid (`dotnet-gameserver`) and the client does not replicate it.
Collision/trigger enter-stay-exit: `PhysicsEventCollectorSystem` + `PhysicsContactTracker`
(`Runtime.Physics/PhysicsContactTracker.cs:30-43`, managed `Dictionary`/`HashSet`, main thread).

## 7. ECS test skeleton

```csharp
[SetUp]    public void SetUp()    { _world = new World("Fixture"); DotsSimulationBootstrap.InstallSimulationSystems(_world); }
[TearDown] public void TearDown() { DotsModules.UninstallAll(_world); _world.Dispose(); }

[Test] public void Installs_InOrder() => Assert.IsEmpty(SystemOrderVerifier.Verify(_world));
// time-driven: _world.SetTime(new TimeData(elapsed, dt)); _gameplay.Update();
```

Setup and teardown: `UninstallAll` in `TearDown` (`Tests/Editor/DotsSimulationBootstrapTests.cs:16-26`), the
order assertion `SystemOrderVerifier.Verify` (`:43`); time-driven ticks: `SetTime` then `Update`
(`Tests/Runtime/SimulationSystemsTests.cs:41-45`).
