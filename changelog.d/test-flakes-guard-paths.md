### Fixed

- `MACHINE_PATH` (`scripts/lib/plan_paths.py`) now flags a `file:` URL with a home or Users path
  (`file:///home/<name>/...`, `file:///Users/<name>/...`, `file:///C:/Users/<name>/...`) like the drive form; an inner
  path segment named `home` or `Users` (`docs/home/readme.md`) and an `http(s)` URL with `/home/` stay allowed.
- The git guard's english-only advisory now resolves a relative `git -C <path>` against the hook's cwd before its scope
  test, so `git -C ../clone commit -m '<non-English text>'` from an unrelated directory gets the advisory when the
  target is in scope.
- `tests/facts.test.sh`: the HEAD export note no longer claims that LFS-tracked files always stay pointers; it says they
  stay pointers without git-lfs and are smudged (possibly fetched, so not offline) when git-lfs is configured.
