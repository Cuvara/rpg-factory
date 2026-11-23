### Changed

- **Symbol-level case reach.** A case map may name a top-level function, class or module-level name of a Python file
  (`PATH::NAME`, `PATH::*` for the whole file). `tests/affected.py cases [--base REF]` maps the changed lines
  (`git diff -U0` against the merge-base) to top-level functions and classes with ast. It then selects only the case
  groups whose named entries reach them through the file's own scope-aware static references. So a change inside one
  `cmd_*` verb of `scripts/factory-pipeline.py` no longer runs every case group of `tests/pipeline.test.sh`. Anything
  unsure keeps the file-level reach: module-level code, imports, decorators, an added, deleted or renamed function, a
  parse failure, a helper `main()` or other import-time code reaches, an unnamed helper of a module with dynamic name
  lookup, or a file list that is not the changed set from that base.
- **run-all passes its base to case selection.** `tests/run-all.sh --affected --base B` hands `--base B` to
  `affected.py cases`, so the changed line ranges come from the same merge-base as the changed files.

### Fixed

- **Assetgen CLI help case.** The case 'CLI help documents --run RUN-ID and resolve --verbose' captures the help text
  before it matches it. It no longer pipes into `grep -q` under pipefail, where an early grep exit could fail the case
  with SIGPIPE.
