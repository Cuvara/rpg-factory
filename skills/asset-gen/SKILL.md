---
name: asset-gen
description: SCAFFOLD: AI image asset generation runs: purpose x style x ComfyUI workflow template, reviewed prompt, comfy-mcp generation, deterministic QA, image review, gen-run record and human-approved handoff. Use when SCAFFOLD: <the developer situation this skill applies to>. Not for SCAFFOLD: <what the neighbouring skills own>.
argument-hint: "[task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*)
---

# SCAFFOLD: asset-gen - title

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first. Honour the declared Factory mode: in `analyze`, `plan` and `review` apply this skill's workflow, rules and checklist to produce the analysis, plan or findings - change nothing; in `validate` only run and grade checks.

Task: $ARGUMENTS

## Applies when / Not when

- **Applies:** SCAFFOLD: the paths and tasks this skill owns.
- **Not when:** SCAFFOLD: the neighbouring skill for each excluded area.

## Scope

Repo(s) `authoring`. SCAFFOLD: modules and contracts (from the registry), hand-offs.

## Workflow delta

1. SCAFFOLD: the steps this skill adds to factory-core's workflow.

## Rules

- SCAFFOLD: each rule with its source doc (rules that are registry module rules stay in the registry).

## Generated & protected paths

- SCAFFOLD: generator-owned or protected paths, or "none".

## Validation delta

- SCAFFOLD: the registry checks that matter and their evidence; external checks.

## Human gates

- SCAFFOLD: the registry human gates this work reaches.

## Review checklist

- [ ] SCAFFOLD: what a reviewer verifies.

## Report additions

- SCAFFOLD: what the report adds to factory-core's template.

## Tools

- `comfy-mcp`: SCAFFOLD: the step that uses it and the fallback when it is not OK.
