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
  rule 5, `.claude/CLAUDE.md` "Releases"): without it a task stops at READY_TO_TAG.
- One mutating command per worktree at a time is `git-safety.md` rule 14.
- Worktrees an Orca run created are removed with `orca worktree rm`, which also deletes the checked-out local branch
  when Orca can prove it is merged: merge a child into its parent first (delivery.md section 4, "Child worktrees").

## Tier commands of this plugin repo (delivery.md section 10, "QA tiers")

The QA tiers table of delivery.md carries this repo's commands (registry `pipeline.qa_tiers`); the single-verify rule
(`policy:single-verify`) is there too. The rules behind them:

- **One full run per machine: the run-all lock.** A full `tests/run-all.sh` takes a per-machine lock and a second one
  waits. CI (`.github/workflows/tests.yml`, `--no-workspace --no-claude`) is the full-suite gate and
  `tests/run-all.sh --workspace-only` covers what CI cannot, before the PR. Four parallel full runs made every suite
  2-4x slower and timed some out. Never create a worktree or branch while a full run is in flight: the shared
  `.git/config` check fails (`.claude/CLAUDE.md` "Operating lessons").
- **The lock.** A full run (no `--affected` or `--only-suites`, or any `--release` run) takes the lock in the
  persistent state dir; a second full run waits (`waiting for full run <pid> in <checkout>`), `--no-wait` exits 3
  instead, and a lock whose holder is dead is taken over (`run-all: taking over stale full-run lock (<pid>)`).
- **Reuse.** A full run on a clean tree writes a result record for that tree; `--reuse` exits 0 at once on a PASS
  record of the same clean tree with at least the same coverage (`reused full run at <HEAD> (tree <tree>, <date>)`;
  a `--no-workspace` or `--no-claude` record does not satisfy a run without that flag). Each suite's PASS is also
  recorded under a hash of its inputs (`tests/affected.py hashes`, the conservative rule: the suite file, the paths
  it names, every file in the tree of each code file the suite reaches, helpers with a caller edge included, the
  global inputs and the tool versions, and the imports of every included code file in turn until nothing new is
  added). Three exceptions: a `scripts/lib` module that is imported stays narrowed to its importers, suites
  directly in `tests/` are not tree data, and the index docs `scripts/README.md` and `tests/README.md` count only
  where a suite names them. A later run skips that suite (`PASS  <check> (reused <suite> inputs <hash>)`). Suites
  graded by a postprocessor and checks that read the live workspace are never reused, and no record is published when the inputs
  changed during the run. `--no-reuse` runs every suite, `--release` never reuses, and an input mapping that is
  unsure runs the suite.
- **Selection.** `--affected` follows the narrow static graph of `tests/affected.py` (Python imports and the shell
  and jq helpers a script loads or runs by name): a library module or a helper selects only the suites of the
  scripts that reach it, and anything unsure runs. A miss there is caught by integration QA, whose suite reuse uses
  the conservative rule above. `--only-suites` is unioned with `--affected`. In either mode the live-workspace blocks and the
  checks that run a script outside a suite line (skill citations, `factory-context.sh`, pin status, pin plan,
  package ready, Netcode headless) are selected like suites by that script path, else they count as not affected;
  `--only-suites` may name such a script (`tests/run-all.sh` usage header). `--only-suites` exits 2 on a name
  run-all does not run; `tests/run-all.sh --list-suites` (read-only) prints the names it accepts, and
  `dispatch --phase qa` folds into `--only-suites` only the checks that list names (other checks stay extra
  commands). A check that mentions `tests/run-all.sh` is folded only when it is one plain standalone scoped
  invocation (an optional `env -u TMPDIR` and `bash` prefix, plain flag tokens, `--affected` or `--only-suites`
  among them); every other check that mentions run-all, a plain full run included, is printed `DO NOT RUN` and the
  QA session reports it NOT_RUN. No check is dropped.
- **Test-run slots.** The generic rule is in delivery.md section 10 ("QA tiers"). Here: `RPG_FACTORY_TEST_SLOTS` (default
  2, `0` disables the cap, a non-integer exits 2) caps the targeted runs, the slots are `locks/run-all-slots/<n>` in
  the persistent state dir, the wait line is `run-all: waiting for a test slot (<n> in use: <holders>)`, `--no-wait`
  exits 3 and a dead holder is taken over (`run-all: taking over stale test slot <n> (<pid>)`).
- **Case selection.** `pipeline.test.sh`, `parallel-policy.test.sh`, `routing.test.sh` and `git-guard.test.sh` take
  `--case NAMES` and `--list-cases`; `--affected` passes the cases `tests/affected.py cases` selects (case maps are
  `# case-map:` header lines of each suite), and an explicit `--only-suites` name runs all its cases.
- **Release.** `tests/run-all.sh --release` and `tests/dogfood.sh --installed` run only for a release.

## RPG Orca notes (delivery.md section 5)

- Codex runs the rpg-factory hooks only after the user has trusted them once in Codex (a one-time step outside the
  run; `AGENTS.md`). A Codex session that stops at that trust prompt follows the "Codex, else Claude" fallback.
- The run lead's waiter is `scripts/orca-wait.sh --run <id>`; its suite runs inside `tests/parallel-policy.test.sh`.
- The run report is `docs/plans/<plan>/report.md` (`docs/plans/README.md`); verdicts and specs stay in the
  per-machine state dir, so a new machine re-runs review and QA. The report layout is `report.md` in this folder's
  `references/`.
