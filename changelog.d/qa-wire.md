### Added

- **Orca visibility for task worktrees.** A worktree made with `git worktree add --no-track` has no Orca lineage and
  lands in Orca's hidden section. `factory-pipeline.py dispatch --phase lead` (and every place that prints a worktree
  creation) now prints `orca worktree set --worktree path:<dir> --parent-worktree path:<parent> --display-name
  <topic>-<task> --workspace-status in-progress` before `orca agent launch`, with the integration (else main) checkout
  as parent; a child worktree a task lead makes gets the task worktree as parent. Documented in `delivery.md` section 4
  ("Orca visibility"); `tests/pipeline.test.sh` asserts the line and `tests/parallel-policy.test.sh` has a mutation case.
- **Routing scenario** in `tests/routing.test.sh` for the new QA wiring.

### Changed

- **`dispatch --phase qa` prints the case list.** The QA spec names the exact cases `tests/affected.py` selects for the
  candidate, so task QA runs only the cases a change can break.
- **`dispatch --phase implement` forbids whole slow suites.** An implementer runs only the targeted checks of its spec
  and, in a suite with cases, only the cases its change touches (`--case`).
- **Lead QA for tier S and docs-only tasks.** Those tasks get the task lead's own QA verdict instead of a QA session.
- **QA tiers carry typical times, and the test-run slot rule replaces the "at most 2 full runs" lesson.** `delivery.md`
  section 10 and `.claude/CLAUDE.md` describe the machine-wide test slots (`RPG_FACTORY_TEST_SLOTS`, default 2): a busy
  machine queues targeted runs instead of slowing every suite 2-4x, and a QA worker's background run is stopped before
  the worker is abandoned. `parallel-work.md` keeps only the RPG slot names and case selection.

### Fixed

- **`tests/parallel-policy.test.sh` and `tests/orca-commands.test.sh` read the single policy copy.** After the generic
  policy moved to `skills/delivery/references/delivery.md` they still read `parallel-work.md` and failed; they now check
  `delivery.md` and keep their mutation and command checks.
