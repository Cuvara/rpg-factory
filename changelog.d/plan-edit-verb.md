### Added

- **Pipeline.** `factory-pipeline.py plan-edit <plan.json> --from <edited copy> [--commit [--message <text>]]` makes the
  atomic plan edit of delivery.md section 8 enforceable: it validates the copy with the `validate` code path and
  replaces the plan (temp file plus `os.replace`) only when there is no error. With `--commit` it stages and commits
  only the plan file, never pushing. An invalid copy leaves the plan, HEAD and the index untouched (exit 1), and a
  missing copy, an `id` mismatch or `--commit` outside a git checkout exits 2. It prints the tasks added, removed and
  changed (paths, acceptance, deps) and the staleness note. This closes the case where `validate | grep && git commit`
  committed an invalid plan because `grep`'s exit code decided.
