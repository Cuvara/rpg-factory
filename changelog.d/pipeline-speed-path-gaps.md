### Fixed

- **Plan paths.** `MACHINE_PATH` now also flags a `file:` URL with a host part before a home directory
  (`file://host/C:/Users/<name>/...`, `file://server/home/<name>/...`); a hosted URL whose path is not under a home
  directory stays allowed.
- **Guard.** The language advisory's relative `git -C` check resolves the path against a preceding literal `cd <dir>`
  in the same command line (`cd x && git -C ../y commit ...`), not only against the hook's cwd; a `cd` whose target is
  not a literal directory gives no opinion for the relative `-C` paths after it.
