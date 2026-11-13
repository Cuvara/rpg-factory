### Added

- **CI plan.** `scripts/ci-plan.py` plans the CI suites from `tests/affected.py`: one matrix row per `{suite, os}`, and
  anything unsure (no usable base, an `affected.py` error, a changed workflow, action, `tests/run-all.sh`,
  `tests/affected.py` or plan file) plans every suite. Covered by `tests/ci-plan.test.sh`.
- **Inline-only run.** `tests/run-all.sh --inline-only` runs only the inline checks (JSON parse, `bash -n`,
  `py_compile`, executable bits, wording greps), so a PR that selects no suite still gets them.
- **Windows suites.** `tests/ci-windows-suites.txt` lists the suites that also run on `windows-2025`; every suite runs on
  `ubuntu-24.04`.

### Changed

- **CI workflow.** `.github/workflows/tests.yml` runs one matrix job per affected suite (`plan` job, then `suite`) instead
  of the whole `run-all` on every PR; the inline checks run on both OSes. `workflow_dispatch` with `full=true` (the
  default) runs every suite. A release runs the full matrix on its commit besides the local
  `tests/run-all.sh --release` gate (`docs/releasing.md`).
- **Required check.** `ci-ok` is the single required check: branch protection must require only `ci-ok`. The old
  `run-all (no workspace, <os>)` checks no longer exist, and the per-suite job names change with every plan.
- **QA policy wording.** `factory-pipeline.py` QA specs and the `qa_tiers` description follow the
  affected-only CI: CI runs the affected suites per change, `ci-ok` must be green before merging, and
  `workflow_dispatch` with `full=true` runs every suite.
- **Merge gate wording.** `skills/delivery/references/delivery.md` calls CI the merge gate (`ci-ok`) in the QA tiers
  table and bullet, because CI runs only the suites a change affects.
