# UI Toolkit and VContainer patterns

Verified 2026-10-21 against UIToolkit origin/main @ ac871bb (com.cuvara.uitoolkit 0.7.2) and the client
origin/develop @ c2cf32c. Paths:
`UIToolkit/...` for the package, client paths relative to `IndieRPGMMOAdventure/`. Design rules
(10 questions, layering) are the client's `docs/UI-ARCHITECTURE.md` "Before implementing anything" and
"Layers, and what each may know"; this page is
how the code does it.

## Layers of one screen

| Layer | Owns | Never |
|---|---|---|
| View (`BaseUIToolkitView`, `UIToolkit/Runtime/View/BaseUIToolkitView.cs:32`) | UXML, `SetBinding`, raising UI events | services, network, game state |
| ViewModel (`BindableViewModel`, `UIToolkit/Runtime/ViewModel/BindableViewModel.cs:44`) | display state as `[CreateProperty]` properties | logic, UI types |
| Presenter (`BaseUIToolkitScreenPresenter`, `UIToolkit/Runtime/Flow/BaseUIToolkitScreenPresenter.cs`) | subscriptions, calls into services, navigation | `UIDocument`, `VisualElement` (`docs/UI-ARCHITECTURE.md` "Layers, and what each may know") |
| Service (VContainer singleton) | domain state, network | anything UI (same section) |

## Binding

- ViewModel setters go through `Set(ref field, value)` (`BindableViewModel.cs:66-73`), which raises
  `propertyChanged` only on a real change; binding paths use `nameof` on `[CreateProperty]` properties (`:35-38`).
- The view sets `Root.dataSource = viewModel` once and binds each element:
  `Label.SetBinding(nameof(Label.text), ToTarget(nameof(Vm.LevelCaption)))`; converters for
  non-string targets such as `style.display` (`Assets/Scripts/UI/Gameplay/GameplayPanelView.cs:56-64`,
  `HudView.Bind`: `Assets/Scripts/UI/Hud/HudView.cs:38-58`).
- One-way only (`ToTarget`); writes go through the presenter, never `TwoWay`
  (`UIToolkit/Documentation~/HYBRID-DATA-BINDING.md` "MVP or binding? Per screen type"). Navigation is never a
  binding side effect (same doc, "What binds, what stays manual").
- `.uxml` edits regenerate `Generated/*.uxml.g.cs` through the codegen; commit both (client-integration rule).

## Lists and grids (virtualization)

- Use the package adapters: `UIToolkitListAdapter<TModel,TView,TPresenter>`
  (`UIToolkit/Runtime/Collections/UIToolkitListAdapter.cs:44,80`), `UIToolkitGridAdapter`
  (`UIToolkit/Runtime/Collections/UIToolkitGridAdapter.cs:37,71`), `UIToolkitMultiTemplateListAdapter`
  (`UIToolkit/Runtime/Collections/UIToolkitMultiTemplateListAdapter.cs:85,128`; `DynamicHeight` when rows
  differ, `:145`). They wire make/bind/unbind/destroy, give one presenter per visible row, dispose it in
  `DestroyItem` (`UIToolkitListAdapter.cs:151-160`), and null every callback on `Dispose` (`:215-230`). `SetItems` for a new source, `RefreshItems` for new
  contents of the same source.
- Pass a `fixedItemHeight` > 0 to get `FixedHeight` virtualization (`UIToolkitListAdapter.cs:88`).
- The client inventory list is hand-rolled (`MakeRow` / `BindRow`: `Assets/Scripts/UI/Gameplay/GameplayPanelView.cs:33-36,72-102`)
  and correct for its size; a new list uses an adapter or says why not.
- No per-frame UI work: refresh on events or a throttled tick
  (`StatsInterval`, 0.1 s: `Assets/Scripts/DI/GameplayPanelDriver.cs:49,164-165`).

## Screen flow and lifecycle

- Navigation is `IScreenNavigator` only (`UIToolkit/Runtime/Flow/IScreenNavigator.cs:49`; `PushAsync`,
  `ReplaceAsync`, `PopAsync`, `PopToRootAsync`, `HandleBack`: `:73-108`). Popups/modals are a registration option
  (`RegisterPopup`, `UIToolkit/Runtime/VContainer/ScreenFlowRegistration.cs:96-103`). Never GameFoundation's
  screen manager (client-integration rule).
