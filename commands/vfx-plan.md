---
description: Plan a VFX effect through the five production steps (style profile, textures, recipe, capture, record) - the state of each step, what is missing, the lead and next steps. Read-only. e.g. /rpg-factory:vfx-plan --effect fire-burst --project C:/Game/Packages/vfx; /rpg-factory:vfx-plan Create a VFX for the fire burst
argument-hint: "[--json] [--effect <id>] [--root <authoring>] [--project <dir>] [--style <file>] [--spec <id|file>] [--asset <id|file>] [--gen-run <id>]... [--captures <dir>] [--lint <file>] <request>"
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py:*)
---
## rpg-factory VFX plan (computed now, read-only)

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py vfx-plan "$ARGUMENTS"`

Show the plan above to the user (status, effect, the five steps with their states, missing items, next steps).

- **NOT_VFX:** say it is not a VFX request, load no VFX skill, and continue with `rpg-factory:factory-core` only.
- **NEEDS_CONTEXT:** ask the user for exactly the items under Missing (nothing more) and stop. Never guess an effect
  id, authoring root, project path or style profile.
- **PLAN:** follow Next steps in order: invoke `rpg-factory:factory-core`, then the lead `rpg-factory:vfx`. A step
  that is NEEDS_APPROVAL waits for a person; never approve a profile, a gen-run or a record yourself.
- Never claim a capture, a lint or a render succeeded without its evidence; grade results with PASS, FAIL, BLOCKED,
  NOT_AVAILABLE, HUMAN_REQUIRED, SKIPPED, NOT_RUN or STALE.
- If it printed a usage error, show it and the accepted form.

Usage examples:

- `/rpg-factory:vfx-plan Create a VFX for the fire burst`
- `/rpg-factory:vfx-plan --json --effect fire-burst --project C:/Game/Packages/vfx`
- `/rpg-factory:vfx-plan --effect fire-burst --gen-run fire-sprite-001 --captures C:/Game/Captures`
