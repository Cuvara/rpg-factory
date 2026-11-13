### Changed

- **Suite jobs run the planned cases.** A CI suite job passes the cases `scripts/ci-plan.py` planned to
  `tests/run-all.sh --only-cases` (handed to the suite as `--case`), so a suite with a case map runs only the affected
  cases; a plan row with `ALL` runs every case, and a case subset publishes no suite PASS record.
- **Dispatch base.** `workflow_dispatch` gains a `base` input (a sha or a ref the checkout has, e.g. `origin/main`) used
  when `full` is false, so such a run plans only the suites affected since that base; an empty or unusable base still
  plans every suite.
