### Added

- **Agents.** New read-only plugin agent `factory-explorer` (`agents/factory-explorer.md`): a code locator for Factory
  sessions that returns a `path:line` table and a short conclusion (at most 200 words). Tools are limited to Read, Grep,
  Glob and Bash, the model is `sonnet`, and it never edits files, runs git writes, calls Orca or the pipeline dispatch
  and verdict, or spawns agents.
