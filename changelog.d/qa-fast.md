### Added

- **Case selection in the slow suites.** `tests/pipeline.test.sh`, `tests/parallel-policy.test.sh`, `tests/routing.test.sh`
  and `tests/git-guard.test.sh` accept `--case NAMES` (alias `--only`; comma list, repeatable), `--list-cases` and
  `-h|--help`. `--help` prints the usage and exits 0; an unknown argument or case name exits 2 before any fixture or
  run starts. No selector still runs every case.
- **Case maps.** A suite declares which changed files cover which case with `# case-map: <case> <path-or-glob>...`
  header lines. `tests/affected.py cases FILE SUITE...` prints each selected suite with its affected cases, or `ALL`
  when the suite has no (or an invalid) map, the suite itself or a global input changed, or a selecting file is not
  in the map. `tests/run-all.sh --affected` passes `--case A,B` to such a suite and names the cases in the result
  line, so task QA runs only the cases a change can break. An explicit `--only-suites` name still runs all its cases,
  and a case subset never writes a suite PASS record (a full-suite PASS record can still satisfy a subset).
- **Machine-wide test-run slots.** `tests/run-all.sh --affected` and `--only-suites` runs take one of
  `RPG_FACTORY_TEST_SLOTS` slots (default 2, `0` disables the cap, a non-integer exits 2) under the persistent state
  directory (`locks/run-all-slots/<n>`). When every slot is busy the run prints `run-all: waiting for a test slot`
  with the holders and queues, `--no-wait` exits 3 instead, and a slot whose holder died is taken over
  (`run-all: taking over stale test slot`). Parallel sessions now queue instead of slowing every suite 2-4x. Full
  runs keep their own lock.

### Changed

- **`tests/pipeline.test.sh` is faster.** The multi-wave fixture repositories are built once per run as templates and
  copied per case, independent cases run as parallel child runs (`PIPELINE_TEST_UNITS`, default 4) whose output is
  printed in case order, and the assertion helpers match in bash instead of forking a subshell and `grep` per check
  (`PIPELINE_TEST_MATCH=check` compares both); `PIPELINE_TEST_TIMES=1` prints each section's wall time. On a loaded
  machine the full run (710 assertions) went from 59m51s to 14m12s, and `--case validate` (12 assertions) takes 17 s.
