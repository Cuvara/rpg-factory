---
name: ui-figma-import
description: How a Figma frame becomes UI Toolkit UXML/USS in a Unity project through Unity's official UI Toolkit Connector for Figma (com.unity.ui.figma) and the com.cuvara.uitoolkit 0.8 integration around it - scoping the frame, the designer preflight (variables on components only, FIG023), the environment check, the headless import helper, the validator and its FIG0xx codes, the diagnostics window, profiles, token bridges, the mapping preset and mode sheets. Use when importing, analysing, validating or troubleshooting a Figma design for Unity UI. Not for writing UXML/USS or a Figma converter by hand (never), not for the screen's View/Presenter code (ui-toolkit-screen), choosing components (ui-component-selection) or validating the finished screen (ui-validation), and not for deciding scope, rules or gates (client-integration owns those).
argument-hint: "[figma frame url] [task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ui/figma_env.py:*)
---

# Figma to Unity UI Toolkit (official connector + com.cuvara.uitoolkit 0.8)

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first. Honour the declared Factory mode: in `analyze`, `plan` and `review` apply this skill's workflow, rules and checklist to produce the analysis, plan or findings - change nothing; in `validate` only run and grade checks.

> **Supporting skill, never the owner:** invoke the lead (and co-leads) from the snapshot's routing line
> first - here `client-integration`, `unity-package`. If you have not, stop and invoke it now: rules, gates, validation and the
> report come only from it. This skill adds how the technology works; it decides nothing.

Task: $ARGUMENTS

Paths `UIToolkit/...` are the package repo at the client's pin (inside a project: `Packages/com.cuvara.uitoolkit/`
or its `Library/PackageCache` entry). Docs: `Documentation~/FIGMA-INTEGRATION.md`, `FIGMA-VALIDATION.md`,
`TROUBLESHOOTING-FIGMA.md`, `FIGMA-REAL-IMPORT.md`. **The connector imports, the package integrates:** nothing here
converts Figma data, and no file under `Assets/Figma/<file>/` is ever written by hand.

## Applies when / Not when

- **Applies:** a Figma frame URL or file is to be imported, analysed for import, re-pushed, validated, or an
  imported screen breaks (FIG0xx, `cuvara.import.*`, `NullReferenceException` in `StyleVariableResolver`).
- **Not when:** the Unity side of the screen (view, presenter, registration: `rpg-factory:ui-toolkit-screen`),
  component choice (`rpg-factory:ui-component-selection`), final screen checks (`rpg-factory:ui-validation`),
  design artifacts without an import (`ui-ux`), or scope, rules and gates (`client-integration`, `unity-package`).

## Scope

Repo `client` (and any Unity project the user names, e.g. a lab). Owns no module, contract or check. Reads the
package repo `uitoolkit` read-only. The client pin must be v0.8.0 or later; older is a `pin-bump` follow-up.

## Architecture

- **Two halves.** The connector writes `Assets/Figma/<file>/` (screen and template `.uxml`/`.uss`, `tokens.uss`,
  `<mode>.uss`, `images/`, `.figma-manifest.json`). The package's Figma Editor assembly is gated on it:
  `CUVARA_UITOOLKIT_FIGMA` (`UIToolkit/Editor/Figma/Cuvara.UIToolkit.Editor.Figma.asmdef:16-24`) is set only when
  `com.unity.ui.figma` at or above that `versionDefines` floor is installed (proposed fact
  `uitoolkit-figma-connector-floor`). Without the connector the Figma menus are missing by design; the validator
  core (`Editor/FigmaCore/`) and ScreenCreator stay available.
- **Headless import** goes through Unity's Pipeline server: the helper reads `PORT_FILE`
  (`UIToolkit/Tools~/FigmaImport/figma-import.py:42`), queues `figma_import_url` (`:320`) and polls
  `figma_import_status` (`:344`). The Figma plugin performs the export, so it must be open on that file and paired.
  It saves the final result under `RESULT_FOLDER` (`:43`), `Library/CuvaraFigma/last-import-<file>.json`.
- **Validator:** `FigmaImportValidator.ValidateFolder` (`UIToolkit/Editor/FigmaCore/FigmaImportValidator.cs:53`), Unity-free,
  also compiled into the CLI verb `FigmaValidateCommand.Usage` (`UIToolkit/Tools~/UxmlCodegenCli/FigmaValidateCommand.cs:18-19`):
  `validate <importFolder> [--prefix p] [--max-inline N] [--max-absolute N] [--no-token-colors] [--json]`, exit 0/1/2.
