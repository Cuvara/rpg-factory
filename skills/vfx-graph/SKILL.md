---
name: vfx-graph
description: How a VFX Graph effect is authored with com.cuvara.vfx in UnityVFX - the recipe (cuvara.vfx-recipe/1) and its ops, catalog before writing, describe to learn from existing graphs, build and apply, import-texture for generated textures, inspect, the agent-owned Sandbox opened with Tools~/setup-sandbox.py and driven through Tools~/vfxcli.py and unity-mcp-cli, deterministic capture and how to read its contact sheet and stats.json, and a review checklist for a VFX Graph effect. Use when you write, build, debug, capture or review an effect, a recipe, a .vfx graph, an imported effect texture, a Sandbox~ capture or the Samples~/Showcase scene, or record the capture evidence of a vfx-asset. Not for deciding scope, rules, checks or gates (unity-package, vfx own those), not for the vfx-style profile, specs or the delivery record's lifecycle (vfx), not for generating the texture itself (asset-gen), and not for the client's runtime use of an effect (client-integration).
argument-hint: "[task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*)
---

# VFX Graph effects with com.cuvara.vfx (recipe, build, Sandbox, capture)

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first. Honour the declared Factory mode: in `analyze`, `plan` and `review` apply this skill's workflow, rules and checklist to produce the analysis, plan or findings - change nothing; in `validate` only run and grade checks.

> **Supporting skill, never the owner:** invoke the lead (and co-leads) from the snapshot's routing line
> first - here `unity-package`, `vfx`. If you have not, stop and invoke it now: rules, gates, validation and the
> report come only from it. This skill adds how the technology works; it decides nothing.

Task: $ARGUMENTS

Paths are relative to the UnityVFX repository root unless they start with `vfx/` (the authoring repo). Documents are
cited by section: `Documentation~/AUTHORING.md` (the built behaviour; it wins over `Documentation~/DESIGN.md`, and
its section "Differences from DESIGN.md" lists every gap), `Documentation~/CAPTURE.md`, `Documentation~/SHOWCASE.md`
and `Schemas~/`. Versions are registry facts: `unityvfx-editor-version`, `unityvfx-vfx-graph-version`,
`unityvfx-sandbox-unity-mcp-version`.

## Applies when / Not when

- **Applies:** a new or changed effect under `Effects/<Name>/` (recipe, `.vfx`, prefab, `<Name>_<Purpose>.png`), a
  fixture under `Tests/Fixtures/`, a subgraph (`.vfxoperator`, `.vfxblock`), the verbs in `Editor/`, a Sandbox run,
  a capture, the Showcase, reviewing a graph, or the capture and lint evidence of a `vfx/assets/` record.
- **Not when:** which effect to make, its look and budgets (`vfx` and its style profile); package rules, checks,
  release and gates (`unity-package`); generating the source image (`asset-gen`); playing effects in the game client.

## Scope

Repos `unityvfx`, `authoring`. Owns no module, contract or check. Read-only on the authoring repo except what the
`vfx` lead's workflow asks for; writes in UnityVFX only on the `unity-package` leg.

## Architecture

- **One effect, one folder** (`Effects/README.md`): `<Name>.vfxrecipe.json` is the source of truth, `build` writes
  `<Name>.vfx` next to it, `<Name>.prefab` holds the `VisualEffect` a `VfxLibrary` entry points at, textures are
  `<Name>_<Purpose>.png`. Shared pieces (the `Library/Grid` stage materials, shared subgraphs) live in `Library/`.
- **Seven verbs behind one command** (`Documentation~/AUTHORING.md`, "Agent interface: `Tools~/vfxcli.py`"):
  `catalog`, `describe`, `build`, `apply`, `import-texture`, `inspect`, `capture`. The C# entry is
  `Cuvara.VFX.Editor.VfxCli.Run(verb, jsonArgs)` (`Editor/Cli/VfxCli.cs`); every result is
  `{"ok", "verb", "errors", "warnings", ...payload}` on stdout as UTF-8 JSON, progress on stderr. Exit 0 ok,
  1 `"ok": false` or the Unity call failed, 2 usage, 3 no editor available (the message names the fix).
