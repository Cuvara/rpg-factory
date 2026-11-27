# Run report: plan-edit

Tier M plan, two tasks in one wave, on branch `plan-edit` (base `main` `82208fb`). It closes backlog topics
`plan-edit-verb`, `plan-edit-commit-guard` and `run-lead-waiter-reaped`.

## Summary

- New verb `factory-pipeline.py plan-edit <plan.json> --from <edited copy> [--commit [--message <text>]]` (task
  `plan-edit-verb`). It validates the copy through the `validate` code path, as if it were at the plan's path, and
  only with no error replaces the plan atomically (temp file in the plan's directory, mode kept, `os.replace`). With
  `--commit` it stages and commits only the plan file (default message `docs(plans): edit plan <id>`), never pushes.
  An invalid copy leaves the plan, HEAD and the index untouched (exit 1); a missing copy, an id mismatch or a plan
  outside a git checkout with `--commit` exits 2. It prints the task-level changes and a staleness note when paths or
  acceptance changed. Documented in `docs/pipeline-cli.md`; the "Plan edits are atomic" line of
  `skills/delivery/references/delivery.md` points to it.
- `skills/factory-core/references/parallel-work.md` carries the waiter lesson (task `waiter-lesson`): Claude Code stops
  the run lead's waiter under memory pressure and the run lead may not restart it on its own, so on every wake it runs
  `orca orchestration check --run <id>` and `factory-pipeline.py status <plan>`, restarts the waiter only when the
  owner asks, and keeps fewer task leads open on a loaded machine.

Mode: implement. Model rule: Codex was unavailable (`codex login status`: not logged in; recorded with `agents --down
codex`), so by the owner's instruction Claude Sonnet 5.5 implemented, Claude Opus 5.5 led and reviewed, and Claude
Sonnet 5.5 ran QA. Every review is SAME_MODEL (same vendor), noted by the gate.

## Sessions and verdicts

| Task | Implementer | Verify (review + QA) | Candidate | Tier run |
|---|---|---|---|---|
| plan-edit-verb | claude-sonnet-5-5 high (verb, docs, tests); the task lead (claude-opus-5-5) for a 2-line fix | review PASS at 17029d7 (claude-opus-5-5 medium); the run lead reviewed the delta to 4a20496, PASS; QA PASS by the task lead | 4a20496 | NOT_RUN (killed for low memory); the task's checks passed (below) |
| waiter-lesson | claude-sonnet-5-5 high | review PASS (claude-opus-5-5 medium, no findings); QA PASS (tier S, lead checks plus the run lead's parallel-policy run) | 94837c1 | `--only-suites tests/parallel-policy.test.sh` at 2d60a37: 625 checks, 377 passed, 0 failed |
| integration:plugin | - | QA PASS by the run lead (claude-opus-5-5) | 2d60a37 | `tests/run-all.sh --workspace-only`: 24 checks, 24 passed, 0 failed, 0 skipped |

Checks run directly, one at a time:

- plan-edit-verb at 4a20496: `tests/pipeline.test.sh --case plan-edit` 43/43, `tests/delivery-generic.test.sh` 47/47,
  `tests/line-budget.test.sh` 7/7. At 17029d7 the plan-edit case had 3 failures on Windows (the printed plan path used
  the OS separator); 4a20496 fixed them.
- waiter-lesson at 94837c1: `tests/skills-lint.sh` 726/726, `tests/line-budget.test.sh` 7/7.

## Limitations

- The full `tests/pipeline.test.sh` (every case) did not run locally: it was killed for low memory. CI runs it.
- The parallel-policy run at 2d60a37 reused the suite's PASS record for identical inputs instead of re-executing it.
- The 2-line fix 4a20496 was made by the task lead, not a fresh session; the run lead reviewed it.
- `validate` prints no staleness note of its own (the plan objective assumed one); `plan-edit` prints its own NOTE.
- `skills/delivery/references/delivery.md` is at 32767 of its 32768-byte cap: the next edit must trim first.
- Released verify sessions left their `tests/run-all.sh` runs alive, holding both test slots for hours; they ended on
  their own before the owner's stop order was carried out. The run lead's own run was stopped once by the harness for
  low memory and was restarted on the owner's word.
- Every Orca `worker-start` of this run left the prompt typed but unsubmitted in the Claude composer
  (`turn_start_unobserved`); the task leads submitted them with `orca terminal send --enter` (about 25 minutes lost).
- Cost: NOT_AVAILABLE.
