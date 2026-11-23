# Run report: pipeline-speed

Tier M plan, four tasks in one wave, on branch `pipeline-speed` (base `main` `8a2843e`). It covers the pipeline start
cost of test-speed-followups, run-lows-followups and test-flakes-followups.

## Summary

- Task `verb-speed`:
  - `factory-pipeline.py` memoizes `git rev-parse` and `git worktree list` for the length of one CLI verb run (off on
    module import, so in-process callers never see a stale answer).
  - `status docs/plans/qa-guards.json` on Windows: 13 subprocesses before (5 `git worktree list`, 7 `git rev-parse`,
    1 `orca account list`), 6 after; wall 2.6-4.1 s before, 1.5-2.6 s after on a loaded machine. Output is
    byte-identical. Agent availability was already memoized per process, so `pipeline_route.py` is unchanged.
  - The dispatch spec no longer lists the repo-wide guard scripts as left to CI.
  - A re-QA after a QA FAIL with `--failed-suites` runs `--within` the failed suites plus the task suites the fix
    delta reaches; when the affected selection is not computed it keeps all task suites.
  - `cleanup` uses the same branch ownership as `status` (`Lineage.owns`), including the topic's Orca QA children.
  - The `model_scope_widen` case counts the problem text.
  - Changelog fragment `changelog.d/pipeline-speed.md`.
- Task `reader-guard`:
  - The workspace reader guard moved from `tests/workspace-default.test.sh` into `scripts/checks/workspace-readers.sh`
    (same rules, exit 0/1/2); the suite's self-test calls it.
  - It is a run line of `tests/run-all.sh` and the third entry of `WITHIN_GUARDS`; `tests/affected.py` selects it for
    changes under `scripts/` and `tests/`.
  - Changelog fragment `changelog.d/pipeline-speed-reader-guard.md`.
- Task `path-gaps`:
  - `MACHINE_PATH` flags a `file:` URL with a host part before a home directory.
  - The git guard resolves a relative `git -C` against a preceding literal `cd` in the same command line (`git_c_dirs`
    in `scripts/lib/rpgf_guard/git.py`, used by `git_dir_in_scope` in `language.py`).
  - Changelog fragment `changelog.d/pipeline-speed-path-gaps.md`.
- Task `hash-extra-paths`:
  - `assetgen.py model-hashes` also hashes the folders that ComfyUI extra model path files name for the hashed kinds:
    `extra_model_paths.yaml` next to the install, the Comfy Desktop instance file and `--extra-model-paths FILE`
    (`--no-extra-model-paths` turns discovery off). A malformed file is a warning. Folder order follows ComfyUI.
  - comfy-desktop-setup step 7 describes it. Changelog fragment `changelog.d/pipeline-speed-model-hashes.md`.

Mode: implement. Model rule: Codex was unavailable (`agents --down codex`), so by the owner's instruction Claude
Sonnet 5.5 implemented, Claude Opus 5.5 led and reviewed (SAME_MODEL), and verify sessions or the run lead ran QA.

## Sessions and verdicts

| Task | Verify | Candidate | QA run |
|---|---|---|---|
| path-gaps | review PASS, QA PASS; re-recorded by the run lead after the plan edit that added `language.py` | eca33be | `--within tests/git-guard.test.sh,tests/plan-paths.test.sh -j 1`: 454 passed, 0 failed |
| verb-speed | review FAIL (QA children dropped by cleanup); review PASS then QA FAIL (19: stale memo for in-process callers, fixtures); review and QA PASS | bb8e2e6 | `--affected --base 994fbc5 --within tests/pipeline.test.sh -j 1`: 402 passed, 0 failed |
| reader-guard | review PASS; QA NOT_RUN (low memory) | 7d67d21 | 389 passed, 0 failed before the stop (guard lines, `tests/affected.test.sh`); `tests/run-all-parallel.test.sh` and `tests/workspace-default.test.sh` left to CI |
| hash-extra-paths | review PASS (2 nits fixed); QA NOT_RUN (low memory) | 104577f | skills-lint PASS, 414 guard lines PASS; the 25 new cases by hand; `tests/assetgen.test.sh` and `tests/comfy-desktop-setup.test.sh` left to CI |
| integration:plugin | QA by the run lead | 3ff95fc | `--workspace-only --base origin/main`: 19 checks, 9 passed, 0 failed, 10 not affected, 1104 s |

## Limitations

- QA NOT_RUN for reader-guard and hash-extra-paths: the machine was short on memory, background runs were stopped and
  forks failed. The run lead stopped one of its own orphaned QA runs that was still making progress. CI on the PR runs
  every affected suite on Linux and Windows.
- `model-hashes`: explicit `--extra-model-paths` files are read before the auto-discovered root file (ComfyUI reads the
  root file first), and `is_default` accepts true/yes/on words rather than Python truthiness.
- Docstrings of `git_dir_in_scope` (`language.py`) and `literal_cd_target` (`git.py`) are stale; the
  `_GIT_MEMO_ON` branch in `factory-pipeline.py` reads awkwardly.
- The reader guard is selected only for changes under `scripts/` and `tests/`.
- Cost: NOT_AVAILABLE.
