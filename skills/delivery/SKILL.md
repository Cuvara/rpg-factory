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

1. **Tier.** `tier --plan plan.json --repo <key> --paths <files>` (a plan naming the repo by path; a registry repo:
   `tier -- --repo <key> --paths <files>`) prints S, M or L and the flow. Every tier gets a `plan.json` and
   a task lead; S is a one-task plan. The run lead never implements.
2. **Plan.** Write `plan.json` (`${CLAUDE_PLUGIN_ROOT}/docs/schemas/pipeline-plan.schema.json`): `repos.<key>.path` names the checkout,
   each task has owned paths, deps, a `kind` and a branch. Small tasks with disjoint owned paths. A repo marked
   `worktrees: false`, or one holding a configured no-worktree marker, runs its tasks in sequence in the main checkout.
   `validate plan.json` must print OK.
3. **Dispatch the task lead.** `dispatch plan.json --task <id> --phase lead --report-to <run id> --runner orca`
   (`--runner agent` or `print` without Orca; `--orca-unavailable <reason>` records why). One task lead per task worktree.
4. **Subplan and implement (task lead).** `subplan validate subplan.json`, then
   `dispatch ... --phase implement --subplan subplan.json --subtask <sid>`; shared worktree or an Orca child per `placement`.
   Code, tests, fixes and refactors go to Codex, prose to Claude: the model table in references/delivery.md section 10.
   The task lead does not implement. A missing model never stops the task: every role falls back to the available one.
5. **Review and QA (task lead).** On a frozen SHA, `dispatch ... --phase review --sha <sha>`: the other model
   reviews; no pair available means the same model with `SAME_MODEL (fallback: <model> unavailable)`. Then
   `--phase qa`. QA by tier: the task runs its affected checks once; integration runs the repository's full gate.
   Record each result with `verdict`.
6. **Integrate (run lead).** Merge each task branch per section 7 of the reference, run integration QA on the
   integration HEAD, then `gate plan.json`: READY_FOR_PR is the only green state. Push and open the PR only when
   the user asked for a PR; never merge.
7. **Resume.** `status plan.json` re-derives progress from git and the verdicts; continue at the first open step.
8. **Cleanup and report.** Remove the run's worktrees (keep the branches), release every Claude and Codex session,
   `cleanup plan.json` until CLEAN, then report what ran with exact counts and what did not run.

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
- `${CLAUDE_SKILL_DIR}/pipeline-defaults.json` - the agents, review pairing, routing and QA tiers used without a registry.

All paths above are relative to `${CLAUDE_SKILL_DIR}`.
