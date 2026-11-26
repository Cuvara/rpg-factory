# Run report: flow-lows-2

Tier M plan, four tasks in three waves, on branch `flow-lows-2` (base `main` `faf2745`, plan commit `6873b21`). It
covers the Orca, cleanup, plan-edit, validate and case-map lows of plugin-flow-5-followups, workflow-slim-followups,
policy-followups-leftovers, plan-edit-followups and qa-reach-followups-2. Wave 2 (plan-lows) waited for orca-lows: both
own `scripts/factory-pipeline.py` and `tests/pipeline.test.sh`.

## Summary

- Task `orca-lows` (none of its items was fixed on main before):
  - New read-only verb `factory-pipeline.py orca-wait --worktree PATH [--gone] [--timeout 60] [--interval 2]` polls
    `orca worktree list --json` (exit 1 on timeout or when Orca fails). It is not `scripts/orca-wait.sh`, the run
    lead's message waiter.
  - The lead handoff prints `orca-wait --worktree <path> && orca worktree set ...`, so the lineage is set only once Orca
    lists the worktree; cleanup prints `orca-wait --gone --worktree <path>` after each `orca worktree rm`, before the
    first `git branch -d`.
  - A concise `worker-list` row released through `terminalState` without `state` counts as released.
  - Changelog fragment `changelog.d/flow-lows-2-orca.md`.
- Task `guard-reach`:
  - `scripts/checks/workspace-readers.sh` reads only `scripts/` and `tests/` (hooks and registry files are global and
    already select it), so the selection was already its read set; six `tests/affected.test.sh` cases pin it.
  - `parallel-work.md` records the lesson: a message to a finished Orca dispatch creates a follow-up worker. Changelog
    fragment `changelog.d/flow-lows-2-guard.md`.
- Task `plan-lows`:
  - `validate` adds a NOTE per stale recorded review or QA verdict (the verdict fingerprint cannot tell which field
    changed); exit code unchanged; also in `--json` notes.
  - `plan-edit` reads the edited copy once through `read_plan` (no behaviour change).
  - Every `tests/pipeline.test.sh` case group names `scripts/lib/pipeline_route.py` symbols; a one-line change inside
    one function selected all 26 groups before and 19 to 26 after (`record`/`mark` 19, `qa_checks` 22, most others 24
    or 26: `cmd_dispatch` and `cmd_status` reach most of the module). A cli-selftest case recomputes the closure.
  - Scope widened by plan-edit (reason in the plan): `delivery.md` "Orca visibility" and cleanup and
    `docs/pipeline-cli.md` describe the worktree wait and the verb. Changelog fragment `changelog.d/flow-lows-2-plan.md`.
- Task `ci-fix` (added by plan-edit after CI failed on PR 153: `tests/delivery-generic.test.sh` delivery.md size cap
  and a stale `tests/affected.test.sh` expectation): `delivery.md` 33282 -> 32307 bytes (wording tightened in sections
  4, 5, 8 and 10, no rule, command, flag or heading removed); the pipeline_route.py half of the affected case accepts
  ALL or the full case list, like the factory-pipeline.py half.

Mode: implement. Model rule: Codex was unavailable (`agents --down codex`), so by the owner's instruction Claude
Sonnet 5.5 implemented, Claude Opus 5.5 led and reviewed (SAME_MODEL), and verify sessions ran QA.

## Sessions and verdicts

| Task | Verify | Candidate | QA run |
|---|---|---|---|
| guard-reach | review PASS, QA PASS | fa88d64 | `--affected --within tests/affected.test.sh,tests/parallel-policy.test.sh -j 1`: 418 passed, 0 failed |
| orca-lows | review PASS, QA FAIL (three test-side matches); review and QA PASS | 3805474 | `--affected --base 33c4bbe --within tests/pipeline.test.sh -j 1`: 407 passed, 0 failed |
| plan-lows | review PASS, QA PASS | fd11997 | `--affected --base 21ded14 --within tests/pipeline.test.sh,tests/parallel-policy.test.sh -j 1`: 426 passed, 0 failed |
| ci-fix | review PASS, QA PASS | 897d200 | `--affected --base 1573104 --within tests/delivery-generic.test.sh,tests/affected.test.sh,tests/parallel-policy.test.sh -j 1`: 421 passed, 0 failed |
| integration:plugin | QA by the run lead | a7565ad | first run: 7 passed, 1 failed (orca-commands: the new lesson cited a bare `orca orchestration`); run lead fix a7565ad cites `orca orchestration send`; rerun `--workspace-only --base origin/main`: 8 of 19 checks run, 8 passed, 0 failed (616 s); `--only-suites tests/parallel-policy.test.sh,tests/skills-lint.sh -j 1`: 399 passed, 0 failed; after ci-fix (8691187): 8 passed, 0 failed (391 s) |

## Merge of main (PR 154)

PR 154 (plan none-affected-notrun) merged into `main` first and conflicted in the integration QA row of `delivery.md`.
The run lead merged `main` (`295293a`), kept both sides and tightened two orca-wait sentences to stay under the
32768-byte cap (32765). Every verdict was re-recorded at `295293a` after `--affected --base 112d273 --within
tests/pipeline.test.sh,tests/affected.test.sh -j 1` (431 passed, 0 failed), delivery-generic, parallel-policy and
skills-lint (400 passed, 0 failed) and integration QA `--workspace-only --base faf2745` (8 passed, 0 failed).

## Limitations

- The run lead fixed one word in `parallel-work.md` after integration QA (commit a7565ad), outside a task session.

- Every review is SAME_MODEL (Claude implemented and reviewed).
- The `pipeline_route.py` narrowing is modest; the other pipeline libraries stay ALL by design.
- The validate stale-verdict case covers a paths change only, not an acceptance change (review nit).
- The first CI run of PR 153 failed two suites that task QA had left to CI (delivery-generic, affected).
- Cost: NOT_AVAILABLE.
