---
description: Delivery pipeline - task tier, plan validation, worker dispatch, review/QA verdicts, the READY_FOR_PR gate and run status
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py pipeline:*)
argument-hint: "tier|validate|planner|dispatch|verdict|gate|cleanup|status [args]"
---
!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py pipeline $ARGUMENTS`
