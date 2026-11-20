# Run report: test-flakes

Tier M plan, three tasks in one wave, on branch `test-flakes` (base `main` `19c8950`). It follows the owner request of
2026-11-18 (tests fast and precise): it removes cases that failed at random under host load and closes lows of
run-lows-followups, path-audit-followups, plugin-flow-5-followups, policy-followups-leftovers and
test-speed-followups. It avoids the paths of the parallel plan runtime-quirks.

## Summary

- Task `load-flakes`:
  - `tests/netcode-headless.test.sh`: the fake timeout is 8 s, and the fake sleep mode is 20 s, so the timeout case
    still times out.
  - `tests/routing.test.sh`: a scenario is retried once, only on a snapshot git timeout, and it prints RETRY.
  - `testlab/tests/test_lab.py`: the 1.0 % host-guard CPU budget is asserted only on an idle host; on a busy host
    the check is skipped and the reason and values are printed.
  - `tests/orca-wait.test.sh`: the young-guard case no longer depends on scheduling delay, and the INT case runs
    under run-all through a launcher that resets SIGINT.
  - Changelog fragment `changelog.d/test-flakes-load.md`.
- Task `runall-doctor`:
  - The run-all slot takeover message is on stderr.
  - The netcode evidence prune orders same-second directories by numeric pid.
  - `doctor` names the Git Bash `python3` Store stub and a missing `jq`, with fix hints (text and `--json`).
  - `scripts/README.md` lists the assetgen case groups and the two `scripts/checks/` conventions.
  - Changelog fragment `changelog.d/test-flakes-runall-doctor.md`.
- Task `guard-path-lows`:
  - `MACHINE_PATH` flags `file:` URLs with a home or Users path; an inner segment named `home` or `Users` stays
    allowed.
  - The git guard's english-only scope resolves a relative `git -C` against the hook cwd.
  - The facts LFS note is true with and without git-lfs.
  - Changelog fragment `changelog.d/test-flakes-guard-paths.md`.

Mode: implement. Model rule: Codex was unavailable (`agents --down codex`), so by the owner's instruction Claude
Sonnet 5.5 implemented, Claude Opus 5.5 led and reviewed (SAME_MODEL), and verify sessions ran QA.

## Sessions and verdicts

| Task | Verify | Candidate | QA run (`--affected --base test-flakes --within <checks> -j 1`) |
|---|---|---|---|
| load-flakes | review PASS, QA PASS | de91034 | 408 passed, 0 failed; orca-wait 53/53 with INT PASS (direct, as a background job); test_lab 307 OK (direct) |
| runall-doctor | review PASS, QA PASS | 201ae77 | 429 passed, 0 failed; 31 affected suites left to CI |
| guard-path-lows | review PASS, QA PASS at 33c53a6. After merge, the portable-paths enforce line flagged five placeholder user names in the new cases; fixed in cea9b88, delta verify PASS | cea9b88 | 395 passed, 0 failed; portable-paths enforce 0 findings |
| integration:plugin | QA by the run lead | 89d2571 | `--workspace-only --base origin/main`: 19 checks, 5 passed, 0 failed, 14 not affected, 795 s |

The run lead's plan file held a `file:` URL example with a Users path (a gate blocker); it was reworded with
`plan-edit` in 6e85bd1.

## Limitations

- test_lab ran on a busy host (mean CPU 83 %): the idle-host assertion branch was not exercised.
- The orca-wait INT launcher and the young-guard toucher had not yet run on Linux CI when the PR opened.
- The task verify did not run the portable-paths enforce line, so the placeholder names were caught only after the
  merge. The tier command's inline checks do not include it.
- `doctor` text prints the older python3 hook-speed advice next to the new setup-fault line (near-duplicate).
- `scripts/README.md` says `root_default` reads are allowed in `scripts/lib/`; the guard allows only
  `lib/workspace.py` and `lib/fstate.py`.
- The netcode prune case lives in `tests/run-all-parallel.test.sh`, which `tests/affected.py` does not map to
  `scripts/checks/netcode-headless.sh`.
- A `file:` URL with a host part before the home directory is not flagged; `cd x && git -C ../y` resolves against the hook cwd, not the cd target.
- Cost: NOT_AVAILABLE.
