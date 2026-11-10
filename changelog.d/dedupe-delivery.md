### Changed

- **Delivery.** `skills/delivery/references/delivery.md` states each rule once and shrinks from 56018 to 32495 bytes (the
  Orca lineage lesson lives only in section 4 "Orca visibility"; session release, "sub-sessions never commit" and the
  one-full-run-per-machine rule are stated once). The verdict and model CLI details moved to `docs/pipeline-cli.md`, the tier
  command details of this repo to `tests/README.md`. `skills/delivery/SKILL.md` and `skills/factory-core/SKILL.md` point to
  delivery.md section 10 instead of restating the flow steps.

### Fixed

- **Tests.** `tests/delivery-generic.test.sh` expected key set now includes `subagents`, as `pipeline-defaults.json` has. New
  assertions keep delivery.md at most 32768 bytes and the Orca lineage command only in section 4 "Orca visibility".