- **Two run paths, same bytes:** editor (`--mode editor`, or `auto` when this clone's Sandbox editor runs) through
  `unity-mcp-cli run-tool script-execute <open path>` with arguments and result in files; batch (`--mode batch`, or
  `auto` with no editor) through a batch-mode editor with graphics, killed above the memory limit.
- **The bridge** `Editor/Bridge/` (assembly `Unity.Testing.VisualEffectGraph.Editor`, class `VfxGraphBridge`) is the
  only code that touches VFX Graph internals; recipe ops run through it (`VFXModel.AddChild`, `SetSettingValue`,
  `VFXSlot.Link`, `VFXContext.LinkTo`) and the asset is written by VFX Graph, never as YAML text.
- **The Sandbox** (`Sandbox~/`) is a committed URP + VFX Graph + Unity-MCP project that agents may open, drive and
  rebuild. It is always opened through the **open path** `<sandbox home>/Sandbox`, with the package linked at
  `<sandbox home>/package` (`Documentation~/AUTHORING.md`, "Never open `Sandbox~` directly: use the open path").
- **Capture** plays an effect in play mode in a code-built stage (grid ground and wall of `Library/Grid`, the
  Showcase's `VfxLightingRig` and `VfxCameraRig`) and writes `frame-<t>.png`, `contact-sheet.png` and `stats.json`
  (`cuvara.vfx-capture/1`). The Showcase (`Samples~/Showcase`) is the same look for a person's Play-mode review.
- **Who reads the evidence:** the `vfx` lead's `/rpg-factory:vfx-lint` reads the recipe, an `inspect` result and
  `stats.json` (`scripts/vfx/vfx_lint_rules.py` docstring) and the delivery record cites them.

## Idioms

The order of work (`Documentation~/AUTHORING.md`, introduction). Details: `references/recipe-format.md`,
`references/capture.md`, `references/vfxgraph-review.md`.

1. **Open the Sandbox** from the UnityVFX root: `python Tools~/setup-sandbox.py`, then
   `OPEN="$(python Tools~/setup-sandbox.py --print-open-path)"` and `python Tools~/setup-sandbox.py --open` (guarded
   start, waits for Unity-MCP). Prove the answering editor is the Sandbox before any `run-tool`:
   `script-execute` returning `Application.dataPath` and the PID must show `<open path>/Assets` and the PID `status`
   printed (`Documentation~/AUTHORING.md`, "Open, watch, check, drive, close"). One editor at a time.
2. **`catalog` first:** `python Tools~/vfxcli.py catalog --out catalog.json` (about 800 KB, once per session), or
   `--json '{"filter": "burst"}'`. Use its `type`, `variant.id`, setting and slot names (`inputs`/`outputs`
   `ref`), never names remembered from the graph window; `recipe_ops`, `recipe_op_fields`, `texture_steps` print
   the formats as the build reads them.
3. **`describe` to learn:** `vfxcli.py describe --json '{"asset": "<.vfx>"}'` gives stable ids (`c0`, `c0.b1`,
   `o2`, `p0`, `s0`) and slot addresses (`c1.b0._Position`, `o0.#0`). Read `Tests/Fixtures/BurstQuads` first;
   Unity's VFX Graph samples only from a gitignored scratch copy (Unity Companion License: never copy them in).
4. **Write the recipe, then `build`** (`vfxcli.py build --json '{"recipe": "Effects/<Name>/<Name>.vfxrecipe.json"}'`)
   or `apply` ops to an existing graph by describe ids. The first failing op stops the build with `op_error` and the
   valid names, nearest first: fix the name from the list, do not guess.
5. **Textures:** `vfxcli.py import-texture --args <file>.json` with `source` (the approved generated PNG), `target`
   `Effects/<Name>/<Name>_<Purpose>.png` and ordered `transform` steps; keep `source_sha256` and `output_sha256`
   for the delivery record.
6. **`inspect`** the `.vfx` or prefab for the static facts a lint judges (systems, capacities, outputs, blend,
   shader, textures and bytes, exposed properties, HDR colours) and keep it with `--out` for `vfx-lint --inspect`.
7. **`capture`** with a fixed seed (`vfxcli.py capture --json '{"effect": "...", "seed": 1234}'`), then **look at
   the contact sheet yourself** before reporting, and read `stats.json` (`references/capture.md`).
8. **Close** with `python Tools~/setup-sandbox.py --close`; never `unity-mcp-cli close` or `EditorApplication.Exit`.

- Paths: through `vfxcli.py` a path relative to the shell's directory works (rewritten to
  `Packages/com.cuvara.vfx/...` or `Assets/...`, logged on stderr); through `VfxCli.Run` give a project path.
- Compare graphs by `describe_sha256` (in `build`, `apply`, `inspect` results), never by `.vfx` file hash.
- Write `run-tool` input with a JSON library to a file and pass `--input-file <absolute path>`.
- After an editor start or a script change, wait for `rql-query editor | select isCompiling isUpdating` to be false;
  `wait-for-ready` answers before the import ends.

## Pitfalls

Each is a verified failure recorded in UnityVFX `Documentation~/AUTHORING.md`, section "Pitfalls" (sub-section named).

- **Never open the project at `Sandbox~`:** with a hidden path component no package script maps to a class (0 of 1333). Use `setup-sandbox.py --open` and the open path (`Documentation~/AUTHORING.md`, "Package scripts have no class when the project path has a hidden component").
- **Never make a link inside the repository to its root:** the editor's indexing walked the cycle and grew by gigabytes per second (`Documentation~/AUTHORING.md`, "A link cycle in the project made the editor grow by gigabytes per second").
- **Close only with `setup-sandbox.py --close`:** `EditorApplication.Exit` from a tool call reset the connection or never quit, and `unity-mcp-cli close` reports no editor for a linked path (`Documentation~/AUTHORING.md`, "Quitting with `EditorApplication.Exit` from a tool call"; "`unity-mcp-cli close` does not find an editor opened through a link").
- **The Unity-MCP plugin starts in Cloud mode** and `wait-for-ready` times out on HTTP 401; `setup-sandbox.py` pins a local server (`Documentation~/AUTHORING.md`, "The Unity-MCP plugin starts in Cloud mode").
- **Missing NuGet DLLs stop the first open at a dialog:** run `setup-sandbox.py --restore-nuget` (or `--open`), never a plain `unity-mcp-cli open` (`Documentation~/AUTHORING.md`, "Missing NuGet DLLs stop the first open at a dialog").
- **`script-execute` cuts a returned string at 20000 characters:** run verbs through `vfxcli.py`, which passes results in files; return only short values from your own snippets (`Documentation~/AUTHORING.md`, "`script-execute` cuts a returned string at 20000 characters").
- **Initialize forwards its data settings:** set `capacity` and `boundsMode` on the Initialize context; catalog lists them there (`Documentation~/AUTHORING.md`, "Catalog listed no settings for Initialize although `capacity` is set there").
- **The default `boundsMode` `Recorded` warns on every build:** set `Manual` with `bounds` (`center`, `size`) or `Automatic` (`Documentation~/AUTHORING.md`, "The default bounds mode warns on every build").
- **Two builds of one recipe differ in bytes:** new sub-asset file ids each write; compare `describe_sha256` (`Documentation~/AUTHORING.md`, "Two builds of the same recipe give different `.vfx` bytes").
- **A repository-relative path fails through `VfxCli.Run`:** the editor's directory is the project; use `vfxcli.py` or `Packages/com.cuvara.vfx/<path>` (`Documentation~/AUTHORING.md`, "A path relative to the repository is not found").
- **Do not judge an effect from edit mode or an unfocused editor:** a script-made `VisualEffect` stays culled in edit mode, and play mode does not advance without `runInBackground`; use `capture` (`Documentation~/AUTHORING.md`, "A `VisualEffect` made by a script in edit mode does not simulate"; "Play mode in an unfocused Sandbox editor does not advance").
- **`Random` `Uniform` on a vector attribute puts particles on a line:** use `PerComponent` for a spread in a box (`Documentation~/AUTHORING.md`, "`Random` `Uniform` on a vector attribute puts particles on a line").
- **Inline `--input` JSON with a Windows path loses an escape level:** write the input file with a JSON library (`Documentation~/AUTHORING.md`, "Inline `--input` JSON with a Windows path").
- **`rql-query console` keeps fixed compile errors:** ask `EditorUtility.scriptCompilationFailed`; count console errors only after a restart (`Documentation~/AUTHORING.md`, "The console still shows a compile error that is fixed").
- **`aliveParticleCount` lags by up to 60 frames:** never read counts yourself; `capture` holds the effect for `settle_frames` (min 62) before each read (`Documentation~/AUTHORING.md`, "`aliveParticleCount` lags by up to 60 frames").
- **Gradient keys are linear values stored as written:** do not convert from sRGB; a graph below the current resource version gets its keys converted at compile, so `build` fails on the upgrade warning and `apply` warns (`Documentation~/AUTHORING.md`, "Gradient colours of a built graph changed at the first compile").
- **Material colour properties are sRGB** in the linear Sandbox (0.5 renders as 0.214 linear): read every material colour as sRGB (`Documentation~/AUTHORING.md`, "Material colour properties are sRGB values in the linear Sandbox").
- **A `VfxPlayer` library set by script was lost on save:** set it through `SerializedObject.FindProperty("library")` and check the saved scene (`Documentation~/AUTHORING.md`, "A `VfxPlayer`'s library set by a script was missing in the saved scene").
- **`tests-run` refuses a dirty scene** even with no byte changed: save it or open a new empty scene first (`Documentation~/AUTHORING.md`, "`tests-run` refused to start with an unsaved scene").
- **`build` fails on any error logged during its compile**, also one from another source; a busy editor can fail a clean graph (`log:` prefix) (`Documentation~/AUTHORING.md`, "Other observations").
- **`ScreenCapture.CaptureScreenshot` can write a black frame** (27,260 bytes): look at every screenshot and retake (`Documentation~/AUTHORING.md`, "Other observations").

## Testing

- EditMode `Cuvara.VFX.Editor.Tests` (`Tests/Editor`: `RecipeBuildTests`, `RecipeCoverageTests`, `CaptureTests`,
  `TextureImportTests`) and PlayMode `Cuvara.VFX.Tests` (`Tests/Runtime`); Showcase smoke tests in
  `Sandbox~/Assets/Tests/ShowcaseSmokeTests.cs`. Run one through `unity-mcp-cli run-tool tests-run "$OPEN"
  --input-file tests.json` on the open Sandbox; `RecipeCoverageTests.EveryOpAndField_IsUsedByARecipeThatBuilds`
  fails when an op field has no recipe that uses it.
- CI (`.github/workflows/ci.yml`, `Documentation~/CI.md`) validates recipes, schemas, metas and asmdefs without a
  licence; the game-ci jobs open a copy at `sandbox-home/Sandbox`. A capture or test not run is `NOT_RUN` with
  the exact command, never PASS.

## Tools

- Unity-MCP CLI on PATH: the registry dev tool `unity-mcp-cli` of the `unity-package` leg. `setup-sandbox.py` and
  `vfxcli.py` call it on the open path; without it the verbs exit 3 and the Sandbox steps stay `NOT_RUN` with the
  command they would run.
- The Sandbox's Unity-MCP plugin (dev tool `unity-mcp`) is what `unity-mcp-cli` talks to; no other tool, and the `vfx`
  lead's scripts never launch Unity.
