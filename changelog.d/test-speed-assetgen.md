### Changed

- **Asset-gen suite speed.** `tests/assetgen.test.sh` is the slowest suite (about 4 min on Linux CI, over 40 min on a
  Windows host, where every process start costs 0.5-1.5 s), so it now counts processes instead of work. Every `AG` call
  is served by one interpreter for the whole run (`tests/fixtures/assetgen/agserver.py`: argv, working directory, the
  `ASSETGEN_*`/`RPG_FACTORY_*` variables the cases set, stdout, stderr and the exit code carry over; a plain process
  is the fallback). The render-golden loop (every core purpose and variant against its golden workflow) and the
  ui-workflow loop (every `workflow.ui.json` converted back with the stdlib converter, now `ui2api.py`) each run in one
  interpreter (`loops.py`), jq runs with `-b` on Windows instead of behind a `tr` process, and the lint and graph-style
  rows are read from one jq call instead of one per template. No assertion was dropped or weakened: every PASS line and
  its count is unchanged.
- **Asset-gen suite case groups.** The suite is a list of 41 named case groups with `--case NAMES` (alias `--only`) and
  `--list-cases`; a group that reads another group's state names it in `case_deps` and the prerequisite runs first,
  once. `ASSETGEN_TEST_TIMES=1` prints the wall time of each group and `ASSETGEN_TEST_PLAN=1` the groups a selection
  would run. `# case-map:` header lines list the inputs of each group (`tests/affected.py` case map), so a change to
  data, a fixture or the plugin side runs only the groups that read it; the engine modules reach every group and still
  select all of them.
