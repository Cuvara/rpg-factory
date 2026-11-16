### Added

- **Asset generation.** `promote-anchor --external --origin --rights-note` proposes an anchor from existing art with an `external_source` record containing its image sha256, origin, rights note and attester. A person activates the anchor and attests its source; `gen-run-style` fails agent-attested or unattested external anchors. Anchors from gen-runs continue to work as before.
