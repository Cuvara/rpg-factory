# tests/

Suites of the rpg-factory plugin. Each `*.test.sh` (or `*.test.py`) runs standalone and sets its own temp `TMPDIR` and
`RPG_FACTORY_STATE_DIR`; `tests/run-all.sh` runs them all and prints the usage header with `-h`. Fixtures live in
`tests/fixtures/`. Full command list and flags: `scripts/README.md` "Commands".

## QA tiers and run-all flags

The QA tiers table of `skills/delivery/references/delivery.md` (section 10, "QA tiers"; registry `pipeline.qa_tiers`)
names the command of each tier. In short: a task runs `tests/run-all.sh --affected --base <base> -j 2` or its own
suites with `--only-suites`; integration QA before a PR runs `tests/run-all.sh --workspace-only`; CI
runs only the suites a change affects (`scripts/ci-plan.py`, one matrix job per suite, `--no-workspace --no-claude`)
and every suite through `workflow_dispatch` with `full=true`; `ci-ok` is the single required check
(`.github/workflows/tests.yml`, section "CI" below); `tests/run-all.sh --release` and `tests/dogfood.sh --installed`
run only for a release. The rules behind those commands follow.

## CI

`.github/workflows/tests.yml` plans first, then runs:

- The `plan` job runs `scripts/ci-plan.py`, which calls `tests/affected.py cases` once and emits one matrix job per
  `{suite, os}`.
- Anything unsure plans every suite: a CI plumbing change (`.github/workflows/**`, `.github/actions/**`,
  `tests/run-all.sh`, `tests/affected.py`, `scripts/ci-plan.py`, `tests/ci-windows-suites.txt`), no or an unusable
  base, or a `schedule` event. `workflow_dispatch` with `full=true` (the default) plans every suite on purpose; with
  `full=false` it plans from its `base` input (a sha or a ref the checkout has, e.g. `origin/main`), and an empty or
  unusable base plans every suite.
- Every suite runs on ubuntu-24.04, and also on windows-2025 when `tests/ci-windows-suites.txt` lists it (one suite
  path per line, `#` comments). A line that is not a runnable suite makes `ci-plan.py` exit 2.
- The inline checks run on both OSes through `tests/run-all.sh --inline-only`, even when no suite is selected.
- A suite job runs only its planned cases: it passes them to run-all with `--only-cases`, and a plan row with `ALL`
  runs every case. A case subset publishes no suite PASS record.
- `ci-ok` is the single required check, and branch protection must require only it. It fails on any failed or
  cancelled job and passes when no suite is affected. The old `run-all (no workspace, <os>)` checks no longer exist.
- `tests/ci-plan.test.sh` tests the plan.

## One full run per machine: the run-all lock

A full `tests/run-all.sh` takes a per-machine lock and a second one waits. Four parallel full runs made every suite
2-4x slower and timed some out. `tests/run-all.sh --workspace-only` covers what CI cannot, before the PR. Never create
a worktree or branch while a full run is in flight: the shared `.git/config` check fails (`.claude/CLAUDE.md`
"Operating lessons").

A full run (no `--affected` or `--only-suites`, or any `--release` run) takes the lock in the persistent state dir; a
second full run waits (`waiting for full run <pid> in <checkout>`), `--no-wait` exits 3 instead, and a lock whose
holder is dead is taken over (`run-all: taking over stale full-run lock (<pid>)`).

## Reuse

A full run on a clean tree writes a result record for that tree; `--reuse` exits 0 at once on a PASS record of the
same clean tree with at least the same coverage (`reused full run at <HEAD> (tree <tree>, <date>)`; a
`--no-workspace` or `--no-claude` record does not satisfy a run without that flag).

Each suite's PASS is also recorded under a hash of its inputs (`tests/affected.py hashes`, the conservative rule: the
suite file, the paths it names, every file in the tree of each code file the suite reaches, helpers with a caller edge
included, the global inputs and the tool versions, and the imports of every included code file in turn until nothing
new is added). Three exceptions: a `scripts/lib` module that is imported stays narrowed to its importers, suites
directly in `tests/` are not tree data, and the index docs `scripts/README.md` and `tests/README.md` count only where
a suite names them. A later run skips that suite (`PASS  <check> (reused <suite> inputs <hash>)`). Suites graded by a
postprocessor and checks that read the live workspace are never reused, and no record is published when the inputs
changed during the run. `--no-reuse` runs every suite, `--release` never reuses, and an input mapping that is unsure
runs the suite.

## Selection

`--affected` follows the narrow static graph of `tests/affected.py` (Python imports and the shell and jq helpers a
script loads or runs by name): a library module or a helper selects only the suites of the scripts that reach it, and
anything unsure runs. A miss there is caught by integration QA, whose suite reuse uses the conservative rule above.

`--only-suites` is unioned with `--affected`. In either mode the live-workspace blocks and the checks that run a script
outside a suite line (skill citations, `factory-context.sh`, pin status, pin plan, package ready, Netcode headless)
are selected like suites by that script path, else they count as not affected; `--only-suites` may name such a script
(`tests/run-all.sh` usage header). `--only-suites` exits 2 on a name run-all does not run; `tests/run-all.sh
--list-suites` (read-only) prints the names it accepts, and `dispatch --phase verify` (or `--phase qa`) folds into
`--only-suites` only the checks that list names (other checks stay extra commands). A check that mentions
`tests/run-all.sh` is folded only when it is one plain standalone scoped invocation (an optional `env -u TMPDIR` and
`bash` prefix, plain flag tokens, `--affected` or `--only-suites` among them); every other check that mentions
run-all, a plain full run included, is printed `DO NOT RUN` and the verify or QA session reports it NOT_RUN. No check
is dropped.

## Test-run slots

The generic rule is in delivery.md section 10 ("QA tiers"). `RPG_FACTORY_TEST_SLOTS` (default 2, `0` disables the cap,
a non-integer exits 2) caps the targeted runs, the slots are `locks/run-all-slots/<n>` in the persistent state dir,
the wait line is `run-all: waiting for a test slot (<n> in use: <holders>)`, `--no-wait` exits 3 and a dead holder is
taken over (`run-all: taking over stale test slot <n> (<pid>)`).

## Case selection

`pipeline.test.sh`, `parallel-policy.test.sh` and `git-guard.test.sh` take `--case NAMES` and `--list-cases`;
`--affected` passes the cases `tests/affected.py cases` selects (case maps are `# case-map:` header lines of each
suite), and an explicit `--only-suites` name runs all its cases unless `--only-cases L` names a subset (exactly one
`--only-suites` suite that has a case map; misuse exits 2; `ALL` or an empty list runs every case).
`routing.test.sh` also takes `--case` and `--list-cases` when run by hand, but it has no case map: `--affected` always
runs all its cases and `--only-cases` rejects it.
