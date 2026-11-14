### Added

- **asset-gen.** `assetgen.py style bump --authoring DIR --id ID [--list-only] [--json]` prepares version N+1 of an
  active game style. It writes a draft copy at `assetgen/styles/<ID>/versions/<N+1>.json` (the raw style with `version`
  N+1 and `status: draft`; not a layer file, so resolve, selection, drift and the active hash do not change) and never
  edits an active file. The report names every anchor, run and rejection that needs re-approval under the new version:
  valid active anchors whose PNG matches `image_sha256` are carried as NEW `proposed` anchors (`<id>-v<N+1>`, a byte copy
  of the PNG, `approved_by` null, never `active`), other version-N anchors, the runs of version N and the rejections of
  version N are listed with the reason. The assetgen `artifact-quality` check runs before and after the writes: a new
  FAIL, or a check that cannot run, removes the carried anchors and limits the verb to listing, said plainly in the
  output. A style that is a draft, deprecated, core-only or without a version, or an existing draft file, is refused
  (exit 1, nothing written). `--list-only` writes nothing. A person activates the draft and the proposed anchors. The
  logic lives in `scripts/assetgen/style_cmd.py`.

### Changed

- **asset-gen.** `assetgen.py` hooks `style derive` up through the return value of `style_cmd.add_parsers` instead of
  reading argparse private attributes (`_actions`, `_SubParsersAction`); `style derive` behaves as before.
