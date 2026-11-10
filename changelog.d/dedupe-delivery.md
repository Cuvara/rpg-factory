### Changed

- **Delivery.** `skills/delivery/references/delivery.md` states each rule once and shrinks from 57813 bytes (main with
  the single verify flow) to 32727 bytes (the Orca lineage lesson lives only in section 4 "Orca visibility"; session
  release, "sub-sessions never commit" and the one-full-run-per-machine rule are stated once). The verdict, verify,
  fallback and model CLI details moved to `docs/pipeline-cli.md`, the tier command details of this repo to
  `tests/README.md`. `skills/delivery/SKILL.md` and `skills/factory-core/SKILL.md` point to delivery.md section 10
  instead of restating the flow steps. delivery.md now states that a plan task carries a `kind` for the "Which model"
  routing, and that the integration checkout itself gets the main checkout as its Orca lineage parent.

### Added

- **Tests.** `tests/delivery-generic.test.sh` keeps delivery.md at most 32768 bytes and the Orca lineage command only
  in section 4 "Orca visibility".

### Fixed

- **Tests.** `tests/delivery-generic.test.sh` expected key set now includes `subagents`, as `pipeline-defaults.json`
  has. The `tests/parallel-policy.test.sh` "rule moved out of section 5" mutation ends its range at the Orca-first
  rule again instead of deleting to the end of the file.
