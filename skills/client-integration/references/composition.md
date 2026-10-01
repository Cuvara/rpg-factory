# Client composition map

Verified 2026-09-30 against IndieRPGMMOAdventure `develop` (`_SampleBuild` and workflows 2026-10-01). Paths are repo-relative.

## Scopes

`Assets/VContainer/VContainerSettings.asset` names `GameLifetimeScope`
(`Assets/VContainer/GameLifetimeScope.prefab`) as the project root, so every scene scope is its
child automatically (remarks in `Assets/Scripts/Benchmark/Workload/BenchmarkLifetimeScope.cs`).

| Scope | File | Registers |
|---|---|---|
| `GameLifetimeScope` (root, outlives scenes) | `Assets/Scripts/DI/GameLifetimeScope.cs` | in order: `BackendSettings` (from `BackendCommandLine.Resolve`), `TransportSecurityReport.Warn`, `RegisterNetworking(NetworkSettings, encoding:)` (package `Cuvara.Netcode.DI`), `RegisterNakama(NakamaSettings)`, `RegisterDots(viewRoot: transform)` under `CUVARA_DOTS && CUVARA_DOTS_VCONTAINER`, then a build callback that injects a scene `NetworkBootstrap` if present |
| `MainSceneScope` | `Assets/Scripts/DI/MainSceneScope.cs` | `RegisterEntryPoint<MainSessionDriver>()`; build callback injecting `DotsWorldBridge` if present (guarded by `CUVARA_DOTS && CUVARA_DOTS_VCONTAINER && CUVARA_NETCODE && CUVARA_SHARED_GAMELOGIC`) |
| `LoadingSceneScope` | `Assets/Scripts/DI/LoadingSceneScope.cs` | nothing |
| `BenchmarkLifetimeScope` | `Assets/Scripts/Benchmark/Workload/BenchmarkLifetimeScope.cs` | `RegisterComponentInHierarchy<BenchmarkWorkload>()` - eager on purpose (a benchmark scene without its workload must fail loudly). The only sanctioned eager resolve. Must not call `RegisterDots` again |

Why order matters (all from the file comments / `docs/DOTS-WIRING.md`):

- `RegisterNetworking` picks the single `IWireCodec` from `encoding:`; the client asks for
  protobuf by default (`-cuvara-encoding`). A second codec registration is a container build error.
- `RegisterNakama` registers `NakamaAuthProvider` as `IAuthProvider`; without the
  `NetworkBootstrap` build-callback injection, `NetworkBootstrap` builds its own client and
  silently mints a development JWT, bypassing Nakama.
- `RegisterDots` (`Assets/Scripts/DI/Dots/DotsRegistration.cs`) starts with the project's only
  `RegisterMessagePipe()` + 5 brokers (`ViewSpawned`, `ViewDespawned`, `ChunkWarmed`,
  `ChunkReleased`, `ChunkCascadeReleased`) because the package's `RegisterDotsViews` resolves
  `IPublisher<T>` at build; then the view provider, `RegisterDotsViews(viewRoot, world)`,
  `RegisterSimulationModel()`.

## Assemblies (`Assets/**.asmdef`, excluding Samples)

| asmdef | Folder | Notes |
|---|---|---|
| `NDC.Scripts` | `Assets/Scripts/` | root namespace `Scripts` |
| `NDC.Scripts.DI` | `Assets/Scripts/DI/` (+ `DI/Dots/`) | composition root; refs netcode, dots, Nakama, Session, MessagePipe, Shared.GameLogic |
| `NDC.Scripts.Nakama` | `Assets/Scripts/Nakama/` | refs `NakamaRuntime`, `Cuvara.Netcode.Runtime` (for `IAuthProvider`) |
| `NDC.Scripts.Session` | `Assets/Scripts/Session/` | no references - pure C# |
| `NDC.Scripts.UI` | `Assets/Scripts/UI/` | refs `Cuvara.UIToolkit`; compiles with no ECS |
| `NDC.Scripts.UI.Hud.Ecs` | `Assets/Scripts/UI/Hud/Ecs/` | gated by `CUVARA_DOTS` + `CUVARA_NETCODE` + `CUVARA_UITOOLKIT_ENTITIES` |
| `NDC.Scripts.Benchmark`, `.Benchmark.Dots`, `.Benchmark.Workload` | `Assets/Scripts/Benchmark/**` | device benchmark (`docs/DEVICE-BENCHMARK.md`) |
| `NDC.Tests.Editor` | `Assets/Tests/Editor/` | Editor-only, namespace `Tests.Editor` |
| `NDC.Tests.Runtime` | `Assets/Tests/Runtime/` | PlayMode, namespace `Tests.Runtime` |
| `BuildScript.Editor` / `BuildScript.Runtime` | `Assets/BuildScripts/{Editor,Runtime}/` | build automation, `GameVersion` |
| (none) | `Assets/_SampleBuild/Editor/` | no asmdef: compiles into `Assembly-CSharp-Editor` |

Defines are per-asmdef `versionDefines`; they do not flow from packages. Table:
`docs/DOTS-WIRING.md` "Defines".

## Nakama (`Assets/Scripts/Nakama/`)

