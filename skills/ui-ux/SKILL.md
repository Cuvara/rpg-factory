---
name: ui-ux
description: Foundation-only ui/ux foundation authoring. Use when routing and drafting registered domain artifacts. Not for production execution or tooling.
argument-hint: "[task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*)
---

# UI/UX foundation

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. Respect the active Factory mode.

Task: $ARGUMENTS

## Applies when / Not when

- **Applies:** Feature specifications, flows, information architecture, interaction behavior and accessibility intent.
- **Not when:** implementing engine UI/assets/effects; engineering owns those paths.

## Scope

Repo `authoring`; registered authoring paths under `ui/specs/`. Foundation only.

## Workflow delta

1. Route with `factory-context.sh --domain ui` or `--kind` and follow registry ownership.
2. Draft the registered artifact using the `---json` front matter defined by `docs/artifacts.md`; do not create approval records.
3. Run the registry shared checks for the artifact.
4. Hand off through: `feature-spec-to-ui-spec, ui-spec-to-art2d-brief, ui-spec-to-client`.
5. Engine-side UI work that follows the spec (Unity UI Toolkit screens, Figma import, component choice, UI review) is planned by `rpg-factory:ui-orchestrator`; invoke it only for that part.

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
