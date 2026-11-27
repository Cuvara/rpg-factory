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
exclusive resources, QA tiers and model policy. Its `pipeline.subagents.models.claude.agent` names
`rpg-factory:factory-explorer`, the read-only scout of delivery.md section 8 "In-session subagents". `plan.json`
`repos.<key>` names a registry repo (`server`, `client`, `netcode`, `dots`, `uitoolkit`, `skills`, `contracts`); work
on this plugin names its own checkout: `"plugin": {"path": "<this checkout>"}` (`.claude/CLAUDE.md`, "Developing this
plugin"). `run-checks.py --repo <key> --paths <files> --status` regrades the fast checks the gate reads. The snapshot
of delivery.md section 2 is `factory-context.sh`.

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
(`policy:single-verify`) is there too. The runner rules behind them are in `tests/README.md`: the run-all lock, suite
reuse, `--affected` and `--within` selection, test-run slots and case selection. The shape for this repo:

- **Task QA is scoped:** `tests/run-all.sh --affected --base <review base> --within <check suites> -j 1` runs only the
  task's check suites, each limited to the cases the change reaches (all cases when unsure; a named suite the change
  does not reach still runs). A suite the change reaches outside the list prints `left to CI: N suites (...)` and is
  not run. A plan's task `checks` name the suites that test the changed behaviour; the plan author picks them and the
  verify session may add one it finds missing and says so.
- **CI is the breadth gate:** it runs every affected suite on Linux and Windows per PR, and `ci-ok` must be green
  before merging (`gh pr checks <pr> --watch`).
- **Integration QA is scoped too:** `tests/run-all.sh --workspace-only --base <plan base>` runs only the workspace
  checks whose declared inputs in `tests/affected.py` the change reaches (unsure or a global input runs the check;
  without `--base` all of them). Exit 6 (nothing the change reaches) is NOT_RUN, never a pass: then run
  `tests/run-all.sh --workspace-only` without a base and grade that run. `tests/run-all.sh --release` and
  `tests/dogfood.sh --installed` run everything and only for a release.
- **On a loaded machine run task QA with `-j 1`, one task QA at a time; a task lead reports NOT_RUN after one retry
  instead of looping.** Reason: plans policy-followups, path-audit, flow-lows and run-lows - verify sessions lost their
  tier run many times when Claude Code stopped background shells under low memory.

- **Before rerunning a tier command whose terminal or wrapping command is gone, look for its run first:** check the slot
  directories (`<persistent state dir>/locks/run-all-slots/<n>`: `checkout`, `pid`, `winpid`, `args`) for a live run of
  your checkout and read its result with `tests/run-all.sh --last-result` instead of starting a copy (a second run of
  the same checkout and arguments exits 4 and names the holder; `--attach` waits for it and returns its status).
  `factory-pipeline.py status` names each holder with the run's last check, its counts and the age of that update (the
  slot's `progress` file): a run whose update is recent is live, however it was started. Stop
  that process only when you started it, by its PID and never by pattern. Reason: backlog run-all-orphan-after-reap - a
  stopped wrapper left run-all running and holding its test slot while the session believed it dead, so a rerun queued
  behind or duplicated its own run.

## Stacked dispatch and test selection in this repo (delivery.md sections 4 and 10)

The stacked-dependent rule is delivery.md section 4, "Stacked dependents" (`policy:stacked-dispatch`); these are the
lessons of this repo behind it, each with its reason.

- **Any edit under `scripts/assetgen/*.py` selected every suite:** a leaf file that only an EXTRA pattern of
  `tests/assetgen.test.sh` covered was unsure, and unsure runs all. The fix is plan assetgen-v2-core task
  affected-leaf-fix (`tests/affected.py` counts a leaf an EXTRA pattern covers as named). A verify that selects most
  suites costs about an hour.
- **`scripts/factory-cmd.py` widens the selection:** it reaches a wide import closure and selects many suites, while
  `scripts/factory-pipeline.py` is narrowed by `tests/affected.py` `PIPELINE_SUITES`. Keep a task that touches it
  small; the live number is the pre-flight `selected N of M suites` that `dispatch --phase verify` prints (a warning
  above `--suite-warn`, default 40): read it before starting the session.
- **On Windows Git Bash `python3` can be the Microsoft Store stub:** `tests/run-all.sh --affected` now exits 2
  instead of silently running every suite (seen in the finalize-verb verify).
