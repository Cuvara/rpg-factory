---
name: game-design
description: Use when authoring production game concepts, gameplay systems, features, content, GDDs, decisions and engineering handoffs. Not for code, interface specifications or asset production.
argument-hint: "[task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*) Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checks/artifact-quality.py:*)
---
# Game Design
> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first.

Task: $ARGUMENTS

## Applies when / Not when
Applies to design concepts and production artifacts in the design domain. Route UI behavior to `ui-ux`, assets to art leads, and implementation to engineering.

## Scope
Use `/rpg-factory:workflow` or `bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh --domain design`. Author only in registered authoring modules. Inputs are upstream artifact ids and revisions; outputs are versioned design artifacts and named handoffs. If authoring is absent, return artifact text and report checks as not run.

## Workflow delta
1. Resolve scope and upstream ids/revisions through Core. Record each upstream revision as the Git blob id from `git hash-object <path>` for that source file.
2. Draft a `game-concept` before systems/content when the project premise is unsettled. Capture audience, pillars, genre, platforms, USP and constraints.
3. Write one `gameplay-system` per system type. Define core loop, mechanics, progression, interaction/combat, economy sources and sinks, difficulty and meta progression.
4. Write feature and content specs (`feature-spec`, `level-spec`, `quest-spec`, `npc-spec`, `item-spec`) against existing concept/system IDs: record IDs in artifact `sources` and in `spec.game_concept` or `spec.gameplay_systems` as applicable. Store each source's current Git blob revision in `upstream` with `git hash-object <path>`. Keep IDs stable.
5. Produce a GDD to integrate approved concepts and systems; record decisions as `design-decision` artifacts with alternatives and consequences.
6. Create `technical-handoff` with gameplay/state/data requirements, events, edge cases, testable acceptance criteria and registered engineering dependencies.
7. Validate using `artifact-quality.py`; resolve every `FAIL` and rerun until none remain. Route accepted design to UI, engineering, art2d/art3d and VFX through registered contracts.

## Rules
Use schema version 2, stable ids, authors, sources and spec payloads. Gameplay numbers are explicitly unresolved (`TBD`) or `{value, status: proposal, rationale}` unless the artifact declares `binding_values: true` and the shared verifier reports approval as `verified` for its current revision. Missing approval is `HUMAN_REQUIRED`; invalid or untrusted approval fails with verifier reasons. A source id must resolve. Economy systems declare currencies, sources and sinks. Difficulty curves are monotonic when declared. Never write approval records.

## Generated & protected paths
Approvals are immutable human records; agents never write or edit them. No generated paths.

## Validation delta
Core checks metadata, lifecycle, dependencies, trace and approvals. The design plugin checks numbers against verified approval for the current artifact revision, source resolution, economy balance declarations, content ids, difficulty curves and handoff completeness. Plugin `FAIL` blocks readiness; missing gameplay-rules approval reports `HUMAN_REQUIRED`; missing optional balancing tools report `NOT_AVAILABLE` or `HUMAN_REQUIRED`, never PASS. There is no required external tool.

## Human gates
`design-review` for independent review and `gameplay-rules` before binding values. Report open gates; agents do not approve.

## Review checklist
- [ ] Each artifact has stable identity, version, authors, sources and required payload.
- [ ] Gameplay values are unresolved or justified proposals, or binding values have verified current-revision gameplay-rules approval.
- [ ] Source ids resolve and upstream revisions are current.
- [ ] Handoff acceptance criteria are testable and engineering dependencies are routed.
- [ ] Required human gates are complete before binding.

## Report additions
List artifact ids/revisions, lifecycle and validation results, number status, unresolved inputs, human gates, handoff destinations and authoring availability.

## Tools
No registry dev tools required. Optional spreadsheet/CSV balancing is not required; use the standard-library CSV path when provided.
