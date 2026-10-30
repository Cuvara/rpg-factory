---
name: ui-component-selection
description: How to discover and choose UI components for a screen or a need from the real com.cuvara.uitoolkit catalog (read from git at the client pin or a named ref) plus Unity's built-in UI Toolkit controls - reuse, configure, compose or missing, each choice with its source line. Use when a UI task needs controls, services or screen scaffolding (a settings, inventory, shop, quest, popup or HUD screen, a Figma frame's components) and before writing any new control. Not for building the screen (ui-toolkit-screen), Figma import (ui-figma-import), validation (ui-validation), deciding scope, rules or gates (client-integration, unity-package own those), or changing the package itself.
argument-hint: "[screen or need]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ui/ui_select.py:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ui/ui_catalog.py:*)
---

# UI component selection (com.cuvara.uitoolkit catalog + Unity built-ins)

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first. Honour the declared Factory mode: in `analyze`, `plan` and `review` apply this skill's workflow, rules and checklist to produce the analysis, plan or findings - change nothing; in `validate` only run and grade checks.

> **Supporting skill, never the owner:** invoke the lead (and co-leads) from the snapshot's routing line
> first - here `client-integration`, `unity-package`, `ui-ux`. If you have not, stop and invoke it now: rules, gates, validation and the
> report come only from it. This skill adds how the technology works; it decides nothing.

Task: $ARGUMENTS

Paths below are relative to the client repo `IndieRPGMMOAdventure/`; package paths start with `UIToolkit/`.

## Applies when / Not when

- **Applies:** the UI plan (`/rpg-factory:ui*`) lists this skill, or you are about to pick controls, services or a
  screen base for a UI change, or about to write a new control.
- **Not when:** building or wiring the screen (`ui-toolkit-screen`), importing Figma (`ui-figma-import`), validating
  (`ui-validation`), or deciding scope, rules, checks or gates (`client-integration`, `unity-package`, `ui-ux`).

## Scope

Repos `client`, `uitoolkit` (read-only here). Owns no module, contract or check. Output is a selection table the
lead and `ui-toolkit-screen` build from.

## Workflow

1. Run the selection, never a memory of the package:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py ui-components --json <request>` (the plan carries
   `components`), or directly `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ui/ui_select.py --screen <archetype>` /
   `--need <need>...` (archetypes: settings, inventory, popup, hud, quest-panel, shop, confirm). Add
   `--uitoolkit-ref <ref>` only when the task targets another tag; the default is the client pin.
2. Read the header first: ref, source (`arg`, `client-pin`, `latest-tag`) and every warning. A pin-behind warning
   means an entry absent at the pin needs a `pin-bump` follow-up before client code may use it.
3. Decide in this order, one row per need: **reuse** (a package type or service as is) > **configure** (a package
   type with options or attributes) > **compose** (Unity built-ins styled with `--cuvara-*` tokens) > **missing**.
   Never create a component the catalog has; prefer composing built-ins over a new custom control.
4. **missing:** name the owner from `owner_if_missing` - `unity-package` for a reusable package control,
   `client-integration` for a game-specific one - and stop for the user's decision before creating anything.
   `NOT_AVAILABLE` (no UIToolkit repo or unknown ref) is reported as is; nothing is guessed.
5. Hand the table (need, status, choice, evidence) to the lead and to `ui-toolkit-screen`. Each choice keeps its
   catalog `source` (`<path>:<line>@<ref>` or the Unity docs URL) as evidence.
6. Look up anything the recipes do not cover in the full catalog:
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ui/ui_catalog.py --kind package-service --kind package-uxml-element`.

## Architecture

- The catalog reads the UIToolkit git repo at a ref (`git ls-tree`, `git cat-file`), never the working tree or the
  client's embedded clone, so it shows what a pin really ships. The ref order is `--ref`, the client pin in
  `Packages/manifest.json`, then the highest `v*` tag.
