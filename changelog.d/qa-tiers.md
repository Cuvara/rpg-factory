### Added

- **run-all.** One full run per machine: a full `tests/run-all.sh` (no `--affected` or `--only-suites`) and every
  `--release` run take a lock in the persistent state dir. A second full run waits and prints `waiting for full run <pid> in <checkout>`;
  `--no-wait` exits 3 instead, and a lock whose holder is dead is taken over
  (`run-all: taking over stale full-run lock (<pid>)`).
- **run-all.** A full run on a clean tree writes a result record for that tree; `--reuse` exits 0 at once on a PASS
  record of the same clean tree with at least the same coverage (a `--no-workspace` or `--no-claude` record does not
  satisfy a run without that flag) and prints `reused full run at <HEAD> (tree <tree>, <date>)`. `--release` never
  reuses the record.
- **run-all.** Suite-level reuse: each suite's PASS is recorded under a hash of its inputs (the suite file, the files
  `tests/affected.py` maps to it, the global inputs and the tool versions), and a later run skips that suite and
  prints `PASS  <check> (reused <suite> inputs <hash>)`. Suites graded by a postprocessor, checks that read the live
  workspace (a `run` inside a live block too) and `--no-history` runs are never reused, and no record is published when the inputs changed during the run.
  `--no-reuse` runs every suite; `--release` never reuses.
- **run-all.** `--only-suites LIST` runs only the named suites (comma-separated paths), unioned with `--affected` when
  both are given; neither takes the full-run lock. A name run-all does not run (a missing file, or a suite without a
  run-all line such as `tests/dogfood.sh`) exits 2. `--list-suites` (read-only) prints the names `--only-suites`
  accepts. A one-suite `--only-suites` run took 76 s before and 14 s after.
- **run-all.** With `--affected` or `--only-suites`, the live-workspace blocks and the checks that run a script outside
  a suite line (`scripts/checks/skill-citations.py`, `scripts/factory-context.sh`, `scripts/checks/pin-status.py`,
  `pin-plan.py`, `package-ready.py`, `netcode-headless.sh`) are selected like suites by that script path, else they
  count as not affected; `--only-suites` may name such a script.
- **run-all.** When `python3` resolves to the Windows Store alias, run-all puts the real Python directory first on
  `PATH` for the suites (about 70 ms saved per call); the user's system is not changed.
- **Tests.** `tests/affected.py` no longer treats `scripts/lib/*` as global: a lib module selects only the suites of
  the scripts that import it (static scan; a module it cannot map still selects every suite).
  `tests/affected.test.sh` covers it. `affected.py hashes SUITE...` prints each suite's input hash for suite reuse
  (`-` when reuse is unsafe).
- **Guard.** `scripts/git-guard.py --batch` evaluates JSON-line cases in one process through the same evaluation as
  the hook. `tests/git-guard.test.sh` runs most cases through it and keeps a representative set on the real hook
  process (exit codes, `; exit 0` wiring, crash safety); the case count is unchanged. Suite wall time: 717 s before,
  about 96-128 s after.
- **Pipeline.** QA tiers (registry `pipeline.qa_tiers`): `dispatch --phase qa` prints one tier command. Task QA runs
  `tests/run-all.sh --affected --base <review base> [--only-suites <check suites>] -j 2` (the suites the task's checks
  name that `tests/run-all.sh --list-suites` lists, each once; a full `tests/run-all.sh` check is dropped and folded
  into it, other checks stay extra commands)
  and its spec forbids a full run. `verdict --phase qa --state FAIL --failed-suites LIST` records the failed suites;
  the next QA dispatch on a new candidate reruns them with `--affected --base <that FAIL's candidate>`. Integration
  QA runs `tests/run-all.sh --reuse -j 4` under the lock. `validate` warns when a task's checks contain a full
  `tests/run-all.sh` or its acceptance requires a full run (`full runs belong to integration QA`).
- **Pipeline.** A tier S task (plan or task tier S, or every owned path under `docs/`, `skills/`, `changelog.d/` or a
  `.md` file) needs no QA session: the task lead runs the task QA command after the review PASS and records
  `verdict --phase qa --state PASS --by <lead> --note 'tier S: lead ran task suites'`. The gate accepts such a
  lead-run QA verdict (note starting `tier S`, no QA session) only for a tier S task. A QA PASS from a fresh QA
  session is accepted as before for every tier, including the one-model fallback where the implementer's model runs
  QA.

### Changed

- **Core.** `parallel-work.md` section 10 has a "QA tiers" table (task QA, re-QA, tier S, reviewer, integration QA,
  release) with the lock and reuse rules: a task never runs the whole suite, reviewers run no suites, and the only
  full run of a batch is integration QA. It replaces the "at most two concurrent full runs" rule with one full run
  per machine. `.claude/CLAUDE.md` follows: the PR rule names integration QA's full run (or a reused PASS record of
  the same tree), and Commands lists `--reuse`, `--no-wait`, `--only-suites` and `--no-reuse`.
- **Tests.** `tests/parallel-policy.test.sh` builds one minimal throwaway plugin copy, copies only the lint inputs
  per mutation and runs only the lint sections a mutation reaches, concurrently (`PARALLEL_POLICY_JOBS`, default 4).
  It also checks the QA tiers table: one copy under its marker, the required rows, no full run in the task row.
  Suite wall time: 831 s before, about 61-115 s after.
- **Tests.** `tests/routing.test.sh` caches each history replay result in the persistent state dir, keyed by commit
  SHA and a hash of the routing inputs (the suite, the registry, every script, the routing environment and the tool
  versions), and replays only commits without a cached result (`history replay: <n> cached / <n> replayed`);
  `--no-history` skips the replay.
- **Tests.** `tests/pipeline.test.sh` captures the output of identical commands once and runs independent cases in
  parallel. Suite wall time: 459 s before, 242 s after.
