---
name: pin-bump
description: Use when the Unity client must move to a released upstream version - a new com.cuvara.netcode, com.cuvara.dots or com.cuvara.uitoolkit tag, or a new Shared.GameLogic sgl-v tag - or when Packages/manifest.json, packages-lock.json or the imported DOTS Sample must be brought back in line with a pin. Cross-repo driver of the sgl-pin and package-pins contracts. Not for changing package code (unity-package), not for local file: testing (a human-gated toggle), never for creating the tag itself.
argument-hint: "<package> <tag>  e.g. com.cuvara.netcode v0.46.0"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checks/pin-plan.py:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checks/pin-status.py:*)
---

# Pin bump - move a client pin to a released tag

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first.

## Applies when / Not when

- **Applies:** "move the client to Netcode vX.Y.Z", "pin sgl-vX.Y.Z", a manifest/lock mismatch, a stale DOTS Sample, or the final leg of `wire-contract` or `unity-package` after the lead tagged.
- **Not:** editing package code (`unity-package`); editing Shared.GameLogic (`server-realtime`); testing unreleased package code in the client (`client-package-toggle` human gate, never committed); creating or pushing tags (the lead - denied by the guard).

## Scope

- Repo `client`, modules `client.packages`, `client.dots-sample`. Contracts `package-pins` and `sgl-pin` (this skill is their driver).
- Upstream repos (`netcode`, `unitydots`, `uitoolkit`, `server` for SGL) are **read only** here: tags, `package.json`, `Samples~/DOTSSample`.
- Hand-offs: compile/test fallout in client code → `client-integration`; a bug in the new package version → `unity-package` (and a new tag by the lead).

## Workflow delta (after Core steps 1-4: scope, baseline, route, branch)

1. **Status.** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checks/pin-status.py` - current pins, manifest = lock,
   tags present locally, newer tags available, `.sample-source` agreement. If the target tag is missing locally,
   `git -C <upstream> fetch --tags` (read-only for the working tree) or `pin-status.py --remote`.
2. **Plan.** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checks/pin-plan.py <package> <tag>` - exact manifest string,
   lock `version` + `hash` (the tag's commit), upstream dependency changes, DOTS Sample files changed.
   `BLOCKED` = stop: the tag does not exist or its `package.json` disagrees. Report "needs tag <tag> from the lead".
3. **Edit manifest and lock together** (`Packages/manifest.json`, `Packages/packages-lock.json`): the pin string in
   both; the lock `hash` = the tag commit. If `dependency_changes` is non-empty, the lock entry's own
   `dependencies` block must match the new `package.json` - edit it to match, or ask the user to let the Unity
   Editor re-resolve (external). Never leave a `file:` pin.
4. **Netcode only - recopy the DOTS Sample** (`references/pin-chain.md` §DOTS Sample): replace
   `Assets/Samples/Netcode/DOTS Sample/` with the tag's `Samples~/DOTSSample` byte-for-byte (including `.meta`),
   keep `.sample-source` and set `version=` and `commit=` to the plan's values. Never re-import through the
   Package Manager.
5. **CHANGELOG** (`CHANGELOG.md` `[Unreleased]` → `### Changed`): the plan's line plus one sentence of what the
   new version changes for the client (from the upstream CHANGELOG section of that version).
6. **Validate** (below), then Core steps 8-12 (obligations, validate, verify, review, report). One pin per commit unless the user asks to batch.

## Rules

- The lock is what Unity resolves; a manifest-only bump is silently ignored (`rpg-mmo-server#380`, `02-package-pins.yml` header).
- Pin to tags only - never a branch or raw commit (#130).
- `toggle-packages.sh` output is never committed: it writes WSL `file:` paths and does not touch the lock (`known_issues.toggle-packages-lock`).
- Skipping versions is normal (the client pinned 21 of 77 Netcode tags) - read every skipped CHANGELOG section for breaking changes / `### Migration`.
- Shared.GameLogic: package CIs (Netcode, UnityDots) bootstrap their own sgl pin (`contracts.sgl-pin` watchers, currently sgl-v0.5.0; UIToolkit CI has none). When moving the client's sgl pin, report whether those CI pins lag; changing them is `unity-package` work.

## Generated & protected paths

- `Assets/Samples/Netcode/DOTS Sample/` - a generated copy; changes only by recopy from a tag.
- `Assets/Samples/Cuvara */<version>/` - Package Manager imports, frozen; untracked ones are usually the user's (never delete).
- `Packages/com.gdk.*` submodules and gitignored `Packages/com.cuvara.*` clones - never touched.

## Validation delta

| Tier | Check | Evidence |
|---|---|---|
| fast | `pin-status.py` (and `--remote` when network is available) | `OK: N git-URL pins checked, 0 problem(s)`; the moved pin shows `lock=manifest True`, `tag local True` |
| fast | `unity-package-pins.py .` (registry check, mirrors 02-package-pins step 1) | `OK: N git-URL dependencies pinned identically` |
| fast | DOTS Sample byte check: `git -C <Netcode> archive <tag> Samples~/DOTSSample \| tar -x -C <tmp>` then `diff -r <tmp>/Samples~/DOTSSample "Assets/Samples/Netcode/DOTS Sample"` (only `.sample-source` may differ) | empty diff apart from `.sample-source` |
| external | Unity Editor compile + EditMode/PlayMode tests (Unity MCP `tests-run` if `unity-mcp` reachable) | counts per mode; zero executed = failed |
| external | CI `02-package-pins.yml`, `sgl-pin-check.yml`, `01-ci.yml` on the PR | each job listed and passing |

## Human gates

`tag` (the lead creates upstream tags - this skill only reports "needs tag"), `client-package-toggle`, `publish` (push/PR only on request).

## Review checklist

- [ ] Manifest string == lock `version`; lock `hash` == tag commit; no `file:`.
- [ ] Lock `dependencies` block matches the new upstream `package.json` (or re-resolved in the Editor).
- [ ] Netcode: DOTS Sample recopied byte-identical, `.sample-source` version+commit updated.
- [ ] CHANGELOG entry names old → new and the client-visible change; skipped versions' migrations handled.
- [ ] Baseline untouched: the user's `com.gdk.*` pointers and untracked Samples are not staged.

## Report additions

A **pin table**: package, old → new tag, tag commit, manifest = lock (yes/no), sample-source (n/a / updated),
dependency changes, and the external checks still owed (Unity tests, CI) with `not-run:external` reasons.
