---
description: Factory health - install state (what this session loads), registry validity, workspace and repos, state directories, tools, hooks. Read-only.
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py:*)
---
## rpg-factory doctor (read-only)

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py doctor`

Summarise problems first (install state not CURRENT, registry errors, missing repos or tools), each with
the fix the report names.
