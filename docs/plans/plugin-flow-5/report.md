# Run report: plugin-flow-5

Plugin batch 5, after the 1.8.0 release: CI coverage, run-lead visibility of task leads and workers, and a set of
lows from earlier plans. Plan: `docs/plans/plugin-flow-5.json`. Integration branch `plugin-flow-5`, integrated HEAD
`63a44f0` (base main `8d64341`, v1.8.0 plus the plan PR). Run on a second machine; the first-machine state of the
earlier plan workflow-slim was rebuilt retrospectively and is not part of this run.

## Outcome

- **ci-coverage:** `delivery-generic.test.sh` wired into `tests/run-all.sh` and `tests/affected.py`; no bare `bash`
  probe in `affected.py`; `routing-golden --update` keeps the WSL scenarios on Windows; a config WARN is counted and
  its `GITCFG_COPY` removed (also on a failed `cp`); the git-guard RETRY line records rc, elapsed and stderr;
  `factory-pipeline.py` changes select 6 suites (was 21). Carried the three one-line edits `checks-lows` needed
  (`run-all.sh` globs for `rpgf_guard`, plan-paths wiring, the `git-guard.test.sh` comment).
- **lead-report:** root cause of the lost plugin-flow-4 reports: task leads send `--type status`, while
  `scripts/orca-wait.sh` waited only for `worker_done,escalation,question`. Fixed; `status` shows the last lead
  report and READY_FOR_PR per task (new `report` verb). Also: UNRELEASED false positive (a settled dispatch with no
  terminal), test-slot holders and orphaned processes named by `status` and `cleanup`, `tier <plan>`,
  implementer-refusal scope, `pipeline.test.sh --help`, orca-wait lows and the orphaned waiter lock, Orca
  `externalWorktreeVisibility` (dispatch prints `orca repo set ... show`), `verdict --fallback` text,
  model-unavailable detection.
- **checks-lows:** checks-hygiene lows, native plan paths (also a WSL root rewritten by Git Bash), the guard package
  renamed to `scripts/lib/rpgf_guard/`; `git archive` submodules and LFS are reported, not handled.

## Sessions and verdicts

Codex was unavailable for the run (`agents --down codex`): every review is `SAME_MODEL (fallback: codex
unavailable)`, so `gate --allow-same-model` was needed. Task leads: Claude Opus 5.5 medium.

| Task | Orca Run | Review | QA |
|---|---|---|---|
| ci-coverage | run_386f601a03c7 | FAIL 39d8fb8, PASS 6f23784, PASS 38f535e, PASS d1e8660 | FAIL 6f23784, FAIL 38f535e, PASS d1e8660 |
| lead-report | run_94bb70428dc1 | FAIL 3829178, FAIL 6096585, FAIL db23862, PASS fad325d, FAIL 0ca4187, PASS 3a0d49d | FAIL fad325d, PASS 3a0d49d |
| checks-lows | run_3fae8fc0082c | FAIL e8ecd46, FAIL 62da9a3, PASS 71dd3c5 | PASS 71dd3c5 |
| integration:plugin | run_d27e7341bae5 | n/a | PASS 63a44f0 |

## Checks (integrated HEAD 63a44f0)

Integration QA (`tests/run-all.sh --workspace-only`, `RPG_FACTORY_WORKSPACE` set, `jq` and a real `python3` on PATH):
21 passed, 3 failed, none from this plan: two `claude plugin validate --strict` (frontmatter of `skills/pin-bump`,
`skills/unity-client-tech`, `commands/assetgen.md`, failing at main too) and `wire-parity` (sibling repo drift: Netcode
`406a1b6` against server `633a792`). All 10 acceptance criteria and ten extra suites pass with 0 failed: affected 62,
run-all-parallel 130, routing-golden 12, git-guard 598, orca-wait 51, pipeline 965, parallel-policy 135, skills-lint
674, facts 37, ui-catalog 72. Run lead: plan `validate` OK, `changelog.py check` 3 fragments, `build-registry.py
--check` OK. CI on the PR is the full gate.

## Limitations

- No cross-model review (Codex down); the integration QA failures above are host or sibling-repo conditions.
- Option A for `checks-lows` (own the three `ci-coverage` files) was rejected by `validate` (overlapping paths);
  the dependency ran through `ci-coverage` instead, so `checks-lows` waited for its integration before its verify.
- Task QA reported NOT_RUN or `jq: command not found` failures until a PATH shim (`jq` 1.7.1, a `python3` wrapper)
  was used; `jq` 1.8.2 was then installed with winget on this machine.
- Stray Orca follow-up workers appeared after a `status` message to a finished dispatch (two stopped).
- `orca worktree set` right after `git worktree add` ran before Orca knew the worktree, so the three task worktrees
  landed in "Hidden worktrees"; fixed by hand (`orca repo set ... show`, then `worktree set`). The plugin fix is item
  9 of `lead-report`.

### Cost

| Task | Session role | Model | Effort | Tokens / cost | Source |
|---|---|---|---|---|---|
| all tasks | task lead, implementer, reviewer, QA | see Sessions | see Sessions | NOT_AVAILABLE | no usage reported through Orca |
| run lead (total) | run lead | claude-sonnet-5-5 | - | NOT_AVAILABLE | n/a |

## Cleanup

Task worktrees and branches `plugin-flow-5-ci-coverage`, `-lead-report` and `-checks-lows` are removed after the PR
is merged (`cleanup --after-merge`). Follow-ups: `docs/plans/backlog.md` topic plugin-flow-5-followups.

## Gate

`factory-pipeline.py gate --allow-same-model` at 63a44f0: READY_FOR_PR (SAME_MODEL notes only).
