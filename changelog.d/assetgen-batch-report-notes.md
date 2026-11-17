### Changed

- Asset generation: the spend budget follows one rule with and without a sheet. It counts generations made, so a discarded output still counts (a discard never refunds a generation) and a sliced sheet counts as one generation whether or not its cells were discarded. `budget` text says how many counted outputs are discarded (`N used (n outputs, d discarded + f failed attempts)`); `budget --json` and finalize's `budget` key add `discarded`, and `sheet_cells_discarded` next to `sheet_cells` when the run has a sheet.
- Asset generation: the `- Sheet:` line of `run.md` counts the cells that are still outputs and names the discarded ones separately (`-> N outputs, D discarded (sheet.json, discards.json)`).
- Asset generation: `style report` counts distinct selected anchors and selected anchor copies separately in the `tone.tolerance` suggestion (`--json`: `anchors` and `anchor_copies`; text: `<a> selected anchor(s) (distinct); <c> selected anchor copy/copies`), so one anchor selected by two runs is one anchor and two copies.

### Fixed

- Asset generation: the `--discard-qa-fail` branch of `finalize` no longer shadows the sheet `rows` parameter with its own list of discard rows; tests cover `--discard-qa-fail` together with `--rows` and `--cols`.
- Asset generation tests: the setup of the selected-anchor style report regression case fails loudly when its script fails, and the `- Fit:` line of `run.md` and the distinct-anchor counts have cases.
