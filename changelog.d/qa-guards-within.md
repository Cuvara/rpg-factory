### Changed

- **Task QA.** Scoped task QA (`tests/run-all.sh --affected --base <b> --within <suites>`) also runs the English-only and
  portable-paths enforcement lines when the change reaches them, so a breach fails task QA instead of only the merged tree.
- **Affected selection.** A change to `scripts/checks/netcode-headless.sh` now selects `tests/run-all-parallel.test.sh`
  (the netcode evidence prune case) through an explicit `EXTRA` mapping, not through a literal path mention.