- `NakamaSessionService` - device/email auth, recovery, link/unlink, restore from PlayerPrefs
  (`nakama.auth_token`, `nakama.refresh_token`). Recovery design: `docs/ACCOUNT-RECOVERY.md`.
- `Auth/NakamaAuthProvider` - calls RPC `gateway_token`, reads `token` from the payload.
- `Social/PartyService` - RPCs `party_create`, `party_join`, `party_leave`, `party_get`
  (payload `{"party_id":...}`); the party id feeds `NetworkClient.ConnectToDungeonAsync`.
- `Tls/PinnedCertificateHandler`, `Tls/PinnedHttpAdapter` - exact-DER pin, no accept-any mode.
  Pin comes from `-cuvara-nakama-tls-cert` via `TransportSecurityReport.LoadNakamaPinOrNull`.
- Server side of every RPC: `rpg-mmo-server/backend/nakama/main.go` `InitModule`.

## Session (`Assets/Scripts/Session/`, `Assets/Scripts/DI/MainSessionDriver.cs`)

- `MainSessionFlow` - pure state machine: authenticate device -> connect map (-> party/dungeon
  when `-cuvara-party` / `-cuvara-dungeon`). Seam `MainSessionFlow.IEndpoint`; tests
  `Assets/Tests/Editor/MainSessionFlowTests.cs`. Its `[DOTSNet]` prefixes (`AuthOkPrefix`,
  `InWorldPrefix`, ...) are asserted by `Tools/verify-multiclient.sh`.
- `MainSessionDriver` (`IStartable`, `IDisposable`, entry point of `MainSceneScope`) adapts
  `NakamaSessionService` + `NetworkClient` + `PartyService` to the endpoint.
- `BackendCommandLine` - every `-cuvara-*` flag / `CUVARA_*` env var (gateway host/port/tls/cert,
  nakama scheme/host/port/key/tls-cert, sealed, encoding, party, dungeon, device, instance, map,
  status-url). Tests: `BackendCommandLineTests`. `Tools/run-clients.sh` passes these flags.

## DOTS views (`Assets/Scripts/DI/Dots/`, `Assets/DotsViews/`)

- Archetype names: `DotsViewArchetypes.All` = `player-local`, `player-remote`, `mob`.
- Library: `Assets/Resources/DotsViews/DotsViewLibrary.asset` -> Addressable prefabs
  `Assets/DotsViews/Prefabs/{PlayerLocal,PlayerRemote,Mob}.prefab` at addresses
  `dots/view/<name>` (Default Local Group).
- `DotsViewProviderMode.Production` (default) = `LeasedViewAssetProvider` over
  `AddressableViewPrefabLoader`; no library asset -> warning and fallback to `Primitive`
  (`PrimitiveViewAssetProvider`, capsules/spheres). Tests: `DotsRegistrationTests`
  (`ViewAssetProvider_IsPrimitive_InPrimitiveMode`, `..._IsTheLeasedPooledProvider_InProductionMode`),
  `DotsViewLibraryValidationTests`, `LeasedViewAssetProviderTests`.
- Build gate: `Assets/BuildScripts/Editor/DotsViewLibraryBuildCheck.cs` runs before every build
  and fails on a missing archetype / malformed key / unresolved prefab (`CLAUDE.md` "DOTS view
  library"). Editor menus: `Cuvara/DOTS/Create Placeholder View Library`,
  `Cuvara/DOTS/Ensure MainScene DotsWorldBridge` (`DotsViewLibraryAuthoring.cs`).
- Scene half: `DotsWorldBridge` - traps list in `docs/DOTS-WIRING.md` (no-predictor binder
  overload, one input owner, hp on `NetworkEntityState`, teardown order).

## Build (`Assets/BuildScripts/Editor/`, `BuildConfig/`)

- `PlayerBuilder.Build` (`-bootScene`, `-buildOutput`, `-development`), `AddressableBuilder.Build`,
  `SampleImporter.Import` (`-samplePackage <pkg> -importSample "<name>" [-addToBuild 1]`),
  `StrippingProbeBuilder.Build` (`-probeScene`, `-strippingLevel`, `-buildOutput`).
- `Assets/_SampleBuild/Editor/`: `PlayClientBuilder.Build` (the netcode DOTS Sample scene as a standalone
  multi-window player) and `SampleBuilder.Build` (the UI Toolkit ScreenFlow sample); both pass the scene
  straight to `BuildPipeline` and leave `EditorBuildSettings` alone. Read `BUILD_RESULT`, not the exit code.
- `BuildConfig/base.json` + `development.json` / `staging.json` / `production.json` overlays,
  consumed by the `unity-build-workflows` pipeline (`unity-pipeline.yml@v6`); stage 01 fails when
  `BuildConfig` and `ProjectSettings.asset` disagree (`unity-build-workflows/CHANGELOG.md`).
- Entry workflows: `01-ci.yml` (push/PR, tests, no player), `01-ci-docs.yml` (docs-only PRs, no-op
  stand-ins for the six required contexts), `02-package-pins.yml` / `sgl-pin-check.yml` (manifest/lock
  pins), `uxml-codegen-drift.yml`, `10-build-development.yml`,
  `11-build-release.yml` (dispatch), `20/22/23/24-release-*.yml` (promote a `source-run-id`, need
  `artifact-name`). Details: `CLAUDE.md` "CI/CD".
