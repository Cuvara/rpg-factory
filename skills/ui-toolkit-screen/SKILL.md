---
name: ui-toolkit-screen
description: How a screen or popup is built on com.cuvara.uitoolkit 0.8 in the Unity client - ScreenCreator (new or existing UXML), presenters and ScreenSubscriptions, ScreenRegistry and VContainer RegisterScreen/RegisterPopup, IScreenNavigator push/pop/replace with ScreenOptions and Back, Require<T> and the opt-in UXML codegen, SettingsModel, ConfirmDialog, ToastService and the theme service. Use when implementing, integrating or analysing a UI Toolkit screen, popup or its theme wiring in IndieRPGMMOAdventure. Not for picking components (ui-component-selection), running the Figma connector (ui-figma-import), validation evidence (ui-validation), design artifacts (ui-ux) or changing the package itself (unity-package).
argument-hint: "[task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checks/pin-status.py:*)
---

# UI Toolkit screens on com.cuvara.uitoolkit 0.8

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first. Honour the declared Factory mode: in `analyze`, `plan` and `review` apply this skill's workflow, rules and checklist to produce the analysis, plan or findings - change nothing; in `validate` only run and grade checks.

> **Supporting skill, never the owner:** invoke the lead (and co-leads) from the snapshot's routing line
> first - here `client-integration`, `unity-package`. If you have not, stop and invoke it now: rules, gates, validation and the
> report come only from it. This skill adds how the technology works; it decides nothing.

Task: $ARGUMENTS

Paths starting `UIToolkit/` are the package repo, read at the tag the client pins; other paths are the client
repo `IndieRPGMMOAdventure/`. Client layers, folders and the codegen CI: `rpg-factory:client-integration`
(its UI and HUD procedure); general UI Toolkit, VContainer and async rules: `rpg-factory:unity-client-tech`.

## Applies when / Not when

- **Applies:** writing or reviewing a View, Presenter, screen registration, navigation call, theme or mode
  wiring, a `ScreenCreator` run, or mapping how an existing project's UI is built (analyze mode: read only).
- **Not when:** deciding which module, rules, checks or gates apply (`client-integration`, `unity-package`);
  choosing components (`rpg-factory:ui-component-selection`); importing from Figma
  (`rpg-factory:ui-figma-import`); grading the result (`rpg-factory:ui-validation`).

## Scope

Repos `client`, `uitoolkit`. Owns no module, contract or check. A missing package API is a `unity-package`
hand-off, never a client copy.

## Architecture

- **Pin first.** Code against the tag the client pins (`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checks/pin-status.py`).
  The theme service, mode sheets and ScreenCreator's "Existing UXML" source arrived in 0.8.0
  (`UIToolkit/Documentation~/MIGRATION-0.8.md` "Summary"); on an older pin they are a `pin-bump` follow-up.
- **ScreenCreator** is `ScreenCreatorWizard.OpenWindow` (`UIToolkit/Editor/ScreenCreator/ScreenCreatorWizard.cs:40-41`),
  menu `Assets/Cuvara/Create Screen`, types Screen, Popup, Item. The file list comes from
  `ScreenCreatorPlan.Build` (`UIToolkit/Editor/ScreenCreator/ScreenCreatorPlan.cs:53`): with source
  `ExistingUxml` it writes only `<Name>Screen.cs` (`:63-77`); with `NewUxml` it adds `.uxml` and `.uss` (`:79-94`);
  both add `PresenterTests` (`:101-103`). It refuses an output folder inside a connector import folder,
  `IsInsideConnectorImportFolder` (`UIToolkit/Editor/ScreenCreator/ScreenCreatorWizard.cs:193`), and never overwrites a
  file, `TryWriteFile` (`:231-237`).
- **Presenter** derives from `BaseUIToolkitScreenPresenter` (`UIToolkit/Runtime/Flow/BaseUIToolkitScreenPresenter.cs:35`)
  and writes `OnBindAsync` (`:130`), or the model variant `OnBindAsync` (`:178`). Popups derive from
  `BaseUIToolkitPopupPresenter` and call `Close` (`:198`). `View` and `Nav` throw when read before the flow
  attached them (`:52-59`). Back goes to `OnBackRequested` (`:153`).
