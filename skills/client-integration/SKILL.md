---
name: client-integration
description: Use when changing the game's own code in the thin Unity client IndieRPGMMOAdventure - how packages are composed in VContainer scopes, the Nakama login/party/TLS-pin path, the MainScene session flow, the HUD or a new UI Toolkit screen, DOTS view prefabs and the view library, build scripts and BuildConfig, or the client's EditMode/PlayMode tests. Not for changing the com.cuvara.* packages themselves (netcode, dots, uitoolkit), package pins or the DOTS Sample copy, or server code.
argument-hint: "[client task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*)
---
# Client integration (IndieRPGMMOAdventure)

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first.

Task: $ARGUMENTS

The client is thin: networking, ECS views and UI navigation live in the `com.cuvara.*`
packages. This repo composes them. Most client work is wiring, so the order of
registrations and the scope a thing lives in matter more than the code volume.

## Applies when / Not when

Applies: `Assets/Scripts/**` (DI, Nakama, Session, UI/Hud, Benchmark), `Assets/DotsViews/`,
`Assets/Resources/DotsViews/`, `Assets/VContainer/`, `Assets/BuildScripts/`, `BuildConfig/`,
`Assets/Tests/`, client docs, client CI workflow files that call `unity-pipeline.yml`.

Not when: the fix belongs inside a package (a `NetworkClient`, codec, `RegisterNetworking`,
`RegisterDotsViews`, `IScreenNavigator`, the UXML codegen) -> `unity-package`. Bumping a
`com.cuvara.*` or `com.rpgmmo.shared-gamelogic` pin, or recopying the DOTS Sample ->
`pin-bump`. A wire message changing on both sides -> `wire-contract`; a Nakama RPC name/payload ->
`server-services` (contract `nakama-rpc`, this skill edits the client caller as its follow-up). Frame-time or
multi-client measurements (`Tools/run-clients.sh`, `verify-multiclient.sh`) -> `measure`.

## Scope

Repo `client`. Modules: `client.scripts`, `client.tests`, `client.ui`, `client.buildscripts`,
`client.unity-assets`, `client.ci`. Read-only here: `client.packages`, `client.dots-sample`,
`client.samples-imported`, `client.gdk-submodules`, `client.build-workflows`, `client.tools`
(`measure`), `client.wire-conformance` (`wire-contract`); `client.docs` is updated as an obligation.

Query facts, do not copy them: `jq '.modules[] | select(.id|startswith("client."))' "${CLAUDE_PLUGIN_ROOT}/registry.json"`.

## Workflow delta

1. **Find the layer.** Place the change with `references/composition.md` (scopes, what each
   registers, which asmdef and define guards it). New code goes in the asmdef that already owns
   the folder; a new folder gets its own `.asmdef` (repo convention) plus `.meta`.
2. **Check the package boundary.** If the change needs a new public API in a package, stop the
   client leg and hand off to `unity-package`; resume against the released tag via `pin-bump`.
   Never edit gitignored `Packages/com.cuvara.*` clones.
3. **UI work:** run the 10 questions in `docs/UI-ARCHITECTURE.md` "Before implementing
   anything" and follow `references/ui-hud.md`. Edit `.uxml` in a way that regenerates the
   `Generated/*.uxml.g.cs` (Editor save through the codegen) and commit both.
