---
name: unity-client-tech
description: How the Unity 6 code in IndieRPGMMOAdventure and the com.cuvara.* packages actually works - Entities system install and world lifecycle, UniTask/Task and main-thread rules, VContainer, asmdef and test-assembly rules, domain reload, input handling, WebGL limits, and running one EditMode/PlayMode test through Unity MCP or batchmode. Use when writing or reviewing an ECS system, async code, an asmdef or a Unity test in the client or a package. Not for deciding where a change goes or which rules, checks and gates apply (client-integration, unity-package, pin-bump own that), and not for server C#.
argument-hint: "[task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*)
---
# Unity client technology (Entities, async, asmdefs, tests)

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first. Honour the declared Factory mode: in `analyze`, `plan` and `review` apply this skill's workflow, rules and checklist to produce the analysis, plan or findings - change nothing; in `validate` only run and grade checks.

Task: $ARGUMENTS

Paths are relative to the client repo `IndieRPGMMOAdventure/` unless a package repo is named.
Worked examples (HUD data path, DOTS bridge lifecycle, async seams, test templates):
`references/ecs-and-async.md`.

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
  group: `Assets/Scripts/UI/Hud/Ecs/HudEcsBootstrap.cs:30-47` (client),
  `UnityDots/Runtime/Simulation/DotsSimulationBootstrap.cs:42` (package; same pattern in
  `DotsViewBootstrap`, `DotsNetcodeBootstrap`, `DotsPredictionBootstrap`). Install is idempotent
  (`GetOrCreateSystem` + `AddSystemToUpdateList` refuse duplicates); `Uninstall` destroys
  (`HudEcsBootstrap.cs:16-25,50-68`). Root-scoped systems (dots views) are never uninstalled by a
  scene (`Assets/Scripts/DI/Dots/DotsWorldBridge.cs:40`).
- **One world:** `World.DefaultGameObjectInjectionWorld`. Scene components reach it in `Update`
  and install once; teardown is `OnDestroy` in reverse install order
  (`HudWorldBridge.cs:51-105`, `DotsWorldBridge.cs:134-232,381-400`).
- **ECS -> UI goes through a bridge system.** `HudStateSystem` (unmanaged `ISystem`, Simulation
  group) writes a singleton only when it changed; `HudBridgeSystem` (managed, Presentation group)
  derives `UIToolkit/Runtime/Ecs/EcsViewModelBridge.cs:62` (a `SystemBase`) and pushes a struct
  snapshot to a presenter. `VisualElement` is never touched from `ISystem`, jobs, Burst or a worker
  thread (`docs/UI-ARCHITECTURE.md:61-72`).
- **Async is two types.** Nakama, session driver and UI asset loading use UniTask
  (`MainSessionDriver.cs`, `Nakama/NakamaSessionService.cs`, `Nakama/Social/PartyService.cs`,
  `UI/AddressableAssetLoader.cs`); the DOTS view seam is `System.Threading.Tasks.Task` because
  the package interface is (`UnityDots/Runtime/Provisioning/IViewAssetProvider.cs:44`,
  `Assets/Scripts/DI/Dots/LeasedViewAssetProvider.cs:115,146`). `NDC.Scripts.Session` has zero
  references (`Assets/Scripts/Session/NDC.Scripts.Session.asmdef`), so `MainSessionFlow.IEndpoint`
  returns `Task` (`MainSessionFlow.cs:39-54`).
- **Composition is VContainer** (scopes and order: `rpg-factory:client-integration`'s
  composition map). Scene components get `[Inject] Construct(...)` from a scope build callback and
  stay inert without a container (`DotsWorldBridge.cs:120-132`).

## Idioms

- New system: prefer unmanaged `ISystem` with `SystemAPI.Query` / `IJobEntity`; no
  `Entities.ForEach`; `com.unity.jobs` is merged into collections (`CLAUDE.md:523-526`). Package
  hot-path systems add `[BurstCompile]` (`UnityDots/Runtime/Simulation/MoveTowardSystem.cs:38-55`);
  the HUD aggregator is not Burst-compiled (`HudStateSystem.cs:33-35`).
- `OnCreate`: create the singleton you own, then `state.RequireForUpdate<T>()`; `OnDestroy`
  removes it so a reinstall starts fresh (`HudStateSystem.cs:47-70`).
- Compare before write: `if (!SystemAPI.GetSingleton<T>().Equals(next)) SystemAPI.SetSingleton(next)`
  - the change filter fires on any write, equal or not (`HudStateSystem.cs:28-31,107-109`).
- Fire-and-forget at an entry point: `IStartable` + an owned `CancellationTokenSource` +
  `async UniTaskVoid RunAsync(...)` + `.Forget()`, cancelled in `Dispose`; not `IAsyncStartable`,
  whose return type depends on VContainer's UniTask define (`MainSessionDriver.cs:38-40,57,92-95`).
