# Run report: path-audit

Tier M plan, five tasks, on branch `path-audit` (base `main` `72f5583`). It closes backlog topic `repo-path-audit`;
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
- The first CI run of the pull request failed in `tests/compat.test.sh` (Linux and Windows) and
  `tests/workspace-default.test.sh`: the new check lacked the UTF-8 stdio block and read the registry workspace key
  itself. Task `ci-fix` added the stdio block and the helper `registry_workspace_default` in
  `scripts/lib/workspace.py`; the check reads the default of its `--root` through it.
- Integration QA at db9ed37 failed in one check that also fails at `main`: four skill citations had drifted after the
  server repo's develop branch moved. Task `citation-drift` refreshed them (`skills/go-backend/SKILL.md`,
  `skills/go-backend/references/testing.md`, `skills/server-ops/references/manifests-and-checks.md`);
  `scripts/checks/skill-citations.py --strict` reports 461 citations, 0 problems, 0 moved.

Mode: implement. Model rule: the registry profiles, cross-model. Codex gpt-6.1-terra implements, Claude Opus 5.5 leads
and reviews; QA ran where memory allowed (below).

## Sessions and verdicts

| Task | Implementer | Verify (review + QA) | Candidate | Tier run |
|---|---|---|---|---|
| machine-path-lows | codex gpt-6.1-terra high | claude-opus-5-5 medium review PASS; QA rerun by the run lead (claude-fable-5-2) PASS | eb16c5b | 614 checks: 452 passed, 0 failed, 162 skipped |
| user-path-check | codex gpt-6.1-terra (check, fixtures), claude-sonnet-5-5 (doc) | claude-opus-5-5 review PASS at a4bcff9; QA BLOCKED (memory) | a4bcff9 | NOT_RUN; the task's own checks passed (below) |
| affected-mapping | codex gpt-6.1-terra (fixture), claude-sonnet-5-5 (mapping) | claude-opus-5-5 medium review PASS; QA PASS on the task's checks, recorded by the task lead | b090b9e | stopped by memory; the task's own checks passed (below) |
| ci-fix | claude-sonnet-5-5 | codex gpt-6.1-sol high: first QA FAIL at c634ac9 (helper name matched the reader guard), PASS at 3bee197 | 3bee197 | stopped after `compat` passed; the task's own checks passed (below) |
| citation-drift | claude-sonnet-5-5 | claude-opus-5-5 review and lead QA PASS (docs-only); codex gpt-6.1-sol review PASS, no findings | 489e8a1 | NOT_RUN; the citation check and `tests/skills-lint.sh` (700 passed) ran directly |
| integration | - | run lead, `tests/run-all.sh --workspace-only` with the workspace variable unset | daae3c3 | 24 checks: 23 passed, 1 failed (transient, below); the failed suite rerun alone: 131 passed, 0 failed. Earlier: 38bf8a9 24 passed; db9ed37 23 passed, 1 failed (the citation drift); 63b6e80 24 passed |

Checks the task leads ran directly, one at a time:

- `user-path-check` at a4bcff9: `tests/portable-paths.test.sh` PASS; `scripts/checks/portable-paths.py --enforce`
  862 files, 0 findings; testlab `test_failsum.py` 20 passed, `test_framegc.py` 7 passed, `test_lab.py` 306 passed and
  1 failed (below).
- `affected-mapping` at b090b9e: `tests/affected.test.sh` 153 passed; `tests/ci-plan.test.sh` 41 passed;
  `tests/portable-paths.test.sh` PASS; `tests/checks-candidate.test.sh` 33 passed; the enforce line 864 files,
  0 findings.
- `ci-fix` at 3bee197: `tests/compat.test.sh` PASS; `tests/workspace-default.test.sh` 84 passed;
  `tests/portable-paths.test.sh` PASS; the enforce line 864 files, 0 findings.

## Limitations

- Integration QA at daae3c3 (the merge of `main` after PR 124 refreshed the same citations; the conflict in
  `skills/go-backend/references/testing.md` took the version of `main`) is not one clean run: `routing + history
  replay` failed in one scenario ("Redis servers:id -> wire-contract leads") whose snapshot reported the server repo as
  "not a git work tree" on a heavily loaded machine (the suite took 633 s, the run 2122 s). The repo was intact, and
  `tests/routing.test.sh` rerun alone at the same commit passed 131 of 131. CI at daae3c3: 92 jobs passed, `ci-ok` green.

- The two CI failures were not caught before the pull request because the task QA of `user-path-check` never ran and
  integration QA (`--workspace-only`) does not include those suites.
- Task QA of `user-path-check` is BLOCKED, not PASS: Claude Code stopped both verify sessions for low system memory
  before the tier command ran. The tier commands of `affected-mapping` and `ci-fix` (58 of 77 suites, because `scripts/lib/workspace.py` is a shared
  helper) were stopped the same way or cut short (the task's own checks
  ran instead). Integration QA and CI (`ci-ok`, the suites `scripts/ci-plan.py` selects on Linux and Windows) cover
  the suites those runs did not reach.
- testlab `test_lab.py` case `test_live_guard_samples_the_host_read_only_and_its_own_cpu_is_small` failed once (sampler
  CPU 1.56 % against a 1.0 % bound) on the loaded machine. It measures the live host and reads no fixture, so it is
  not from the scrub; not rerun at base.
- `machine-path-lows` review lows: a `file:` URL with a home or Users path is not flagged (same as the existing drive
  form), and there is no explicit allowed case for an inner path segment named home (checked by hand).
- A test slot stayed recorded for a process that no longer ran after a memory stop (`status` shows it as not running).
- The first Codex verify session of `citation-drift` started with an empty prompt and idled for about 4.5 hours until
  the run lead nudged the task lead, which then reviewed and ran lead QA itself. The gate asked for the cross-model
  review, so the run lead dispatched a Codex review afterwards (PASS, no findings).
- Cost: NOT_AVAILABLE (no usage reported through Orca).
