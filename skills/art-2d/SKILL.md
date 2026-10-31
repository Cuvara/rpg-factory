---
name: art-2d
description: Use when producing and validating 2D art direction, concepts, asset specifications, and runtime exports. Not for client code, Unity imports, 3D assets, or effects.
argument-hint: "[asset or task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checks/artifact-quality.py:*)
---

# 2D Art production

> **Prerequisite:** follow `rpg-factory:factory-core` and the active Factory mode.

Task: $ARGUMENTS

## Applies when / Not when

- **Applies:** 2D art direction, concept development, production asset specifications, and runtime export verification.
- **Not when:** implementing client runtime code, Unity import settings, UI behavior, 3D assets, or visual effects.

## Scope

Repo `authoring`; registered paths under `art2d/`. Product files are owned by engineering.

## Start and inputs

1. Route with `factory-context.sh --domain art2d` or `factory-context.sh --kind <kind>`; use `/rpg-factory:workflow` for multi-artifact work.
2. Work in the registered `authoring` repository under `art2d/`. If authoring is unavailable, use a fixture or report the missing repository; never write into a product repo.
3. Record upstream artifact IDs and Git blob revisions, computed with `git hash-object <path>` on each source file. UI illustration work consumes `ui-spec`; gameplay-relevant values come from approved design artifacts. Do not invent binding values. Mark unknown numbers `unresolved` or clearly label a proposal.

## Production workflow by kind

1. **art-direction-2d:** define palette constraints, line, shading, proportions, and rights-cleared references. Human review confirms visual coherence.
2. **concept-2d:** explore character, environment, prop/item, or UI illustration concepts. Concepts always remain `draft`/`proposed`; they are never production deliverables. Optional tools `game-art-mcp` and `ai-pixel-art-image-generation` may create concept drafts only. Record `{generated_by, tool, model}` provenance.
3. **asset-spec-2d:** cite the art-direction ID and upstream briefs/specs; specify purpose, pixel resolution, format, transparency, naming, export targets, and sprite frame count/fps when animated. Unresolved fields remain explicit unresolved. Draft/review/approved specs describe intended production and do not require a runtime export; create and validate a real linked export before claiming `in-implementation` or later.
4. **runtime-export-2d:** record the product repo key, repo-relative file path, SHA-256, dimensions, format, alpha, and atlas metadata. This is a record, not permission to edit product repositories. Engineering imports through registered `client.unity-assets` routing.
5. **reference-2d:** record source, rights/license, relevance, and provenance. Reference material is never a deliverable and cannot be verified or released.

Keep legacy `art2d-brief` and `art2d-asset` valid as compatibility kinds; new work uses the versioned production kinds.

## Handoffs

- From UI/UX: `ui-spec` requirements by artifact ID and revision.
- To UI/UX: approved illustration/icon runtime export records and usage constraints.
- To Engineering: verified runtime exports plus asset spec IDs/revisions and import targets. Do not copy or create engine files during checks.

## Validation delta

Run `python3 -B scripts/checks/artifact-quality.py <authoring-repo> --registry registry.json --domain art2d --json`. Resolve every `FAIL` and rerun until none remain. Read schema, lifecycle, trace/approval, dependency, and art2d plugin results. `NOT_AVAILABLE` means an optional check could not run; `HUMAN_REQUIRED` needs a person. Palette inspection is optional and explicitly unavailable without Pillow.

## Review checklist

- IDs, schema version 2, sources, authors, and `spec` are present; upstream revisions are current.
- Direction constraints are testable; concept/reference records do not claim production status.
- Spec values match upstream decisions or are marked unresolved/proposal.
- Runtime export exists in the registered repo and its bytes, declared metadata, naming, frames, and atlas agree.
- Rights and human visual acceptance are resolved before approval.

## Failure and recovery

On rejected work, record findings and create a corrected draft revision. On blocked or stale upstream, resolve or refresh the cited source and revalidate downstream artifacts. Humans approve artistic quality, rights, and binding gameplay values; agents never create approval records. Optional image tools are advisory workflow steps only and their absence does not block authoring.

## Human gates

Humans approve artistic quality, rights, and binding gameplay values; agents never create approval records.

## Report additions

List artifact IDs/kinds/revisions, upstream IDs, export paths/hashes, check states, unresolved human decisions, and handoff destinations.

## Tools

No required discipline tools. `Pillow`, `game-art-mcp`, and `ai-pixel-art-image-generation` are optional; provider availability is probed through `scripts/lib/tools.py` when supported, and checks degrade explicitly when absent.
