### Fixed

- **Snapshot views.** `factory-context.sh --domain <id>` and `--domain <id> --graph` now print the same `Language:` line
  as the default snapshot (text) and carry a `language` key (JSON); one helper, `language_line()` in
  `scripts/lib/snapshot_render.py`, renders it for every view.
