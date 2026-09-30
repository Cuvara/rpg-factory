# Package map: Netcode, UnityDots, UIToolkit

Verified 2026-09-30 from each repo's working tree (`git`, `package.json`, `*.asmdef`,
`.github/`, `Documentation~/`) and `gh repo view`. Re-check versions and pins before quoting them.

## Common to all three

- Repo root **is** the package root (`package.json`, `CHANGELOG.md`, `README.md`, each with `.meta`).
- `unity: "6000.3"`; every Unity CI job uses Unity `6000.3.9f1` via `game-ci/unity-test-runner`.
- `release.yml` on `v*` tag: tag must equal `package.json` version, notes = the
  `## [X.Y.Z]` section, GitHub Release, then `npm publish` of `@cuvara/<name>` to GitHub Packages.
- `release-reminder.yml` warns on push to the integration branch while the version is untagged.
  Never tags.
- No `CLAUDE.md` in any of them.
- Client consumes them as git-tag pins and lists all three in `Packages/manifest.json`
  `testables` (client pins today: dots `v0.29.0`, netcode `v0.45.0`, uitoolkit `v0.7.2`,
  shared-gamelogic `sgl-v0.6.0`).

## Netcode - `com.cuvara.netcode`

| Item | Value |
|---|---|
| Remote / integration | `Cuvara/Netcode`, **`develop`** (GitHub default; CI on push develop/main, PR into develop/main) |
| Version | `0.45.0`, tag `v0.45.0` exists; `[Unreleased]` empty |
| Branches seen | `feat/view/...`, `fix/samples/...`, `perf/snapshot/...`, `chore/release/0.44.0`, `release/v0.43.0`, `sync-main/v0.41.0` (bot) |
| Commits | `feat(view): ... (#163)`, release commit `chore(release): 0.45.0 (#176)` = `package.json` + `CHANGELOG.md` only |
| Deps | unitask 2.5.10, System.Runtime.CompilerServices.Unsafe 6.0.0, unitywebrequest, physics modules |

Assemblies: `Runtime/Cuvara.Netcode.Runtime`, `Runtime/Bootstrap/Cuvara.Netcode.Bootstrap`,
`Runtime/DI/Cuvara.Netcode.DI` (both gated on `CUVARA_NETCODE_VCONTAINER` - VContainer is
optional), `Tests/Editor/Cuvara.Netcode.Tests.Editor`, `Tests/Runtime/Cuvara.Netcode.Tests.PlayMode`.
Runtime folders: Auth, Bootstrap, Client, Codec, Connection, Content, Crypto, DI, Diagnostics,
Interpolation, Json, Plugins, Prediction, Protocol, Snapshot, Transport, View, World.

Samples: 18 listed in `package.json` `samples[]` / 18 folders; 17 asmdefs named after the
folder without prefix (`KcpProbe`, `DOTSSample`, ...). `DemoBootstrap` has no asmdef.
`Samples~/DOTSSample` is the client's play build (copied byte-for-byte; see pin-bump).

Docs (`Documentation~/`): `NETCODE.md` (architecture, "Regenerating the schema types"),
`WIRE-PROTOCOL.md`, `PREDICTION.md`, `INTERPOLATION.md`. Release procedure: `README.md`
"Branching and releases".

Generated / vendored: `Runtime/Protocol/Generated/Wire.cs` (server copy, byte-identical today);
`Runtime/Plugins/Google.Protobuf.dll` (3.29.3, matches server `GameServer.csproj`),
`Runtime/Plugins/BouncyCastle.Cryptography.dll`; `Runtime/link.xml` preserves them.
`Runtime/Protocol/WireProtocolVersion.cs`: `Current = 2` (line 54), mirrors Go
`shared/messages.WireProtocolVersion` and server `GameServer/Net/WireProtocol.cs`; bump rules
are in its XML doc.

CI (`.github/workflows/ci.yml`), 9 check runs expected on a PR:

