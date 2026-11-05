### Added

- **`tests/run-all.sh --affected [--base REF]`.** Runs only the suites a change touches (`tests/affected.py`: files
  changed since the merge-base with `origin/main`/`main` plus untracked files; a suite runs when it is the changed
  file, names it, lists it as an indirect input, or a global input such as the registry or `scripts/lib/` changed).
  Cheap inline checks always run; `--release` ignores it. Every suite line now shows its duration
  (`tests/affected.test.sh`).
