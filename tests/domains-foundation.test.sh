#!/usr/bin/env bash
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
T="$(mktemp_win)"; trap 'rm -rf "$T"' EXIT
P="$T/plugin"; FW="$T/workspace"; FA="$FW/game-authoring"
mkdir -p "$P" "$FA" "$FW/rpg-mmo-server/backend" "$FW/IndieRPGMMOAdventure/ProjectSettings"
cp -R "$ROOT/." "$P/"
rm -rf "$P/.git"
touch "$FW/rpg-mmo-server/backend/TEAM.md" "$FW/IndieRPGMMOAdventure/ProjectSettings/ProjectVersion.txt"
git -C "$FA" init -q -b main
out=$(cd "$P" && CLAUDE_PLUGIN_ROOT="$P" RPG_FACTORY_WORKSPACE="$FW" bash "$P/scripts/factory-context.sh" --json --kind ui-spec 2>&1)
jq -e '.domain.id == "ui" and .domain.lead == "ui-ux"' <<<"$out" >/dev/null && echo 'PASS --kind ui-spec' || { echo "$out"; exit 1; }
out=$(cd "$P" && CLAUDE_PLUGIN_ROOT="$P" RPG_FACTORY_WORKSPACE="$FW" bash "$P/scripts/factory-context.sh" --json --kind art2d-asset 2>&1)
jq -e '.domain.id == "art2d" and .domain.lead == "art-2d"' <<<"$out" >/dev/null && echo 'PASS --kind art2d-asset' || { echo "$out"; exit 1; }
out=$(cd "$P" && CLAUDE_PLUGIN_ROOT="$P" RPG_FACTORY_WORKSPACE="$FW" bash "$P/scripts/factory-context.sh" --json --kind art3d-asset 2>&1)
jq -e '.domain.id == "art3d" and .domain.lead == "art-3d"' <<<"$out" >/dev/null && echo 'PASS --kind art3d-asset' || { echo "$out"; exit 1; }
out=$(cd "$P" && CLAUDE_PLUGIN_ROOT="$P" RPG_FACTORY_WORKSPACE="$FW" bash "$P/scripts/factory-context.sh" --json --kind vfx-spec 2>&1)
jq -e '.domain.id == "vfx" and .domain.lead == "vfx"' <<<"$out" >/dev/null && echo 'PASS --kind vfx-spec' || { echo "$out"; exit 1; }

for spec in "ui:ui-ux" "art2d:art-2d" "art3d:art-3d" "vfx:vfx"; do
  IFS=: read -r domain skill <<<"$spec"
  out=$(cd "$P" && CLAUDE_PLUGIN_ROOT="$P" RPG_FACTORY_WORKSPACE="$FW" bash "$P/scripts/factory-context.sh" --json --domain "$domain" 2>&1)
  jq -e --arg d "$domain" --arg s "$skill" '.domain.id == $d and .domain.lead == $s' <<<"$out" >/dev/null && echo "PASS --domain $domain" || { echo "$out"; exit 1; }
done
python3 - "$ROOT/registry.json" "$ROOT/scripts/lib/context.py" <<'PY'
import importlib.util,json,sys
spec=importlib.util.spec_from_file_location('context',sys.argv[2]); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
reg=json.load(open(sys.argv[1],encoding='utf-8')); order,cycle=mod.handoff_graph(reg,'design')
assert cycle is None, cycle
pos={d:i for i,d in enumerate(order)}
assert pos['design'] < pos['ui'] < pos['art2d'] < pos['engineering'], order
assert pos['art3d'] < pos['vfx'] < pos['engineering'], order
print('PASS handoff graph orders all requested domain paths without cycles')
PY
