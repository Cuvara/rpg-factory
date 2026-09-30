# UI and HUD procedure

Verified 2026-09-30. Sources: `docs/UI-ARCHITECTURE.md` (authoritative, set 2026-08-21),
`docs/HUD-BRIDGE.md`, `.github/workflows/uxml-codegen-drift.yml`, `Assets/Scripts/UI/Hud/`.

## Which technology

| UI | Technology | Where |
|---|---|---|
| Screens / application UI | UI Toolkit: UXML + USS + MVP + VContainer | `Assets/UI/Screens/<Name>/` per the contract; the tree does not exist yet (see below) |
| World-space / combat UI (HP bars, damage numbers, indicators, anything with a Transform, Animator, DOTween, VFX, pooled) | Prefab / uGUI - permanent, not legacy | prefab next to its feature |

## A new screen

1. Files (contract layout): `<Name>.uxml`, `<Name>.uss`, `I<Name>View.cs`, `<Name>View.cs`,
   `<Name>Presenter.cs`, `<Name>LifetimeScope.cs`, optional `<Name>ViewModel.cs`,
   `I<Name>Service.cs`/`<Name>Service.cs` if screen-specific. Reusable parts go to
   `UI/Components/` as `Component.uxml` + `.uss` + `ComponentView.cs` + `IComponentView.cs`.
2. Presenter derives from `com.cuvara.uitoolkit`'s `BaseUIToolkitScreenPresenter`, is registered
   with `RegisterScreen<TPresenter, TView>(key)`, opened via `IScreenNavigator`. Not the
   GameFoundation classes of the same names in `Packages/com.gdk.core` - those are orphaned.
3. Presenter depends only on `IThingView` + `IThingService`; no `UIDocument`, `VisualElement`,
   UXML, USS. Tested as plain C# with fakes (pattern `Assets/Tests/Editor/HudPresenterTests.cs`).
4. Lists use `ListView` virtualization; `RefreshItems()` for partial updates, `Rebuild()` only on
   source identity change. No per-frame UI work.
5. **Where the folder goes today:** `Assets/UI/` does not exist and has no asmdef; the one UI
   assembly `NDC.Scripts.UI` roots at `Assets/Scripts/UI/`, which is why the HUD lives at
   `Assets/Scripts/UI/Hud/` (`docs/HUD-BRIDGE.md` "Disk layout divergence"). Creating
   `Assets/UI/Screens/` needs a new asmdef + `.meta` and moving the HUD with it - ask the user
   before starting that tree; otherwise follow the HUD precedent under `Assets/Scripts/UI/<Name>/`.
6. Host: no screen flow is registered anywhere yet (`GameLifetimeScope` has no uitoolkit
   registration). Standing up the uitoolkit screen host is itself a wiring change - plan it,
   then the HUD's Presenter + `EcsSinkRegistration` move into a screen child scope
   (`docs/HUD-BRIDGE.md` "Host decision").

## UXML codegen

- Every enrolled `X.uxml` has `Generated/X.uxml.g.cs` committed, byte-exact to the generator.
  The Editor regenerates on UXML save. A `.uxml-namespace` file pins the namespace
  (`Assets/Scripts/UI/Hud/.uxml-namespace` = `Scripts.UI.Hud`).
- CI `uxml-codegen-drift.yml` runs on PRs touching `**/*.uxml`, `**/*.uxml.g.cs`,
  `Packages/packages-lock.json` (excluding `Assets/Samples/**`): it clones `com.cuvara.uitoolkit`
  at the commit `packages-lock.json` pins and runs
  `dotnet run --project <pkg>/Tools~/UxmlCodegenCli/UxmlCodegenCli.csproj -- <pkg> Assets`.
- Local reproduction is only meaningful with a UIToolkit checkout at the pinned commit; the
  workspace `UIToolkit/` clone may be at another commit, and `dotnet run` writes `bin/obj` into it.
  Default: leave it to CI and report HUMAN_REQUIRED (external).
- Renaming an element in UXML breaks compilation in `HudView.Bind`/`AssignQueries` - that is the
  intended failure, fix the View, not the generated file.

## HUD data path (do not bypass)

`NetworkEntity`/`NetworkEntityState`/`LocalTransform` -> `HudStateSystem` (Simulation group,
compares before writing, quantizes to 0.1) -> `HudState` singleton -> `HudBridgeSystem`
(Presentation group, pure `Convert`) -> `HudSnapshot` -> `HudPresenter` -> `HudViewModel`
(`BindableViewModel`) -> `HudView` / `HudView.uxml`. Host: `HudWorldBridge`
(`[RequireComponent(UIDocument)]`, not DI-injected). Teardown: sink first, then
`HudEcsBootstrap.Uninstall`, then the view.

Adding a HUD field: extend `HudState` (+ `IEquatable`), the aggregator, `HudSnapshot`, the
ViewModel property, the UXML element + regenerated binding, and the tests
(`HudSnapshotTests`, `HudPresenterTests`, `HudEcsLifecycleTests`, `HudViewBindingTests`).
Connection state is deliberately not in ECS; it belongs to a presenter subscribing to
`NetworkClient` events.
