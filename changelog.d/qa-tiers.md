### Added

- **run-all.** One full run per machine: a full `tests/run-all.sh` (no `--affected` or `--only-suites`) takes a lock
  in the persistent state dir. A second full run waits and prints `waiting for full run <pid> in <checkout>`;
  `--no-wait` exits 3 instead, and a lock whose holder is dead is taken over.
- **run-all.** A full run on a clean tree writes a result record for that tree; `--reuse` exits 0 at once on a PASS
  record of the same clean tree and prints `reused full run at <HEAD> ...`.
- **run-all.** Suite-level reuse: each suite's PASS is recorded under a hash of its inputs (the suite file, the files
  `tests/affected.py` maps to it, the global inputs and the tool versions), and a later run skips that suite with
  `reused <suite> (inputs <hash>)`. `--no-reuse` runs every suite; `--release` never reuses.
- **run-all.** `--only-suites LIST` runs only the named suites.
- **run-all.** When `python3` resolves to the Windows Store alias, run-all puts the real Python directory first on
  `PATH` for the suites (about 70 ms saved per call); the user's system is not changed.
- **Tests.** `tests/affected.py` no longer treats `scripts/lib/*` as global: a lib module selects only the suites of
  the scripts that import it (static scan; a module it cannot map still selects every suite).
  `tests/affected.test.sh` covers it.
- **Guard.** `scripts/git-guard.py --batch` evaluates JSON-line cases in one process through the same evaluation as
  the hook. `tests/git-guard.test.sh` runs most cases through it and keeps a representative set on the real hook
  process (exit codes, `; exit 0` wiring, crash safety); the case count is unchanged.
- **Pipeline.** QA tiers (registry `pipeline.qa_tiers`): `dispatch --phase qa` prints one tier command. Task QA runs
  `tests/run-all.sh --affected --base <review base> --only-suites <check suites> -j 2` and its spec forbids a full
  run; a re-QA after a FAIL reruns the suites recorded with `verdict --failed-suites` plus `--affected` from the
  previous candidate; integration QA runs `tests/run-all.sh --reuse -j 4` under the lock. `validate` warns when a
  task's checks contain a full `tests/run-all.sh` or its acceptance requires a full run.
- **Pipeline.** A tier S task gets no QA session: the task lead runs the task QA command after the review PASS and
  records `verdict --phase qa --by <lead> --note 'tier S: lead ran task suites'`; the gate accepts this for tier S
  only.

### Changed

- **Core.** `parallel-work.md` section 10 has a "QA tiers" table (task QA, re-QA, tier S, reviewer, integration QA,
  release) with the lock and reuse rules: a task never runs the whole suite, reviewers run no suites, and the only
  full run of a batch is integration QA. It replaces the "at most two concurrent full runs" rule with one full run
  per machine. `.claude/CLAUDE.md` follows: the PR rule names integration QA's full run (or a reused PASS record of
  the same tree), and Commands lists `--reuse`, `--no-wait`, `--only-suites` and `--no-reuse`.
- **Tests.** `tests/parallel-policy.test.sh` builds its throwaway plugin copy once instead of per mutation.
- **Tests.** `tests/routing.test.sh` caches the history replay by commit SHA and registry hash and replays only new
  commits.
- **Tests.** `tests/pipeline.test.sh` builds its fixture git repos once and copies them per case.
