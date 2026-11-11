### Added

- **Lead report in status.** The new `factory-pipeline.py report` verb records a task lead's report, and `status <plan>` shows per task the last lead report and READY_FOR_PR, so a run lead polling status sees completion without messages. `delivery.md` section 8 states the rule: the run lead polls status and never relies on messages alone; a task lead records its report before it sends the status message.
- **Slot holders and busy-directory processes named.** `status` and `cleanup` name the processes that hold a test slot for the plan's worktrees (PID, checkout, start time) and the orphaned processes (`wsl.exe` `sleep infinity` and the like) that keep a released worker's task directory busy (PID, command, start time). They never kill one.
- **Orca repo visibility.** `dispatch --phase lead` (and child placements) print `orca repo set --repo path:<repo> --external-worktree-visibility show` before the worktree add when `orca repo list --json` shows `hide` for the repo; `delivery.md` section 4 "Orca visibility" and the `.claude/CLAUDE.md` lesson name it.
- **Model-unavailable probe.** The Codex gateway's 503 wrappers (`[codex/<model>] [429]: The usage limit has been reached`, `[400] ... model_not_found`) map to MODEL_UNAVAILABLE with the upstream reason in the stall and route helpers.
- **Tier plan usage.** `factory-pipeline.py tier` with a positional plan argument now fails with a usage error instead of misreading it.

### Changed

- **Waiter message types.** `scripts/orca-wait.sh` receives `status` messages by default, so a task lead's report is no longer dropped, and survives heartbeat batches that carry no `deliveryId`.
- **Orphaned waiter.** When Claude Code reaps a background waiter's shell, the orphaned `orca-wait.sh` lock holder now exits when its parent dies, and the next waiter names an orphan PID instead of only exiting 3 "already held". A stale acquire guard is reclaimed.
- **Implementer refusal.** The implementer refusal now covers subtask records, not only plan tasks.
- **`verdict --fallback` text.** The usage text and the "available now" error state that `--fallback` takes the unavailable agent, not its replacement.
- **Test speed.** The `cli-selftest` case of `tests/pipeline.test.sh` runs faster (about 61 s before) and its selftest is stronger.

### Fixed

- **Released workers.** `status --orca-run` no longer lists released workers as UNRELEASED.
- **Lead report in a no-worktree repo.** In a repo without task worktrees the task HEAD is the integration branch and moves when the next task commits; a finished task (phase integrated or qa) keeps `READY_FOR_PR: yes` and no stale marker while its lead report is an ancestor of the HEAD. A report at a commit outside the HEAD's history is still stale.
- **Review findings of the lead-report task.** `status` READY_FOR_PR now honours subtask FAILs and stale reviews; slot holders are named in prefixed and lineage-only child worktrees too; and `tests/pipeline.test.sh` exits 2 on an empty case name inside a list (`--case tier,,status`, `--case ,tier`, `--case tier --case ,`), validated per selector as it is parsed instead of after the commas became spaces.
- **Repo visibility hint for a linked worktree.** A worker placement whose repo path is a linked worktree gets the `orca repo set ... show` hint for the main checkout, which is what `orca repo list` holds.
