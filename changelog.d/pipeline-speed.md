### Changed

- **Pipeline: fewer subprocesses per verb.** `factory-pipeline.py` computes `git rev-parse` and `git worktree list` once
  per repo and probes each agent once per process (never cached across processes), so `status`, `gate`, `dispatch` and
  `verdict` start fewer processes with byte-identical output.
- **Pipeline: a re-QA after a QA FAIL runs only what the failure needs.** With `--failed-suites`, the QA and re-verify
  command is `tests/run-all.sh --affected --base <failed candidate> --within <failed suites + task check suites the fix
  delta reaches> -j 1`, no longer all the task check suites joined with the failed ones (`docs/pipeline-cli.md`).
- **Pipeline: the guard scripts are no longer listed as left to CI.** The `Left to CI (N affected suites ...)` line of
  the dispatch spec and the QA tier command leave out `scripts/checks/english-only.py` and
  `scripts/checks/portable-paths.py` (`WITHIN_GUARDS` in `tests/run-all.sh`), which `--within` already runs.

### Fixed

- **Pipeline: `cleanup` uses the ownership of `status`.** It treated every `<topic>-*` branch as the plan's own; it now
  uses `Lineage.owns`, so a `<topic>-v2` branch or worktree of another plan is no longer listed or offered for removal.
- **Tests: the no-duplicate `model_scope_widen` assertion counts the problem text.** It only looked for duplicate whole
  lines and would have missed a re-appended `; `-joined multi-problem error; each problem text must now occur once.
