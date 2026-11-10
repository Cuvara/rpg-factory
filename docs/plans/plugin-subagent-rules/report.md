# Run report: plugin-subagent-rules

In-session subagent rules per role for Claude and Codex sessions, plus the follow-ups found while running the plan.
Plan: `docs/plans/plugin-subagent-rules.json`. Integration branch `plugin-subagent-rules`, integrated HEAD `d742bda`
(the QA candidate); main (PR #89, PR #90) merged in through task main-sync.

## Outcome

- Registry `pipeline.subagents` (per role: access, max parallel, when; models: Claude Sonnet 5.5 through
  `rpg-factory:factory-explorer`, Codex `gpt-6.1-terra`), `scripts/lib/subagent_policy.py`, scope check in
  `check-registry.sh`.
- One policy copy: `delivery.md` section 8 "In-session subagents" (marker `policy:subagents-read-only`):
  subagents are read-only scouts; parallel writes are subtasks dispatched with `--phase implement`.
- Every dispatch prompt carries its role's rule (planner, lead, implement, review, QA: none).
- Read-only plugin agent `agents/factory-explorer.md` with a lint.
- Doctor probe `codex-subagents` (WARN when the Codex subagent model is outside the scope or `multi_agent` is off;
  reads only the two model keys of the Codex config).
- Cleanup and Orca: leftover task directories, prunable records and stale Orca records are LEFTOVER; never kill a
  process the run did not start; the task worktree's Orca parent is the integration checkout.
- Gate: a review stays current when the owned content is unchanged since the reviewed commit, across a merge of
  the default branch (direct or inside a task branch) and a sync merge of the topic into a task branch; the plan
  file and this report are never stray.

## Sessions and verdicts

Codex was marked MODEL_UNAVAILABLE for the run (user report, 2026-11-09): every implementer, reviewer and QA
session ran on Claude, and every review is `SAME_MODEL (fallback: codex unavailable)`, recorded by dispatch.
Task leads: Claude Opus 5.5 medium. Implementers and QA: Claude Sonnet 5.5 high (heavy: Opus 5.5 high).
Reviews: Claude Opus 5.5.

| Task | Orca Run | Review | QA |
|---|---|---|---|
| registry | run_149c4936db8f | FAIL 6d0702a, PASS aca1edd | BLOCKED aca1edd (2 suites failing at base, fixed by policy and main-sync) |
| policy | run_7f95b6fc6db8 | PASS a1e5ca5 | FAIL 513cf1c (orca-commands at base), PASS a1e5ca5 |
| explorer-agent | run_d3d8b3ac7e34 | PASS 27f3938 | FAIL 692162a, PASS 27f3938 |
| prompts | run_826fe287963d | PASS 43d5669 | PASS 43d5669 |
| doctor-codex | run_7b1c8f8cd69d | FAIL 3ad784b, PASS e027c8a | PASS e027c8a |
| main-sync | run_6c67d97c294f | PASS f2ddb21 | not run (run lead: integration QA only) |
| orca-lineage | run_56bba00060b7 | FAIL 71d5d13, PASS b4fee84 | not run (run lead: integration QA only) |
| gate-nested | run_e5207aa7fa74 | PASS 8b7e9ce | not run (run lead: integration QA only) |
| integration:plugin | run_d6b996028350 | - | PASS d742bda |

## Checks (integrated HEAD d742bda)

- `tests/run-all.sh --workspace-only`: 24 checks, 23 passed, 0 failed, 1 skipped (pin-status: the client pin files
  have uncommitted user changes; committed HEAD OK).
- `build-registry.py --check` OK; `check-registry.sh` OK; `changelog.py check` 0 problems; `claude plugin validate` passed.
- Task suites at their candidates: pipeline.test.sh 816/816 (gate-nested), parallel-policy 125/125, orca-commands 10/10,
  affected.test.sh 97/97, devtools.test.sh 55/55, subagent-policy.test.py 93/93, skills-lint 674/674.
- `gate`: READY_FOR_PR at d742bda. The full suite is CI's gate on the PR.

## Limitations

- Every review is same-model (Codex down); no cross-model review happened in this run.
- Codex dispatches cannot set the subagent model (`orca worker-start` / `agent launch` take no Codex `-c`); doctor
  warns instead. Doctor reads only `CODEX_HOME/config.toml`, not a project config or an active profile.
- `pipeline-defaults.json` and `delivery.md` (generic) name `rpg-factory:factory-explorer`.
- A busy leftover directory's holder cannot be found read-only; cleanup reports it for the user.
- `tests/parallel-policy.test.sh` hit an intermittent Windows PermissionError in its temp copy in two QA runs.

## Cleanup

Task worktrees and branches of all 8 tasks removed after integration; every task lead's workers released. One
leftover: the empty directory of the registry task worktree is held by a process this run did not start (a Codex CLI
in a cmd window, PID 33296); it stays until the user frees it, then `orca worktree rm`.
