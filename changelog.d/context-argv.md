### Fixed

- **Routing on a large diff.** `factory-context --json` no longer fails with `WinError 206` on Windows when a repo is a few hundred files ahead of its base: `scripts/lib/context.py` now sends the changed-file list, substitutions and tools to jq as one JSON object on stdin (registry through `--slurpfile`) instead of `--argjson` arguments, so the command line no longer grows with the path count. Routing output is unchanged.
