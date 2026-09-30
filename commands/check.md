---
description: Run the Factory checks for a change (fast tier, graded PASS/FAIL/BLOCKED/NOT_AVAILABLE/HUMAN_REQUIRED with evidence), or with --status grade stored evidence against the current tree (STALE/NOT_RUN) without running anything.
argument-hint: "<repo> [<path>...] [--status]"
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py:*)
---
## rpg-factory check

!`python3 -B "${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py" check $ARGUMENTS`

Report the table above verbatim (states come from the runner, never from you). Name every check that is not PASS
and what it needs (a fix, a tool, a person). Do not rerun or change anything unless the user asks.