- Package entries: public types under `Runtime/` (services such as `ConfirmDialog`, `ToastService`, `SettingsModel`,
  the navigator and theme service), `[UxmlElement]` controls with their `[UxmlAttribute]`s, USS class constants,
  `--cuvara-*` tokens from `UIToolkit/Runtime/Theme/Resources/CuvaraTheme.uss`, Editor menu items, `Tools~` scripts
  and `Samples~` UXML. Built-ins come from `scripts/ui/data/unity-builtins.json` with a docs URL each.
- Screens start from the presenter base `BaseUIToolkitScreenPresenter` (`UIToolkit/Runtime/Flow/BaseUIToolkitScreenPresenter.cs:35`)
  scaffolded by the `MenuItem` (`UIToolkit/Editor/ScreenCreator/ScreenCreatorWizard.cs:40`) "Assets/Cuvara/Create Screen".
- Recipes (need -> choices) are data in `scripts/ui/data/screen-recipes.json`; a choice absent from the catalog
  turns the need into `missing`.

## Idioms

- Confirmation is one static call: `ShowAsync` (`UIToolkit/Runtime/Flow/ConfirmDialog.cs:29`); toasts go through
  `Show` (`UIToolkit/Runtime/Flow/ToastService.cs:57`); closing is `PopAsync` (`UIToolkit/Runtime/Flow/IScreenNavigator.cs:85`)
  and Back arrives as `BackRequested` (`UIToolkit/Runtime/Input/BackNavigationSource.cs:57`).
- Settings data is `SettingsModel`: bind sliders to setters such as `SetMusicVolume` (`UIToolkit/Runtime/Flow/SettingsModel.cs:69`).
- Item grids are configured, not written: `UIToolkitGridAdapter` (`UIToolkit/Runtime/Collections/UIToolkitGridAdapter.cs:71`)
  over a built-in `ListView` with a cell template.
- The theme is applied with `Apply` (`UIToolkit/Runtime/Theme/ICuvaraThemeService.cs:23`); style composed built-ins by
  overriding `--cuvara-*` variables, as the remark on `CuvaraTheme` (`UIToolkit/Runtime/Theme/CuvaraTheme.cs:13`) asks.
- `SafeAreaElement` is configured in UXML (`apply-mode`, `conform-x`, `conform-y`), declared as `ApplyMode`
  (`UIToolkit/Runtime/Utilities/SafeAreaElement.cs:73`) and its neighbours.

## Pitfalls

- A custom control without `[UxmlElement]` cannot be created from UXML; the mapping preset rejects it at
  `UxmlElementAttribute` (`UIToolkit/Editor/Figma/FigmaMappingPresetCommand.cs:264`). The package has exactly one
  `[UxmlElement]` control (`UIToolkit/Runtime/Utilities/SafeAreaElement.cs:60`); do not assume others exist.
- A catalog read at a newer tag than the client pin lists types the client cannot compile against; the pin lives
  in `Packages/manifest.json` and the catalog header warns. Use the pin's catalog for client work.
- `SettingsModel` setters only raise `Changed`; nothing persists until `Save` (`UIToolkit/Runtime/Flow/SettingsModel.cs:56`).
- Renaming or restyling a package USS class breaks host styling silently (`UIToolkit/Runtime/Theme/CuvaraTheme.cs`);
  override the tokens instead.

## Testing

- Plugin side: `tests/ui-catalog.test.sh` (catalog and selection on a git fixture) and `tests/ui-commands.test.sh`
  (the UI plan). A selection is evidence of availability only; whether the screen works is `ui-validation`'s job.
- `NOT_AVAILABLE` in the header means no UIToolkit repo or ref was readable: report it, do not fill the table by hand.

## Tools

- No registry dev tool: the catalog and selection are plugin scripts (`factory-cmd.py ui-components`,
  `ui_select.py`, `ui_catalog.py`) that need only git and python3.
