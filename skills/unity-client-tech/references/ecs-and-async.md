# ECS and async worked examples

Verified 2026-10-01 against IndieRPGMMOAdventure and the UnityDots / UIToolkit checkouts. Paths
are client-relative unless a package repo is named.

## HUD data path (ECS -> UI Toolkit)

`NetworkEntity` / `NetworkEntityState` (authoritative hp) / `LocalTransform` -> `HudStateSystem`
(`SimulationSystemGroup`, after netcode drain and prediction in `InitializationSystemGroup`;
compares before writing, position quantized to 0.1 - `HudState.cs:25`) -> `HudState` singleton -> `HudBridgeSystem`
(`PresentationSystemGroup`, a pure `Convert` override of the package's `EcsViewModelBridge`) ->
`HudSnapshot` (readonly struct) -> `HudPresenter` (`IViewModelSink<HudSnapshot>`) -> `HudViewModel`
-> `HudView` / `HudView.uxml`.

- Host: `HudWorldBridge` (`[RequireComponent(typeof(UIDocument))]`, not DI-injected).
  `Update` polls the default world, builds the view, calls `HudEcsBootstrap.Install`, then
  `EcsSinkRegistration.Bind(bridge, presenter)` - registering enables the bridge and arms its
  one-shot catch-up push; then `enabled = false` (`Assets/Scripts/UI/Hud/Ecs/HudWorldBridge.cs:51-93`).
- Teardown (`HudWorldBridge.cs:95-105`): `registration.Dispose()` -> `HudEcsBootstrap.Uninstall(world)`
  -> `view.DestroySelf()`.
- Placement reasoning and the change-filter contract: `HudStateSystem.cs:21-31`.
- The assembly `NDC.Scripts.UI.Hud.Ecs` does not reference `NDC.Scripts.DI`; constants it shares
  with DI are duplicated deliberately (`HudStateSystem.cs:37-43`).

## DOTS presentation bridge (`Assets/Scripts/DI/Dots/DotsWorldBridge.cs`)

- Injected by `MainSceneScope`'s build callback (`[Inject] Construct`, lines 120-132); inert while
  `client == null`. `Update` installs once (`TryInstall`, 169-232), then ticks the binder.
- Install order: `DotsSimulationBootstrap.InstallSimulationSystems` -> catalog -> resolver +
  `DotsEntityView` -> `DotsNetcodeBootstrap.Install` -> `WorldViewBinder` -> optional
  `DotsPredictionBootstrap.Install` -> session modules -> `Reconnected` hook -> prewarm.
- Teardown (`OnDestroy`, 381-415) is the reverse: prediction, netcode with mirrors, session modules,
  catalog; then provider `Release` per catalog key (assets after instances). The dots view systems
  are root-scoped and stay.
- Prewarm is a `Task`; `TryFinishPrewarm` checks `IsCompleted` / `IsFaulted` each frame from
  `Update` instead of awaiting (lines 300-320) - frame-polling keeps the result on the main thread.

## Async seams

| Where | Type | Why |
|---|---|---|
| `MainSessionDriver.RunAsync` | `async UniTaskVoid` + `.Forget()` | entry point, owned CTS cancelled in `Dispose` (`MainSessionDriver.cs:57,92-95`, `Dispose` 117-136) |
| `MainSessionFlow.IEndpoint`, `RunAsync` | `Task` | `NDC.Scripts.Session` references nothing, not even UniTask; `MainSessionDriver.Endpoint` adapts with `async Task` wrappers (`MainSessionDriver.cs:139-185`) |
| Nakama services, `AddressableAssetLoader` | UniTask | `Assets/Scripts/Nakama/**`, `Assets/Scripts/UI/AddressableAssetLoader.cs` |
| `IViewAssetProvider`, `IViewPrefabLoader`, `LeasedViewAssetProvider` | `Task<GameObject>` | package interface `UnityDots/Runtime/Provisioning/IViewAssetProvider.cs:44`; main thread only |

No client code uses `Task.Run`, `ConfigureAwait` or a thread-pool switch; keep it that way for
anything touching Unity objects.

## Test templates

EditMode ECS lifecycle (`Assets/Tests/Editor/HudEcsLifecycleTests.cs:30-42`):

```csharp
[SetUp]    public void SetUp()    { this.world = new World("MyFixture"); }
[TearDown] public void TearDown() { if (this.world is { IsCreated: true }) this.world.Dispose(); }
// install via the production bootstrap, then update the groups/systems directly
// (world.GetExistingSystemManaged<SimulationSystemGroup>().Update(), bridge.Update(); lines 60,121)
```

PlayMode UI (`Assets/Tests/Runtime/HudViewBindingTests.cs:49-51,100-133`):

```csharp
[UnityTest]
public IEnumerator Binding_Works() => UniTask.ToCoroutine(async () => { /* await frames, assert */ });
```

`[UnityTest]` resets `LogAssert` state after `[SetUp]`, so set `LogAssert.ignoreFailingMessages`
from code the test body calls (`BuildPanelRoot`, `HudViewBindingTests.cs:46-51`), not in `[SetUp]`.

Presenters and flows need neither: plain NUnit against fakes (`HudPresenterTests`,
`MainSessionFlowTests`).
