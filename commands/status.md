---
description: Factory status - pending cross-repo work (rollout stage, READY_TO_TAG, unpinned releases, CI pin drift), uncommitted work, embedded clones, validation evidence (current vs STALE), fetch freshness. Read-only.
argument-hint: "[--remote]"
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py:*)
---
## rpg-factory status (computed now, read-only)

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py status $ARGUMENTS`

Show the report above to the user. Lead with the **Pending** items (each names its owning skill) and any STALE
evidence or stale fetch. Do not run further commands, fetch, or change anything unless the user asks.
