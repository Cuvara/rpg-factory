### Added

- **run-all.** One full run per machine: a full `tests/run-all.sh` (no `--affected` or `--only-suites`) and every
  `--release` run take a lock in the persistent state dir; the shared-config snapshot is taken after the lock. A second full run waits and prints `waiting for full run <pid> in <checkout>`;
  `--no-wait` exits 3 instead, and a lock whose holder is dead is taken over. A holder counts as alive when its PID
  answers `kill -0` or, on Git Bash, when the Windows PID it recorded from `/proc/$$/winpid` is in `tasklist.exe`, so a
  full run started from another MSYS or Cygwin runtime is not taken over. Takeover prints
  `run-all: taking over stale full-run lock (<pid>)`. Only one waiter reclaims a stale lock, and a lock that a new
  holder has not finished writing is not taken over.
- **run-all.** A full run on a clean tree writes a result record for that tree; `--reuse` exits 0 at once on a PASS
  record of the same clean tree with at least the same coverage (a `--no-workspace` or `--no-claude` record does not
  satisfy a run without that flag) and prints `reused full run at <HEAD> (tree <tree>, <date>)`. `--release` never
  reuses the record.
- **run-all.** Suite-level reuse: each suite's PASS is recorded under a hash of its inputs (the suite file, the files
  `tests/affected.py` maps to it, the files under the directories of the scripts the suite reaches, such as
  `scripts/ui/data/*.json`, the global inputs and the tool versions), and a later run skips that suite and
  prints `PASS  <check> (reused <suite> inputs <hash>)`. Suites graded by a postprocessor, checks that read the live
  workspace (a `run` inside a live block too) and `--no-history` runs are never reused, no record is published when the inputs changed during the run, and a suite that skipped a case for a missing tool
  publishes no PASS record (a later run with the tool runs it).
  `--no-reuse` runs every suite; `--release` never reuses.
- **run-all.** `--only-suites LIST` runs only the named suites (comma-separated paths), unioned with `--affected` when
  both are given; neither takes the full-run lock. A name run-all does not run (a missing file, or a suite without a
  run-all line such as `tests/dogfood.sh`) exits 2. `--list-suites` (read-only) prints the names `--only-suites`
  accepts under the current flags (release-only suites need `--release`). A one-suite `--only-suites` run took 76 s before and 14 s after.
- **run-all.** With `--affected` or `--only-suites`, the live-workspace blocks and the checks that run a script outside
  a suite line (`scripts/checks/skill-citations.py`, `scripts/factory-context.sh`, `scripts/checks/pin-status.py`,
  `pin-plan.py`, `package-ready.py`, `netcode-headless.sh`) are selected like suites by that script path, else they
  count as not affected; `--only-suites` may name such a script.
- **run-all.** `--affected` selects the suites with one `tests/affected.py select-many` call per run instead of one
  call per suite.
- **run-all.** When `python3` resolves to the Windows Store alias, run-all puts the real Python directory first on
  `PATH` for the suites (about 70 ms saved per call); the user's system is not changed.
- **Tests.** `tests/affected.py` no longer treats `scripts/lib/*` as global: a lib module selects only the suites of
  the scripts that import it (imports parsed with `ast`; a module it cannot map still selects every suite). It follows import chains through non-lib modules, so a lib
  module imported only by another script module selects the suites of that module's importers.
  `tests/affected.test.sh` covers it. `affected.py hashes SUITE...` prints each suite's input hash for suite reuse
  (`-` when reuse is unsafe).
- **Guard.** `scripts/git-guard.py --batch` evaluates JSON-line cases in one process through the same evaluation as
  the hook. `tests/git-guard.test.sh` runs most cases through it and keeps a representative set on the real hook
  process (exit codes, `; exit 0` wiring, crash safety); the case count is unchanged. Suite wall time: 717 s before,
  about 96-128 s after.