- Unity objects (prefabs, Addressables handles, `GameObject`) are main-thread only
  (`DI/Dots/IViewPrefabLoader.cs:20`, `LeasedViewAssetProvider.cs:45`).
- Prefer constructor / `[Inject]` method injection. `Assets/Scripts/Extensions/DIExtensions.cs`
  (`GetCurrentContainer()`) is a static service locator caching whichever `LifetimeScope`
  `FindFirstObjectByType` hits first; it has no callers - do not add any.
- Input: branch on `#if ENABLE_INPUT_SYSTEM` / `#elif ENABLE_LEGACY_INPUT_MANAGER` / `#else` zero
  (`DotsWorldBridge.cs:449-476`); the project is new-Input-System-only (`activeInputHandler: 1` in
  `ProjectSettings/ProjectSettings.asset`). One component owns input per scene: sampled, sent and
  recorded on the predictor as one stream (`DotsWorldBridge.cs:58-61`).
- Optional dependency = a gated assembly: `defineConstraints` naming defines that the same asmdef
  sets through `versionDefines` (`Assets/Scripts/UI/Hud/Ecs/NDC.Scripts.UI.Hud.Ecs.asmdef`).
  Defines do not flow between asmdefs; whole-file `#if` guards match them (`DotsWorldBridge.cs:1`).

## Pitfalls

- **Not every folder has an asmdef.** `Assets/_SampleBuild/Editor/` has none and compiles into
  `Assembly-CSharp-Editor`; a test cannot reference it by asmdef name.
- **Domain reload is on today but opt-out is one click away.** `ProjectSettings/EditorSettings.asset:27-28`
  holds registry fact `enter-playmode-options` (options `0` = no `Disable*Reload` flag: both domain and
  scene reload). Code with statics must still reset them
  (`[RuntimeInitializeOnLoadMethod(SubsystemRegistration)]`) - a disabled reload keeps them across
  plays.
- **World may not exist yet, or be gone.** `HudWorldBridge` keeps polling while the world is null;
  `DotsWorldBridge.TryInstall` instead warns and disables itself (`DotsWorldBridge.cs:169-177`). Any
  teardown guards `world is { IsCreated: true }` (`DotsWorldBridge.cs:391`, `HudEcsBootstrap.cs:52`).
- **Sink before systems.** A sink left registered keeps Presenter -> ViewModel -> visual tree
  alive (`HudWorldBridge.cs:31-36,95-105`).
- **WebGL:** no command line (`BackendCommandLine` falls back to `CUVARA_*` env,
  `Assets/Scripts/Session/BackendCommandLine.cs:256-268`); no TLS pinning, the browser does the
  handshake (`Assets/Scripts/Nakama/Tls/PinnedCertificateHandler.cs:34-38`); no browser realtime
  transport (`docs/CUVARA-DOTS-IMPROVEMENT-PLAN.md:212`).
- **IL2CPP + Minimal stripping on Android/WebGL, Mono on Standalone** (`CLAUDE.md:9-20`), and the
  client has no `link.xml` under `Assets/`: reflection-only types can be stripped and a Windows
  build never shows it.
- **Builds through MCP:** `BuildPipeline.BuildPlayer` blocks the Editor main thread, the MCP
  channel drops and its retries start the build again; read `Editor.log`, guard with a sentinel
  (`CLAUDE.md:438-441`).
- **Stale MCP doc:** `CLAUDE.md:528-532` describes a Docker stdio server on port 8080; the live
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
  (`.claude/skills/tests-run/SKILL.md:3,13,26`).
- **Editor closed:** batchmode `Unity -batchmode -projectPath . -runTests -testPlatform EditMode|PlayMode
  -testResults <dir>/results.xml [-testFilter <regex>]`, as CI does
  (`unity-build-workflows/.github/workflows/reusable-unity-tests.yml:401-403,463-465`). It cannot run
  while an Editor holds the project open.
- `Packages/manifest.json:78-82` `testables` lists the three `com.cuvara.*` packages, so client CI
  also runs the package test suites in this project.

## Tools

- `unity-mcp`: the client's `ai-game-developer` MCP server (HTTP :23621, reachable only while
  the Editor has the client open; the snapshot shows its state): `tests-run` for one test or one
  assembly, console logs for compile errors. Fallback: batchmode above on a machine with Unity, or
  report the test HUMAN_REQUIRED.
- `lsp-csharp`: missing on this machine. Fallback: `grep -rn` for the symbol across `Assets/` and
  the package repos, then an Editor compile (console) through `unity-mcp`.
- `context-mode`: run batchmode or CI test logs and `results.xml` through `ctx_execute` and print
  only totals and failures. Fallback: `tail` / `grep` for the summary lines.
