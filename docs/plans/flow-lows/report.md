# Run report: flow-lows

Tier M plan, two tasks in one wave, on branch `flow-lows` (base `main` `58612bd`). It closes the delivery.md headroom
items of backlog topics `plan-edit-followups` and `workflow-slim-followups` and four lows of `plugin-flow-5-followups`.

## Summary

- `skills/delivery/references/delivery.md` trimmed from 32767 to 31497 bytes (LF; cap 32768 unchanged) by wording
  only (task `delivery-headroom`): restatements of what another section of the same file says were dropped, duplicate
  sentences merged, three unused bold labels removed. No heading, policy marker, number, command form or rule was
  removed; the verify review caught two weakened rules (no worktree or branch during a full run; a subagent records no
  verdict), restored in `cb71ea6`. `tests/README.md` now points to delivery.md section 10 "QA tiers" instead of
  restating the tiers.
- Four test and path lows fixed (task `test-lows`), each with a case; main had fixed none of them:
  - `tests/hook-perf.test.sh` writes no `.new` into the cwd when the cache file is missing.
  - `gitcfg_snapshot` (`scripts/lib/gitcfg-guard.sh`) replaces an earlier snapshot copy instead of leaking it.
  - `scripts/checks/netcode-headless.sh` keeps the `.trx` files and the run log of a failed run under the Factory state
    dir (`scripts/lib/fstate.py`) and prints the path (Windows form on Git Bash); a pass cleans up as before.
  - `scripts/lib/plan_paths.py` reads only a leading `/mnt/<letter>/` as a WSL mount.
  - Changelog fragment `changelog.d/flow-lows.md` (### Fixed).

Mode: implement. Model rule: Codex was unavailable (not logged in; recorded with `agents --down codex`), so by the
owner's instruction Claude Sonnet 5.5 implemented, Claude Opus 5.5 led and reviewed, and Claude Sonnet 5.5 or the task
lead ran QA. Every review is SAME_MODEL (same vendor), noted by the gate.

## Sessions and verdicts

| Task | Implementer | Verify (review + QA) | Candidate | Tier run |
|---|---|---|---|---|
| delivery-headroom | claude-sonnet-5-5 high (three subtasks) | review FAIL at f4de496 (two blocking, fixed); review PASS at cb71ea6 (claude-opus-5-5 medium); QA PASS by the task lead | cb71ea6 | stopped for low memory; the lead ran the task's checks directly (below) |
| test-lows | claude-sonnet-5-5 high (five subtasks) | review FAIL at 06609b7 (suite wrote evidence into the real state dir, fixed); lead QA FAIL at ea71040 (POSIX evidence path on Git Bash, fixed); review PASS at a02ef0d (claude-opus-5-5 medium); QA PASS by the task lead | a02ef0d | stopped twice for low memory; the lead ran the task's checks directly (below) |
| integration:plugin | - | QA by the run lead (claude-opus-5-5) | d861414 | `tests/run-all.sh --workspace-only`: 24 checks, 24 passed, 0 failed, 0 skipped |

Checks run directly, one at a time:

- delivery-headroom at cb71ea6: `tests/skills-lint.sh` PASS, `tests/line-budget.test.sh` PASS (reused record),
  `tests/delivery-generic.test.sh` PASS, `tests/parallel-policy.test.sh` 625 checks, 377 passed, 0 failed (after one
  run with a single `orca-wait` failure; standalone `tests/orca-wait.test.sh` 53/53).
- test-lows at a02ef0d: `tests/netcode-headless.test.sh` 42/42, `tests/plan-paths.test.sh` 56/56,
  `tests/git-env-isolation.test.sh` 9/9, `tests/hook-perf.test.sh` 27/27, `tests/parallel-policy.test.sh --case
  portable-plans` 12/12, `scripts/changelog.py check` 0 problems.

## Limitations

- No task's tier command completed: Claude Code stopped them for low memory; every named check ran directly instead.
- `tests/orca-wait.test.sh` failed one case once inside parallel-policy under memory pressure and passed two reruns;
  the case name was not captured (backlog flow-lows-followups).
- `scripts/lib/workspace.py` `native_abs` keeps the broad `/mnt/<letter>/` rewrite for its other callers; the Git root
  check in `plan_paths.py` is a heuristic; netcode evidence dirs are never pruned (all in flow-lows-followups).
- delivery.md headroom is 1271 bytes under the cap.
- Cost: NOT_AVAILABLE.