| Job | Proves | Local equivalent |
|---|---|---|
| `Validate package` | package.json fields, CHANGELOG `[version]`, `check_metas.py`, prints asmdef names | dev-loop §1 |
| `Headless tests (dotnet)` | `Tests~/Headless` via `dotnet test` + trx counter assert (`executed > 0`) | dev-loop §2 |
| `Compile samples (6000.3.9f1)` | every sample imported into a bootstrapped project compiles | none (Unity) |
| `Unity Tests (6000.3.9f1)` | EditMode tests, result XML asserted non-empty | client toggle, dev-loop §3 |
| `Install probe (bare / openupm-registry-only / documented-prereqs / no-vcontainer)` | consumer installs; last two `required` | none |
| `Generated Wire.cs matches the backend` | `cmp` with server `develop` Wire.cs | dev-loop §2 |

CI manifests pin `com.rpgmmo.shared-gamelogic#sgl-v0.5.0`. Also `sync-main.yml` (on tag: PR
moving `main` to the tag, auto-merge).

## UnityDots - `com.cuvara.dots`

| Item | Value |
|---|---|
| Remote / integration | `Cuvara/UnityDots`, **`main`** (only remote branch; local `develop` has no upstream). CI on push main/develop, PR into any branch |
| Version | `package.json` `0.30.0`, latest tag `v0.29.0`; CHANGELOG has `## [Unreleased]` (with entries) **above** an undated `## [0.30.0]` |
| Branches / commits seen | `feat/samples-phase-b`, `release/v0.29.0`; `feat: ... (#31)`, `chore: release v0.29.0 — ...` |
| Deps | entities 1.4.8, burst 1.8.30, collections 2.6.8, mathematics 1.3.2 |

Assemblies (folder -> name): `Runtime` -> `Cuvara.DOTS.Runtime`, `Runtime.DI` -> `Cuvara.DOTS.DI`,
`Runtime.GameFoundation` -> `Cuvara.DOTS.GameFoundation`, `Runtime.GameLogic` -> `Cuvara.DOTS.GameLogic`,
`Runtime.Netcode` -> `Cuvara.DOTS.Netcode` (gated `CUVARA_NETCODE`), `Runtime.Netcode.Prediction`
-> `Cuvara.DOTS.Netcode.Prediction`, `Runtime.Physics` -> `Cuvara.DOTS.Physics`, `Editor` ->
`Cuvara.DOTS.Editor`. Tests: `Tests/Editor` `Cuvara.DOTS.Tests.Editor`, `Tests/Runtime`
`.Tests.Runtime`, `Tests/Editor.DI` `.Tests.DI`, `Tests/Editor.GameLogic` `.Tests.GameLogic`,
`Tests/Editor.Netcode` `.Tests.Netcode`, `Tests/Editor.Physics` `.Tests.Physics`,
`Tests/Editor.Prediction` `.Tests.Prediction`.

Samples: AnimationAndEvents, HybridViews, NetworkedPrediction, PhaseBShowcase (3 asmdefs:
root, `Lifecycle/...Netcode`, `Physics/...Physics`), StressBenchmark; asmdefs `Cuvara.DOTS.Samples.*`.

Docs (`Documentation~/`): OVERVIEW, RELEASE (branch/PR/version/migration/compatibility line/
checklist), SUPPORT-MATRIX (feature classification, §4 compatibility rows, §5 platform gaps;
header still says "as of 0.27.1"), MODULE-LIFECYCLE, NETCODE-INTEGRATION, NETWORK-LIFECYCLE,
PHYSICS, VIEW-PROVISIONING, CAMERA-FOLLOW, CONFIG-VALIDATION, MINIMAP-OVERLAY. Also root `ROADMAP.md`.

CI: `Validate package` (+ `test_assert_test_floors.py` self-test) and 6 Unity rows, each
`testMode: all`, samples imported, `inventory_assemblies.py`, then `assert_test_floors.py`:

| Row | Floors (`Cuvara.DOTS.Tests.*`) |
|---|---|
| netcode absent | Editor>=100 Runtime>=29 GameLogic>=41 Netcode==0 Prediction==0 Physics==0 DI==0 |
| netcode present | Editor>=100 Runtime>=29 GameLogic>=41 Netcode>=47 Prediction>=19 Physics==0 |
| no optional packages | Editor>=100 Runtime>=29 GameLogic==0 Netcode==0 Prediction==0 Physics==0 DI==0 |
| physics present | Editor>=100 Runtime>=29 Physics>=35 GameLogic==0 Netcode==0 Prediction==0 DI==0 |
| full stack | Editor>=100 Runtime>=29 GameLogic>=41 Netcode>=47 Prediction>=19 DI>=5 Physics==0 |
| GameFoundation present | Editor>=100 Runtime>=29 GameLogic==0 Netcode==0 Prediction==0 Physics==0 |

Rows pin `sgl-v0.5.0` and `com.cuvara.netcode#v0.41.0` (client: `sgl-v0.6.0`, `v0.45.0`).
Moving them is a deliberate task with a compatibility line (RELEASE.md §4).

## UIToolkit - `com.cuvara.uitoolkit`

| Item | Value |
|---|---|
| Remote / integration | `Cuvara/UIToolkit`, **`main`**. CI on push main/develop, **PR into `main` only** |
| Version | `0.7.2`, tag `v0.7.2`; `[Unreleased]` has entries |
| Commits seen | `fix(uitoolkit): ...`, `chore: release v0.7.2 — ...`, `ci: ... (#12)` |
| Deps | unitask 2.5.10, uielements module, VContainer 1.16.9 (no shared-gamelogic, no sgl pin in CI) |

Assemblies: `Runtime/Cuvara.UIToolkit`, `Runtime/Ecs/Cuvara.UIToolkit.Ecs`,
`Runtime/TestSupport/Cuvara.UIToolkit.TestSupport`, `Runtime/VContainer/Cuvara.UIToolkit.VContainer`,
`Editor/Cuvara.UIToolkit.Editor`; tests `Tests/Editor/Cuvara.UIToolkit.Editor.Tests`,
`Tests/Runtime/Cuvara.UIToolkit.Tests`, `Tests/Runtime/Ecs/Cuvara.UIToolkit.Ecs.Tests`,
`Tests/Runtime/Flow/Cuvara.UIToolkit.Flow.Tests`. Samples EcsHud, LoadingFlow,
NotificationPopup, ScreenFlow (`Cuvara.UIToolkit.Samples.*`; ScreenFlow's asmdef `name` is
`...ScreenFlowScene`, file name `...ScreenFlow` - pre-existing mismatch).

Docs (`Documentation~/`): `CI.md` (what CI proves; its "Samples~ is not compiled" line is stale,
`ci.yml` has a `samples` job), `UXML-CODEGEN.md`, `HYBRID-DATA-BINDING.md`, `LIFECYCLE-PLAN.md`.

Codegen: core `Editor/Codegen/Core/*.cs` (Unity-free by contract); Editor menu
`Assets/Cuvara/Generate UXML Bindings` enrols a UXML, `UxmlBindingPostprocessor` regenerates
enrolled ones on reimport; `Tools~/UxmlCodegenCli` (net10.0) compiles the same core and only
**checks**. Enrolled: `Tests/Runtime/Generated/ConfirmPopup.uxml.g.cs`,
`Samples~/EcsHud/Generated/VitalsView.uxml.g.cs` (Samples~ is not imported in this repo, so no
Editor auto-regen there).

CI, 5 check runs: `Validate package` (fields, no `com.gdk.core`/`com.gdk.3rd` dependency,
`check_standalone.py`, `check_uss_prefix.py`, CHANGELOG, `check_metas.py`, `check_samples.py`,
asmdef names), `Compile samples (6000.3.9f1)`, `Unity Tests (6000.3.9f1)` (total>0 assert,
project also installs entities 1.4.8 + inputsystem 1.18.0), `Install probe (bare)`
(informational), `Install probe (documented)` (required). `version-bump.yml`
(workflow_dispatch: `npm version` + CHANGELOG heading, commits and pushes as a bot - a push,
so never trigger it without the user).

`CHANGELOG.md` is mixed UTF-8 / cp1252 (first invalid byte 0x97 at offset 1559).