- **Editor tools** (gated assembly): `FigmaDiagnosticsWindow.Open` (`UIToolkit/Editor/Figma/FigmaDiagnosticsWindow.cs:30-31`,
  Window > Cuvara > Figma Diagnostics), `RegenerateAllBridges` (`:38-39`), `ValidateAllProfiles` (`:54-55`),
  `FigmaMappingPresetCommand.ApplyFromMenu` (`UIToolkit/Editor/Figma/FigmaMappingPresetCommand.cs:47-48`, Tools > Cuvara >
  Figma > Apply Cuvara Mapping Preset), `FigmaProfile` (`UIToolkit/Editor/Figma/FigmaProfile.cs:19-20`, Assets > Create >
  Cuvara > UI Toolkit > Figma Profile).
- **Runtime theme:** imported screens link their own mode sheet; `ICuvaraThemeService.RegisterModeSheets`
  (`UIToolkit/Runtime/Theme/ICuvaraThemeService.cs:40`) plus `AttachScreen` (`:53`) keep them on the current mode.

## Idioms

Workflow, in order. Each step's result is a state (PASS, FAIL, BLOCKED, NOT_AVAILABLE, HUMAN_REQUIRED, SKIPPED).

1. **Scope.** Need a frame link with `node-id=` (Copy link to selection). With Figma MCP: `create_session` for the file
   key, then `get_metadata` (frame tree, node ids), `get_screenshot` (the reference image), `get_variable_defs`
   (collections, modes, COLOR/FLOAT). Without it, or on "no edit access" (the MCP account is not the browser's Figma
   account): ask for the frame URL and a PNG export, or a file the MCP account can read; the preflight is then
   HUMAN_REQUIRED - say so. Import ONE frame (or a small set); list components, variables per mode, fonts, images.
2. **Designer preflight - report violations BEFORE any import** (FIGMA-INTEGRATION.md "Supported and unsupported
   Figma features"): variables bound only on component roots and single-text `<Role>/Label` components (a binding on a
   plain layer or as an instance override becomes inline `var()`, FIG023); the screen root's fill stays a literal;
   no auto-layout gap, grid, gradient, frame shadow, background blur or blend mode on the project's Unity (fact `unity-editor-version`; dropped or
   degraded); fonts present in the project or the connector's font map; vectors and icons become PNG (one per
   component); STRING/BOOLEAN variables never arrive; one USS class prefix per project; multiple modes need a paid plan;
   control components single-purpose and named exactly like the control (`references/connector-mapping.md`).
