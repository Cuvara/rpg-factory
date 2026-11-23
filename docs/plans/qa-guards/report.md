# Run report: qa-guards

Tier M plan, three tasks in one wave, on branch `qa-guards` (base `main` `14f9d4d`). It closes the scoped-QA guard
gap of test-flakes-followups, the model-hash cache item of assetgen-run-followups and the doctor near-duplicate. It
avoids the paths of the parallel plan runtime-quirks.

## Summary

- Task `within-enforce`:
  - A `--within` task QA run also runs the `English-only enforcement` and `Portable-paths enforcement` lines when
    the change reaches them (`WITHIN_GUARDS` in `tests/run-all.sh`).
  - `--list-suites` lists both.
  - `tests/affected.py` maps the netcode prune case of `tests/run-all-parallel.test.sh` to
    `scripts/checks/netcode-headless.sh`.
  - Changelog fragment `changelog.d/qa-guards-within.md`.
- Task `model-hash-writer`:
  - New command `assetgen.py model-hashes` (`scripts/assetgen/modelhash.py`). It finds the models directory from
    `--models-dir`, `--comfy-dir` or the Comfy Desktop instance, and hashes the model kinds asset-gen loads plus the
    controlnet_aux annotators.
  - It hashes in 1 MiB chunks, reuses a row while size and `mtime_ns` are unchanged, and writes
    `<state>/comfy/model-hashes.json` through `fstate`. The schema stays `/1`; the new fields are additive.
  - The comfy-desktop-setup skill has a new step 7, "Save the model hashes".
  - Changelog fragment `changelog.d/qa-guards-model-hashes.md`.
- Task `doctor-dedupe`:
  - `doctor` prints the Git Bash python3 Store stub fault and its fix once; `--json` is unchanged.
  - Changelog fragment `changelog.d/qa-guards-doctor.md`.

Mode: implement. Model rule: Codex was unavailable (`agents --down codex`), so by the owner's instruction Claude
Sonnet 5.5 implemented, Claude Opus 5.5 led and reviewed (SAME_MODEL), and verify sessions or the run lead ran QA.

## Sessions and verdicts

| Task | Verify | Candidate | QA run |
|---|---|---|---|
| doctor-dedupe | review PASS, QA PASS | 488c1b5 | `--within tests/commands.test.sh -j 1`: 414 passed, 0 failed; both enforce lines 0 findings |
| within-enforce | review PASS at f1c0139. QA NOT_RUN in the task (low memory). Run lead QA FAIL: two `--list-suites` stand-in expectations lacked the guard scripts, fixed in 4b0d59b. Delta review and QA PASS | 4b0d59b | affected 171+ PASS and both enforcement lines PASS in the task tier run; run-all-parallel 199 PASS before the FAIL stop (run lead); delta: lines 1-369 47/47 and every `--within` case 18/18 |
| model-hash-writer | FAIL at review (test expectation); then QA FAIL (reader case); then review and QA PASS | bb376e3 | `--within tests/assetgen.test.sh -j 1`: 428 passed, 0 failed; comfy-desktop-setup and skills-lint PASS |
| integration:plugin | QA by the run lead | 1d51a3d | `--workspace-only --base origin/main`: 19 checks, 7 passed, 0 failed, 12 not affected, 936 s |

## Limitations

- Most of `tests/run-all-parallel.test.sh` past line 369 ran locally only at f1c0139 (199 PASS); CI runs the full
  suite on the PR.
- The workspace reader guard of `tests/workspace-default.test.sh` is inline and cannot run alone, so `--within` does
  not include it.
- The `factory-pipeline.py` dispatch spec still lists the two enforcement scripts as left to CI; the parallel plan
  runtime-quirks owns that file.
- `model-hashes` was tested with fake model files only, and it does not read `extra_model_paths.yaml`.
- Cost: NOT_AVAILABLE.
