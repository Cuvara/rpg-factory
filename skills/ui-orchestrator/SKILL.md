---
name: ui-orchestrator
description: SCAFFOLD: Entry point for UI requests: deterministic UI plan, intent, minimal skill set, missing context. Use when SCAFFOLD: <the developer situation this skill applies to>. Not for SCAFFOLD: <what the neighbouring skills own>.
argument-hint: "[task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*)
---

# SCAFFOLD: ui-orchestrator - title

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first. Honour the declared Factory mode: in `analyze`, `plan` and `review` apply this skill's workflow, rules and checklist to produce the analysis, plan or findings - change nothing; in `validate` only run and grade checks.

> **Supporting skill, never the owner:** invoke the lead (and co-leads) from the snapshot's routing line
> first - here `client-integration`, `unity-package`, `ui-ux`. If you have not, stop and invoke it now: rules, gates, validation and the
> report come only from it. This skill adds how the technology works; it decides nothing.

Task: $ARGUMENTS

SCAFFOLD: which repo root the paths below are relative to (registry `cite_roots` if not the first repo's root).

## Applies when / Not when

- **Applies:** SCAFFOLD: the code you are writing, debugging or reviewing.
- **Not when:** SCAFFOLD: deciding scope, rules, checks or gates (`client-integration`, `unity-package`, `ui-ux` own those).

## Scope

Repos `client`, `uitoolkit`. Owns no module, contract or check.

## Architecture

- SCAFFOLD: how it is wired, each claim with `Symbol` (`path/File.cs:N`) checked by `skill-citations.py`.

## Idioms

- SCAFFOLD: the patterns the code uses, cited.

## Pitfalls

- SCAFFOLD: a verified failure and the file or issue that proves it (`path/File.cs`).

## Testing

- SCAFFOLD: how to run one test and what a skip means.

## Tools

- SCAFFOLD: no registry dev tool yet; name the ones this skill uses (registry `dev_tools[].used_by`).
