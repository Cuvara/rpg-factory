---
description: Factory domains - every registered domain (lead, repos, artifact counts), or one domain in detail (artifact kinds, quality and human gates, handoffs, artifacts by status, stale upstreams, FAIL and HUMAN_REQUIRED artifacts, next steps). Read-only.
argument-hint: "[<domain>] [--json]"
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py:*)
---
## rpg-factory domain (computed now, read-only)

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py domain $ARGUMENTS`

Show the report above to the user. For one domain, lead with its lead skill, then any stale, FAIL or HUMAN_REQUIRED
artifacts, then the **Next** lines exactly as printed. A HUMAN_REQUIRED artifact needs a person; never approve it
yourself. If it printed a usage error, show the known domains it lists. Do not start the work or change anything
unless the user asks.
