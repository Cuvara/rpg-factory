### Added

- **Pipeline gate.** `factory-pipeline.py gate` now also checks each run lead file (plan, report, backlog) on the integration HEAD with the English-only rule of `scripts/lib/english.py`, honouring `tests/fixtures/english-allow.txt` from the same HEAD, and blocks with the file, the first offending line number and the rule, so a non-English line is caught before the PR and not only by CI. `status` shows the same blockers as `gate blocker:` notes.
