### Added

- **Tests.** `tests/run-all.sh` has a suite registration inline check (it runs with every mode that runs the inline
  checks, including `--affected` and `--inline-only`): every `tests/*.test.sh` must be named on a run line or listed in
  the commented `SUITE_EXEMPT` list with its reason, and an exemption whose file is missing or that also has a run line
  fails too. The only exemption is `tests/orca-wait.test.sh`, which `tests/parallel-policy.test.sh` runs nested (case
  `orca-wait`). `tests/run-all-parallel.test.sh` covers the guard on a temp tree.

### Fixed

- **Tests.** Five suites that had no run line in `tests/run-all.sh` never ran in run-all, the `--affected` selection
  or CI: `tests/workflow.test.sh` (with the Codex Agent-tool runner pin), `tests/handoff-e2e.test.sh`,
  `tests/artifact-quality.test.sh`, `tests/asset-manifest.test.sh` and `tests/domains-foundation.test.sh` are now
  run-all suites, listed by `--list-suites` and selected by `tests/affected.py` and `scripts/ci-plan.py`.
