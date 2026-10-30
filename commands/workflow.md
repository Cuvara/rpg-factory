---
description: Plan, dispatch, inspect, or report a dependency-aware factory workflow
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py workflow:*)
argument-hint: "plan|status|dispatch|report <spec> [options]"
---
!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py workflow $ARGUMENTS`
