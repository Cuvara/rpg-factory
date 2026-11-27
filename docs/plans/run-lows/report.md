# Run report: run-lows

Tier M plan, three tasks in one wave, on branch `run-lows` (base `main` `bbb1f9e`). It closes lows of backlog topics
flow-lows-followups, plugin-flow-5-followups, path-audit-followups, workflow-slim-followups and
policy-followups-leftovers.

## Summary

- Task `workspace-paths`:
  - `scripts/lib/workspace.py` `native_abs` rewrites a missing drive path with a `/mnt/<letter>/` segment only when
    the prefix holds `usr/bin/bash.exe` or `git-bash.exe` (a directory merely named `Git` no longer counts), for
    every caller. `plan_paths.py` uses it instead of its own copy.
  - New `git_result` tells a git timeout from a failure; the snapshot (`scripts/lib/context.py`) reports
    "git timed out after N s" instead of "not a git work tree".
  - The registry `root_default` conversion was already fixed on main (`6b3490d`); existing cases confirm it.
  - Changelog fragment `changelog.d/run-lows-paths.md`.
- Task `run-evidence`:
  - `tests/run-all.sh` names its result record in its last output line (also after TERM). The record itself, the
    newest-20 pruning and `--last-result` were already on main.
  - Dead test slot release was already on main (cases for dead and live holders); no change.
  - `tests/parallel-policy.test.sh` names the failing cases of a nested `orca-wait` run.
  - `scripts/checks/netcode-headless.sh` keeps the newest 10 evidence directories
    (`RPG_FACTORY_NETCODE_EVIDENCE_KEEP`).
  - Changelog fragment `changelog.d/run-lows-evidence.md`.
- Task `pipeline-lows` (`scripts/factory-pipeline.py`):
  - `cleanup` lists each leftover directory once.
  - `status` counts lineage children only on the plan's own branches.
  - `status` proposes no merge while the candidate's task QA is FAIL.
  - The `slot_holders` docstring names `winpid`.
  - `"model_scope_widen": null` fails `validate`, a malformed entry is reported once, and `lead_prompt` loads the
    policy once.
  - The plugin frontmatter item was already fixed on main (`fa1e41b`); `claude plugin validate --strict` passes.
  - Changelog fragment `changelog.d/run-lows-pipeline.md`.

Mode: implement. Model rule: Codex was unavailable (not logged in; `agents --down codex`), so by the owner's
instruction Claude Sonnet 5.5 implemented, Claude Opus 5.5 led and reviewed, and the task lead or the run lead ran QA.
Every review is SAME_MODEL, noted by the gate.

## Sessions and verdicts

| Task | Implementer | Verify (review + QA) | Candidate | Tier run |
|---|---|---|---|---|
| workspace-paths | claude-sonnet-5-5 (three subtasks) | review FAIL at a2012d3 (test helper inherited an outer patch, fixed); review PASS and QA PASS at ac57e13 | ac57e13 | stopped for low memory; checks run directly: plan-paths 70/70, workspace-default 91/91, compat 50/50 |
| run-evidence | claude-sonnet-5-5 (three subtasks) | review PASS at 15ddbb8; QA PASS by the run lead | 15ddbb8 | stopped for low memory; run-all-parallel 176/176 (run lead), parallel-policy `--case portable-plans,orca-wait` 15/15, netcode-headless 54/54 with `NETCODE_HEADLESS_TIMEOUT=8` |
| pipeline-lows | claude-sonnet-5-5 (two subtasks) | QA FAIL at 972caf0 (new case too strict, fixed); review PASS and QA PASS at f9a72f6 | f9a72f6 | `--only-suites tests/pipeline.test.sh,tests/skills-lint.sh -j 1`: 385 passed, 0 failed, 246 skipped |
| integration:plugin | - | QA by the run lead (claude-opus-5-5) | b05a18d | `tests/run-all.sh --workspace-only`: 24 checks, 24 passed, 0 failed, 0 skipped |

## Limitations

- No task's full tier command completed: Claude Code stopped them for low memory; the named checks ran directly.
- `tests/netcode-headless.test.sh` uses a 2 s fake-dotnet timeout that fails at random on a loaded Windows host.
- The routing scenario "Redis servers:id -> wire-contract leads" does not retry once on a git timeout (not owned).
- The slot takeover message goes to stdout, not stderr; the prune order breaks pid ties lexicographically.
- `Lineage.owns`: a helper worktree named only `<topic>-x` is no longer listed as a leftover child; `cleanup` still
  treats `<topic>-*` branches as the plan's own.
- Cost: NOT_AVAILABLE.
