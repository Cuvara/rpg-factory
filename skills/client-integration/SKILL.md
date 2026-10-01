---
name: client-integration
description: Use when changing the game's own code in the thin Unity client IndieRPGMMOAdventure - how packages are composed in VContainer scopes, the Nakama login/party/TLS-pin path, the MainScene session flow, the HUD or a new UI Toolkit screen, DOTS view prefabs and the view library, build scripts and BuildConfig, or the client's EditMode/PlayMode tests. Not for changing the com.cuvara.* packages themselves (netcode, dots, uitoolkit), package pins or the DOTS Sample copy, or server code.
argument-hint: "[client task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-status.py:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checks/pin-status.py:*)
---
# Client integration (IndieRPGMMOAdventure)

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first. Honour the declared Factory mode: in `analyze`, `plan` and `review` apply this skill's workflow, rules and checklist to produce the analysis, plan or findings - change nothing; in `validate` only run and grade checks.

Task: $ARGUMENTS

The client is thin: networking, ECS views and UI navigation live in the `com.cuvara.*` packages; this
repo composes them, so registration order and scope matter more than code volume.

## Applies when / Not when

Applies: `Assets/Scripts/**` (DI, Nakama, Session, UI incl. the HUD, Benchmark), `Assets/DotsViews/`,
`Assets/Resources/DotsViews/`, `Assets/VContainer/`, `Assets/BuildScripts/`, `Assets/_SampleBuild/Editor/`
(`PlayClientBuilder`, `SampleBuilder`), `BuildConfig/`, `Assets/Tests/`, client docs, client CI workflows.

Not when: the fix belongs inside a package (a `NetworkClient`, codec, `RegisterNetworking`,
`RegisterDotsViews`, `IScreenNavigator`, the UXML codegen) -> `unity-package`. Bumping a
`com.cuvara.*` or `com.rpgmmo.shared-gamelogic` pin, or recopying the DOTS Sample ->
`pin-bump`. A wire message changing on both sides -> `wire-contract`; a Nakama RPC name/payload ->
`server-services` (contract `nakama-rpc`, this skill edits the client caller as its follow-up). Frame-time or
multi-client measurements (`Tools/run-clients.sh`, `verify-multiclient.sh`) -> `measure`.

## Scope

