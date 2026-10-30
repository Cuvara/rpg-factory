---
name: vfx
description: Foundation-only vfx foundation authoring. Use when routing and drafting registered domain artifacts. Not for production execution or tooling.
argument-hint: "[task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*)
---

# VFX foundation

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. Respect the active Factory mode.

Task: $ARGUMENTS

## Applies when / Not when

- **Applies:** Effect specifications and asset delivery records.
- **Not when:** implementing engine UI/assets/effects; engineering owns those paths.

## Scope

Repo `authoring`; registered authoring paths under `vfx/`. Foundation only.

## Workflow delta

1. Route with `factory-context.sh --domain vfx` or `--kind` and follow registry ownership.
2. Draft the registered artifact using the `---json` front matter defined by `docs/artifacts.md`; do not create approval records.
3. Run the registry shared checks for the artifact.
4. Hand off through: `art3d-asset-to-vfx, vfx-spec-to-impl`.

## Rules

- This skill defines a foundation contract only; it provides no production workflow, generation process or tool instructions.
- External source files are referenced in metadata; delivery paths must be in a registered repo.

## Generated & protected paths

- None. Do not write engine-ready client files.

## Validation delta

- `artifact-lint` and `artifact-trace`; asset kinds also use `asset-manifest`.

## Human gates

- Maintainers decide approval and artistic acceptance. Agents never create approvals.

## Review checklist

- [ ] Correct kind, domain, lifecycle metadata, and upstream revision.
- [ ] Handoff destination and any asset delivery metadata are explicit.

## Report additions

- State the artifact kind, checks run, and handoff destinations.

## Tools

- No discipline tools are registered for this foundation. Use the shared Factory CLI checks.