4. **Assets.** Scenes, prefabs, `.asset` and `.meta` are Unity-serialized: create and modify them
   in the Editor (Unity MCP tools in the client's `.claude/skills/`), never by hand-editing YAML.
   See *Human gates*.
5. **Tests.** Add EditMode tests to `Assets/Tests/Editor` (asmdef `NDC.Tests.Editor`, namespace
   `Tests.Editor`); PlayMode tests only where a live `UIDocument`/frame loop is required
   (`Assets/Tests/Runtime`, `NDC.Tests.Runtime`). Presenters and flows are tested as plain C#
   against fakes (`MainSessionFlowTests`, `HudPresenterTests` are the pattern).
6. **Docs.** Wiring changes update `docs/DOTS-WIRING.md` / `docs/HUD-BRIDGE.md` /
   `docs/UI-ARCHITECTURE.md` as applicable, plus the root `CHANGELOG.md` `[Unreleased]`.

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
- **ECS never touches UI Toolkit.** ECS -> adapter/presenter -> View; the HUD bridge is the model
  (`docs/HUD-BRIDGE.md`). World-space/combat UI stays prefab/uGUI - it is not legacy.
- **The `[DOTSNet]` session log lines are a contract** with `Tools/verify-multiclient.sh`
  (`MainSessionFlow` remarks): change both in one commit or not at all.
- **Nakama RPC names** (`gateway_token`, `party_create|join|leave|get`) and their JSON
  (`party_id`, `token`) are contract `nakama-rpc` - a rename is driven by `server-services`; this skill
  updates the client caller as its follow-up, never alone.
- **TLS pinning has no accept-any mode** (`PinnedCertificateHandler`); a missing pin means Unity's
  own validation (ADR-24 via `GameLifetimeScope` comments). Do not add a bypass.
- **Scripting backend differs per target** (IL2CPP on Android/WebGL, Mono on Standalone): a
  Windows build proves nothing about AOT or stripping (`CLAUDE.md` "Scripting backend").
- `EditorBuildSettings` changes from `SampleImporter -addToBuild 1` are never committed; the
  release player boots `MainScene` (`CLAUDE.md` "Importing a package sample").

## Generated & protected paths

| Path | Generator / owner |
|---|---|
| `Assets/Scripts/UI/Hud/Generated/HudView.uxml.g.cs` (any `**/Generated/*.uxml.g.cs`) | `com.cuvara.uitoolkit` UXML codegen on UXML save; namespace pinned by `.uxml-namespace` |
| `*.meta`, scenes, prefabs, `.asset`, root `*.csproj`/`*.sln` | Unity Editor |
| `Assets/Resources/DotsViews/DotsViewLibrary.asset` | Editor (`Cuvara/DOTS/Create Placeholder View Library` or the asset menu) |
| `Assets/AddressableAssetsData/**` (`dots/view/*` addresses) | Addressables window |
| `Assets/Samples/**`, `Packages/com.gdk.*`, `unity-build-workflows/` | not ours - see Scope |

## Validation delta

Fast (Core) only covers `BuildConfig` JSON. The domain checks are external:

- **Unity Test Runner** (`unity-test-runner`): if the snapshot shows `unity-mcp` reachable and the
  session has the client's `ai-game-developer` MCP server, run the `tests-run` tool with
  `testMode` EditMode then PlayMode, filtered by `testAssembly` `NDC.Tests.Editor` /
  `NDC.Tests.Runtime`. Save open scenes first (dirty scenes abort the run). `unity-mcp-cli` is
  not installed in WSL; the tool call is the MCP one. Evidence: total/passed/failed/skipped per
  mode; zero executed = `failed`. Otherwise `not-run:external` (Editor closed).
- **CI** `01-ci.yml` (tests, no player; ignores `**.md` and `docs/**`) and
  `uxml-codegen-drift.yml` (any `*.uxml`/`*.uxml.g.cs`/lock change) on the PR. Count jobs.
- **Player build** only if the change is build-affecting: `10-build-development.yml` is a
  gated dispatch; verify the artifact with `strings -el` plus a control (`CLAUDE.md`
  "Verifying a player build").
- A `DotsViewArchetypes` / view-library change: `DotsViewLibraryValidationTests` (EditMode) and
  `DotsViewLibraryBuildCheck` (runs inside every build) are the evidence.

## Human gates

- Scene / prefab / ScriptableObject edits through Unity MCP: state the asset and the change,
  get a yes, save the scene, then show `git status` of the asset and its `.meta`.
- Dispatching `10-build-development`, `11-build-release`, `20/22/23/24-release-*`.
- `toggle-packages.sh dev|release` (workspace root): rewrites `manifest.json` only.
- Unity batch mode `-executeMethod PlayerBuilder.Build|SampleImporter.Import|StrippingProbeBuilder.Build|AddressableBuilder.Build`.
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

- Unity Test Runner table per mode (or `not-run:external` + why), and the CI job count.
- For asset edits: asset path, how it was edited (MCP tool / Editor), `.meta` included.
- Any hand-off opened (`unity-package`, `pin-bump`, `wire-contract`) and its state.
