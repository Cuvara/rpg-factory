---
name: unity-client-tech
description: How the Unity 6 application code in IndieRPGMMOAdventure and the com.cuvara.* packages actually works - world lifecycle and the ECS-to-UI bridge, UniTask/Task and main-thread rules, VContainer scopes and lifetimes, UI Toolkit views, binding, collections and screen flow, asmdef and test-assembly rules, domain reload, input handling, WebGL limits, and running one EditMode/PlayMode test through Unity MCP or batchmode. Use when writing or reviewing async code, a VContainer registration, a UI Toolkit screen, an asmdef or a Unity test in the client or a package (ECS systems and jobs: unity-dots). Not for deciding where a change goes or which rules, checks and gates apply (client-integration, unity-package, pin-bump own that), and not for server C#.
argument-hint: "[task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*)
---
# Unity client technology (Entities, async, asmdefs, tests)

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first. Honour the declared Factory mode: in `analyze`, `plan` and `review` apply this skill's workflow, rules and checklist to produce the analysis, plan or findings - change nothing; in `validate` only run and grade checks.

> **Supporting skill, never the owner:** invoke the lead (and co-leads) from the snapshot's routing line
> first - here `client-integration`, `unity-package` or `pin-bump`. If you have not, stop and invoke it now: rules, gates, validation and the
> report come only from it. This skill adds how the technology works; it decides nothing.

Task: $ARGUMENTS

Paths are relative to the client repo `IndieRPGMMOAdventure/` unless a package repo is named.
Worked examples (HUD data path, DOTS bridge lifecycle, async seams, test templates):
`references/ecs-and-async.md`. UI Toolkit and VContainer patterns: `references/ui-toolkit.md`.
ECS systems, jobs, Burst and ECB: `rpg-factory:unity-dots`. Netcode internals: `rpg-factory:netcode-client`.

## Applies when / Not when

Applies: you are about to write or review a system, a world-lifetime MonoBehaviour, async code
touching Unity objects, an `.asmdef`, or a Unity test - in `Assets/` or in `Netcode/`,
`UnityDots/`, `UIToolkit/`. Not when: the question is which module, scope, rule, gate or CI job
applies (`client-integration`, `unity-package`, `pin-bump`), or the code is the .NET game server.

## Scope

Repos `client`, `netcode`, `unitydots`, `uitoolkit`. Owns no module, contract or check; the
calling skill keeps validation and reporting.

## Architecture

- **Systems are installed, not discovered.** Client and package systems carry
  `[DisableAutoCreation]` + `[UpdateInGroup]` and a static `*Bootstrap` adds them to an existing
  group: `HudEcsBootstrap.Install` in `Assets/Scripts/UI/Hud/Ecs/HudEcsBootstrap.cs:30-47` (client),
  `DotsSimulationBootstrap.InstallSimulationSystems` in
  `UnityDots/Runtime/Simulation/DotsSimulationBootstrap.cs:42` (package; same pattern in
  `DotsViewBootstrap`, `DotsNetcodeBootstrap`, `DotsPredictionBootstrap`). Install is idempotent
  (`GetOrCreateSystem` + `AddSystemToUpdateList` refuse duplicates); `Uninstall` destroys
  (`HudEcsBootstrap.cs:16-25,50-68`). Root-scoped systems (dots views) are never uninstalled by a
  scene: its teardown runs only `DotsModules.UninstallScope(Session)`
  (`Assets/Scripts/DI/Dots/DotsWorldBridge.cs:42-46`).
- **One world:** `World.DefaultGameObjectInjectionWorld`. Scene components reach it in `Update`
  and install once; teardown is `OnDestroy` in reverse install order
  (`HudWorldBridge.cs:51-105`; `DotsWorldBridge.Update` / `OnDestroy`: `DotsWorldBridge.cs:194-209,521-565`).
- **ECS -> UI goes through a bridge system.** `HudStateSystem` (unmanaged `ISystem`, Simulation
  group) writes a singleton only when it changed; `HudBridgeSystem` (managed, Presentation group)
  derives the package's `EcsViewModelBridge` (a `SystemBase`, `UIToolkit/Runtime/Ecs/EcsViewModelBridge.cs:62`)
  and pushes a struct snapshot to a presenter. `VisualElement` is never touched from `ISystem`, jobs,
  Burst or a worker thread (`docs/UI-ARCHITECTURE.md` "Layers, and what each may know").
