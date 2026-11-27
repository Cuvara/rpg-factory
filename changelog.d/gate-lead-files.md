### Changed

- **Pipeline gate.** `factory-pipeline.py gate` keeps the integration QA (or the tier XS lead QA) current when every
  file changed since its SHA, an ancestor of the integration HEAD, is a run lead file (the plan file, its `report.md`,
  the `backlog.md` beside it), and prints a NOTE: a report-only commit no longer forces a workspace QA rerun. Any other
  file, a non-ancestor QA SHA or a git failure still marks it STALE.
- **Pipeline gate.** The gate blocks a run lead file on the integration branch that holds machine-specific path text,
  naming the file. The rule lives in `scripts/lib/plan_paths.py` and is shared with the portable-plans case of
  `tests/parallel-policy.test.sh`, so CI and the gate cannot drift.
