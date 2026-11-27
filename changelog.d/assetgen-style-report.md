### Added

- **asset-gen.** `assetgen.py style report --authoring DIR [--style ID] [--json]` is a read-only report of how a game
  style performs: per style and family, the tone (mean luminance and saturation) and palette (share within
  `max_distance` and the distance each output needs) spread over the outputs of the approved runs, the WARN and FAIL rate
  of each `style-*` QA row over the runs' `qa.json`, the rejections by reason, and suggested thresholds
  (`palette.max_distance`, `tone.tolerance`) printed only together with the numbers behind them and marked as a
  suggestion that is not applied. It writes nothing, is deterministic (byte-identical output for the same data) and exits
  0 when the report is printed. It is also a read-only verb of `/rpg-factory:assetgen`. The logic lives in
  `scripts/assetgen/style_report.py`.
