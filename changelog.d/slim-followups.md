### Added

- **Operating lesson.** `.claude/CLAUDE.md` says never to stop a process by pattern (`pkill -f <name>`): a worker that
  did so to stop its own duplicate skills-lint run may have killed other sessions' runs. Stop only the PID you started.

### Fixed

- **Moved CLAUDE.md sections.** `skill-author`, `README.md`, `docs/dogfood.md` and
  `docs/architecture/multi-discipline-factory.md` point to `docs/releasing.md`, `docs/architecture/overview.md` and the
  `.claude/CLAUDE.md` "Commands" section instead of sections that moved; `docs/architecture/README.md` lists
  `overview.md`.
  `tests/affected.py` maps `docs/architecture/overview.md` to the `new-skill` suite and `tests/run-all.sh` reads
  `docs/releasing.md` in the release policy check.
