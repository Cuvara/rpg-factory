# QA report - <plan id> / <repo> (<integration | task id>)

Candidate SHA: <sha>   (`git rev-parse HEAD` in the QA tree: <sha> - equal | NOT_INDEPENDENT)
QA agent: <claude | codex>   Implementers: <task: agent, ...>
Tree: <worktree path | main checkout (no-worktree repo)>

## Acceptance criteria
| Task | Criterion | State | Evidence |
|---|---|---|---|
| <id> | <criterion from the plan> | PASS / FAIL / NOT_RUN | <test name, command output line, file:line> |

## Checks
Copy the `run-checks.py --repo <key> --paths ...` table (fast tier, plus extended or external when the plan names
them). Counts, never "tests pass". A Unity test run states when it held the `unity-test` resource.
| Tier | Check | State | Evidence |
|---|---|---|---|

## Regressions
- Suites outside the owned paths that ran, with counts: <...> | none run - <reason>

## Edge and failure cases
- <case> - <how it was exercised> - <result>

## NOT_RUN
- <check> - `<exact command>` - <reason (tool missing, resource held, external)>

## Findings
- <path:line> <severity> <problem> <expected fix> | none

VERDICT: <PASS | FAIL | NOT_RUN | BLOCKED>
