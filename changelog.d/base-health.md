### Added

- **Pipeline known failures.** A plan may list `known_failing` (`[{check, reason}]`) for checks that already fail at the
  task base. `validate` warns per entry and rejects malformed ones. The task-lead, task QA and integration QA specs carry
  the list with the rule: a failure of a listed check that also fails at the base is `FAIL_AT_BASE` (named on the QA
  report, not a task FAIL), and a listed check that now passes is reported as fixed. `dispatch --phase lead` prints a
  base health hint (`gh run list --branch <base> --limit 1`, print only) for a repo with a GitHub remote.
  `templates/pipeline/qa-report.md` gains `Failing at base` and `Fixed` lines.
