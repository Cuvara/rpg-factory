# Run report: test-speed

Tier L plan, four tasks in two waves, on branch `test-speed` (base `main` `6f2f225`). Owner request (2026-11-18):
tests must be fast and precise; most task time went into broad runs and checks the change did not need.

Measured before the plan on this Windows host:
- Task QA `--affected --base <b> --only-suites <checks>` unioned the import closure with every case of the named
  suites; a `scripts/lib/workspace.py` change selected 62 of 77 suites.
- Integration QA `--workspace-only` took 869 s, 700 s of it in three checks (routing replay, routing properties,
  facts) that ran whatever the change was.
- The host runs suites about 17x slower than Linux CI: `pipeline.test.sh` about 2 min on CI and 35 min here;
  `assetgen.test.sh` 4 min on CI and 41 min here.

## Summary

- Task `runall-scope` (`tests/run-all.sh`, `tests/affected.py`):
  - `--affected --base <b> --within <suites>` runs only the named suites, each limited to the cases the change
    reaches (ALL when unsure), and prints the suites left to CI.
  - `--workspace-only --base <b>` runs only the workspace checks whose declared inputs the change reaches
    (`WORKSPACE_INPUTS`); without a base, and under `--release`, all of them.
  - The result record holds per-check durations, and the summary prints the five slowest checks.
- Task `pipeline-qa` (`scripts/factory-pipeline.py`):
  - Task QA specs name `tests/run-all.sh --affected --base <b> --within <check suites> -j 1`; integration QA names
    `--workspace-only --base <plan base>`.
  - The selection line reports the suites left to CI.
  - `validate` asks checks to name the suites that test the changed behaviour.
  - Docs, the registry `qa_tiers` description and `pipeline-defaults.json` were updated to match.
  - `tests/pipeline.test.sh` was trimmed: a bytecode-cache launcher, capture-once reuse, and fewer double runs.
- Task `qa-policy`: delivery.md section 10, `parallel-work.md`, `.claude/CLAUDE.md` and `tests/README.md` state the
  new rules:
  - Task QA runs the task's checks only, at the affected cases.
  - CI is the breadth gate: `ci-ok` must be green before merge.
  - Integration QA runs only the affected workspace checks.
  - The low-memory lesson: run `-j 1`, one task QA at a time, and report NOT_RUN after one retry.
- Task `assetgen-speed`: `tests/assetgen.test.sh` is split into 41 case groups with `--case` selection and a case
  map. AG calls are served from one interpreter, and render and UI loops are batched.

Mode: implement. Model rule: Codex was unavailable (`agents --down codex`), so by the owner's instruction Claude
Sonnet 5.5 implemented, Claude Opus 5.5 led and reviewed, and the task lead or the run lead ran QA (SAME_MODEL).

## Sessions and verdicts

| Task | Verify | Candidate | QA run |
|---|---|---|---|
| runall-scope | review PASS (claude-opus-5-5); QA NOT_RUN in the task (low memory), QA PASS by the run lead | f496eff | run-all-parallel 224/224, affected 171/171 |
| qa-policy | review PASS; QA FAIL on one load-sensitive nested orca-wait case outside the diff; re-QA PASS by the run lead | 883bbb2 | delivery-generic, line-budget, skills-lint PASS; parallel-policy 141/142, then `--case orca-wait` 53/53 |
| pipeline-qa | QA FAIL at 35667fa (defaults drift, a crash on non-string paths; fixed); review and QA PASS at fd682e2 | fd682e2 | `--affected --base test-speed --within delivery-generic,pipeline -j 1`: 552 passed, 0 failed, 12 min; 75 suites left to CI |
| assetgen-speed | review PASS three times; QA BLOCKED (memory), then FAIL (missing case prerequisite, fixed), then PASS | c60b0b1 | owner decision B: sequential `--case` group runs, all 41 groups, 1574 PASS 0 FAIL |
| integration:plugin | QA by the run lead | 122fbba | `--workspace-only --base origin/main`: 24 checks, 24 passed, 1191 s (registry changed, so every check was selected) |

## Measured gains on this host

- Task QA selection: the `pipeline-qa` verify ran 2 suites instead of the 77 the old union selected.
- assetgen groups, before and after (s): render-golden 433 / about 25, lint 348 / about 70, graph-style 178 / about 15,
  ui-workflow 151 / 9, resolve 133 / 18.
- `pipeline.test.sh`: small gain under equal load (dispatch 126 / 104 s, child-dispatch 54 / 35 s). Each
  `factory-pipeline.py` start costs 2.5-4 s on this host, and that cost dominates.

## Limitations

- The full wall times of `assetgen.test.sh` are NOT_RUN (owner decision B; every full run was killed for low memory).
- Case-map narrowing is coarse: most `scripts/assetgen/*` changes, and any `scripts/factory-pipeline.py` change,
  still select all groups, because `tests/affected.py` reach is per file.
- `WORKSPACE_INPUTS` also widens ordinary `--affected` and CI selection for keyed scripts (conservative).
- Re-QA in `--phase qa` still unions the task's check suites with the failed suites.
- `scripts/README.md` lists `assetgen.test.sh` without `--case`.
- Cost: NOT_AVAILABLE.