- **Async is two types.** Nakama, session driver and UI asset loading use UniTask
  (`MainSessionDriver.cs`, `Nakama/NakamaSessionService.cs`, `Nakama/Social/PartyService.cs`,
  `UI/AddressableAssetLoader.cs`); the DOTS view seam is `System.Threading.Tasks.Task` because
  the package interface is (`UnityDots/Runtime/Provisioning/IViewAssetProvider.cs:44`,
  `LeasedViewAssetProvider.PrewarmAsync` / `AcquireAsync`: `Assets/Scripts/DI/Dots/LeasedViewAssetProvider.cs:115,146`). `NDC.Scripts.Session` has zero
  references (`Assets/Scripts/Session/NDC.Scripts.Session.asmdef`), so `MainSessionFlow.IEndpoint`
  returns `Task` (`MainSessionFlow.cs:42-65`).
- **Composition is VContainer** (scopes and order: `rpg-factory:client-integration`'s
  composition map). Scene components get `[Inject] Construct(...)` from a scope build callback and
  stay inert without a container (`DotsWorldBridge.cs:178-192`).

## Idioms

- ECS code (system shape, Burst, jobs, ECB, scheduling, allocators): invoke `rpg-factory:unity-dots`.
  A world-lifetime singleton is created in `OnCreate` and removed in `OnDestroy` so a reinstall starts
  fresh (`HudStateSystem.cs:47-70`).
- UI: View (UXML + bindings) / ViewModel (`BindableViewModel`, raises only on change) / Presenter (no
  `VisualElement`); lists through the package adapters; every subscription disposed
  (`references/ui-toolkit.md`).
- VContainer lifetimes: Singleton in a root or scene scope for services; `Scoped` only for per-screen
  presenters (one screen = one scope, `UIToolkit/Runtime/VContainer/ScreenFlowRegistration.cs:68,78`);
  no Transient for stateful services.
- Fire-and-forget at an entry point: `IStartable` + an owned `CancellationTokenSource` +
  `async UniTaskVoid RunAsync(...)` + `.Forget()`, cancelled in `Dispose`; not `IAsyncStartable`,
  whose return type depends on VContainer's UniTask define (`MainSessionDriver.cs:40-42,103-106,143-144`).
- Unity objects (prefabs, Addressables handles, `GameObject`) are main-thread only
  (`IViewPrefabLoader.LoadAsync`: `DI/Dots/IViewPrefabLoader.cs:20`; `LeasedViewAssetProvider` remarks:
  `LeasedViewAssetProvider.cs:45`).
- Prefer constructor / `[Inject]` method injection. `Assets/Scripts/Extensions/DIExtensions.cs`
  (`GetCurrentContainer()`) is a static service locator caching whichever `LifetimeScope`
  `FindFirstObjectByType` hits first; it has no callers - do not add any.
- Input: `DeviceGameplayInputSource.ReadMove` branches on `#if ENABLE_INPUT_SYSTEM` / `#elif ENABLE_LEGACY_INPUT_MANAGER` / `#else` zero
  (`GameplayInput.cs:81-106`); the project is new-Input-System-only (`activeInputHandler: 1` in
  `ProjectSettings/ProjectSettings.asset`). One component owns input per scene: sampled, sent and
  recorded on the predictor as one stream (`DotsWorldBridge.driveInput`, `DotsWorldBridge.cs:63-67,216-251`).
- Optional dependency = a gated assembly: `defineConstraints` naming defines that the same asmdef
  sets through `versionDefines` (`Assets/Scripts/UI/Hud/Ecs/NDC.Scripts.UI.Hud.Ecs.asmdef`).
  Defines do not flow between asmdefs; whole-file `#if` guards on the same defines (`CUVARA_DOTS`, ...)
  match them (`DotsWorldBridge.cs:1`).

## Pitfalls

- **Not every folder has an asmdef.** `Assets/_SampleBuild/Editor/` has none and compiles into
  `Assembly-CSharp-Editor`; a test cannot reference it by asmdef name.
- **Domain reload is on today but opt-out is one click away.** `m_EnterPlayModeOptions` in
  `ProjectSettings/EditorSettings.asset:27-28` holds registry fact `enter-playmode-options` (options `0` = no `Disable*Reload` flag: both domain and
  scene reload). Code with statics must still reset them
  (`[RuntimeInitializeOnLoadMethod(SubsystemRegistration)]`) - a disabled reload keeps them across
  plays.
- **World may not exist yet, or be gone.** `HudWorldBridge` keeps polling while the world is null;
  `DotsWorldBridge.TryInstall` instead warns and disables itself (`DotsWorldBridge.cs:288-296`). Any
  teardown checks `World.IsCreated` first (`DotsWorldBridge.cs:555`; `HudEcsBootstrap.Uninstall`:
  `HudEcsBootstrap.cs:52`).
