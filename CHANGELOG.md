# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.1.0] - 2026-09-30

### Added
- Factory Core v1 plugin (`rpg-factory`) with single-plugin marketplace.
- `factory-core` skill: workflow (scope, baseline, branch, plan, implement, obligations,
  validate, verify, review, report), live snapshot injection, global rules from the registry,
  and references for repos, validation, git safety, report template and skill contract.
- `registry.json` (27 modules across rpg-mmo-server and IndieRPGMMOAdventure) with
  `docs/registry.schema.json`.
- `scripts/factory-context.sh`: read-only live snapshot (branch, working tree, branch diff,
  submodules, touched modules and dependents, checks by tier, obligations, toolchain with
  `dotnet` -> `dotnet.exe` fallback, Unity MCP reachability); `--paths` and `--json` modes.
- `scripts/git-guard.py` PreToolUse(Bash) hook asking before destructive or high-impact git.
- `scripts/check-registry.sh`, `scripts/checks/unity-package-pins.py`.
- `tests/run-all.sh`, `tests/git-guard.test.sh`, and three `claude plugin eval` smoke cases.
