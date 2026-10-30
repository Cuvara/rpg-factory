---
name: ui-validation
description: How to review and validate a UI Toolkit screen in the Unity client and grade it with evidence - UXML and USS references, element bindings, presenter lifecycle, light and dark theme, responsive layout and safe area, Play Mode render and console, EditMode/PlayMode tests, the UXML codegen drift check and the Figma import validator. Use when reviewing a UI diff, answering /rpg-factory:ui-review, or deciding which result state a UI claim may carry. Not for building the screen (ui-toolkit-screen), choosing components (ui-component-selection), running the Figma connector (ui-figma-import), or deciding scope, checks or gates (client-integration, unity-package, ui-ux own those).
argument-hint: "[task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checks/pin-status.py:*)
---

# UI validation and review (UI Toolkit, client)

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first. Honour the declared Factory mode: in `analyze`, `plan` and `review` apply this skill's workflow, rules and checklist to produce the analysis, plan or findings - change nothing; in `validate` only run and grade checks.

> **Supporting skill, never the owner:** invoke the lead (and co-leads) from the snapshot's routing line
> first - here `client-integration`, `unity-package`, `ui-ux`. If you have not, stop and invoke it now: rules, gates, validation and the
> report come only from it. This skill adds how the technology works; it decides nothing.

Task: $ARGUMENTS

Paths starting `UIToolkit/` are the package repo at the tag the client pins
(`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checks/pin-status.py`); other paths are the client repo
`IndieRPGMMOAdventure/`. The full review checklist (also what `/rpg-factory:ui-review` applies):
`references/ui-review.md`. Result states and their meaning are factory-core's; this skill says which
artifact can back each UI claim.

## Applies when / Not when

- **Applies:** reviewing or validating a screen, popup, theme or imported UI; writing the UI part of a
  validation table; answering whether a UI claim has evidence.
- **Not when:** implementing the fix (`rpg-factory:ui-toolkit-screen`), importing (`rpg-factory:ui-figma-import`),
  or choosing the checks and gates of the change (the lead and the Factory check runner).

## Scope

Repos `client`, `uitoolkit`. Owns no module, contract or check: the registry checks stay with the lead;
this skill adds the UI-specific evidence and how to read it.

## Architecture

Seven areas, each with the artifact that proves it. No artifact means no PASS.

| Area | What is checked | Evidence artifact |
|---|---|---|
| References | `<Style src>`, `<Template src>`, USS `url()`, `project://` paths resolve | Editor import with an empty Console, or validator JSON (import folders) |
| Bindings | every `Require<T>` name exists with that type; generated bindings match the UXML | Play Mode open without exception; drift CLI exit 0 |
| Lifecycle | subscriptions released, Show/Hide and close order legal | EditMode test result file |
| Theme | base, overrides and mode sheets attached; imported screens attached; no literal colour where a token exists | screenshot per mode; validator `FIG020` count |
| Responsive | PanelSettings scale mode and reference resolution; safe area where needed; two aspect ratios | two screenshots, resolutions named |
| Runtime | renders in Play Mode, Console clean, controls interactive | screenshot + Console log excerpt |
| Tests | EditMode/PlayMode counts; codegen drift; Figma validator | `results.xml` or `tests-run` output; CLI exit and summary |

- **Bindings fail loudly by design:** `Require` throws with the name and type
  (`UIToolkit/Runtime/Utilities/VisualElementQueryExtensions.cs:29-41`), so a wrong name shows as an exception the
  first time the view is constructed, not as a null later.
- **Lifecycle has test helpers:** `LiveCount` (`UIToolkit/Runtime/Flow/ScreenSubscriptions.cs:38`),
  `AssertAllReleased` (`UIToolkit/Runtime/TestSupport/ScreenSubscriptionsAssertions.cs:27`) and
  `IsLegalTransition` (`UIToolkit/Runtime/TestSupport/ScreenLifecycleRecorder.cs:75`).
- **Theme mechanics:** mode sheets are switched per root by `SetModeSheet` and inside imported screens only when
  attached, `AttachScreen` (`UIToolkit/Runtime/Theme/CuvaraThemeService.cs:109-116`); `SyncScreen` does nothing
  without registered mode sheets (`:136-138`).
