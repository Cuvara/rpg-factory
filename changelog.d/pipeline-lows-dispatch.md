### Fixed

- **Delivery pipeline: `worker-start --run`.** The `orca orchestration worker-start` command that `dispatch` prints
  carries `--run <id>` when a Run is known (`--orca-run`, else the task's recorded `orca_run`; never for
  `--phase lead`), so a task lead's sub-sessions join its Run without the lead adding it by hand.
- **Delivery pipeline: review and verify diff base.** `dispatch --phase review` and the verify spec diff from the
  newest topic commit a task branch merged instead of from the plan base, so a task that merged another integrated
  task no longer shows that task's files as scope findings (a false FAIL).
- **Delivery pipeline: QA spec cleanup.** The QA spec tells the worker to clean up by a literal path or a guarded
  variable (`rm -f -- "${S:?}"/*.log`), never by a variable that may be empty, which expanded to an unscoped path and
  stalled an unattended worker on a permission prompt.
- **Delivery pipeline: known failing checks.** `known_failing_text(plan)` runs once per prompt, and a `known_failing`
  entry with an unknown key gets only the validation error, no longer also the "known failing at base" warning.
- **Delivery pipeline: gate stray changes.** `gate` no longer reports as "changes outside every task's owned paths"
  the files that came in with a merge of the default branch (also with the plan base pinned to a SHA or a stale local
  default branch after a merge of `origin/<b>`): a file whose content equals the merge-base of the integration HEAD
  and a default branch ref is credited, while a conflict resolution or later edit in it is still stray. The run
  lead's `docs/plans/backlog.md` is credited wherever the plan file lives, like the plan file and its report.
