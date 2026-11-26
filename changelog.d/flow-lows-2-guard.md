### Changed

- **QA.** The affected-suite selection of the workspace reader guard (`scripts/checks/workspace-readers.sh`) is verified
  against what the guard reads: it greps only `scripts/` and `tests/` under its root, so a change there (nested fixtures
  and the guard itself included) selects it, hooks and registry fragments select it as global inputs, and a skills or
  docs change does not. `tests/affected.test.sh` covers each of these cases.
- **Delivery.** `skills/factory-core/references/parallel-work.md` records that a message sent to an Orca dispatch that
  has already finished starts a follow-up worker: lead messages go only to the run of a live task lead, and a session's
  context goes into its start prompt.
