---
name: unity-package
description: Use when changing the source of a Cuvara Unity package itself - com.cuvara.netcode (Netcode repo), com.cuvara.dots (UnityDots repo) or com.cuvara.uitoolkit (UIToolkit repo) - including its runtime code, tests, samples, docs, CI, generated files, or preparing a package release up to "ready to tag". Also runs the Netcode leg (Wire.cs resync) when wire-contract invokes it. Not for moving the client's pins to a new package tag (pin-bump), not for client code that uses the packages (client-integration), and not for server or proto changes.
argument-hint: "[package] [task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*)
---
# Unity package development (Netcode, UnityDots, UIToolkit)

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first.

Task: $ARGUMENTS

## Applies when / Not when

- **Applies:** any edit inside `Netcode/`, `UnityDots/` or `UIToolkit/` at the workspace root:
  runtime/editor code, asmdefs, tests (Unity or headless), `Samples~`, `Documentation~`,
  `.github/`, generated files, and the release-prep commit (version + CHANGELOG heading).
- **Not when:** the client's `Packages/manifest.json` / `packages-lock.json` pins or the DOTS
  Sample recopy (**pin-bump**); client glue in `IndieRPGMMOAdventure/Assets/` (**client-integration**);
  `wire.proto` or the server's generated bindings (**wire-contract**, server leg).
- A package change that the client must consume is two tasks: this skill ends at
  "ready to tag"; after the **user** tags, pin-bump moves the client.

## Scope

| Repo (key) | Modules |
|---|---|
| `Netcode/` (netcode) | `netcode.protocol`, `netcode.codec`, `netcode.runtime`, `netcode.samples`, `netcode.tests`, `netcode.package` |
| `UnityDots/` (unitydots) | `unitydots.runtime`, `unitydots.editor`, `unitydots.samples`, `unitydots.tests`, `unitydots.package` |
| `UIToolkit/` (uitoolkit) | `uitoolkit.runtime`, `uitoolkit.editor`, `uitoolkit.codegen-cli`, `uitoolkit.samples`, `uitoolkit.tests`, `uitoolkit.package` |

Hand-offs: `wire-contract` drives `netcode.protocol` (Wire.cs, `WireProtocolVersion`);
`pin-bump` after a tag; `client-integration` for client call sites. None of the three repos
has a CLAUDE.md: read the package's `README.md` and the `Documentation~` pages named in
`references/packages.md` instead.

## Workflow delta

1. **Branch base differs per repo.** Netcode integrates on `develop` (GitHub default; the local
   `origin/HEAD` still says `main` - trust `gh repo view`). UnityDots and UIToolkit integrate on
   `main`; their local `develop` has no upstream. Branch from the integration branch.
2. **Read before edit:** the package map in `references/packages.md` (asmdefs, gates, docs,
   generated files) for the repo you touch.
3. **Implement.** Every new Unity-visible file *and folder* gets a `.meta`. A new optional
   dependency means a new gated assembly (`defineConstraints` + `versionDefines`), never a
   reference from the core assembly (UnityDots `Documentation~/RELEASE.md` §2).
4. **CHANGELOG** entry under `## [Unreleased]` in the repo-root `CHANGELOG.md`; update the
   `Documentation~` page that describes the behaviour.
5. **Wire leg (Netcode, only when invoked by wire-contract):** copy the server's committed
   `Wire.cs` byte-for-byte (procedure in `references/dev-loop.md`), decide whether
   `WireProtocolVersion.Current` moves (rules in its XML doc), and return `cmp` evidence.
6. **Validate** fast tier locally (`references/dev-loop.md`); Unity tests need the client
   project (human gate `client-package-toggle`).
7. **Release prep (only when asked):** bump `package.json` `version`, turn `[Unreleased]` into
   `## [X.Y.Z] - YYYY-MM-DD` in the same commit, then stop: **"ready to tag <repo> vX.Y.Z"**.

## Rules

- **Never tag, never publish.** A `v*` tag triggers `release.yml`, which runs `npm publish` to
  GitHub Packages; that cannot be undone (Netcode `README.md` "Cutting a release").
- `package.json` version must equal the tag, and the tagged commit must carry `## [X.Y.Z]`;
  `release.yml` extracts the notes by that heading and refuses a mismatched version.
- UnityDots release sections also carry one compatibility line per moved pin and a
  `### Migration` block for consumer-visible changes (`Documentation~/RELEASE.md` §2, §4).
- Test-count gates: CI fails on zero executed tests (Netcode, UIToolkit) or on per-assembly
  floors (UnityDots `assert_test_floors.py`). If you add tests that make a floor unable to fail,
  raise the floor; never lower one to go green.