- Presenter hooks: `OnBindAsync(ScreenSubscriptions, CancellationToken)`, `OnActivate`, `OnDeactivate`,
  `OnSuspend`, `OnResume`, `OnBackRequested` (`BaseUIToolkitScreenPresenter.cs:130-153`). The navigator owns
  the token; a presenter never creates or cancels its own CTS for screen work
  (`UIToolkit/Documentation~/LIFECYCLE-PLAN.md` "4.1 Cancellation — one token, one owner"). No `IStartable`
  for screen open logic ("0.1 What was verified, and against what"), no `ITickable` on a presenter
  ("8. Data binding — unchanged from v1"), no `async void` in `Runtime/Flow/` ("10. Failure modes, and
  what structurally prevents each").
- Subscriptions go through `ScreenSubscriptions`: `Clicked(button, handler)`, `On<TEvent>(element, cb)`,
  `Add(IDisposable)`; everything is undone on `Dispose` (`UIToolkit/Runtime/Flow/ScreenSubscriptions.cs:51-156`).
  Outside the flow (the gameplay panel), the presenter subscribes in its constructor and unsubscribes all
  of it in `Dispose` (`Assets/Scripts/UI/Gameplay/GameplayPanelPresenter.cs:55-60,91-98`).
- Test doubles: `UIToolkit/Runtime/TestSupport/` (`ScreenLifecycleRecorder`, `ScreenSubscriptionsAssertions`,
  `SpyViewModelSink`). Presenters and view models are plain NUnit; a live `UIDocument` needs PlayMode.

## Two ways game state reaches UI

| Path | When | Example |
|---|---|---|
| ECS bridge system -> presenter (sink) | the data is ECS component data each frame | HUD: `HudStateSystem` -> `HudBridgeSystem` -> `HudPresenter` (`ecs-and-async.md`) |
| VContainer service / `ITickable` driver -> presenter | the data lives in a service (netcode `WorldState`, inventory) | `GameplayPanelDriver` (`Assets/Scripts/DI/GameplayPanelDriver.cs:43,96`) |

Do not create ECS components only to feed UI, and do not read ECS from a presenter.

## VContainer

- **Scopes:** `GameLifetimeScope` (root, outlives scenes; networking, Nakama, content, DOTS,
  `Assets/Scripts/DI/GameLifetimeScope.cs:7-34`, registrations in `ClientRootInstaller.Install`,
  `Assets/Scripts/DI/ClientRootInstaller.cs:24-124`), `MainSceneScope` (`Assets/Scripts/DI/MainSceneScope.cs:6-13`; entry points
  `MainSessionDriver`, `GameplayPanelDriver` in `MainSceneInstaller.Install`, `Assets/Scripts/DI/MainSceneInstaller.cs:16-24`). Map: client-integration
  `references/composition.md`.
- **Lifetimes in use:** client Singleton x9, no Scoped/Transient; UIToolkit Singleton for flow services and
  `Scoped` presenters (`ScreenFlowRegistration.cs:30-53,78`). A new stateful service is a Singleton in the
  narrowest scope that outlives its users; a per-screen object is Scoped through `RegisterScreen`.
- **Scene objects** that a scene may lack are injected from a build callback
  (`RegisterBuildCallback` + `FindAnyObjectByType` + `container.Inject`, `Assets/Scripts/DI/ClientRootInstaller.cs:116-123`) - the
  one sanctioned lookup, at composition time only. `RegisterComponentInHierarchy` only where the component
  is guaranteed (`Assets/Scripts/Benchmark/Workload/BenchmarkLifetimeScope.cs:40`).
- **Entry points:** `IStartable` + owned CTS + `async UniTaskVoid ... .Forget()`, cancelled in `Dispose`
  (`MainSessionDriver.Start` / `RunAsync` / `Dispose`: `Assets/Scripts/DI/MainSessionDriver.cs:85-149`).
- **MessagePipe:** exactly one `RegisterMessagePipe()` (`Assets/Scripts/DI/Dots/DotsRegistration.cs:81-89`);
  new messages add a `RegisterMessageBroker<T>` there.
- **Never:** a static container or `LifetimeScope` cache (the client deleted its unused `DIExtensions` locator), `Resolve` from a MonoBehaviour's `Update`, injection into an ECS system (systems get
  managed state through singletons set by a bootstrap, `rpg-factory:unity-dots`).
