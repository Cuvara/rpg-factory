### Added

- `assetgen.py resolve --profile api-only|local-4gb|local-8gb|auto` picks the template per purpose and hardware profile from `scripts/assetgen/data/template-profiles.json` (a game layer may override entries), refuses a template whose requires profile is above the chosen one, and records `spec.profile`; `auto` reads the profile saved from `comfy-desktop-setup.py --check --json`, else api-only; without `--profile` nothing changes. UNTESTED on RTX 5060: nothing was generated or measured; the user will test on the RTX 5060 8 GB machine after merge.
