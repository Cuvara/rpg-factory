### Changed

- **run-all: an affected run that reaches no check passes.** With a base (`--affected`, `--inline-only` or
  `--workspace-only --base`), a run with 0 passed, 0 failed and every skip counted as not affected now exits 0 and
  prints `run-all: nothing the change reaches: no check ran (not affected: N)` after the summary. Any other run with
  0 passes (a skip for another reason, no base, `--only-suites` or `--within` alone, a full run) and any failure still
  exit 1; such a run publishes no suite PASS record.
