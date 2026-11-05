# Changelog fragments

Every behaviour change adds one file here, `changelog.d/<topic>.md` (for example the branch topic
`codex-hook-dialect.md`), instead of editing `CHANGELOG.md`. Parallel branches then never edit the same lines.

A fragment holds Keep a Changelog subsections only: `### Added`, `### Changed`, `### Deprecated`, `### Removed`,
`### Fixed` or `### Security`, each followed by its entries.

```markdown
### Fixed

- **Guard.** What changed and why.
```

- `python3 -B scripts/changelog.py check` validates the fragments and that `CHANGELOG.md` `[Unreleased]` is empty
  (run-all runs it).
- `python3 -B scripts/changelog.py preview` prints the assembled unreleased notes.
- At release, `python3 -B scripts/changelog.py release X.Y.Z [--summary TEXT]` writes `## [X.Y.Z] - <date>` into
  `CHANGELOG.md` (categories in Keep a Changelog order, fragments in file-name order) and deletes the fragments;
  `scripts/release-check.py` then requires this directory to hold no fragment.
