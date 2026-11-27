# Run report: session-lows

Tier M plan, four tasks in two waves, on branch `session-lows` (base `main` `7a98590`, plan commit `622c6b2`). It
covers the dispatch-health lows of policy-followups-leftovers, plan-edit-followups and path-audit-followups, two
workflow-slim-followups lows and qa-reach-followups-2. Wave 2: tier-lows waited for dispatch-health (both own
`scripts/factory-pipeline.py` and `tests/pipeline.test.sh`); workflow-suite waited for defaults-lows.

## Summary

- Task `dispatch-health` (nothing covered the slot or stalled workers before; `nudge` already found unsubmitted
  start prompts):
  - The verify spec ends with a run-stop rule: stop your own `tests/run-all.sh` by PID (never by pattern) and confirm
    the slot is free before the verdict, else NOT_RUN or BLOCKED.
  - `status` prints `Slots: LEFT BY VERIFY ...` for a live slot held in a plan task worktree whose verify dispatch has
    reported or been released, with the stop command for that PID only (read-only, never kills).
  - `nudge --stall SECONDS` (default 900) and `--orca-run` list a running worker idle that long as STALLED (no turn
    start, or a turn ended without `worker_done`) with re-dispatch advice; `--send` still applies only to STUCK.
  - Changelog fragment `changelog.d/session-lows-dispatch.md`.
- Task `tier-lows` (all four items were open):
  - Plain `tier -- <factory-context.sh args>` and `--context-json` count changed lines (git diff --numstat against the
    merge-base, plus untracked files) with the same XS threshold, and print the basis.
  - The lead spec carries a `Base health:` line (the stderr hint is unchanged).
  - `changelog.d/base-health.md` was released in 1.8.0, so the known_failing-in-verify-spec correction is in
    `changelog.d/session-lows-tier.md`.
  - `docs/pipeline-cli.md` documents the tier line basis, `nudge --stall`/`--orca-run` and the LEFT BY VERIFY line.
  - The tier XS one-task rule is unchanged (left in the backlog: `delivery.md` is at its size cap).
- Task `defaults-lows`:
  - The Codex runner `codex:codex-rescue` is right (upstream openai/codex-plugin-cc agent `codex-rescue` in plugin
    `codex`); unchanged, pinned by a `tests/workflow.test.sh` case.
  - The asset-gen style lock accepts a dollar word before a slash in prose (`$USD/month`) and still refuses a path
    variable (`$HOME/a.png`, `${NAME}/`, `$NAME\`). Accepted limitation: `$HOME/art` (one segment, no extension)
    reads as prose.
  - Changelog fragment `changelog.d/session-lows-defaults.md`.
- Task `workflow-suite` (added by plan-edit: defaults-lows found `tests/workflow.test.sh` was never run):
  - Registered five suites that `tests/run-all.sh` never ran: workflow, handoff-e2e, artifact-quality, asset-manifest
    and domains-foundation (each passed standalone on Windows before registration).
  - A new inline check fails a `tests/*.test.sh` with no run line and no `SUITE_EXEMPT` entry (exempt:
    `tests/orca-wait.test.sh`, run nested by `tests/parallel-policy.test.sh`).
  - Changelog fragment `changelog.d/session-lows-suites.md`.

Mode: implement. Model rule: Codex was unavailable (`agents --down codex`, not logged in), so by the owner's
instruction Claude Sonnet 5.5 implemented, Claude Opus 5.5 led and reviewed (SAME_MODEL), and verify sessions ran QA.

## Sessions and verdicts

| Task | Verify | Candidate | QA run |
|---|---|---|---|
| defaults-lows | review PASS, QA PASS | 36ee0c8 | `--affected --within tests/assetgen.test.sh -j 1`: 484 passed, 0 failed; `tests/workflow.test.sh` standalone 18/18 |
| dispatch-health | review PASS, QA PASS | 11a7b6e | `--affected --base 622c6b2 --within tests/pipeline.test.sh -j 1`: 418 passed, 0 failed |
| tier-lows | review FAIL (`tier --paths` ignored `--base`); review PASS, QA PASS | 9a64948 | `--affected --within tests/pipeline.test.sh -j 1`: 420 passed, 0 failed |
| workflow-suite | review PASS, QA FAIL (affected.test.sh 214/215); review PASS, QA PASS | 830b4b9 | `--affected --base 34128f8 --within tests/affected.test.sh,tests/run-all-parallel.test.sh -j 1`: 414 passed, 0 failed; workflow 18/18 standalone |
| integration:plugin | QA by the run lead | final | `--workspace-only --base 622c6b2`: 1 passed, 1 failed (FAIL_AT_BASE: registry paths exist in workspace, plan known_failing), 17 not affected |

## Limitations

- Integration QA: `registry paths exist in workspace` fails on `main` `7a98590` the same way (the `game-authoring`
  checkout is on `feat/design/economy`, without `assetgen/runs/` and `ui/requirements/`); recorded as plan
  `known_failing`, FAIL_AT_BASE.

- Every review is SAME_MODEL (Claude implemented and reviewed).
- The four newly registered suites besides workflow ran only standalone on Windows before this PR; CI is their first
  Linux run.
- Review nits left: the nudge usage overstates when `lastError` counts as no turn start; the released-worker leg of
  the slot check could flag a non-verify worker released in the same checkout; the `tier_of` docstring still says
  lines are known only for `tier --plan`; a `--base` whose merge-base fails falls back silently.
- Cost: NOT_AVAILABLE.
