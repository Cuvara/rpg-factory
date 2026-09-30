#!/usr/bin/env bash
# factory-context.sh — live Factory snapshot of the RPG MMO workspace (read-only, persists nothing).
# Thin entry point; the engine is scripts/lib/context.py and the routing is scripts/lib/resolve.jq.
#
# Usage: factory-context.sh [--repo <key>|all] [--paths <path>...] [--base <ref>] [--json]
#                           [--lead <skill>] [--explain] [--full] [--toolchain] [--submodules]
#   --repo       default: the repo/worktree containing the cwd, else every registered repo
#   --paths      resolve ONLY these paths (single repo); everything after --paths is a path
#   --lead       override the lead skill (must be a candidate; exit 2 otherwise)
#   --explain    why each registered skill was or was not selected
#   --full       all rules, gates, known issues and tool versions
#   --toolchain  probe tool versions (dotnet.exe ~5 s on WSL)
#   --submodules scan uncommitted work inside submodules (client com.gdk.* ~9 s)
#   --json       machine-readable output
# Env: RPG_FACTORY_WORKSPACE  workspace root override.
set -uo pipefail
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
command -v jq >/dev/null 2>&1 || { echo "factory-context: jq is required" >&2; exit 3; }
CLAUDE_PLUGIN_ROOT="$PLUGIN_ROOT" exec python3 -B "$PLUGIN_ROOT/scripts/lib/context.py" "$@"