- **Pipeline.** QA tiers (registry `pipeline.qa_tiers`): `dispatch --phase qa` prints one tier command. Task QA runs
  `tests/run-all.sh --affected --base <review base> [--only-suites <check suites>] -j 2` (the suites the task's checks
  name that `tests/run-all.sh --list-suites` lists, each once; only a standalone suite or `tests/run-all.sh`
  invocation is folded into it, a full `tests/run-all.sh` check is dropped, compound checks and other checks stay
  whole extra commands)
  and its spec forbids a full run. `verdict --phase qa --state FAIL --failed-suites LIST` records the failed suites;
  the next QA dispatch on a new candidate reruns those that `tests/run-all.sh --list-suites` lists, each once, with
  `--affected --base <that FAIL's candidate>`. The tier commands are read from registry `pipeline.qa_tiers`. A repo
  without `tests/run-all.sh` keeps the previous QA body: its checks and the `run-checks.py` fast tier. Integration
  QA runs `tests/run-all.sh --reuse -j 4` under the lock. `validate` warns when a task's checks contain a full
  `tests/run-all.sh` or its acceptance requires a full run (`full runs belong to integration QA`).
- **Pipeline.** Task QA never prints a full run. A standalone `tests/run-all.sh` check (optionally behind `env` or
  `bash`) is folded into the tier command, and a full one is dropped. A compound or wrapped check that contains a full
  run (`tests/run-all.sh -j 4 && ...`, `bash -c "tests/run-all.sh -j 4"`, `sh tests/run-all.sh`) is printed in the QA
  spec as an extra command `DO NOT RUN (...; report it NOT_RUN)`. Without a review base the task QA command is
  `tests/run-all.sh --only-suites <check suites> -j 2`; with no check suites either, the spec prints `NONE` and asks
  the task lead for a base. When two extra commands run the same suite, the `env -u TMPDIR` form is kept.
  `verdict --failed-suites` accepts any suite `tests/run-all.sh --list-suites` lists (for example
  `testlab/tests/test_lab.py` and `scripts/check-registry.sh`).
- **Pipeline.** A tier S task (plan or task tier S, or every owned path prose: a `.md` file anywhere, a path under `changelog.d/` or a `skills/` directory path; a non-`.md` file under `skills/`, `docs/*.json` and `docs/schemas/` are not prose) needs no QA session: the task lead runs the task QA command after the review PASS and records
  `verdict --phase qa --state PASS --by <lead> --note 'tier S: lead ran task suites'`. The gate accepts such a
  lead-run QA verdict (note starting `tier S`, no QA session) only for a tier S task. A QA PASS from a fresh QA
  session is accepted as before for every tier, including the one-model fallback where the implementer's model runs
  QA.

### Changed

- **Core.** `parallel-work.md` section 10 has a "QA tiers" table (task QA, re-QA, tier S, reviewer, integration QA,
  release) with the lock and reuse rules: a task never runs the whole suite, reviewers run no suites, and the only
  full run of a batch is integration QA. It replaces the "at most two concurrent full runs" rule with one full run
  per machine. `.claude/CLAUDE.md` follows: the PR rule names integration QA's full run (or a reused PASS record of
  the same tree), and Commands lists `--reuse`, `--no-wait`, `--only-suites`, `--list-suites` and `--no-reuse`.
- **Tests.** `tests/parallel-policy.test.sh` builds one minimal throwaway plugin copy, copies only the lint inputs
  per mutation and runs only the lint sections a mutation reaches, concurrently (`PARALLEL_POLICY_JOBS`, default 4).
  It also checks the QA tiers table: one copy under its marker, the required rows, no full run in the task row.
  Suite wall time: 831 s before, about 61-115 s after.
- **Tests.** `tests/routing.test.sh` caches each history replay result in the persistent state dir, keyed by commit
  SHA and a hash of the routing inputs (the suite, the registry, every script, the routing environment and the tool
  versions), and replays only commits without a cached result (`history replay: <n> cached / <n> replayed`); each
  write prunes old cache keys;
  `--no-history` skips the replay.
- **Tests.** `tests/pipeline.test.sh` captures the output of identical commands once and runs independent cases in
  parallel. It does not copy prebuilt fixture repos: per-case setup is a few git commands, and the time is in the
  `factory-pipeline.py` CLI calls. Suite wall time: 459 s before, 242 s after.
