### Added

- **asset-gen.** `assetgen.py style init --id ID --extends CORE [--family FAM=STYLE]... --authoring DIR [--title T] [--json]`
  writes a draft game style (`assetgen/styles/<id>.json`: extends the core style, version 1, status draft) and a valid
  `assetgen/project.json` skeleton, plus a draft stub for each family style that does not exist yet. It never overwrites
  a file (exit 1, nothing written), refuses a family style that is a core style or a game style that does not extend the
  project style, and never edits core data. A draft style raises no lint WARN; once it is active, lint WARNs until a
  structured field (`palette.colors`, `tone`, `canvas`, `outline.edge_darkness`) is set. The logic lives in
  `scripts/assetgen/style_cmd.py`.
