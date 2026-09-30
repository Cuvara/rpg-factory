---
description: Show how Factory routes a change - lead skill, co-leads, legs, follow-ups, contracts, checks, gates, and why each skill was or was not chosen. Read-only.
argument-hint: "<repo> <path>... [--lead <skill>]   e.g. server backend/gateway/server/server.go"
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py:*)
---
## rpg-factory route (computed now, read-only)

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py route $ARGUMENTS`

Summarise the routing above for the user: lead and why, co-leads, follow-ups in other repos, touched contracts,
checks by tier, human gates. If it printed a usage error, show it and the accepted form. Do not start the task.