- **Subscriptions:** every handler goes through `ScreenSubscriptions`: `Clicked` (`UIToolkit/Runtime/Flow/ScreenSubscriptions.cs:84`),
  `On<TEvent>` (`:94`), `OnFirstGeometry` (`:119`), `Add` for any `IDisposable` (`:51`); the flow disposes
  them in reverse order, `Dispose` (`:156-163`).
- **Registration (VContainer):** `RegisterUIToolkit` (`UIToolkit/Runtime/VContainer/UIToolkitRegistration.cs:55-59`) registers
  `RootUIDocument` from the hierarchy, the view factory and `ICuvaraThemeService`. `RegisterScreenFlow`
  (`UIToolkit/Runtime/VContainer/ScreenFlowRegistration.cs:28-55`) adds the registry, scope factory and navigator.
  `RegisterScreen` (`:71-84`) registers the presenter `Scoped` and the key in `ScreenRegistry`;
  `RegisterPopup` (`:96-103`) always adds `Modal`. One registration per presenter: `Register` throws on a
  second (`UIToolkit/Runtime/Flow/ScreenRegistry.cs:71-80`). The host also supplies an `IVisualTreeAssetLoader`
  (client: `Assets/Scripts/UI/AddressableAssetLoader.cs`).
- **Navigation:** `IScreenNavigator` (`UIToolkit/Runtime/Flow/IScreenNavigator.cs:49`): `PushAsync` (`:73-76`),
  `ReplaceAsync` (`:79-82`), `PopAsync` (`:85`), `PopToRootAsync` (`:88`), `HandleBack` (`:108`).
  `ScreenOptions` (`UIToolkit/Runtime/Flow/ScreenOptions.cs:26-70`): `Modal`, `DimsBelow`, `CloseOnTapOutside`,
  `Retain`. Back: `BackNavigationSource.BackHandler` (`UIToolkit/Runtime/Input/BackNavigationSource.cs:72`) set to
  the navigator's `HandleBack` (`UIToolkit/Samples~/LoadingFlow/LoadingFlowSample.cs:443`).
- **Theme:** `ICuvaraThemeService` (`UIToolkit/Runtime/Theme/ICuvaraThemeService.cs:20-53`): `Apply`, `AddOverride`,
  `RegisterModeSheets`, `SetModeSheet`, `AttachScreen`. `RootUIDocument` serialises `applyTheme`
  (`UIToolkit/Runtime/Managers/RootUIDocument.cs:62`), `themeOverrides` (`:65`) and `themeModeSheet` (`:68`) and applies
  the theme when its layers resolve, `Apply` (`:176`). Tokens are the `--cuvara-*` variables in
  `UIToolkit/Runtime/Theme/Resources/CuvaraTheme.uss` (`UIToolkit/Documentation~/THEMING.md` "Tokens").
- **Views start invisible:** the base constructor calls `UpdateAlpha` with 0 (`UIToolkit/Runtime/View/BaseUIToolkitView.cs:52`);
  `Open` (`:72`) or `Show` (`:88`) reveals the view; `StretchToParent` (`:120`) fills the layer.

## Idioms

- Typed queries: `Require` (`UIToolkit/Runtime/Utilities/VisualElementQueryExtensions.cs:29-41`) throws with the
  element name and type; keep `Q<T>` only for optional elements.
- UXML codegen is opt-in: enrol once with `Assets/Cuvara/Generate UXML Bindings`; `Generated/<Name>.uxml.g.cs`
  regenerates on save and is never hand-edited; the namespace comes from `.uxml-namespace`
  (`UIToolkit/Documentation~/UXML-CODEGEN.md` "Rules and conventions"; client precedent
  `Assets/Scripts/UI/Gameplay/Resources/Generated/GameplayPanelView.uxml.g.cs`).
- The client view pattern: `GameplayPanelView` (`Assets/Scripts/UI/Gameplay/GameplayPanelView.cs:22-30`) is a `partial`
  `BaseUIToolkitView` that calls `AssignQueries` in its constructor.
- Settings: `SettingsModel` (`UIToolkit/Runtime/Flow/SettingsModel.cs:9`) persists through PlayerPrefs, `Load`
  (`:44`) and `Save` (`:56`); `SetGraphicsQuality` clamps to 0-3 (`:71`); `Apply` pushes volume, quality,
  fullscreen and VSync to Unity (`:77-89`).
