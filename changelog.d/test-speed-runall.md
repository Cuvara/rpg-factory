### Added

- **run-all: `--affected --base B --within L` (scoped task QA).** Only the comma-separated suites and gated scripts in
  `L` run (the names `--only-suites` accepts), each limited to its affected cases (`--case`, as `--affected` passes
  them; every case when `tests/affected.py` gives none). A named suite the change does not reach still runs with all
  its cases: it is the task's explicit check. The suites the import closure selects outside `L` do not run and count as
  not affected; one line before the checks names them (`left to CI: N suites (a, b)`, or `left to CI: no base found`
  when no base resolves and only `L` runs). The inline checks keep the `--affected` rule. Exit 2 without `--affected`,
  with an empty list, with an unknown or release-only name, and together with `--only-suites`, `--only-cases`,
  `--inline-only`, `--release`, `--workspace-only` or `--list-suites`.
- **run-all: `--workspace-only --base B` (scoped integration QA).** Runs only the workspace checks the change reaches:
  each is gated like a suite by its inputs, and the two `claude plugin validate` lines by the key
  `claude-plugin-validate`; the others count as not affected. A change that reaches none of routing, skill or registry
  inputs no longer pays for the routing replay, the routing properties and the facts re-probe. It takes no test slot.
  Without `--base` (or when no base is found) every workspace check runs as before, and `--release` still runs
  everything.
- **run-all: per-check durations.** The result record (`rpg-factory.run-all-result/1`) gains `durations`, a list of
  `{name, seconds, status}` (`pass`, `fail` or `skip`) in run order: one entry per check line and one per block
  (`block <function>`); syntax lines, lines inside a block and suites reused from a PASS record have no entry. The end
  summary prints `slowest checks:` with the five slowest after the wall-time line. Both work at `-j 1` and `-j N`, and
  an interrupted run's record holds the checks that ended before it.
