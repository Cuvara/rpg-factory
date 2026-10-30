---
description: Plan a review of a UI screen or Figma import for architecture, layout, theme and runtime issues, loading only the validation skills it needs. Read-only. e.g. /rpg-factory:ui-review Review this screen for architecture, layout, theme and runtime issues
argument-hint: "[--json] [--project <Unity project>] [--uitoolkit-ref <ref>] <request>"
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py:*)
---
## rpg-factory UI plan - review (computed now, read-only)

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py ui-review "$ARGUMENTS"`

Show the plan above to the user (status, intent, skills, lead, missing items, components, next steps).

- **NOT_UI:** say it is not a UI request, load no UI skill, and continue with `rpg-factory:factory-core` only.
- **NEEDS_CONTEXT:** ask the user for exactly the items under Missing (nothing more) and stop. Never guess a Figma
  file key, node id or project path.
- **PLAN:** follow Next steps in order: invoke `rpg-factory:factory-core` with the stated mode and route, then the
  lead, then ONLY the listed UI skills in the listed order. Do not load the skills under "Not loaded".
- Component choices come from the catalog in the plan (reuse > configure > compose > missing); a `missing` need is
  a decision for the user, not something to build silently.
- Never claim an import, a test or a render succeeded without the evidence the skills require; grade results with
  PASS, FAIL, BLOCKED, NOT_AVAILABLE, HUMAN_REQUIRED, SKIPPED, NOT_RUN or STALE.
- If it printed a usage error, show it and the accepted form.

Usage examples:

- `/rpg-factory:ui-review Review this screen for architecture, layout, theme and runtime issues`
- `/rpg-factory:ui-review Review the import of https://www.figma.com/design/<key>/<name>?node-id=1-2`
- `/rpg-factory:ui-review Why does the inventory popup crash on close`
