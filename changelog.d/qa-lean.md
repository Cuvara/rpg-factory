### Changed

- **One verify session per task.** A task is reviewed and tested once, after every subtask is committed. New
  `factory-pipeline.py dispatch --phase verify --sha <sha>` starts one fresh session of the reviewing model: it reviews
  the diff first (a blocking finding is a FAIL and no test runs), then runs the task tier command once. After a FAIL and
  a fix, one fresh re-verify session reviews the fix delta and reruns the failed suites plus what the fix touched.
  `verdict --phase verify` records the review and QA verdicts of the SHA. `--phase review` and `--phase qa` stay for a
  lead that needs only one of them, for example integration QA. `status` names `--phase verify` after the last subtask.
- **Implementers run no suites.** An implementation spec asks for a syntax check of the edited files only. `validate`
  warns when a task's `checks` would make an implementer run a suite.
- **No per-subtask review.** The gate no longer blocks on a subtask review. A prose subtask written by the reviewer's
  model is covered by the verify review. A code subtask written by the reviewer's model is printed as an accepted
  `SAME_MODEL (single verify)` note.
- **Leads do not re-run checks.** The task lead and the run lead read the verify report. The run lead keeps only the
  integration QA and CI.
- **Narrower selection.** `tests/run-all.sh` and `tests/affected.py` are no longer global inputs of
  `tests/affected.py`. A runner change selects `tests/run-all-parallel.test.sh` and `tests/affected.test.sh`, and a
  change to `tests/affected.py` selects `tests/affected.test.sh`. CI still runs every suite.
- **Policy.** `delivery.md` sections 1, 6 and 10 and the QA tiers table describe the single verify flow (new
  `policy:single-verify` marker). `parallel-work.md`, `.claude/CLAUDE.md` and the `delivery` skill point to it.
  `tests/parallel-policy.test.sh` checks the new table rows and that the rule has one copy.
