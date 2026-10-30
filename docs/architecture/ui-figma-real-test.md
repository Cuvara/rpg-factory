# Real Figma-to-Unity integration test: "Game Settings"

> **Status: NOT YET RUN.** The Evidence section below is empty. Do not quote any result from this page until the Lead
> has filled every row with a state (PASS, FAIL, BLOCKED, NOT_AVAILABLE, HUMAN_REQUIRED, SKIPPED, NOT_RUN) and the
> evidence path behind it.

This procedure proves the rpg-factory UI path end to end on real tools: a Figma frame built to the
com.cuvara.uitoolkit 0.8 designer rule goes through Unity's official UI Toolkit Connector for Figma
(`com.unity.ui.figma` 0.3.0-exp.1) into a throwaway lab project, is validated, integrated with the package's
profile, token bridge, mapping preset and theme service, and shown in Play mode in light and dark.
The agent side is driven by the plugin (`/rpg-factory:ui-figma`, skills `ui-figma-import`, `ui-component-selection`,
`ui-toolkit-screen`, `ui-validation`) in a headless `claude -p` session.

It follows the package's own lab procedure (UIToolkit v0.8.0 `Documentation~/FIGMA-REAL-IMPORT.md` "Lab procedure"
and "Evidence checklist"). Nothing here touches the client repo or another project.

## Prerequisites (human)

| Item | Version or state |
|---|---|
| Unity | 6000.3.9f1 (the tested version) installed in Unity Hub |
| Figma | an account with edit access to a draft file; a paid plan for two variable modes (Free has one mode per collection) |
| Figma plugin | Community plugin **Unity UI Toolkit Connector** |
| .NET SDK | 10 (the validator CLI targets `net10.0`) |
| Python | 3.8 or later |
| Claude Code | logged in; this plugin checked out (the worktree under test) |

## 1. Figma test design: "Game Settings"

