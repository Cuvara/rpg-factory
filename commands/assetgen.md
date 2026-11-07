---
description: Asset generation data and commands (read-only) - list or show purposes, styles and ComfyUI workflow templates (core and game layer), resolve a spec, lint the data, print the Codex review command, list style drift of gen-runs and anchors. resolve prints a short summary (--verbose or --json for the source of every field); --run takes a run directory or a run id (<slug>-NNN, under <authoring>/assetgen/runs/)
disable-model-invocation: true
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py assetgen:*)
argument-hint: "list|show|resolve|lint|review-cmd|drift [args]"
---
!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-cmd.py assetgen $ARGUMENTS`
