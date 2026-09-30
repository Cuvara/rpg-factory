---
description: Factory health - install state (what this session loads), tripwire latches, registry validity, workspace and repos, state directories, tools, hooks. Read-only.
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py:*)
---
## rpg-factory doctor (read-only)

!`python3 -B "${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py" doctor`

Summarise problems first (install state not CURRENT, a latch, registry errors, missing repos or tools), each with
the fix the report names. A latch is cleared only by the user after reviewing the repos - never clear it yourself.