- **A stacked verify waits for the dependency's review PASS:** verifying earlier tests code that may still change, so
  dispatch exits 2 until the PASS SHA is in HEAD.
- **Merge, never rebase, the dependency branch:** a rebase rewrites the dependent's own commits, so the SHAs that its
  recorded verdicts and the shared worktree name are gone; a clean merge keeps them, and the gate credits it as a
  sync merge.
- **One in-flight dependency only:** two would need two moving bases and an ambiguous own delta.
- **A sibling worktree beside the integration checkout, never a child of the dependency's worktree:** removing the
  dependency's worktree after its integration would take a child with it, and a `<dep branch>--*` name reads as the
  dependency's child in status and cleanup.

## RPG Orca notes (delivery.md section 5)

- Codex runs the rpg-factory hooks only after the user has trusted them once in Codex (a one-time step outside the
  run; `AGENTS.md`). A Codex session that stops at that trust prompt follows the "Codex, else Claude" fallback.
- The run lead's waiter is `scripts/orca-wait.sh --run <id>`; its suite runs inside `tests/parallel-policy.test.sh`.
- Claude Code stops that waiter under memory pressure (workflow-slim twice, path-audit, owner-policy) and may not
  restart it on its own, so messages waited for an owner nudge. On every wake (task notification, owner message, "You
  have N orchestration messages") run `orca orchestration check --run <id>` and `factory-pipeline.py status <plan>`;
  restart the waiter only when the owner asks; on a loaded machine keep fewer task leads open.
- The run report is `docs/plans/<plan>/report.md` (`docs/plans/README.md`); verdicts and specs stay in the
  per-machine state dir, so a new machine re-runs review and QA. The report layout is `report.md` in this folder's
  `references/`; it includes the Cost table (`skills/delivery/references/delivery.md` section 8).
- `factory-pipeline.py dispatch --phase lead` takes a new task worktree's Orca parent from the checkout that holds
  `plan.topic` and falls back to the main checkout when none has it, so the run lead sets `plan.topic` to its own
  integration branch (or checks the topic out) before dispatching. Reason: in plan ci-matrix a task worktree landed
  under the main checkout instead of the run lead's worktree. Dispatch prints a stderr hint; `tests/pipeline.test.sh`
  covers it.
- **A start prompt can stay unsubmitted in its Orca terminal, and `input_accepted` is no proof:** a verify session's
  prompt once sat unsubmitted for about 30 minutes until the run lead pressed Enter, and on 2026-11-18 two more sessions
  of plan runtime-quirks had theirs unsubmitted (the external-path-uri verify worker, `turn_start_unobserved`, and the
  launch-note-file fix1 worker, idle about 17 hours). When a dispatched session shows no progress a few minutes after
  launch, run `factory-pipeline.py nudge <plan>` and, when it lists STUCK, `--send` (one Enter per spec; the answer
  `nudged, still stuck` means relaunch the session). `tests/pipeline.test.sh` covers the verb.
- **Notes never go on the `--prompt` line:** a lead launch failed with `unknown option '-FilePath'` because a run lead
  note containing quotes was appended to `--prompt`, and cmd.exe misread the quotes and parentheses. Pass extra notes
  with `dispatch --note` or, for text with quotes, parentheses or newlines, `--note-file`; the prompt carries only the
  spec pointer. `tests/pipeline.test.sh` covers pointer-only launch lines and `--note-file`.
- **Never message a finished dispatch:** a `status` (or any) `orca orchestration send` message sent to a dispatch
  whose session has already finished reaches no one and makes Orca start a follow-up worker (two appeared in plan
  plugin-flow-5). Send lead messages only to the run of a live task lead (`--to run:<id>`), and put the context a
  session needs into its start prompt (the dispatch spec, `--note` or `--note-file`), not into a later message.
- `orca terminal read` answering `terminal_handle_stale` is not proof that a task lead ended: check
  `orca orchestration worker-list --run <its run>` for liveness and read the lead's own Run messages before
  dispatching a replacement lead. Reason: on 2026-11-27 Orca resumed the first pkg-core lead one minute before a
  replacement was dispatched, and both started a verify of the same SHA; the first lead's verify noticed the foreign
  Sandbox editor and stopped.
