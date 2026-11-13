# Run report: ci-matrix

Tier M plan, six tasks, delivered on branch `ci-matrix` (base `main` `e0d67df`). The CI ran the whole
`tests/run-all.sh -j 4 --no-workspace --no-claude` on Linux and Windows for every pull request and push. It now runs one
matrix job per suite that the change affects, so a small change no longer waits for every suite.

## Summary

- `scripts/ci-plan.py` (new) plans the CI matrix. It lists the runnable suites with `tests/run-all.sh --list-suites`
  and selects them with one `tests/affected.py cases` call, so there is no second selection rule. The base is the PR
  base or the push `before`. Every suite runs when the base is missing or unusable, when `affected.py` fails, when a
  CI plumbing file changes (`.github/**`, `tests/run-all.sh`, `tests/affected.py`, `scripts/ci-plan.py`,
  `tests/ci-windows-suites.txt`), and on `workflow_dispatch full=true` or `schedule`.
- A suite runs on `ubuntu-24.04`, and also on `windows-2025` when `tests/ci-windows-suites.txt` names it.
- `tests/run-all.sh --inline-only` (new) runs only the inline checks, so a change that selects no suite still gets
  them.
- `.github/workflows/tests.yml` has four jobs: `plan`, `suite` (the matrix), `inline-checks` (both OSes) and `ci-ok`.
  `ci-ok` is the single required check: it fails when a needed job failed or was cancelled and passes when the
  matrix is skipped. The shared setup steps moved to `.github/actions/setup-ci`. Action pins are unchanged.
- Policy text: `.claude/CLAUDE.md`, `skills/delivery/references/delivery.md`, `tests/README.md`,
  `docs/architecture/overview.md`, `docs/releasing.md`, `scripts/factory-pipeline.py` (spec text),
  `skills/delivery/pipeline-defaults.json` and `registry/core.json` now say that CI runs the affected suites and
  `ci-ok` is the merge gate. A release runs every suite through `workflow_dispatch full=true` plus the local
  `--release` gate.
- `factory-pipeline.py dispatch --phase lead` now prints a hint when no checkout holds the plan `topic`, because the
  new task worktree's Orca parent then falls back to the main checkout (task `orca-parent-hint`; it happened in this
  run: the plan topic did not match the run lead's branch).

Mode: implement

## Scope

- Repo / branch: plugin (this checkout) on `ci-matrix` (renamed from `CuongND-sparkon/ci-test-matrix-refactor` at the
  maintainer's choice so the topic matched the run lead's checkout).
- Fragments: `changelog.d/ci-matrix.md` (Added, Changed), `changelog.d/orca-parent-hint.md` (Fixed).
  `CHANGELOG.md` `[Unreleased]` untouched.
- Baseline preserved: yes.

## Sessions and verdicts

| Task | Implementer | Verify (review + QA) | Candidate | Tier run |
|---|---|---|---|---|
| ci-plan | claude-sonnet-5-5 high | claude-opus-5-5 medium: FAIL (UTF-8 stdio), FAIL (CRLF in a test helper), PASS | 843b6b5 | 528 checks: 297 passed, 0 failed, 231 skipped; ci-plan.test.sh 41/0 |
| orca-parent-hint | claude-sonnet-5-5 high | claude-opus-5-5 medium: FAIL (quote in the hint broke a test helper), PASS | 04eab80 | 306 passed, 0 failed, 218 skipped; parallel-policy 293/0 |
| ci-workflow | claude-sonnet-5-5 high | claude-opus-5-5 medium: PASS | 3aa2f0d | 294 passed, 0 failed, 234 skipped |
| ci-docs | claude-sonnet-5-5 high | claude-opus-5-5: FAIL (delivery.md over its size cap); claude-fable-5-2 high: PASS | 9a466d8 | 318 passed, 1 failed (workspace variable unset); rerun 294/0 |
| ci-wording | claude-opus-5-5 medium | claude-fable-5-2 high: PASS | 5a759d2 | 514 of 531 (16 live checks, workspace variable unset); rerun 320/0 |
| ci-gate-pin | claude-opus-5-5 medium | claude-fable-5-2 high: PASS | c78dabf | 323 passed, 0 failed, 205 skipped |
| integration | - | QA claude-opus-5-5 medium: PASS | 40fa39b | `run-all --workspace-only` 24/24; five named suites 303 passed, 0 failed |

Every review is SAME_MODEL: Codex was not available on this machine, so Claude sessions reviewed Claude work. From
`ci-docs` on, a maintainer model trial ran task leads and verify sessions on Fable 5.2 and the rest on Opus 5.5
(a personal override, not saved in the plugin). `gate`: READY_FOR_PR, notes only (SAME_MODEL).

## Not verified here

- No GitHub Actions run yet: the first real run of the new workflow is the PR's. `ci-ok` was checked locally with
  synthetic job results.
- Branch protection still requires the old `run-all (no workspace, <os>)` checks until the maintainer switches it to
  `ci-ok`; those checks no longer run.

## Limitations

- Cost: NOT_AVAILABLE (no usage reported through Orca).

## Follow-ups (backlog topic `ci-matrix-followups`)

Plan ci-followups covered most of these items; what stays open is in `docs/plans/backlog.md` topic
`ci-matrix-followups`.

- Covered by plan ci-followups (task ci-cases, `changelog.d/ci-cases.md`): the CI suite job ran every case of a
  selected suite (`tests/run-all.sh --only-suites` had no case subset, so the cases `scripts/ci-plan.py` planned were
  only shown). A suite job now passes the planned cases to `tests/run-all.sh --only-cases`.
- Covered by plan ci-followups (task ci-cases, `changelog.d/ci-cases.md`): `workflow_dispatch` with `full=false` had
  no base, so it planned every suite like `full=true`. It now takes a `base` input.
- Covered by plan ci-followups (task pipeline-followups, `changelog.d/pipeline-followups.md`): `tests/pipeline.test.sh`
  asserted only the integration QA clause of the new CI wording, not the task QA clause.
- Open: `skills/delivery/references/delivery.md` has about 200 bytes left under its 32 KiB cap; the next policy
  addition needs a split or a trim.
- Worker sessions on Windows need `RPG_FACTORY_WORKSPACE` set and a real `python3` (the Store alias fails): two tier
  runs of this plan failed on that alone. Covered by plan ci-followups (task pipeline-followups,
  `changelog.d/pipeline-followups.md`) for the workspace: the dispatch specs carry `RPG_FACTORY_WORKSPACE` from the
  run lead's environment. Open: the `python3` shim is still added to each worker prompt by hand.
- Covered by plan ci-followups (task pipeline-followups, `changelog.d/pipeline-followups.md`): a stderr line of
  `dispatch` could not contain quote characters while the `pp_spec` test helper shlex-split the combined output; the
  helper now reads the prompt line only.
- Covered by plan ci-followups (task orca-wait-stall, `changelog.d/orca-wait-stall.md`):
  `scripts/orca-wait.sh --stall-ms 0` reported an immediate stall instead of disabling the check.
- Covered by plan ci-followups (task pipeline-followups, `changelog.d/pipeline-followups.md`): delivery policy says
  follow-ups go to the backlog in the integration commit, but the gate treated a run lead's `docs/plans/backlog.md`
  edit as stray; the gate now allows it like the plan's `report.md`.