3. **Environment:** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ui/figma_env.py --project <unity project> [--json]`. It
   reports Unity, package version and source, helper, connector, Pipeline, port file (never the token), Allow
   Browser Clients, `mapping-asset` (needed by the preset; its class prefix), validator CLI and dotnet, each OK / NOT_AVAILABLE / HUMAN_REQUIRED with the exact fix. Add
   `--probe-pipeline` only to test the port (one localhost request). Stop on any required item that is not OK.
4. **Import** (writes into the user's project: get an explicit yes first). Headless:
   `python3 <pkg>/Tools~/FigmaImport/figma-import.py "<frame link>" --project <p> --output-folder Assets/Figma/<Name> --max-wait 400 --validate --json --cli dotnet <built>/UxmlCodegenCli.dll`
   (the flags of the real run; `--prefix` only once the connector prefix is set, else FIG010 on every class),
   or the user pushes from the plugin (Push selection). Exit 0 done and clean, 1 failed/expired/validator errors, 2
   port/connection/usage. Never fake an import by writing UXML/USS.
5. **Validate:** the helper's `--validate`, or the CLI on `Assets/Figma/<file>`; read Window > Cuvara > Figma
   Diagnostics and the saved result. Triage with the table below; fix the design in Figma and push again.
6. **Integrate:** one `FigmaProfile` per game or Figma file (connector folder, prefix, token roles, bridge folder and
   screens folder outside the connector folder, mode sheets); Apply Cuvara Mapping Preset (needs the connector's
   mapping asset); Regenerate Token Bridges; mode sheets through `RegisterModeSheets`/`AttachScreen`; Assets > Cuvara >
   Create Screen with Source `SourceExistingUxml` (`UIToolkit/Editor/ScreenCreator/ScreenCreatorWizard.cs:28`) into a
   game-owned folder. Then hand off to `rpg-factory:ui-toolkit-screen` and `rpg-factory:ui-validation`.
7. **Report:** file key, node ids, Unity / connector / Pipeline / package versions (diagnostics window or figma_env),
   import state and code, validator counts by code, connector facts, what rendered and what did not, each with its
   evidence (saved result path, validator JSON, screenshots). Never claim SafeArea emission, shadow or gradient as
   verified, and never typed node-id bindings (gap G4, deferred).

| Finding | Meaning | Action |
|---|---|---|
| FIG023 | `var()` in an inline style: `CloneTree` throws on the project's Unity | hard blocker: rebind on a component in Figma, push again |
| FIG020 / FIG021 | literal colour / their count | bind on a component, or accept (screen root) |
| FIG022 | token with no definition | variable name or type (TROUBLESHOOTING-FIGMA.md "Tokens do not resolve") |
| FIG010 | class without the profile prefix | set the connector prefix, push again |
| FIG001-007, FIG050/051 | manifest, files or sheets missing or malformed | restore from version control or push again |
| FIG030-032 | inline-style or absolute-position budget | turn repeated parts into components, use auto layout |
| FIG040 / FIG041 | unresolved `url()` / folder outside a project | push again (moved folder) / validate inside the project |
| `cuvara.import.fact.*` | connector finding (`MissingFonts`, `MultiMode`, ...) | report it; fix fonts or design |
| `DroppedGap` | auto layout gap dropped on 6000.3 | spacing in a game-owned sheet, never in the connector file |
| `DiscardedLayers` | a leaf control dropped non-decoration layers | keep control components single-purpose; re-push |
| `NearMissNames` | names with a control word that mapped to no control | advisory: compare with the UXML element counts |
| `ui:Tab` without `ui:TabView` | tabs not grouped (no fact may say so) | plain buttons in code, or a game-owned wrapper UXML |
| request `expired`, `file_not_open`, `ambiguous_file` | plugin not open on that file, stale slug, duplicate names | user action in Figma |

## Pitfalls

- **Inline `var()` breaks the screen at clone time,** not at import: the import says `done`, the validator says FIG023
  `InlineStyleVariable` (`UIToolkit/Editor/FigmaCore/FigmaImportValidator.cs:36`); recorded: 11 x FIG023 on a real
  import (`FIGMA-REAL-IMPORT.md` "Import 1: variables bound on plain layers").
- **The helper's default validator command writes into the package.** `run_validator`
  (`UIToolkit/Tools~/FigmaImport/figma-import.py:243-250`) runs `dotnet run --project <pkg>/Tools~/UxmlCodegenCli`, which
  creates `obj/` and `bin/` there - a read-only PackageCache fails, a `file:` checkout gets polluted. Copy
  `Tools~/UxmlCodegenCli`, `Editor/FigmaCore` and `Editor/Codegen/Core` to a scratch folder, `dotnet build -o <dir>`
  once, and pass `--cli dotnet <dir>/UxmlCodegenCli.dll`.
- **The lab script takes a checkout, not a git URL:** `build_manifest`
  (`UIToolkit/Tools~/FigmaLab/create-lab-project.py:68-70`) writes `file:<abspath>`. Export the tag first
  (`git -C UIToolkit archive <tag>`) and pass that folder.
- **ScreenCreator refuses a connector folder:** `IsInsideConnectorImportFolder`
  (`UIToolkit/Editor/ScreenCreator/ScreenCreatorPlan.cs:115`) walks up looking for `.figma-manifest.json`.
- **Plugin pushes leave no saved result:** only the helper writes `Library/CuvaraFigma/`; for a push, the
  connector window's Last import section is the only record (`TROUBLESHOOTING-FIGMA.md` "The saved import result reports a problem").
- **No element names:** connector output has no `name` attributes (0 in the real import), so `Require<T>("name")`
  finds nothing (`TROUBLESHOOTING-FIGMA.md` "The imported screen has no element names"). Bind by type and order or
  by component class in a game-owned presenter (`rpg-factory:ui-toolkit-screen`); never add names to the connector file.
- **Tabs lose their TabView** unless every meaningful child of the tray is tab-like: `IsTabGroup` in
  `com.unity.ui.figma/Editor/Mapping/ControlMap.cs` (0.3.0-exp.1); real import: 3 `ui:Tab` in a plain row
  (`docs/architecture/ui-figma-real-test.md` "Evidence"). Details: `references/connector-mapping.md`.

## Testing

- Plugin side: `env -u TMPDIR tests/ui-figma-env.test.sh` (fixture projects, no Unity, no network).
- Package side, no Unity: `python3 Tools~/FigmaImport/test_figma_import.py` (mock Pipeline) and the validator fixtures
  `Tools~/UxmlCodegenCli/Fixtures/figma/{good,bad}` with `--prefix rpg --max-inline 5 --max-absolute 1`: good 0 errors,
  bad 7 errors 8 warnings (FIGMA-VALIDATION.md "Fixtures and CI"). Run them from an exported copy, not in the repo.
- Real import: `docs/architecture/ui-figma-real-test.md` (Unity, Figma and the plugin: HUMAN_REQUIRED until the user
  has them open).

## Tools

- `figma-mcp`: scope, screenshots and variables of the frame (step 1). A claude.ai connector server can show
  MISSING in the snapshot while it works in the session; fallback: the user's frame URL and a PNG export.
- `unity-mcp`: Console and Play-mode screenshots (step 5), when the Editor is open; fallback: the user's
  screenshots and the saved result file. The Unity connector package itself is checked by `figma_env.py`, not a dev tool.
