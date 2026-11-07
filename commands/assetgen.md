---
description: Asset generation data and commands (read-only) - list or show purposes, styles and ComfyUI workflow templates (core and game layer), resolve a spec, lint the data, print the Codex review command, list style drift of gen-runs and anchors
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py assetgen:*)
argument-hint: "list|show|resolve|lint|review-cmd|drift [args]"
---
!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py assetgen $ARGUMENTS`