- **Sink before systems.** A sink left registered keeps Presenter -> ViewModel -> visual tree
  alive (`HudWorldBridge` remarks and `OnDestroy`: `HudWorldBridge.cs:31-36,95-105`).
- **WebGL:** no command line (`BackendCommandLine.SafeArgs` returns none and the `CUVARA_*` env
  fallback still works, `Assets/Scripts/Session/BackendCommandLine.cs:288-300`); no TLS pinning, the
  browser does the handshake and never calls `ValidateCertificate`
  (`Assets/Scripts/Nakama/Tls/PinnedCertificateHandler.cs:34-38`); no game-server join at all -
  gameplay is KCP/UDP only and browsers have no UDP (`docs/CUVARA-DOTS-IMPROVEMENT-PLAN.md`
  "D13 - P2: build a focused verification matrix").
- **IL2CPP + Minimal stripping on Android/WebGL, Mono on Standalone** (`CLAUDE.md` "Scripting backend is per-target"), and the
  client has no `link.xml` under `Assets/`: reflection-only types can be stripped and a Windows
  build never shows it.
- **Builds through MCP:** `BuildPipeline.BuildPlayer` blocks the Editor main thread, the MCP
  channel drops and its retries start the build again; read `Editor.log`, guard with a sentinel
  (`CLAUDE.md` "Verifying a player build actually contains your change").
- **Stale MCP doc:** `CLAUDE.md` "Unity MCP (IvanMurzak/Unity-MCP)" describes a Docker stdio server on port 8080; the live
  config is `.mcp.json` (`ai-game-developer`, HTTP `localhost:23621`).

## Testing

- **EditMode (`Assets/Tests/Editor`, `NDC.Tests.Editor`)** is where ECS is tested: a throwaway
  `new World("<Fixture>")` in `[SetUp]`, `Dispose()` in `[TearDown]`, install through the same
  bootstrap the component calls (`Assets/Tests/Editor/HudEcsLifecycleTests.cs:30-42`).
- **PlayMode (`Assets/Tests/Runtime`, `NDC.Tests.Runtime`) cannot test ECS**: its asmdef
  references neither Entities nor the dots/netcode assemblies and has no `versionDefines`
  (`Assets/Tests/Runtime/NDC.Tests.Runtime.asmdef`). Use it for a live `UIDocument`/frame loop:
  `[UnityTest] IEnumerator X() => UniTask.ToCoroutine(async () => ...)` with `LogAssert`
  (`Assets/Tests/Runtime/HudViewBindingTests.cs:49-51,100-133`).
- **Test asmdefs**: `defineConstraints: [UNITY_INCLUDE_TESTS]`, `overrideReferences` +
  `nunit.framework.dll`, `autoReferenced: false`, and every assembly under test listed by name;
  the Editor one is `includePlatforms: [Editor]` and repeats the `versionDefines` it needs
  (`Assets/Tests/Editor/NDC.Tests.Editor.asmdef`). A new production asmdef that tests touch must be
  added there.
- **One test, Editor open:** Unity MCP `tests-run` with `testMode` plus `testAssembly`,
  `testNamespace`, `testClass` or a fully-qualified `testMethod` (`Tests.Editor.Fixture.Test`). It
  resumes across a domain reload and stops on pre-existing compile errors; save dirty scenes first
  (`.claude/skills/tests-run/SKILL.md` description, "Filters", "Domain reloads").
- **Editor closed:** the test is HUMAN_REQUIRED. Hand the user the batchmode command CI uses,
  `Unity -batchmode -projectPath . -runTests -testPlatform EditMode|PlayMode -testResults <dir>/results.xml
  [-testFilter <regex>]` (`unity-build-workflows/.github/workflows/reusable-unity-tests.yml`);
  never run it yourself - it opens the user's project (human gate `unity-batch`) and cannot run while an
  Editor holds the project open.
- The `testables` array of `Packages/manifest.json` lists the three `com.cuvara.*` packages, so client CI
  also runs the package test suites in this project.

## Tools

- `unity-mcp`: the client's `ai-game-developer` MCP server (HTTP :23621, reachable only while
  the Editor has the client open; the snapshot shows its state): `tests-run` for one test or one
  assembly, console logs for compile errors. DOWN: report the test HUMAN_REQUIRED with the
  batchmode command above for the user (gate `unity-batch`); CI `01-ci` is the automated evidence.
- `lsp-csharp`: missing on this machine. Fallback: `grep -rn` for the symbol across `Assets/` and
  the package repos, then an Editor compile (console) through `unity-mcp`.
- `context-mode`: read the user's batchmode or CI test logs and `results.xml` through `ctx_execute` and print
  only totals and failures. Fallback: `tail` / `grep` for the summary lines.
