# Run report: pipeline-lows

Tier M plan, three tasks in two waves, on branch `pipeline-lows` (base `main` `a7cdcd1`, plan commit `daebb46`). It
covers the status, CLI doc, dispatch and gate lows of plugin-flow-5-followups, policy-followups-leftovers,
workflow-slim-followups and qa-reach-followups-2. Wave 2 (dispatch-lows) waited for status-fields: both own
`scripts/factory-pipeline.py` and `tests/pipeline.test.sh`.

## Summary

- Task `status-fields`:
  - `factory-pipeline.py status --json` has per-task `lead_report` (`{at, sha, summary, current}` or null) and
    `ready_for_pr` (`{ready, missing}` or null), computed with the text notes, and a top-level `model_scope_widen`
    (`[]` when none). The text output and the stderr lines are unchanged; `docs/schemas/pipeline-status.schema.json`
    types the fields.
  - The `verdict` usage names `--phase verify` and `--failed-at`, and says one task review covers every subtask.
  - `docs/pipeline-cli.md` documents the `report` verb, READY_FOR_PR and the lead report notes, the new JSON fields,
    the cleanup BUSY? and SLOT lines and every `scripts/orca-wait.sh` exit code. Changelog fragment
    `changelog.d/pipeline-lows-status.md`.
- Task `dispatch-lows`:
  - A printed `orca orchestration worker-start` carries `--run` (from `--orca-run`, else the task's recorded Orca Run;
    not for `--phase lead`).
  - Review and verify specs diff from the merge base of the topic and the candidate when the task branch merged the
    topic, so a merged integrated task no longer shows foreign scope findings.
  - The QA spec cleanup is `rm -f -- "${S:?}"/*.log`.
  - The known-failing text is computed once per prompt; an unknown `known_failing` key gets only the error.
  - `gate` credits files whose content equals the merge base with the default branch, and `docs/plans/backlog.md`.
    Changelog fragment `changelog.d/pipeline-lows-dispatch.md`.
- Task `doc-lows`: the `scripts/README.md` entry of `orca-wait.sh` describes the script (wake types, exit codes 3, 5
  and 6); factory-core `SKILL.md` step 11 is "Verify session: review, then QA".

Mode: implement. Model rule: Codex was unavailable (`agents --down codex`), so by the owner's instruction Claude
Sonnet 5.5 implemented, Claude Opus 5.5 led and reviewed (SAME_MODEL), and verify sessions ran QA.

## Sessions and verdicts

| Task | Verify | Candidate | QA run |
|---|---|---|---|
| doc-lows | review PASS, QA PASS | c1d635a | `--affected --base daebb46 --within tests/skills-lint.sh -j 1`: 415 passed, 0 failed |
| status-fields | review PASS, QA FAIL (a stderr strip in one test); review and QA PASS | 3f28833 | `--affected --base d429c34 --within tests/pipeline.test.sh -j 1`: 415 passed, 0 failed |
| dispatch-lows | review PASS, QA FAIL twice (a pinned spec text, a split usage phrase); review and QA PASS | 041df0a | `--affected --within tests/pipeline.test.sh -j 1`: 408 passed, 0 failed |
| integration:plugin | QA by the run lead | bef25d4 | `--workspace-only --base origin/main`: 8 of 19 checks run, 8 passed, 0 failed (809 s) |

## Limitations

- Every review is SAME_MODEL (Claude implemented and reviewed).
- The second status-fields QA used the previous candidate as base (the cases of the fix delta).
- The run lead's dispatch predates the `--run` fix, so task leads added `--run` by hand in this plan.
- Cost: NOT_AVAILABLE.
