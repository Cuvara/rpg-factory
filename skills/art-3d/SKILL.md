---
name: art-3d
description: Use when authoring, validating, reviewing, and handing off production 3D asset specifications and delivery records. Not for implementing engine-side imports or runtime code.
argument-hint: "[task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/checks/artifact-quality.py:*)
---

# 3D Art production

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first.

Task: $ARGUMENTS

## Applies when / Not when

- **Applies:** 3D art direction, modeling, materials, rigs, animation, optimization, and delivery manifests.
- **Not when:** editing Unity assets or runtime import code; hand off those paths to Engineering.

## Scope

Own the `art3d` domain in the optional `authoring` repo. Outputs are registered `art3d-*`, `model-spec`, `material-spec`, `rig-spec`, `animation-spec`, and `asset-3d` artifacts. Inputs are upstream artifact ids and revisions; downstream consumers are VFX and Engineering.

## Workflow

1. Start from `/rpg-factory:workflow` for cross-domain work or `factory-context.sh --domain art3d` for one domain. Read each upstream artifact by id/rev; request missing design, UI, or 2D art inputs through the workflow graph.
2. Create an `art3d-brief` from feature/UI references and art direction. Keep unknown gameplay-impacting numbers as pending placeholders or explicitly labelled proposals until the owning design authority binds them.
3. Create `model-spec` for topology, polygon budgets by LOD, UVs, naming, units, scale, and pivot. Create `material-spec` for material assignments and texture maps, sizes, formats, and colour spaces. Create `rig-spec` and `animation-spec` when required; state rig hierarchy, skeleton naming, clips, fps, looping, and root motion.
4. Record the complete output in `asset-3d`: source file and hash, format, LODs, collision/physics, texture files, export settings, and engine constraints. Keep concept/proposal artifacts distinct from production-approved values.
5. Validate every artifact with `artifact-quality.py`; review plugin findings and lifecycle output. Use Blender adapter evidence for DCC formats. Missing Blender is `NOT_AVAILABLE` or `HUMAN_REQUIRED`, never evidence of a pass.
6. Ask an independent reviewer to assess visual quality, topology, UVs, naming, technical constraints, rights, and completeness. Human approval gates remain human-owned.
7. Hand off approved asset records to VFX and Engineering with current source revisions. Engineering owns importing and runtime integration.

## Rules

- Do not invent binding values. Keep unknowns as pending placeholders; label proposals and identify the decision owner.
- An existing model file alone is never production-ready. Every declared deliverable and integration constraint must be satisfied.
- Never write engine-ready client files or approval records from this skill.

## Generated & protected paths

Author only registered `art3d/` artifacts in `authoring`. Do not edit client `Assets/`; Engineering owns those paths. External DCC sources are referenced by manifests, not copied into routed paths.

## Validation delta

Run shared schema, lifecycle, trace, and approval checks plus the art3d quality plugin. The plugin parses glTF/GLB with the standard library and checks geometry budgets, materials, texture references, naming, scene structure, scale, axes, and required rig/animation content. FBX, Blend, and OBJ inspection uses Blender when available; unavailable inspection remains explicit. Report every state and reason.

## Review checklist

- [ ] Upstream ids and revisions are current; assumptions and proposals are labelled.
- [ ] Mesh topology, per-LOD budgets, UVs, scale, units, pivot, and names meet the model spec.
- [ ] Materials and texture maps meet resolution, format, and colour-space requirements.
- [ ] Rig, clips, fps, loop, and root-motion requirements are met where specified.
- [ ] All deliverables, hashes, collision/physics data, export settings, and engine constraints are present.
- [ ] An independent reviewer can reproduce the evidence and acceptance decisions.

## Failure handling

For rejected artifacts, record findings and recover with a new draft revision. For blocked work, record blockers and reason. If inputs change, refresh upstream revisions and rerun quality checks; stale outputs must be revalidated before handoff. Escalate subjective visual acceptance and binding gameplay choices to their human owners.

## Human gates

Human reviewers decide visual acceptance, rights/licensing questions, binding gameplay constraints, and any registered approval gate. Agents do not create approvals or self-approve.

## Report additions

Include artifact ids/revisions, upstream ids/revisions, format and deliverables, plugin results, Blender availability/evidence, human decisions, and VFX/Engineering handoff destinations.

## Tools

Blender is optional and detected through the shared tool probe; use it for DCC scene statistics and report `NOT_AVAILABLE` when absent. Standard-library glTF inspection requires no external tool.
