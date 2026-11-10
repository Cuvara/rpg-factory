### Added

- **Pipeline.** Tier XS for a tiny prose-only change (registry `pipeline.tiers.XS`: every path prose, at most 3 files
  and 40 changed lines, no contract or generated path). `tier` prints `Tier: XS` when it applies and `above XS:` with
  the reasons otherwise (`tier --plan` counts the changed lines of the checkout). `validate` accepts a one-task XS plan
  and rejects a path that is not prose, a second task or too many paths. `dispatch --phase lead` on an XS task starts
  no task lead: it prints the run lead's own steps (edit and commit on the plan topic branch, one cross-model review,
  the task tier command, the `tier XS: lead ran task suites` QA verdict, gate); `--phase implement` is refused. Its
  review reads the topic checkout and pairs against the run lead's model. The gate accepts the XS review plus the
  lead-run QA and blocks when the committed diff is above the XS thresholds.

### Fixed

- **Delivery.** `delivery.md` is back under its 32 KiB size cap (`tests/delivery-generic.test.sh`).
