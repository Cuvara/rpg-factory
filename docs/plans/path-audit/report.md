# Run report: path-audit

Tier M plan, three tasks, on branch `path-audit` (base `main` `72f5583`). It closes backlog topic `repo-path-audit`;
the low findings moved to `path-audit-followups`.

## Summary

- The plans check (`MACHINE_PATH` in `scripts/lib/plan_paths.py`, case `portable-plans` of
  `tests/parallel-policy.test.sh`) rejects a WSL drive mount followed by punctuation (a comma, a closing
  parenthesis) and no longer flags a URL whose path holds a Users or home directory (task `machine-path-lows`).
- New read-only check `scripts/checks/portable-paths.py` (report by default, `--enforce` exits 1): one pass over the
  tracked text files outside `docs/plans` flags a user home with a user name, an expanded Windows application-data
  path and a machine-only scratch root. It allows environment-variable forms, the registry `workspace.root_default`
  and its platform spellings (read from `registry.json`), obviously fake names, CI runner names under `.github`, URLs
  and the allowlist `tests/fixtures/portable-paths-allow.txt` (one reason per entry). `tests/run-all.sh` runs the
  suite `tests/portable-paths.test.sh` and the enforce line next to the English-only lines. The findings are fixed:
  the testlab fixtures carry a fake user and host name, and the provenance paragraph of
  `docs/architecture/ui-figma-real-test.md` names no machine path (task `user-path-check`).
- `tests/affected.py` maps the new check as a global one (every change runs the enforce line; a change to the check
  runs its suite), so the affected tier and `scripts/ci-plan.py` select it. `tests/fixtures/failed.trx` carries a fake
  user and host name and its allowlist entry is gone (task `affected-mapping`, added mid-run from the findings of
  `user-path-check`).

Mode: implement. Model rule: the registry profiles, cross-model. Codex gpt-6.1-terra implements, Claude Opus 5.5 leads
and reviews; QA ran where memory allowed (below).

## Sessions and verdicts

| Task | Implementer | Verify (review + QA) | Candidate | Tier run |
|---|---|---|---|---|
| machine-path-lows | codex gpt-6.1-terra high | claude-opus-5-5 medium review PASS; QA rerun by the run lead (claude-fable-5-2) PASS | eb16c5b | 614 checks: 452 passed, 0 failed, 162 skipped |
| user-path-check | codex gpt-6.1-terra (check, fixtures), claude-sonnet-5-5 (doc) | claude-opus-5-5 review PASS at a4bcff9; QA BLOCKED (memory) | a4bcff9 | NOT_RUN; the task's own checks passed (below) |
| affected-mapping | codex gpt-6.1-terra (fixture), claude-sonnet-5-5 (mapping) | claude-opus-5-5 medium review PASS; QA PASS on the task's checks, recorded by the task lead | b090b9e | stopped by memory; the task's own checks passed (below) |
| integration | - | run lead, `tests/run-all.sh --workspace-only` with the workspace variable unset | 38bf8a9 | 24 checks: 24 passed, 0 failed, 0 skipped |

Checks the task leads ran directly, one at a time:

- `user-path-check` at a4bcff9: `tests/portable-paths.test.sh` PASS; `scripts/checks/portable-paths.py --enforce`
  862 files, 0 findings; testlab `test_failsum.py` 20 passed, `test_framegc.py` 7 passed, `test_lab.py` 306 passed and
  1 failed (below).
- `affected-mapping` at b090b9e: `tests/affected.test.sh` 153 passed; `tests/ci-plan.test.sh` 41 passed;
  `tests/portable-paths.test.sh` PASS; `tests/checks-candidate.test.sh` 33 passed; the enforce line 864 files,
  0 findings.

## Limitations

- Task QA of `user-path-check` is BLOCKED, not PASS: Claude Code stopped both verify sessions for low system memory
  before the tier command ran. The tier command of `affected-mapping` was stopped the same way (the task's own checks
  ran instead). Integration QA and CI (`ci-ok`, the suites `scripts/ci-plan.py` selects on Linux and Windows) cover
  the suites those runs did not reach.
- testlab `test_lab.py` case `test_live_guard_samples_the_host_read_only_and_its_own_cpu_is_small` failed once (sampler
  CPU 1.56 % against a 1.0 % bound) on the loaded machine. It measures the live host and reads no fixture, so it is
  not from the scrub; not rerun at base.
- `machine-path-lows` review lows: a `file:` URL with a home or Users path is not flagged (same as the existing drive
  form), and there is no explicit allowed case for an inner path segment named home (checked by hand).
- A test slot stayed recorded for a process that no longer ran after a memory stop (`status` shows it as not running).
- Cost: NOT_AVAILABLE (no usage reported through Orca).
