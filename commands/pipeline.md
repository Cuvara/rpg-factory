---
description: Delivery pipeline - task tier, plan validation, worker dispatch, review/QA verdicts, the READY_FOR_PR gate and run status
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py pipeline:*)
argument-hint: "tier|validate|subplan|planner|dispatch|verdict|gate|cleanup|status [args] (planner/dispatch: --grade light|standard|heavy, --model ID, --effort LEVEL)"
---
!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py pipeline $ARGUMENTS`

Every dispatch carries a model and effort from the registry `pipeline.models` policy (`lib/model_policy.py`; policy:
`skills/delivery/references/delivery.md` section 10, "Model choice"; flags: `docs/pipeline-cli.md`). `planner` and `dispatch` accept `--grade light|standard|heavy`,
`--model ID` and `--effort LEVEL`; a value outside the scope exits 2. `verdict` accepts optional `--model` and `--effort`.