- A failing UnityDots CI row "is the finding" - never add a dependency to a row's manifest to
  make it pass (`UnityDots/.github/workflows/ci.yml` header).
- UIToolkit is standalone: no GameFoundation / `com.gdk.*` references, exported USS classes
  start with `cuvara-` (`Documentation~/CI.md`).
- `Samples~` is never checked by `check_metas.py` (it skips `~` folders). Netcode samples keep
  full `.meta` coverage anyway: `Samples~/DOTSSample` is copied byte-for-byte into the client.
- `Tests~/` and `Tools~/` are not imported by Unity and need no `.meta`.
- UIToolkit `CHANGELOG.md` mixes UTF-8 and cp1252 bytes; touch only the `[Unreleased]` region
  and do not transcode it inside a feature change.

## Generated & protected paths

| Path | Generator / owner |
|---|---|
| `Netcode/Runtime/Protocol/Generated/Wire.cs` | copy of server `backend/gameserver-dotnet/GameServer/Net/Generated/RpgMmo/Wire/V1/Wire.cs` (wire-contract) |
| `Netcode/Runtime/Plugins/*.dll` | vendored binaries (Google.Protobuf 3.29.3, BouncyCastle) - replace only on request |
| `UIToolkit/**/Generated/*.uxml.g.cs` | UXML codegen (Editor: `Assets/Cuvara/Generate UXML Bindings` to enrol, auto-regen on reimport) |
| `UnityDots/.github/scripts/__pycache__/*.pyc` | tracked by mistake; run Python with `PYTHONDONTWRITEBYTECODE=1` |
| `.meta` files | Unity Editor (or copied with their asset) |

## Validation delta

- **fast** (local, per repo): package.json fields, CHANGELOG version heading, `check_metas.py`,
  Netcode headless tests via `bash ${CLAUDE_PLUGIN_ROOT}/scripts/checks/netcode-headless.sh` (temp copy; counts);
  UIToolkit adds `check_standalone.py`, `check_uss_prefix.py`, `check_samples.py`; UnityDots adds
  the floor-script self-test. Commands and evidence: `references/dev-loop.md`.
- **extended:** UIToolkit codegen drift CLI from a temp copy (registry check `uitoolkit.codegen-cli/uxml-drift`) (trigger: `*.uxml`,
  `*.uxml.g.cs`, `Editor/Codegen/Core/`); Netcode Wire.cs `cmp` (trigger: wire leg).
- **external:** Unity Test Runner in the client project with the package toggled to the local
  clone (gate), and the package CI on the PR - count jobs per `references/packages.md`.

## Human gates

- `client-package-toggle` - pointing the client at a local package clone edits the user's client
  tree. Ask first; back up and restore exactly (`references/dev-loop.md`).
- `tag` / `npm publish` - lead only. Stop at "ready to tag".
- Replacing a vendored DLL or bumping `unity` / dependency versions in `package.json`.

## Review checklist

- [ ] `.meta` for every new file **and folder** outside `~` dirs; staged before `check_metas.py`
- [ ] Netcode `Samples~` still has 100 % `.meta` coverage
- [ ] asmdef file name == asmdef `name`, prefix `Cuvara.Netcode.` / `Cuvara.DOTS.` / `Cuvara.UIToolkit.`
- [ ] Optional dependency behind its own gated assembly; core assembly references nothing optional
- [ ] `[Unreleased]` entry; release: version bumped + dated heading (+ Migration, pin lines for UnityDots)
- [ ] New sample listed in `package.json` `samples[]`, has an asmdef, compiles (CI `samples` job)
- [ ] UIToolkit: standalone, `cuvara-` USS prefix, no `com.gdk.*` dependency, bindings in sync
- [ ] UnityDots: floors still able to fail
- [ ] CI pins (`sgl-v*`, netcode tag in UnityDots rows) unchanged unless the task moves them
- [ ] Wire.cs byte-identical to the server copy (Netcode)

## Report additions

- Per repo: branch + integration base, package version before/after, `[Unreleased]` entry.
- Test evidence: headless trx counters, Unity Test Runner totals per assembly (and UnityDots
  floors), or `not-run:external` with the reason.
- Wire leg: `md5sum` of both `Wire.cs` copies and `WireProtocolVersion.Current` before/after.
- Toggle gate: confirmation that `Packages/manifest.json` and `packages-lock.json` were restored
  byte-identical (`cmp` against the backup).
- Release prep: the exact line **"ready to tag <repo> vX.Y.Z"** and the pin-bump hand-off.
