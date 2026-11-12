# Parallel work in the RPG workspace: what factory-core adds

The policy for splitting a task across agents (roles, the two-level flow, worktrees and child worktrees, Orca,
review and QA, cleanup, the session lifecycle, the delivery pipeline) is the delivery skill's
[delivery.md](../../delivery/references/delivery.md): that file is its only copy, usable in any repository.
This file keeps only what is specific to the UnityIndie RPG MMO workspace and this plugin repo. It adds no gate and
no prompt: when something is missing, the task reports it and other work continues. A "section N" reference in the
skills and docs means that section of delivery.md.

## Unity projects never get a worktree (delivery.md section 4)

A repo with registry `repos.<key>.worktrees: false` (the client) or a `ProjectSettings/ProjectVersion.txt` at its root
(registry `pipeline.no_worktree_markers`) is a no-worktree repo: each worktree would need its own multi-GB `Library/`
import. Its task lead runs in the main checkout on the plan `topic` branch (`orca agent launch --worktree
path:<main checkout>`); its subtasks, review and QA run one after another in that checkout and its tasks run in
sequence. Package, server, tool and plugin repos use worktrees and parallelise well. `subplan validate` and
`dispatch` refuse `placement: child` for a no-worktree repo.

## Shared exclusive resources (delivery.md section 4)

Registry `pipeline.exclusive_resources` names `unity-test`: Unity Editor and Unity test runs go one at a time across
the client and every package test project. A local or scratch Docker stack, the test lab and fixed ports are
exclusive too. The run lead assigns each to one task at a time; a task without the resource reports the dependent
check as `NOT_RUN` with the exact command and reason.

## Registry repos and the plugin checkout (delivery.md section 10)

Pipeline settings are the registry `pipeline` block (`registry/core.json`): tier thresholds, agents, review pairing,
exclusive resources, QA tiers and model policy. `plan.json` `repos.<key>` names a registry repo (`server`, `client`,
`netcode`, `dots`, `uitoolkit`, `skills`, `contracts`); work on this plugin names its own checkout:
`"plugin": {"path": "<this checkout>"}` (`.claude/CLAUDE.md`, "Developing this plugin"). `run-checks.py --repo <key>
--paths <files> --status` regrades the fast checks the gate reads. The snapshot of delivery.md section 2 is
`factory-context.sh`.

## Human gates, git safety and releases (delivery.md sections 7, 8 and 9)

- The consequential actions of delivery.md section 9 are registry `human_gates` and keep their rules.
- Commit, push, PR and merge only on request, except worker commits and task-branch integration inside a task the
  user asked for and the `deliver: pr` delivery exception (`git-safety.md` rule 5). Merging into develop, main,
  staging or release-* and pushing stay on the user's request.
- Tags and releases only with explicit release authorization from the user in the current task (`git-safety.md`
  rule 5, `.claude/CLAUDE.md` "Releases", `docs/releasing.md`): without it a task stops at READY_TO_TAG.
- One mutating command per worktree at a time is `git-safety.md` rule 14.
- Worktrees an Orca run created are removed with `orca worktree rm`, which also deletes the checked-out local branch
  when Orca can prove it is merged: merge a child into its parent first (delivery.md section 4, "Child worktrees").

## Tier commands of this plugin repo (delivery.md section 10, "QA tiers")

The QA tiers table of delivery.md carries this repo's commands (registry `pipeline.qa_tiers`); the single-verify rule
(`policy:single-verify`) is there too. The rules behind them are in `tests/README.md`: the run-all lock (one full run per machine; CI is the full-suite gate and
`tests/run-all.sh --workspace-only` covers what CI cannot, before the PR), suite reuse, `--affected` selection, test-run
slots and case selection. `tests/run-all.sh --release` and `tests/dogfood.sh --installed` run only for a release.

## RPG Orca notes (delivery.md section 5)

- Codex runs the rpg-factory hooks only after the user has trusted them once in Codex (a one-time step outside the
  run; `AGENTS.md`). A Codex session that stops at that trust prompt follows the "Codex, else Claude" fallback.
- The run lead's waiter is `scripts/orca-wait.sh --run <id>`; its suite runs inside `tests/parallel-policy.test.sh`.
- The run report is `docs/plans/<plan>/report.md` (`docs/plans/README.md`); verdicts and specs stay in the
  per-machine state dir, so a new machine re-runs review and QA. The report layout is `report.md` in this folder's
  `references/`; it includes the Cost table (`skills/delivery/references/delivery.md` section 8).
- `factory-pipeline.py dispatch --phase lead` takes a new task worktree's Orca parent from the checkout that holds
  `plan.topic` and falls back to the main checkout when none has it, so the run lead sets `plan.topic` to its own
  integration branch (or checks the topic out) before dispatching. Reason: in plan ci-matrix a task worktree landed
  under the main checkout instead of the run lead's worktree. Dispatch prints a stderr hint; `tests/pipeline.test.sh`
  covers it.
