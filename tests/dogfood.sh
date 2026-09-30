#!/usr/bin/env bash
# Headless end-to-end dogfood: real Claude sessions with this plugin loaded from the local
# checkout, one per scenario, read-only prompts ("do not edit"). Asserts which Factory skills the
# model actually invoked (Skill tool calls in the stream-json transcript).
#
# Opt-in: it spends model tokens and takes minutes. Not part of run-all.sh.
# Tools are restricted to Skill/Read/Grep/Glob; the skills' own allowed-tools grant the
# factory-context / check scripts. Transcripts land in ${DOGFOOD_OUT:-/tmp/rpgf-dogfood}/.
#
# Usage: tests/dogfood.sh [--model sonnet] [scenario...]
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WS="${RPG_FACTORY_WORKSPACE:-/mnt/c/Workspaces/UnityIndie}"
OUT="${DOGFOOD_OUT:-/tmp/rpgf-dogfood}"; mkdir -p "$OUT"
model=sonnet
[ "${1:-}" = "--model" ] && { model="$2"; shift 2; }

declare -A PROMPT EXPECT
PROMPT[tick-knob]="Add a configurable tick-rate knob to the rpg-mmo-server C# game server and expose it as a metric."
EXPECT[tick-knob]="server-realtime"
PROMPT[wire-field]="Add a region string field to EnterWorldResponse in the wire protocol and propagate it to the Unity client."
EXPECT[wire-field]="wire-contract"
PROMPT[netcode-bump]="Move the Unity client IndieRPGMMOAdventure to Netcode v0.46.0."
EXPECT[netcode-bump]="pin-bump"
PROMPT[k8s-change]="Change the Kubernetes deployment of the gateway in rpg-mmo-server (backend/deploy/k8s/app/40-gateway.yaml) to add a readiness probe."
EXPECT[k8s-change]="server-ops"
PROMPT[nakama-rpc]="Add a new Nakama RPC party_kick to rpg-mmo-server and call it from the Unity client."
EXPECT[nakama-rpc]="server-services"
PROMPT[measure]="Measure whether the new replication importance weighting in rpg-mmo-server improves bytes per player per tick."
EXPECT[measure]="measure"
PROMPT[netcode-fix]="Fix a bug in the Netcode package where a pending TCP socket read ignores cancellation."
EXPECT[netcode-fix]="unity-package"
PROMPT[client-session]="Add a reconnect step to the Unity client's Nakama session flow in IndieRPGMMOAdventure."
EXPECT[client-session]="client-integration"

scenarios=("$@"); [ ${#scenarios[@]} -eq 0 ] && scenarios=("${!PROMPT[@]}")
run() {
  local n="$1"
  (cd "$WS" && timeout 900 claude --plugin-dir "$ROOT" -p "${PROMPT[$n]} Do NOT edit any file and do NOT run git commands that change state. Use the rpg-factory skills to plan it, then answer with: the lead skill, the files that must change, the validation (tier + command) and the human gates. Under 250 words." \
    --model "$model" --output-format stream-json --verbose --allowedTools "Skill,Read,Grep,Glob" </dev/null > "$OUT/$n.jsonl" 2>/dev/null)
}
for n in "${scenarios[@]}"; do run "$n" & done; wait

pass=0; fail=0
for n in "${scenarios[@]}"; do
  used=$(grep '^{' "$OUT/$n.jsonl" | jq -r 'select(.type=="assistant") | .message.content[] | select(.type=="tool_use" and .name=="Skill") | .input.skill' | sed 's/^rpg-factory://' | tr '\n' ' ')
  if grep -qw "factory-core" <<<"$used" && grep -qw "${EXPECT[$n]}" <<<"$used"; then
    pass=$((pass + 1)); echo "PASS  $n -> $used"
  else
    fail=$((fail + 1)); echo "FAIL  $n -> invoked: ${used:-none}; expected factory-core + ${EXPECT[$n]}"
  fi
done
echo "dogfood: $((pass + fail)) run, $pass passed, $fail failed (model $model; transcripts in $OUT)"
[ "$fail" -eq 0 ] && [ "$pass" -gt 0 ]
