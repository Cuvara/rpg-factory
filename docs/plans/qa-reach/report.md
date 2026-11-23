# Run report: qa-reach

Tier M plan, three tasks in two waves, on branch `qa-reach` (base `main` `c0f9586`). It covers pipeline-speed-followups
and the case reach item of test-speed-followups. Wave 2 (case-reach) waited for wave 1 because it shares
`tests/pipeline.test.sh` and `tests/assetgen.test.sh` with it, and the machine was short on memory.

## Summary

- Task `slot-progress`:
  - `tests/run-all.sh` keeps a `progress` file in the held test slot (check, result, passed, failed, updated; written
    with a temp file and `mv`, removed with the slot and on a stale takeover).
  - `factory-pipeline.py status` prints each slot holder's last check, counts and the age of the last update (or "no
    progress yet"), so a live run is not mistaken for an orphan. The `_GIT_MEMO_ON` branch reads plainly.
  - The slot paragraph of `parallel-work.md` says what status prints. Changelog fragment
    `changelog.d/qa-reach-slot-progress.md`.
- Task `lows`:
  - `assetgen.py model-hashes` reads the root `extra_model_paths.yaml`, then the Comfy Desktop instance file, then
    explicit `--extra-model-paths` files (ComfyUI's root-first order); `is_default` is the Python truthiness of the
    YAML 1.1 value (a quoted 'false' is truthy, as in ComfyUI).
  - The `git_dir_in_scope` and `literal_cd_target` docstrings describe the code. Changelog fragment
    `changelog.d/qa-reach-lows.md`.
- Task `case-reach`:
  - Case-map patterns may name symbols (`PATH::NAME`, `PATH::*`). `affected.py cases [--base REF]` maps the changed
    line ranges of a Python file (`git diff -U0`, ast on both sides) to top-level defs and classes, and selects only
    the case groups whose named symbols reach a changed one through the in-module reference closure. Any change
    outside one def, an added, deleted or renamed def, a parse failure, or a new or deleted file keeps the file-level
    reach; an unmapped caller gives ALL. `tests/run-all.sh` passes the base to `cases`.
  - `tests/pipeline.test.sh` groups map to the `factory-pipeline.py` verbs they run; `tests/assetgen.test.sh` groups
    map to `assetgen.py` entries (module-level reach cannot narrow: `assetgen.py` imports every module at the top).
  - One-function change, groups selected before and after: `scripts/factory-pipeline.py` 26/26 before, median 19/26
    after (202 of 208 defs narrow; `cmd_cleanup` 7, `cmd_gate` 10, `cmd_status` 17); `scripts/assetgen/assetgen.py`
    41/41 before, median 21/41 after (79 of 84 defs narrow; `publish` 8, `render` 34).
  - The flaky assetgen "CLI help" case and three similar `AG ... | grep -q` pipes capture the text before matching.
  - Changelog fragment `changelog.d/qa-reach-cases.md`; `tests/README.md` and the `tests/affected.py` docstring
    describe the rules.

Mode: implement. Model rule: Codex was unavailable (`agents --down codex`), so by the owner's instruction Claude
Sonnet 5.5 implemented (Opus 5.5 for two engine subtasks), Claude Opus 5.5 led and reviewed (SAME_MODEL), and verify
sessions or the run lead ran QA.

## Sessions and verdicts

| Task | Verify | Candidate | QA run |
|---|---|---|---|
| lows | review PASS, QA PASS | e9685c6 | `--within tests/assetgen.test.sh,tests/git-guard.test.sh -j 1`: 461 passed, 1 failed (the flaky "CLI help" case, untouched, PASS/FAIL/PASS at base; fixed in case-reach) |
| slot-progress | review PASS, QA FAIL (stale `--list-suites` expectations); review and QA PASS | 7eb2fc8 | `--affected --base 6d442f4 --within tests/pipeline.test.sh,tests/run-all-parallel.test.sh -j 1`: 402 passed, 0 failed |
| case-reach | review PASS, QA FAIL (a stale ALL assertion); review and QA PASS | 4a9a4d3 | `--affected --base 8fdd8d3 --within tests/affected.test.sh -j 1`: 397 passed, 0 failed |
| integration:plugin | QA by the run lead | 0f1b6bc | `--workspace-only --base origin/main`: 19 checks, 9 passed, 0 failed, 10 not affected, 586 s |

Scope changes by plan-edit (reasons recorded in the plan): case-reach also fixes the flaky assetgen "CLI help" case,
and owns `tests/run-all.sh` to pass the diff base to `affected.py cases`.

## Limitations

- `status --json` carries the slot progress only in the stderr "Slots:" text line (the status schema has no slots
  field); `cleanup --json` carries it structured.
- `scripts/ci-plan.py` and `factory-pipeline.py` `affected_selection` call `cases` without `--base`: they get symbol
  reach only when their file list equals the default-base changed set, else file-level.
- Six assetgen groups keep the plain glob for `assetgen.py`; other assetgen modules stay file-level. A new verb or
  helper that a group reaches through a caller must be named in the map.
- Any `scripts/assetgen/assetgen.py` change still selects every group of `tests/pipeline.test.sh` (its import closure
  reaches files no pipeline group maps).
- `tests/pipeline.test.sh` and `tests/assetgen.test.sh` ran only in part locally; CI runs them on the PR.
- Cost: NOT_AVAILABLE.
