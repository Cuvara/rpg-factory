### Added

- **Plans in the repo.** `docs/plans/` holds the plugin's pipeline plans (`docs/plans/<topic>.json`, starting with
  `plugin-flow-2.json`), the backlog (`docs/plans/backlog.md`) and run reports (`docs/plans/<plan>/report.md`), so a
  run can resume from any clone. `docs/plans/README.md` states what stays in the per-machine state dir (verdicts,
  specs, subplans, Orca state: a new machine re-runs review and QA) and the portable `repos.<key>.path` forms.
  `tests/parallel-policy.test.sh` fails on any machine-specific absolute path under `docs/plans/`.
- **Portable plan repo paths.** `scripts/lib/plan_paths.py` (`resolve_repo_path`) resolves a plan-relative path and
  `${RPG_FACTORY_WORKSPACE}/<repo>` against the workspace root; a later task wires it into `factory-pipeline.py`.
- **Run lead waiter.** `scripts/orca-wait.sh --run <id>` waits on a Run for `worker_done`, `escalation` or
  `question`, acks heartbeats, keeps waiting on timeout, prints the first real message and exits; one instance per
  Run by a lock file in the state dir (`tests/orca-wait.test.sh`, fake `orca`).
- **Run report rule.** The run lead writes `docs/plans/<plan>/report.md` at integration (sessions, verdicts, checks,
  limitations) and commits it with the integration.

### Changed

- **Parallel work policy.** `parallel-work.md` section 5 names `scripts/orca-wait.sh` as the run lead's single
  waiter; section 8 adds the run report and the lesson that plan edits are atomic (write a copy, validate it, then
  replace the plan).
