### Added

- **Pipeline.** Orca child worktrees at both levels. A subplan subtask takes `placement` (`shared`, the default, or `child`) and a `reason` (required for `child`); `subplan validate` rejects an unknown placement, `child` without a reason and `child` in a no-worktree repo (Unity project). `dispatch --subplan <file> --subtask <id>` (implement, review, qa) defaults `--paths`, the agent (implementer for implement, reviewer for review) and the placement from the subtask; `--placement shared|child` overrides it. A child prints `orca orchestration worker-start ... --worktree new-child --name <task branch>--<subtask or phase> --base-branch <task branch or --sha>`: a child implement session commits on its child branch and the task lead merges it and removes the child at once. `--phase lead --placement child` creates the task worktree with `--parent-worktree path:<integration checkout>` instead of `--no-parent`, and `--task integration:<repo> --phase qa --placement child` runs the QA in a child at the SHA. Every child command and spec says never to create or remove a child while a full `tests/run-all.sh` runs (shared `.git/config`); a child in a no-worktree repo is a usage error.
- **Pipeline.** `status` lists each task's leftover child worktrees (`children`: path, branch, merged; status schema updated) with a merge-then-`orca worktree rm` note, and `cleanup` names each one as "child of <task>" (its `orca worktree rm` command once merged).
- **Pipeline.** `verdict --subtask <id>` records a subtask's review or QA in its own file; every verdict is also kept per candidate (`<task>__<phase>__<sha12>__<by>.json`).

### Changed

- **Pipeline.** Shorter dispatch specs: the task-lead rules are seven short lines (commands spelled once), the implement, review and QA specs keep objective, owned paths, checks and report format, and the task spec JSON puts each key on one line. For the plugin-flow child-worktrees task the lead spec went from 55 to 24 lines and the implement spec from 47 to 17.

### Fixed

- **Pipeline.** Plans and subplans with a UTF-8 BOM (PowerShell `Out-File`/`Set-Content`) load instead of failing with a JSON error.
- **Pipeline.** A task review recorded by a model other than the task's paired reviewer (a paired review of a Codex subtask without `--subtask`) no longer overwrites the pair's review of the same SHA; it is kept per candidate and named on stderr.
