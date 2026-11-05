---
description: Delivery pipeline - task tier, plan validation, worker dispatch, review/QA verdicts and the READY_FOR_PR gate
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py pipeline:*)
argument-hint: "tier|validate|planner|dispatch|verdict|gate|cleanup [args]"
---
!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py pipeline $ARGUMENTS`