One frame, 390 x 844, named `GameSettings`, built to the designer rule (FIGMA-INTEGRATION.md "Supported and
unsupported Figma features"): **variables are bound only on component roots and on single-text `<Role>/Label`
components; plain layers keep literals; the screen root's fill is a literal.**

Variables (collection `Theme`, modes `Light` and `Dark`; COLOR and FLOAT only - STRING and BOOLEAN never import):

| Variable | Light | Dark |
|---|---|---|
| `Surface/Background` | `#F4F1EA` | `#14161A` |
| `Surface/Panel` | `#FFFFFF` | `#22262D` |
| `Text/Primary` | `#1B1D21` | `#F2F2F2` |
| `Text/Muted` | `#5E636B` | `#A3A9B3` |
| `Accent/Primary` | `#2F6FEB` | `#5B8DFF` |
| `Radius/Panel` | 12 | 12 |
| `Space/Padding` | 16 | 16 |

Components (each root binds its own variables; inner layers stay unbound):

| Component | Root binding | Contents | Expected Unity control |
|---|---|---|---|
| `Title/Label` | text colour `Text/Primary`, text style Title | one text layer | `ui:Label` (name convention) |
| `Body/Label` | text colour `Text/Muted`, text style Body | one text layer | `ui:Label` |
| `Panel` | fill `Surface/Panel`, radius `Radius/Panel`, padding `Space/Padding` | auto layout, vertical | `VisualElement` with a class |
| `Button` | fill `Accent/Primary`, radius | one text layer | `ui:Button` |
| `Toggle` | - | box + one text layer | `ui:Toggle` (record what the import produced) |
| `Slider` | - | track + handle | `ui:Slider` (record what the import produced) |
| `Dropdown` | fill `Surface/Panel` | one text layer + chevron icon | record the result; a near-miss name shows as `fact.NearMissNames` |
| `ConfirmDialog` | fill `Surface/Panel`, radius | `Title/Label`, `Body/Label`, two `Button` instances | design reference only: Unity uses the package's `ConfirmDialog.ShowAsync`, themed through the bridge |

Frame content, top to bottom, all auto layout without gap (gap is dropped on 6000.3; use padding):

1. Background: the frame root, literal fill `#F4F1EA` (expected: `FIG020` x1, accepted).
2. Header: `Title/Label` "Settings" and a close `Button` (icon "X" as a vector inside the component - becomes a PNG).
3. Section tabs: a tab container with tabs "Audio", "Graphics" (tabs outside their container show `fact.TabsOutsideTabView`).
4. `Panel` instance holding: `Toggle` "Music", `Toggle` "Sound", `Slider` "Volume", `Dropdown` "Graphics Quality".
5. Footer: `Button` "Apply" and `Button` "Cancel" (one component, used twice: the reusable-instance check).
6. A `ConfirmDialog` instance beside the frame (not inside it), for the visual reference.

Do not use: frame drop shadows, gradients, background blur, blend modes, grid layout, negative spacing, instance-level
variable overrides. Use a font that is in the lab project or record `fact.MissingFonts`. Rename the file to
`RpgFactory-GameSettings` before copying the link (the connector matches the file by the name slug in the link).

Capture: `Copy link to selection` on the frame (with `node-id=`) and a PNG export of the frame (`figma-frame.png`).

## 2. Lab project

The lab script takes a package **checkout** and writes `file:<abspath>` (`Tools~/FigmaLab/create-lab-project.py`,
`build_manifest`); it does not accept a git URL. Export the tag read-only, then create the lab:

```bash
mkdir -p C:/tmp/rpgf-ui/lab/uitoolkit-v0.8.0
git -C C:/Workspaces/UnityIndie/UIToolkit archive v0.8.0 | tar -x -C C:/tmp/rpgf-ui/lab/uitoolkit-v0.8.0
python3 C:/tmp/rpgf-ui/lab/uitoolkit-v0.8.0/Tools~/FigmaLab/create-lab-project.py C:/tmp/rpgf-ui/lab/project \
  --package C:/tmp/rpgf-ui/lab/uitoolkit-v0.8.0
```

To test the git pin instead, edit the lab's `Packages/manifest.json` afterwards to
`"com.cuvara.uitoolkit": "https://github.com/Cuvara/UIToolkit.git#v0.8.0"` and record which form was used.

Build the validator CLI once, outside any package folder (`dotnet run` in the package would write `obj/` and `bin/` there):

```bash
dotnet build C:/tmp/rpgf-ui/lab/uitoolkit-v0.8.0/Tools~/UxmlCodegenCli/UxmlCodegenCli.csproj -o C:/tmp/rpgf-ui/lab/cli
```

(The build writes `obj/` into the exported copy, never into the UIToolkit repo.)

Open the project in Unity 6000.3.9f1, wait for the first compile (no Console error), enable Allow Browser
Clients if the lab script asks, restart the Pipeline server, **Window > UI Toolkit > Connector for Figma design >
Copy token**, and paste it within 60 s into the Figma plugin's Settings tab, then **Connect to Unity**. In Edit >
Project Settings > UI Toolkit > Connector for Figma design, **Create mapping**.

## 3. Agent run

Run each command from the lab folder with this plugin checkout loaded. Record each session's stream to a file.

```bash
P=<this plugin checkout>; L=C:/tmp/rpgf-ui/lab/project; E=C:/tmp/rpgf-ui/lab/evidence; mkdir -p "$E"
python3 -B "$P/scripts/ui/figma_env.py" --project "$L" --json --probe-pipeline > "$E/01-figma-env.json"
cd "$L" && claude --plugin-dir "$P" -p "/rpg-factory:ui-figma import <frame link> into the Unity project $L, prefix rpg" \
  --output-format stream-json --verbose > "$E/02-session-import.jsonl"
cd "$L" && claude --plugin-dir "$P" -p "/rpg-factory:ui-review review the imported GameSettings screen in $L" \
  --output-format stream-json --verbose > "$E/03-session-review.jsonl"
```

Expected agent behaviour (graded from the stream): the UI plan lists `ui-figma-import`, `ui-component-selection`,
`ui-toolkit-screen`, `ui-validation` in that order and no other UI skill; factory-core runs first; the designer
preflight is reported before the import; figma_env runs; the import uses
`Tools~/FigmaImport/figma-import.py ... --validate --prefix rpg --json --cli dotnet C:/tmp/rpgf-ui/lab/cli/UxmlCodegenCli.dll`;
the agent asks before writing into the project; no UXML or USS is written by hand; the report names states with evidence.

Then, in the Editor (by the agent through the Unity MCP server when available, else by hand):

1. Assets > Create > Cuvara > UI Toolkit > Figma Profile: connector folder `Assets/Figma/RpgFactory-GameSettings`,
   prefix `rpg`, bridge folder `Assets/Game/UI/Theme`, screens folder `Assets/Game/UI/Screens`, mode sheets
   `light.uss`, `dark.uss`; map at least `--cuvara-color-surface`, `--cuvara-color-primary` and the text roles.
2. Tools > Cuvara > Figma > Apply Cuvara Mapping Preset; Tools > Cuvara > Figma > Regenerate Token Bridges.
3. Assets > Cuvara > Create Screen, Source **Existing UXML (e.g. Figma import)**, the imported `GameSettings.uxml`,
   output `Assets/Game/UI/Screens`.
4. A scene with a `RootUIDocument` (`themeOverrides` = `tokens.uss`, `cuvara-theme-bridge.uss`; `themeModeSheet` =
   `light.uss`), the screen registered with its `AssetKey`, `RegisterModeSheets(light, dark)` and `AttachScreen`.
5. Play mode: screenshot light; switch to dark; screenshot; open `ConfirmDialog.ShowAsync` from Apply; screenshot.
6. Run the package's EditMode tests in the lab (Test Runner, or batchmode with the human gate `unity-batch`).

## 4. Evidence to capture

Store everything under `C:/tmp/rpgf-ui/lab/evidence/` and list the paths in the Evidence table.

- `figma-frame.png` (Figma export) and the frame link (file key, node id).
- `01-figma-env.json` and the two session streams.
- The saved import result `Library/CuvaraFigma/last-import-RpgFactory-GameSettings.json` (copy) and the helper's stdout JSON.
- Validator JSON: `dotnet C:/tmp/rpgf-ui/lab/cli/UxmlCodegenCli.dll validate <lab>/Assets/Figma/RpgFactory-GameSettings --prefix rpg --json`.
- Figma Diagnostics window screenshot (versions, mapping, profile, token coverage, bridge freshness, last import result).
- Console log after import and after Play (no error expected; any warning listed).
- Play-mode screenshots: light, dark, dark with ConfirmDialog.
- Test results XML or Test Runner screenshot with counts.
- `git status` (or file times) of the lab after a second push: only connector files changed.

## Evidence

> NOT YET RUN - every row below is a placeholder for the Lead.

Run date: `<YYYY-MM-DD>` - Lead: `<name>` - plugin commit: `<sha>`

| Item | Value |
|---|---|
| Unity version | `<fill>` |
| `com.unity.ui.figma` / `com.unity.pipeline` | `<fill>` / `<fill>` |
| `com.cuvara.uitoolkit` (source: file export or git `#v0.8.0`) | `<fill>` |
| Figma plugin version | `<fill>` |
| Figma file key / frame node id | `<fill>` / `<fill>` |

| # | Check | Expected | Evidence path | State |
|---|---|---|---|---|
| 1 | figma_env | status OK (figma-plugin HUMAN_REQUIRED is informational) | `01-figma-env.json` | NOT_RUN |
| 2 | UI plan | skills in order, no extra UI skill, lead `client-integration` | `02-session-import.jsonl` | NOT_RUN |
| 3 | Preflight before import | designer-rule findings reported first | `02-session-import.jsonl` | NOT_RUN |
| 4 | Import | state `done`, `ok` true; files listed | saved result, helper stdout | NOT_RUN |
| 5 | Validator | 0 errors, no `FIG023`; `FIG020` x1 for the literal background | validator JSON | NOT_RUN |
| 6 | Connector facts | every dropped or degraded feature listed (`DroppedGap`, `MissingFonts`, ...) | saved result | NOT_RUN |
| 7 | Hierarchy | header, tabs, panel controls, footer in Figma order | `.uxml`, UI Toolkit Debugger | NOT_RUN |
| 8 | Control mapping | Button, Toggle, Slider, Label, tabs, dropdown: what each became | `.uxml`, diagnostics mapping section | NOT_RUN |
| 9 | Reusable instance | `Button` template used by close, Apply and Cancel with the `rpg-` class | `.uxml`/`.uss` | NOT_RUN |
| 10 | Tokens and bridge | `tokens.uss`, `light.uss`, `dark.uss`; bridge fresh; no unknown token | bridge file, diagnostics | NOT_RUN |
| 11 | ScreenCreator | View and Presenter in `Assets/Game/UI/Screens`, no UXML/USS written | generated files | NOT_RUN |
| 12 | Play mode light | screen renders, no exception | screenshot, Console | NOT_RUN |
| 13 | Play mode dark | imported screen and ConfirmDialog switch | screenshots | NOT_RUN |
| 14 | ConfirmDialog | package dialog, themed by the bridge | screenshot | NOT_RUN |
| 15 | Tests | EditMode package tests pass (count) | results | NOT_RUN |
| 16 | Re-push | only connector files rewritten; profile, bridge and screens untouched | `git status` / file times | NOT_RUN |
| 17 | Not claimed | SafeArea emission, shadows, gradients, typed node-id bindings: not verified here | - | NOT_RUN |

Limitations found during the run: `<fill>`
