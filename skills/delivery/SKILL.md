---
name: delivery
description: Generic multi-step delivery for any repository or workspace - the two-level flow (run lead, one task lead per task, short sub-sessions), agent routing with model fallback, cross-model review, child worktrees, session release, Orca waiting, QA tiers and the plan, verdict and gate pipeline. Use when a change is big enough to split into tasks run by separate agent sessions or worktrees, when you dispatch, review, integrate or clean up that work, or when you resume it. Not for a small single-session edit, not for product-specific module rules, checks or human gates (the project's own skills and instructions own those), and never for tagging, releasing or merging on your own.
argument-hint: "[tier|plan|dispatch|review|gate|resume] [task]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-pipeline.py:*), Bash(python3 -B ${CLAUDE_PLUGIN_ROOT}/scripts/factory-pipeline.py:*), Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/orca-wait.sh:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/run-checks.py:*), Bash(python3 -B ${CLAUDE_PLUGIN_ROOT}/scripts/run-checks.py:*)
---

# Delivery

The generic delivery flow for any repository. It needs no registry and no workspace layout: the pipeline script
reads `${CLAUDE_SKILL_DIR}/pipeline-defaults.json` when you pass `--registry none` (or set `RPG_FACTORY_PIPELINE_REGISTRY=none`); the installed plugin always ships `registry.json`, so the flag selects the defaults. Task: $ARGUMENTS
**Codex:** resolve `${CLAUDE_PLUGIN_ROOT}` as `PLUGIN_ROOT` in hooks, otherwise two directories above this skill's containing directory; use that absolute root for commands. Load other skills by reading their `SKILL.md`.
**Layering:** in a workspace routed by `rpg-factory:factory-core`, run factory-core first: it adds the registry, routing,
checks, human gates and the RPG specifics (`rpg-factory:factory-core`, its parallel-work.md: Unity no-worktree
repos, the `unity-test` resource, registry repos) and calls this skill for the generic flow. Elsewhere this skill is the whole flow.

## Roles

Two levels. The main session is the **run lead**: it plans, dispatches, integrates, runs integration QA, gates and
reports, and never edits task files. One **task lead** per task works in that task's worktree: it writes the subplan,
starts one short, fresh sub-session per subtask, has the result reviewed and QA-checked, and commits or merges. A
dispatched session follows its spec and never merges or pushes. Policy: [references/delivery.md](references/delivery.md) section 1.

## Flow

Run the script as `python3 -B ${CLAUDE_PLUGIN_ROOT}/scripts/factory-pipeline.py <verb>`; outside an RPG workspace run
`python3 -B ${CLAUDE_PLUGIN_ROOT}/scripts/factory-pipeline.py --registry none <verb>` (the option also works after the verb).

Each step is stated once, in [references/delivery.md](references/delivery.md) section 10 (policy there; command forms
and flags: `${CLAUDE_PLUGIN_ROOT}/docs/pipeline-cli.md`):

1. **Tier** - step 1: `tier` prints S, M or L; every tier gets a `plan.json` and a task lead.
2. **Plan** - step 2: write `plan.json` (`${CLAUDE_PLUGIN_ROOT}/docs/schemas/pipeline-plan.schema.json`), `validate` it.
3. **Task lead, subplan, implement** - step 3: `dispatch --phase lead`, then the task lead's `subplan` and `--phase implement`.
4. **Cross-model review and task QA** - step 4: `dispatch --phase review`, `--phase qa`, `verdict`.
5. **Integrate** - step 5 (checklist: section 7).
6. **Integration QA** - step 6.
7. **READY_FOR_PR** - step 7: `gate plan.json`.
8. **PR** - step 8: only when the user asked for `deliver: pr`.
9. **Cleanup and report** - step 9 (section 8): `cleanup plan.json` until CLEAN.

Resume with `status plan.json` (it re-derives progress from git and the verdicts) and continue at the first open step.

## Orca

When Orca is available it is the coordinator: dispatch prints `orca` commands, workers report with
`orca orchestration`, and the run lead waits on them instead of polling (policy: references/delivery.md section 5).
Without Orca, dispatch prints Agent-tool commands for the same flow.

## Never

- Never tag, release, merge, force-push or delete a branch without the user's explicit authorization in this task.
- Never stage, stash or commit another session's files; one task, one worktree, one owner per path.
- Never create a second clone for parallel work; use a worktree.
- Never mark a check PASS you did not see run; an absent check is NOT_RUN, not a pass.

## References - read when

- [references/delivery.md](references/delivery.md) - before delegating, dispatching workers or integrating their branches (the only copy of the policy).
- `${CLAUDE_PLUGIN_ROOT}/docs/pipeline-cli.md` - command forms and flags of `factory-pipeline.py`: dispatch, verdict, fallback reviews, gate, cleanup, model flags.
- `${CLAUDE_SKILL_DIR}/pipeline-defaults.json` - the agents, review pairing, routing and QA tiers used without a registry.

All paths above are relative to `${CLAUDE_SKILL_DIR}`.
