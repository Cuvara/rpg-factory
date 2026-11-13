# Run report: ci-followups

Tier M plan, four tasks, on branch `ci-followups` (base `main` `6ae4bb8`, the merge of plan `ci-matrix`, PR #106).
It closes the follow-ups of `docs/plans/ci-matrix/report.md`.

## Summary

- `tests/run-all.sh --only-cases C` gives the one `--only-suites` suite a case subset (it passes `--case C` like
  `--affected` does; `ALL` or empty runs every case; a subset publishes no suite PASS record; misuse exits 2 before any
  check). The CI suite job passes the cases `scripts/ci-plan.py` planned, so a slow suite runs only the cases a change
  touches. `workflow_dispatch` has a `base` input used when `full` is false (task `ci-cases`).
- `factory-pipeline.py`: the implement, verify and QA specs carry `RPG_FACTORY_WORKSPACE` when the run lead has it set;
  `gate` treats `docs/plans/backlog.md` like the plan file and its report (never stray), so follow-ups can go to the
  backlog in the integration commit as delivery.md says. `tests/pipeline.test.sh`: `pp_spec` reads only the prompt
  line, so stderr text with quote characters cannot break it; the task QA CI clause is asserted (task
  `pipeline-followups`).
- `scripts/orca-wait.sh --stall-ms 0` disables the frozen-output stall check instead of reporting an immediate stall
  (task `orca-wait-stall`).
- Docs: the unreleased `changelog.d/ci-matrix.md` no longer states the removed limitations; the ci-matrix report marks
  its follow-ups covered; backlog topic `ci-matrix-followups` keeps what stays open (task `followups-docs`).

Mode: implement

## Sessions and verdicts

| Task | Implementer | Verify (review + QA) | Candidate | Tier run |
|---|---|---|---|---|
| ci-cases | claude-opus-5-5 high | claude-opus-5-5 high: PASS | 5a31c09 | 529 checks: 308 passed, 0 failed, 221 skipped |
| pipeline-followups | claude-opus-5-5 high | claude-opus-5-5 high: PASS | dc7b411 | 529 checks: 313 passed, 0 failed, 216 skipped |
| orca-wait-stall | claude-opus-5-5 high | claude-opus-5-5 high: PASS | bb128d1 | 529 checks: 314 passed, 0 failed; orca-wait.test.sh 53/53 |
| followups-docs | claude-opus-5-5 high | claude-opus-5-5 high: PASS | e98e825 | 529 checks: 303 passed, 0 failed, 226 skipped |

Every review is SAME_MODEL: Codex is not available on this machine, so Claude reviewed Claude work (maintainer's
choice for this plan).

## Incident

The three wave-1 task worktrees were first created from `e0d67df`: the local `main` in the main checkout had not been
updated after PR #106 merged. The run lead fast-forwarded local `main` and the three task branches to `6ae4bb8` before
any task had a commit or an edit, and told each task lead to re-read from the new HEAD.

## Not verified here

- The `base` input of `workflow_dispatch` runs only on a manual dispatch; the PR's CI covers `--only-cases` only for
  suites whose planned cases are a subset.

## Limitations

- Open follow-ups are in `docs/plans/backlog.md` "ci-matrix-followups" (delivery.md size cap, the Windows python3 shim,
  free-form session notes in dispatch).
- Cost: NOT_AVAILABLE (no usage reported through Orca).
