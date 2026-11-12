### Added

- **asset-gen.** `assetgen.py finalize --run <run> [--force] [--json]`: after `fetch_outputs` it runs defringe (only for a
  purpose with `qa.alpha` required), embed and qa in that fixed order, so embed can no longer be skipped before qa, and
  stops at the first FAIL naming the step. Exit codes follow qa (0 PASS, 1 FAIL, 3 NOT_AVAILABLE). It refuses an approved
  run and a run without `spec.json`, outputs or `workflow.ui.json` before writing anything. A second finalize on an
  unchanged run is idempotent (defringe is skipped while `defringe.json` still matches the output pixels), outputs that
  `qa.json` or an image review already bind stop defringe unless `--force`, and the image reviews it made stale are
  printed. The qa verb's logic moved into a function both verbs call; defringe, embed and qa keep their contracts.
