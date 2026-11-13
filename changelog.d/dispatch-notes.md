### Added

- **Dispatch notes.** Repeatable session notes travel into dispatch specs and onward from task leads; Windows specs
  also flag the Microsoft Store `python3` alias and name the dispatch interpreter when the Store alias is the
  `python3` on PATH or exists in WindowsApps (also behind a `python3` shim). A task lead's `<dispatch>` forwards each
  note as one `--note=<value>` token, so a note starting with `-` survives.
