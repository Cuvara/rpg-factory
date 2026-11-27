---
description: "Lint one VFX recipe (<Name>.vfxrecipe.json) against the project's vfx-style profile (read-only) - per-rule PASS/FAIL/WARN/NOT_AVAILABLE rows for timing, HDR intensity, palette, textures, shader, budgets, capture conditions, recipe hash and spec match. A relative --style or --spec that does not exist from the current directory resolves under the authoring repo. It writes nothing and refuses --out; --json prints the rpg-factory.vfx-lint/1 result. Exit 1 = a FAIL, 3 = an input is missing or unreadable. e.g. /rpg-factory:vfx-lint --style vfx/style/house.md --recipe FireBurst.vfxrecipe.json"
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py vfx-lint:*)
argument-hint: "[--json] --style <profile> --recipe <file> [--inspect <file>] [--stats <file>] [--spec <file>]"
---
!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py vfx-lint "$ARGUMENTS"`

Examples: `/rpg-factory:vfx-lint --style vfx/style/house.md --recipe FireBurst.vfxrecipe.json`,
`/rpg-factory:vfx-lint --json --style vfx/style/house.json --recipe FireBurst.vfxrecipe.json --stats Captures/stats.json`.