- **Responsive mechanics:** scaling lives on the `PanelSettings` asset; `CalculateMatch`
  (`UIToolkit/Runtime/Utilities/PanelScaleRatio.cs:48-54`) picks width or height around
  `LandscapeStandardScreenRatio` (`:32`) and `PortraitStandardScreenRatio` (`:35`).
  `SafeAreaElement` (`UIToolkit/Runtime/Utilities/SafeAreaElement.cs:60-61`) is a UXML element with
  attributes `ConformX`, `ConformY` and `ApplyMode` (`:69-73`); `SafeAreaSource` (`:80`) is injectable for tests.
- **Figma validator:** `FigmaImportValidator.ValidateFolder` (`UIToolkit/Editor/FigmaCore/FigmaImportValidator.cs:53`),
  CLI verb `Verb` (`UIToolkit/Tools~/UxmlCodegenCli/FigmaValidateCommand.cs:16`); codes, options and exit codes:
  `UIToolkit/Documentation~/FIGMA-VALIDATION.md` "Rules" and "CLI". It expects a connector import folder (a
  missing `.figma-manifest.json` is `FIG001`); hand-written UXML is checked by import and Play Mode instead.

## Idioms

- **Grade, do not describe.** Each row of the UI table carries one state from factory-core's list and one
  artifact path. "Looks right" is not an artifact.
- **Play Mode run (Editor open):** enter Play Mode, open the screen, read the Console, take a Game view screenshot
  per theme mode and per aspect ratio, exit Play Mode. Name the scene, resolution and mode in the evidence.
- **Drift check without writing into a repo:** export the pinned tag and run the CLI from the copy (`dotnet run`
  writes `bin/` and `obj/` beside the project):
  `git -C UIToolkit archive <pin> | tar -x -C "$tmp/uitk"`, then
  `dotnet run --project "$tmp/uitk/Tools~/UxmlCodegenCli/UxmlCodegenCli.csproj" -- "$tmp/uitk" IndieRPGMMOAdventure/Assets`.
  Exit 0 = no drift, 1 = drift listed, 2 = missing root (`UIToolkit/Documentation~/UXML-CODEGEN.md` "5. Drift check in CI").
- **Validator on an import folder:** the same exported CLI with
  `validate <Assets/Figma/<file>> [--prefix <p>] --json`; keep the JSON as the artifact; errors fail the row.

## Pitfalls

- **Package tests never resolve a rendered colour;** a green theme test is not visual evidence
  (`UIToolkit/Documentation~/THEMING.md`, "Known gaps in verification"). Theme rows need screenshots.
- **Batchmode exit 0 proves nothing** when the session started with compile errors: no import runs and bindings
  stay stale (`UIToolkit/Documentation~/UXML-CODEGEN.md`, "Known limitation"). Read the log.
- **Inline `var()` crashes `CloneTree`** (`FIG023`, verified on the editor of registry fact `unity-editor-version`):
  a validator error, not a warning to waive (`UIToolkit/Documentation~/FIGMA-VALIDATION.md`, "Rules").
- **PanelSettings is a shared project asset:** writing `match` at runtime edits it on disk in the Editor;
  `CloneSettings` (`UIToolkit/Runtime/Utilities/PanelScaleRatio.cs:85`) exists for that. A diff on the asset after a
  Play Mode run is a finding.
- **SafeArea mapping, shadows and gradients from a real Figma import are not verified;** never grade them PASS
  from the import alone (`UIToolkit/Documentation~/FIGMA-REAL-IMPORT.md`, "Unsupported constructs").
- **A docs-only client PR runs no-op "Unity Tests"** (`.github/workflows/01-ci-docs.yml`); it is not test evidence.

## Testing

- **One test, Editor open:** the client's Unity MCP `tests-run` (EditMode, then PlayMode) as
  `rpg-factory:unity-client-tech` "Testing" describes; zero executed is FAIL.
- **Editor closed:** Unity tests, Play Mode, screenshots and Console rows are HUMAN_REQUIRED; give the user the
  exact steps. The drift CLI and the validator need only `dotnet` and still run.
- Client CI `uxml-codegen-drift.yml` runs the drift check on the PR; an absent run is NOT_RUN, not PASS.

## Tools

- `unity-mcp`: `tests-run`, `console-get-logs` and `screenshot-game-view` for the test, Console and screenshot
  rows. Down: HUMAN_REQUIRED with the steps for the user.
- `dotnet`: the UXML codegen drift check and the Figma validator CLI. Missing: NOT_AVAILABLE locally; CI
  `uxml-codegen-drift.yml` still runs the drift check.
