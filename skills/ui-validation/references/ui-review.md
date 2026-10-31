# UI review checklist

Applied by `/rpg-factory:ui-review`, by factory-core step 11 when `ui-validation` is in `routing.tech`, and
by any review of a UI Toolkit change in the client. Each line is a yes/no question; a "no" is a finding with
the file and line. Paths starting `UIToolkit/` are the package repo at the tag the client pins; others are
`IndieRPGMMOAdventure/`. Every fact below was checked against UIToolkit `v0.8.0` on 2026-10-31.

## 1. References

- Every `<Style src>` and `<Template src>` in the changed `.uxml` resolves to a committed file (validator codes
  `FIG050`, `FIG051` for import folders; `UIToolkit/Documentation~/FIGMA-VALIDATION.md` "Rules").
- Every USS `url()` and `@import` resolves (`FIG040`); `project://database/Packages/...` is left to the
  package manager.
- New assets have their `.meta` files; no file was written inside a connector import folder (a folder holding
  `.figma-manifest.json`) except by the connector.

## 2. Bindings

- Each `Require<T>("name")` names an element that exists in the UXML with that type
  (`UIToolkit/Runtime/Utilities/VisualElementQueryExtensions.cs`).
- An enrolled UXML and its `Generated/<Name>.uxml.g.cs` change in the same commit; the generated file is not
  hand-edited; the namespace matches `.uxml-namespace` (`UIToolkit/Documentation~/UXML-CODEGEN.md`).
- No element name PascalCases to the class name, and no two names collide (codegen hard failures, same page,
  "Rules and conventions").
- Connector output (no `name` attributes): the game-owned view binds by type, document order or component class,
  once, and throws with the expected and found counts when the shape changes; nothing was added to the connector
  file. A PlayMode test clones the real imported UXML, builds the view and asserts every bound control; its result
  file is the evidence, re-run after each re-push (`skills/ui-toolkit-screen/references/imported-uxml.md`).

## 3. Lifecycle

- Presenter handlers go through `ScreenSubscriptions` (`Clicked`, `On<TEvent>`, `Add`); none is added with a bare
  `+=` that outlives the screen (`UIToolkit/Runtime/Flow/ScreenSubscriptions.cs`).
- An imported screen that links a mode sheet adds `theme.AttachScreen(View.Root)` to its subscriptions.
- Async work in `OnBindAsync` honours its `CancellationToken`; a dialog awaited there passes it on
  (`UIToolkit/Samples~/FigmaImport/ShopCardScreen.cs`).
- The presenter has no `UIDocument` or `VisualElement` field; it reaches the tree only through its view
  (`docs/UI-ARCHITECTURE.md`, "Testability").
- A test asserts zero live subscriptions after dispose (`LiveCount` or `AssertAllReleased`).

## 4. Theme (light and dark)

- Colours come from `--cuvara-*` or the game's tokens; a literal colour where a token exists is a finding
  (`FIG020` counts them in import folders).
- `RootUIDocument.themeOverrides` lists `tokens.uss` before the bridge sheet; the bridge holds aliases only
  (`UIToolkit/Documentation~/THEMING.md`, "Overriding from a game: the bridge sheet").
- Every mode sheet the game uses is registered (`RegisterModeSheets`) before a mode switch.
- Evidence: one screenshot per mode with the built-in dialog or toast visible when the screen uses them.

## 5. Responsive

- The screen's `PanelSettings` asset states its scale mode and reference resolution; nothing writes the shared
  asset at runtime (`UIToolkit/Runtime/Utilities/PanelScaleRatio.cs`, `CloneSettings`).
- Full-screen layouts that reach the screen edge sit inside `SafeAreaElement` on mobile targets
  (`UIToolkit/Runtime/Utilities/SafeAreaElement.cs`).
- Evidence: screenshots at two aspect ratios, one at or above 16:9 and one below (portrait too when the
  target is mobile), with the resolutions named.

## 6. Runtime

- In Play Mode the screen opens without an exception and the Console has no new error or warning.
- Every interactive control responds (click, Back through `BackNavigationSource`, close).
- No `SetActive` toggling and no second navigation system (`docs/UI-ARCHITECTURE.md`, "Navigation").

## 7. Tests and evidence

- EditMode and PlayMode counts per mode (`tests-run` or `results.xml`); zero executed is FAIL.
- Drift CLI exit code and summary line for enrolled UXML; validator JSON for each import folder.
- Each claim in the report names its artifact. Anything without one is NOT_RUN, HUMAN_REQUIRED or
  NOT_AVAILABLE, never PASS.