- Built-in dialogs: `ConfirmDialog.ShowAsync` (`UIToolkit/Runtime/Flow/ConfirmDialog.cs:29-34`) returns `false` on
  cancel or a cancelled token; `ToastService` (`UIToolkit/Runtime/Flow/ToastService.cs:33`) takes a parent element and
  `Show` (`:57`) a message, duration and `ToastType`. Parent both into `RootUIOverlayElement`, as
  `ConfirmDialog.ShowAsync` in `UIToolkit/Samples~/FigmaImport/ShopCardScreen.cs:135-140` does.
- **Connector output (imported UXML) has no `name` attributes:** bind by type and document order or by the
  component class (`root.Query<Toggle>().ToList()`, `root.Q<Button>(className: "button-close")`), once, in the
  view the presenter's bind step receives, and throw when a count changes (a re-push may reorder). Never add names
  to the connector file. View, settings mapping, `ConfirmDialog` and light/dark pattern: `references/imported-uxml.md`.
- An imported screen that links its own mode sheet stays on the current mode with
  `subs.Add(theme.AttachScreen(View.Root))`; the sample wraps it in `Track` (`UIToolkit/Samples~/FigmaImport/ShopCardScreen.cs:118`).

## Pitfalls

- **No screen host in the client yet.** `Assets/` registers neither `RegisterUIToolkit` nor `RegisterScreenFlow`;
  the gameplay panel builds its own `UIDocument` (`Assets/Scripts/DI/GameplayPanelDriver.cs`). Standing up the
  navigator is a wiring change the lead plans (client-integration's UI and HUD procedure, "A new screen"; `docs/HUD-BRIDGE.md` "Host decision").
- **Mode sheets inside imported screens win over the root.** Switching only the root leaves an open imported
  screen in the old mode unless it was attached (`UIToolkit/Documentation~/THEMING.md`, "Imported screens and
  their mode sheets").
- **Theme order:** `tokens.uss` must be in `themeOverrides` before the bridge sheet, or the bridge resolves
  nothing (`UIToolkit/Documentation~/THEMING.md`, "Overriding from a game: the bridge sheet").
- **Name clash:** a `StyleSheet` named `CuvaraTheme` in a game `Resources` folder can replace the package sheet
  (`UIToolkit/Documentation~/MIGRATION-0.8.md`, "1. Theme contract for the built-in UI").
- **Batchmode with compile errors never regenerates bindings** and still exits 0
  (`UIToolkit/Documentation~/UXML-CODEGEN.md`, "Known limitation").
- **`SettingsModel` has no music or sound on/off flag** - only volumes, `GraphicsQuality`, `Fullscreen`, `VSync`
  and `Language` (`UIToolkit/Runtime/Flow/SettingsModel.cs`); a mute toggle maps to game-owned state, never to an
  invented member.
- **Imported controls carry no range or choices:** set `Slider` range and `DropdownField` choices in code; the real
  "Game Settings" import carried neither (`references/imported-uxml.md`).
- **Wrong view type** in a registration fails at attach with both types named, `AttachViewCore`
  (`UIToolkit/Runtime/Flow/BaseUIToolkitScreenPresenter.cs:100-110`).

## Testing

- A presenter is plain C#: drive `OnBindAsync` with a fake view and a `ScreenSubscriptions`, then assert
  `LiveCount` (`UIToolkit/Runtime/Flow/ScreenSubscriptions.cs:38`) or `AssertAllReleased`
  (`UIToolkit/Runtime/TestSupport/ScreenSubscriptionsAssertions.cs:27`) after `Dispose`. ScreenCreator's skeleton
  asserts the same (`UIToolkit/Editor/ScreenCreator/ScreenCreatorTemplates.cs`, `OnBind_LeaksNothing`).
- Client EditMode tests live in `Assets/Tests/Editor` (pattern `Assets/Tests/Editor/HudPresenterTests.cs`); a live
  `UIDocument` needs PlayMode. How to run one test: `rpg-factory:unity-client-tech` "Testing". Grading and
  evidence: `rpg-factory:ui-validation`.

## Tools

- `unity-mcp`: ScreenCreator and the codegen menu run in the open Editor, behind the lead's asset-edit gate;
  Console for compile errors. Down: HUMAN_REQUIRED with the menu path for the user.
- Symbol lookup: the lead's `lsp-csharp`, fallback `git -C UIToolkit grep` at the pinned tag.