Repo `client`. Modules: `client.scripts` (all C#, incl. UI code in `Assets/Scripts/UI/`), `client.tests`,
`client.ui` (only the `Assets/UI Toolkit/` theme), `client.buildscripts`, `client.unity-assets`, `client.ci`.
Read-only here: `client.packages`, `client.dots-sample`, `client.samples-imported`, `client.gdk-submodules`,
`client.build-workflows`, `client.tools` (`measure`), `client.wire-conformance` (`wire-contract`);
`client.docs` is updated as an obligation. Module rules: the snapshot; repo-level files -> `client.root`.

## Workflow delta

1. **Find the layer.** Place the change with `references/composition.md` (scopes, what each
   registers, which asmdef and define guards it). New code goes in the asmdef that already owns
   the folder; a new `Assets/Scripts/` area gets its own `.asmdef` plus `.meta`. Before writing an ECS
   system, async code, an asmdef or a test, follow `rpg-factory:unity-client-tech`.
2. **Check the package boundary.** Code against the pinned tag's API only
   (`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checks/pin-status.py`; not the gitignored embedded clone, not package
   `develop`, never edit those clones). A new or changed package API stops the client leg (hand-off below).
3. **UI work:** run the 10 questions in `docs/UI-ARCHITECTURE.md` "Before implementing
   anything" and follow `references/ui-hud.md`. Edit `.uxml` in a way that regenerates the
   `Generated/*.uxml.g.cs` (Editor save through the codegen) and commit both.
4. **Assets.** Scenes, prefabs, `.asset` and `.meta` change in the Editor (Unity MCP), never by
   hand-editing YAML. See *Human gates*.
5. **Tests.** EditMode in `Assets/Tests/Editor` (`NDC.Tests.Editor`); PlayMode in `Assets/Tests/Runtime`
   only for a live `UIDocument`/frame loop (it cannot see ECS). Templates: `rpg-factory:unity-client-tech`.
6. **Docs.** Wiring changes update `docs/DOTS-WIRING.md` / `docs/HUD-BRIDGE.md` /
   `docs/UI-ARCHITECTURE.md` as applicable, plus the root `CHANGELOG.md` `[Unreleased]`.

## Cross-repo hand-offs

| Situation | Hand to | Client resumes when |
|---|---|---|
| needs a package API or fix | `unity-package` (package repo, stops at READY_TO_TAG) → lead tags → `pin-bump` | the pin moved to that tag (`factory-status.py` shows no pin-bump pending) |
| server message / field needed | `wire-contract` (server → Netcode → client) | the rollout reaches `client pin`; then wire the new field here |
| Nakama RPC changed | `server-services` drives `nakama-rpc` | server side merged; update `PartyService.cs` / `NakamaAuthProvider.cs` callers |
| compile/test fallout after a pin move | this skill, as `pin-bump`'s follow-up | now |

- First `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-status.py`: a pending pin-bump or wire rollout means the
  code you need is not pinned yet - say so. Reuse the upstream legs' `<type>/<area>/<topic>` branch topic.

## Unity-MCP hand-off

Editor-owned files change only through the client's Unity-MCP skills behind the `unity-asset-edit` gate (hooks
do not inspect MCP calls - ask before every edit); tests run through `tests-run`. `references/unity-mcp.md`.

## Rules

- **One `RegisterMessagePipe()`**, the first thing `RegisterDots` does; new MessagePipe consumers
  add `RegisterMessageBroker<T>` there, never a second call (`docs/DOTS-WIRING.md`).
- **One `IWireCodec`**: the encoding is chosen only by the `encoding:` argument of
  `RegisterNetworking` in `GameLifetimeScope`; a second registration fails the container build
  (comment in `Assets/Scripts/DI/GameLifetimeScope.cs`).
- **Scene components are injected by build callback** (`RegisterBuildCallback` +
  `FindAnyObjectByType`), not `RegisterComponentInHierarchy`, for anything a scene may lack
  (`GameLifetimeScope`, `MainSceneScope`).
- **Never wire GameFoundation's screen flow** (`RegisterScreenManager`, `IScreenManager`,
  `RegisterGameFoundation`). The only navigation is `com.cuvara.uitoolkit`'s `IScreenNavigator`.
  The check is a human grep of `Assets/` returning nothing (`docs/UI-ARCHITECTURE.md`).
- **ECS never touches UI Toolkit** (ECS -> bridge -> presenter -> View, `docs/HUD-BRIDGE.md`).
- **The `[DOTSNet]` session log lines are a contract** with `Tools/verify-multiclient.sh`
  (`MainSessionFlow` remarks): change both in one commit or not at all.
- **Nakama RPC names/JSON** (`gateway_token`, `party_*`, `party_id`, `token`) are contract `nakama-rpc`.
- **TLS pinning has no accept-any mode** (`PinnedCertificateHandler`, ADR-24); do not add a bypass.
- **A Windows (Mono) build proves nothing about IL2CPP/stripping** (`CLAUDE.md` "Scripting backend").
- `EditorBuildSettings` changes from `SampleImporter -addToBuild 1` are never committed; the
  release player boots `MainScene` (`CLAUDE.md` "Importing a package sample").

## Generated & protected paths

