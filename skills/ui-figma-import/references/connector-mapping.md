# How the connector maps Figma layers to controls (verified by a real import)

What one real import showed. The import used connector `com.unity.ui.figma` 0.3.0-exp.1 on Unity 6000.3.9f1 with
com.cuvara.uitoolkit v0.8.0, on frame "Game Settings", node `3:59`, with 116 nodes. Evidence:
`docs/architecture/ui-figma-real-test.md` "Evidence", and the saved result
`Library/CuvaraFigma/last-import-<file>.json` in the lab project. Rules about connector behaviour come from the connector's
source at that version, `com.unity.ui.figma/Editor/Mapping/ControlMap.cs` (`ResolveUncached`, `NameConvention`,
`MeaningfulChildCount`, `IsTabGroup`) and `com.unity.ui.figma/Editor/Mapping/FigmaImportReport.cs`. They describe 0.3.0-exp.1
only. Re-check them when the connector version changes; they are not a guarantee for other versions.

## Controls are found by component name

- Without a designer tag or a mapping row, a **component or instance** becomes a control when its name normalises
  to a catalog control. The whole name counts, or one `/` segment of it: `Toggle`, `Slider`, `Dropdown` (becomes
  `DropdownField`), `Button` or `Button/Primary`, `Tab`, `<Role>/Label`. Plain frames are never guessed (`NameConvention`).
  Seen: 3 `ui:Button`, 2 `ui:Toggle`, 1 `ui:Slider`, 1 `ui:DropdownField`, 3 `ui:Tab` and 6 `ui:Label` in
  `GameSettings.uxml`. The connector put the component name into the class: `.toggle`, `.slider`, `.dropdown`,
  `.button-close`, `.button-primary`, `.button-secondary`, `.title-label`, `.body-label`, `.muted-label`, `.tab`.
- **A leaf control keeps only decoration.** RECTANGLE, ELLIPSE and VECTOR children are decoration. Any other child
  layer of a leaf control (Button, Toggle, Slider, DropdownField, Label) is dropped, and the result reports it as
  `DiscardedLayers`. Seen: x4, the `Knob` of 2 toggles, the slider's `Fill, Thumb`, and the dropdown's text `High ▾`.
- **A leaf with 2 or more meaningful children (TEXT, FRAME, GROUP, COMPONENT, INSTANCE) is not mapped.** It
  stays a `VisualElement` (`MeaningfulChildCount`). A child the control can take as its icon does not count.
- Designer preflight: keep control components single-purpose. A component holds one control's own parts, with the
  label as a separate `<Role>/Label` and the state visuals as variants. The row composition goes in a plain frame.

## Advisory facts

- `NearMissNames` lists component or instance names that contain a control word but resolved to no control. It lists
  layer names, for example `MusicToggle` and `CloseButton`. It is advisory: in this import the controls themselves still
  mapped. Compare it with the UXML element counts before you act. The stored result keeps at most 10 items
  (count 14, 10 listed; FIGMA-REAL-IMPORT.md "Connector commands").
- `DroppedGap` (x11 here): the auto layout gap is dropped on Unity 6000.3 (FIGMA-INTEGRATION.md). Spacing must come
  from a game-owned sheet: margins on the imported classes in the game's own USS, never in the connector file.
- `MultiMode` (Light, Dark: `light.uss`, `dark.uss`) and `MissingFonts` (Inter) behave as documented.

## Tabs need a TabView

- The 3 tabs imported as `ui:Tab` inside a plain `ui:VisualElement` row, with **no `ui:TabView` parent**. The
  connector promotes a container to TabView only when all of its meaningful children are tab-like (`IsTabGroup`).
  This import emitted no `TabsOutsideTabView` fact, so check the UXML for the grouping and do not rely on the fact
  list. With no TabView, either treat the tabs as plain buttons in the presenter (selection state is game code), or
  instantiate the screen from a game-owned UXML that wraps the tabs in a `TabView`.

## No element names in connector output

- The generated UXML has **no `name` attributes**: 0 in `GameSettings.uxml` (gap G4, still deferred). Code cannot
  call `Require<T>("name")` on connector output. Bind by type and document order, or by the component class (`.toggle`,
  `.button-close`), once, in a game-owned presenter, and fail clearly when the counts change. A re-push may reorder.
- Never edit the connector file to add names: the next push overwrites it. The binding pattern lives in
  `rpg-factory:ui-toolkit-screen`.

## Figma MCP account

- The Figma MCP server runs as the MCP account, which can differ from the Figma account in the browser where the
  plugin runs. In the run, `get_metadata`, `get_screenshot` and `get_variable_defs` all failed with "you don't have
  edit access to this file" on the browser account's file. The preflight is then HUMAN_REQUIRED: ask for a PNG
  export, or for the file to be shared with or duplicated to the MCP account. The import itself does not need MCP.

## Import flags that worked

```bash
python3 <pkg>/Tools~/FigmaImport/figma-import.py "<frame link with node-id=>" --project <p> \
  --output-folder Assets/Figma/<Name> --max-wait 400 --validate --json \
  --cli dotnet <scratch>/cli-bin/UxmlCodegenCli.dll
```

The validator CLI was built once from a scratch copy: `Tools~/UxmlCodegenCli` (without `Fixtures`), `Editor/FigmaCore`
and `Editor/Codegen/Core`, then `dotnet build <copy>/Tools~/UxmlCodegenCli/UxmlCodegenCli.csproj -o <scratch>/cli-bin`.
`--output-folder` applies only to the file's first import. `--cli` must come last.
