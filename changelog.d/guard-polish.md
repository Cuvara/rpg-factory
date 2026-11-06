### Changed

- **Guard.** `scripts/lib/gitguard.py` loads the `scripts/lib/guard/` package by path under the unique name
  `rpgf_guard`, so no module named `guard` is imported and no other `guard` module on `sys.path` can shadow it or
  be shadowed by it. Behaviour and public names are unchanged; `tests/hook-perf.test.sh` asserts the package name and
  its cached bytecode.

### Fixed

- **Docs.** The `scripts/README.md` library index lists the current `lib/` modules (guard package, snapshot rendering,
  workspace helpers, process runner, artifacts, Orca commands), and `docs/architecture/ui-skills.md` names
  `scripts/lib/snapshot_render.py` for the snapshot Next line.
- **Guard.** Dropped a duplicate import in `scripts/lib/guard/common.py` and the blank line at the end of six guard
  modules (`git diff --check` is clean).
- **Tests.** `tests/artifact-quality.test.sh` puts `scripts/lib` on `sys.path` before it loads `scripts/lib/tools.py`
  by path, so the suite no longer fails on `codexconfig` when run on its own.
