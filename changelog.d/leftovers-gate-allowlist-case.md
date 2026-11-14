### Fixed

- **Gate.** The run lead file English check (`gate` and `status`) now looks the `tests/fixtures/english-allow.txt`
  entry up with the exact tree path, as `scripts/checks/english-only.py` does. It used the case-folded path on Windows,
  so an allowlisted run lead file with an upper-case letter in its path (plan id `GmCase`, `docs/plans/GmCase/report.md`)
  was reported as a false English blocker that CI never raised. Only the run lead file membership test stays case-folded.
