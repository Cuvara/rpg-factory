# Run report: qa-reach-followups

Tier M plan, four tasks in one wave, on branch `qa-reach-followups` (base `main` `6307b75`, plan commit `76eeb51`). It
covers qa-reach-followups, external-path-dollar and generic-explorer-name.

## Summary

- Task `pipeline`:
  - `factory-pipeline.py status --json` has a typed top-level `slots` array (in `docs/schemas/pipeline-status.schema.json`;
    `[]` for an invalid plan): the same entries as `cleanup --json`, with the progress or null. The text output and the
    stderr "Slots:" lines are unchanged.
  - `affected_selection` passes `--base` to `tests/affected.py cases`, so dispatch and QA case lists get the symbol reach.
  - The `tests/pipeline.test.sh` case map maps the assetgen import-closure files to the groups that use them: a
    one-function `scripts/assetgen/assetgen.py` change selected all 26 groups before and selects 4 after (dogfood,
    gate-merge, model-routing, recorded-implementer). `scripts/checks/domains/assetgen.py` is copied by
    `check-registry.sh` in two enum-copy cases; `scripts/factory-cmd.py` and the assetgen fixtures map to the only group
    whose text names them (conservative: it can only over-select).
  - Changelog fragment `changelog.d/qa-reach-followups-pipeline.md`; `docs/pipeline-cli.md` status bullet.
- Task `ci-base`:
  - `scripts/ci-plan.py` calls `affected.py cases --base BASE` when the base is valid; `--changed-file` without a base
    and every full fallback are unchanged.
  - The `hashes.py` stand-in in `tests/run-all-parallel.test.sh` skips leading options in any order before the file and
    suites. Changelog fragment `changelog.d/qa-reach-followups-ci.md`.
- Task `dollar`: the `$NAME` branch of `stylelock.EXTERNAL_URI_OR_ENV` matches only before a path separator, plus
  `${NAME}`; prose such as "priced in $USD" passes. Changelog fragment `changelog.d/external-path-dollar.md`.
- Task `explorer-name`: `skills/delivery/pipeline-defaults.json` names the built-in read-only `Explore` subagent type;
  `delivery.md` says the type comes from `pipeline.subagents.models.claude.agent` and names no plugin agent;
  `parallel-work.md` says the RPG registry names `rpg-factory:factory-explorer`. `scripts/lib/subagent_policy.py` was
  unchanged (it accepts any non-empty type). Changelog fragment `changelog.d/generic-explorer-name.md`.

Mode: implement. Model rule: Codex was unavailable (`agents --down codex`), so by the owner's instruction Claude
Sonnet 5.5 implemented, Claude Opus 5.5 led and reviewed (SAME_MODEL), and verify sessions ran QA.

## Sessions and verdicts

| Task | Verify | Candidate | QA run |
|---|---|---|---|
| pipeline | review PASS, QA PASS | 06bb267 | `--affected --within tests/pipeline.test.sh -j 1`: 415 passed, 0 failed |
| ci-base | review PASS, QA PASS | d95e856 | `--affected --base 76eeb51 --within tests/ci-plan.test.sh,tests/run-all-parallel.test.sh -j 1`: 412 passed, 0 failed |
| dollar | review PASS, QA PASS | 20e27bb | `--affected --within tests/assetgen.test.sh -j 1`: 440 passed, 0 failed |
| explorer-name | review PASS, QA PASS | d393c44 | `--affected --base 76eeb51 --within tests/delivery-generic.test.sh,tests/parallel-policy.test.sh -j 1`: 418 passed, 0 failed |
| integration:plugin | QA by the run lead | f89339f | `--workspace-only --base origin/main`: 8 of 19 checks run, 8 passed, 0 failed (652 s) |

## Limitations

- Every review is SAME_MODEL (Claude implemented and reviewed).
- A dollar word directly before a slash in prose (`$USD/month`) is still refused.
- The generic defaults still name the Codex plugin runner `codex:codex-rescue` (`pipeline.agents.codex.agent_runner`).
- `dispatch` prints a worker-start command without `--run`; a task lead with its own Run adds it by hand. The run
  lead's dispatch note named `--allow-same-model`, which is not a dispatch flag.
- Review nits not fixed: `tests/pipeline.test.sh` line 24 does not say why gate-merge owns the assetgen fixtures; one
  `ci-plan.py` docstring line may pass 120 characters.
- Cost: NOT_AVAILABLE.
