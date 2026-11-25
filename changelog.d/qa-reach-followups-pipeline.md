### Added

- **Pipeline status slots.** `factory-pipeline.py status --json` has a `slots` field (in
  `docs/schemas/pipeline-status.schema.json`): one entry per test slot held by a run in one of the plan's checkouts,
  with slot, pid, winpid, alive, checkout, started and the holder's last progress (check, result, passed, failed,
  updated, age_seconds; null before the first one), the same entries as `cleanup --json`. The stderr `Slots:` lines and
  the text output are unchanged; status still never stops a holder.

### Fixed

- **Affected cases base.** The dispatch and QA case lists call `tests/affected.py cases --base <base>` with the base
  they diff against, so the per-symbol reach applies whenever the changed files are the diff from that base, not only
  when that base is affected.py's default.
- **Pipeline case map.** A one-function `scripts/assetgen/assetgen.py` change no longer selects every case group of
  `tests/pipeline.test.sh` (26) but 4: the files its import closure reaches are mapped to the groups that use them
  (`scripts/checks/domains/assetgen.py` to model-routing and recorded-implementer, `scripts/factory-cmd.py` to
  dogfood, `tests/fixtures/assetgen/*.py` to gate-merge).