| Path | Generator / owner |
|---|---|
| `Assets/Scripts/UI/Hud/Generated/HudView.uxml.g.cs` (any `**/Generated/*.uxml.g.cs`) | `com.cuvara.uitoolkit` UXML codegen on UXML save; namespace pinned by `.uxml-namespace` |
| `*.meta`, scenes, prefabs, `.asset`, root `*.csproj`/`*.sln` | Unity Editor |
| `Assets/Resources/DotsViews/DotsViewLibrary.asset` | Editor (`Cuvara/DOTS/Create Placeholder View Library` or the asset menu) |
| `Assets/AddressableAssetsData/**` (`dots/view/*` addresses) | Addressables window |

## Validation delta

Fast (Core) only covers `BuildConfig` JSON. The domain checks are external:

- **Unity Test Runner** (`unity-test-runner`): `tests-run` (EditMode then PlayMode, `NDC.Tests.Editor` /
  `NDC.Tests.Runtime`) when `unity-mcp` is reachable - details in `references/unity-mcp.md`; zero executed = FAIL.
- **CI** `01-ci.yml` (tests, no player; ignores `**.md`, `docs/**`) and `uxml-codegen-drift.yml` (any
  `*.uxml`/`*.uxml.g.cs`/lock change) on the PR. Count jobs. A docs-only PR runs `01-ci-docs.yml`,
  which reports the six required contexts as no-op echoes - its green "Unity Tests" is not evidence.
  `02-package-pins.yml` and `sgl-pin-check.yml` run when `Packages/manifest.json`/lock change.
- **Player build** only if build-affecting: `10-build-development.yml` (gated dispatch) or a local
  `PlayerBuilder` / `_SampleBuild` build; verify with `strings -el` plus a control (`CLAUDE.md`).
- A `DotsViewArchetypes` / view-library change: `DotsViewLibraryValidationTests` (EditMode) and
  `DotsViewLibraryBuildCheck` (runs inside every build) are the evidence.

## Human gates

- Scene / prefab / ScriptableObject edits through Unity MCP: state the asset and the change,
  get a yes, save the scene, then show `git status` of the asset and its `.meta`.
- Dispatching `10-build-development`, `11-build-release`, `20/22/23/24-release-*`.
- `toggle-packages.sh dev|release` (workspace root): rewrites `manifest.json` only.
- Unity batch mode `-executeMethod PlayerBuilder.Build|SampleImporter.Import|StrippingProbeBuilder.Build|AddressableBuilder.Build|PlayClientBuilder.Build|SampleBuilder.Build`.
- Touching the user's baseline (dirty `Packages/com.gdk.*`, untracked `Assets/Samples/**`, scratch scenes).

## Review checklist

- Registration lives in the right scope (root = outlives scenes; scene scope = per scene).
- No second `RegisterMessagePipe`, codec, navigation system, or `RegisterScreenManager`.
- Presenter has no `UIDocument`/`VisualElement`; View has no service/network logic.
- Every new asset/folder has its `.meta`; new asmdef has the right `versionDefines` guards
  (`CUVARA_DOTS`, `CUVARA_NETCODE`, ... per `docs/DOTS-WIRING.md` "Defines").
- `.uxml` and `.uxml.g.cs` change together; namespace matches `.uxml-namespace`.
- No `file:` pins, no `EditorBuildSettings` test scenes, no baseline paths in the diff.

## Report additions

- Unity Test Runner table per mode (or HUMAN_REQUIRED (external) + why), and the CI job count.
- For asset edits: asset path, how it was edited (MCP tool / Editor), `.meta` included.
- Any hand-off opened (`unity-package`, `pin-bump`, `wire-contract`) and its state.

## Tools

- `unity-mcp`: asset edits (gated) and `tests-run`; fallback: report tests HUMAN_REQUIRED, never hand-edit YAML.
- `lsp-csharp`: symbol lookup across client and pinned packages; fallback: grep plus an Editor compile via `unity-mcp`.
- `context-mode`: keep CI, batchmode and Editor logs out of the conversation; fallback: `tail`/`grep` the summary.
- `codex`: second diagnosis of a stuck client bug (`codex:rescue`), reviewed like any diff; fallback: none needed.
