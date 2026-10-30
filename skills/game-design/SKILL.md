---
name: game-design
description: Native Game Design lead for mechanics, loops, progression, balance, systems, GDDs, feature specs and design decisions. Use when authoring or reviewing those concepts and artifacts. Not for engineering code, UI layout specifications (ui-ux), or asset production.
argument-hint: "[task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*)
---

# Game Design

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first.

Task: $ARGUMENTS

## Applies when / Not when

- **Applies:** game concepts, mechanics, loops, progression, balance, systems, GDDs, feature specifications and design decisions.
- **Not when:** engineering code, UI layout or interaction specifications (`ui-ux`, when available), and asset production.

## Scope

Owns the Game Design domain in the optional `authoring` repo, in its registered design modules. Route by `--domain design`, `--kind <artifact-kind>`, or paths. If the authoring repo is absent, work fixture-free: provide the artifact text in the response and state that the repo is absent. Never create or publish the repo.

## Workflow delta

1. Route through Factory Core with `--domain design`, `--kind`, or authoring paths; read module rules and gates from the snapshot.
2. Draft the artifact with the shared front matter and lifecycle from `docs/architecture/artifacts.md`. Mark numbers `TBD` or as labelled proposals; binding values need verified approval.
3. Never write or edit `approvals/`. Run the registered `artifact-lint` and `artifact-trace` checks when the authoring repo exists.
4. Prepare engineering handoff through the registered contracts; for feature specs, route the server and client follow-ups through `feature-spec-to-impl`, and record each implementation trace's `spec_rev` and commit ref.

## Rules

- This domain owns GDDs, feature specifications, design decisions and feature state only in its registered authoring paths. See `docs/architecture/multi-discipline-factory.md`, sections 5, 8.1-8.4.
- Product-repo phase rules remain authoritative for product code. The shared artifact and approval contract is in `docs/architecture/artifacts.md`.

## Generated & protected paths

- `approvals/` contains immutable, human-only approval records. Agents never write, edit, move or delete these files.
- No generated paths are registered for this domain.

## Validation delta

- Core runs registered fast checks. `artifact-lint` validates metadata and lifecycle; `artifact-trace` validates upstream revisions, implementation coverage and approvals.
- A missing or unverifiable approval is `HUMAN_REQUIRED`; schema and trace failures are `FAIL`. If the authoring repo is absent, include the artifact text and report the checks as not run.

## Human gates

- `design-review`: a maintainer reviews and accepts an artifact before approval; agents never approve their own proposals.
- `gameplay-rules`: verified human approval is required before binding gameplay values or rules.

## Review checklist

- [ ] Goals, player-facing behavior and acceptance criteria are clear and testable.
- [ ] Numbers are `TBD` or labelled proposals unless the artifact has verified approval.
- [ ] Lifecycle, upstream revisions, trace entries and human gates match the registry.
- [ ] No approval record was created or changed by an agent.
- [ ] Any engineering handoff names artifact ids and revisions.

## Report additions

State the artifact id, lifecycle status, whether values are proposals or binding, check results, open human gates, authoring-repo availability and any P6 handoff.

## Tools

No registry dev tools are required for this skill.
