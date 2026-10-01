#!/usr/bin/env bash
# Headless end-to-end dogfood: real Claude sessions, one per scenario, read-only prompts ("do not
# edit"). Asserts which Factory skills the model actually invoked (Skill tool calls in the
# stream-json transcript) and which skills its answer hands work to.
#
#   --installed   use the INSTALLED plugin (no --plugin-dir) and assert the session loaded
#                 rpg-factory@rpg-factory (not @inline) at the source version from the install's
#                 load path (directory marketplace: the marketplace dir in place; otherwise the
#                 version-keyed cache copy), and that the snapshot header says
#                 "runtime <version> (installed ...)" with install state CURRENT.
#   (default)     load the working tree with --plugin-dir (development).
#
# Opt-in: it spends model tokens and takes minutes. Not part of run-all.sh.
# Tools are restricted to Skill/Read/Grep/Glob; the skills' own allowed-tools grant the
# factory-context / status / check scripts. Transcripts land in ${DOGFOOD_OUT:-/tmp/rpgf-dogfood}/.
#
# Usage: tests/dogfood.sh [--installed] [--model sonnet] [scenario...]
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WS="${RPG_FACTORY_WORKSPACE:-/mnt/c/Workspaces/UnityIndie}"
OUT="${DOGFOOD_OUT:-/tmp/rpgf-dogfood}"; mkdir -p "$OUT"
model=sonnet; installed=false
while [ $# -gt 0 ]; do case "$1" in
  --installed) installed=true; shift;;
  --model) model="$2"; shift 2;;
  *) break;;
esac; done
VERSION=$(jq -r .version "$ROOT/.claude-plugin/plugin.json")
LOADS=$(python3 -B "$ROOT/scripts/install-status.py" --json 2>/dev/null | jq -r '.installed.loads_from // empty')

# EXPECT: skills that must be invoked (space = all of, a|b = either).
# HANDOFF: skills the final answer must name as later / follow-up work (space = all of).
# MODE:    the Factory mode the session must declare (factory-context.sh --mode <m>), if set.
# TOOLRUN: a script the session must run (e.g. run-checks.py), if set.
# SHOWS:   text the transcript must contain (command output), if set; RAW scenarios send the prompt as-is.
declare -A PROMPT EXPECT HANDOFF MODE TOOLRUN SHOWS RAW
PROMPT[realtime-knob]="Add a configurable GAMESERVER_ tick-rate knob to the rpg-mmo-server C# game server and expose the value in force on /status."
EXPECT[realtime-knob]="server-realtime"; HANDOFF[realtime-knob]=""
PROMPT[nakama-rpc]="Add a new Nakama RPC party_kick to rpg-mmo-server and call it from the Unity client's party service."
EXPECT[nakama-rpc]="server-services"; HANDOFF[nakama-rpc]="client-integration"
PROMPT[wire-field]="Add a region string field to EnterWorldResponse in the wire protocol and propagate it to the Unity client."
EXPECT[wire-field]="wire-contract"; HANDOFF[wire-field]="unity-package pin-bump"
PROMPT[netcode-change]="Change the Netcode package's client reconnect backoff, then make the Unity client use it."
EXPECT[netcode-change]="unity-package|pin-bump"; HANDOFF[netcode-change]="pin-bump"
PROMPT[package-propagation]="UIToolkit has a new released tag; propagate it to the Unity client IndieRPGMMOAdventure."
EXPECT[package-propagation]="pin-bump"; HANDOFF[package-propagation]=""
PROMPT[client-integration]="Add a reconnect step to the Unity client's Nakama session flow in IndieRPGMMOAdventure."
EXPECT[client-integration]="client-integration"; HANDOFF[client-integration]=""
PROMPT[k8s]="Add a readiness probe to the gateway Kubernetes deployment in rpg-mmo-server (backend/deploy/k8s/app/)."
EXPECT[k8s]="server-ops"; HANDOFF[k8s]=""
PROMPT[benchmark]="Benchmark whether the replication importance weighting in rpg-mmo-server improves bytes per player per tick."
EXPECT[benchmark]="measure"; HANDOFF[benchmark]=""

PROMPT[analyze-only]="Analyze only - do not plan or change anything: what would changing the gateway's redirect JSON (backend/gateway) in rpg-mmo-server touch?"
EXPECT[analyze-only]="server-services|wire-contract"; HANDOFF[analyze-only]=""; MODE[analyze-only]="analyze"
PROMPT[plan-only]="Plan only, do not implement: add a GAMESERVER_ knob for the AOI radius to the rpg-mmo-server C# game server."
EXPECT[plan-only]="server-realtime"; HANDOFF[plan-only]=""; MODE[plan-only]="plan"
PROMPT[validate-only]="Validate only, change nothing: does the rpg-mmo-server gateway module (backend/gateway/server/server.go) pass its Factory checks right now?"
EXPECT[validate-only]=""; HANDOFF[validate-only]=""; MODE[validate-only]="validate"; TOOLRUN[validate-only]="run-checks.py"
# tech skills: the lead must be the repo skill AND the session must load the tech skill the routing line names,
# and the answer must apply the tool fallback the snapshot reports (C# LSP MISSING, Unity MCP DOWN)
PROMPT[tech-dotnet]="Analyze only: in the rpg-mmo-server C# game server, how do I run only the SnapshotAllocationTests class, what does it guard, and how do I find every caller of EcsWorld.UpdateComponents before changing it?"
EXPECT[tech-dotnet]="server-realtime dotnet-gameserver"; HANDOFF[tech-dotnet]=""; SHOWS[tech-dotnet]="grep"
PROMPT[tech-go]="Analyze only: in the rpg-mmo-server Go gateway, how do I run one gateway test with the race detector, and can a green integration_test run hide dotnet interop tests that never ran?"
EXPECT[tech-go]="server-services go-backend"; HANDOFF[tech-go]=""; SHOWS[tech-go]="SKIP|skip"
PROMPT[tech-unity]="Analyze only: how do I run just the HudEcsLifecycleTests EditMode tests of the IndieRPGMMOAdventure Unity client right now, and why can they not be PlayMode tests?"
EXPECT[tech-unity]="client-integration unity-client-tech"; HANDOFF[tech-unity]=""; SHOWS[tech-unity]="HUMAN_REQUIRED|not reachable|Editor is closed|Editor closed"
PROMPT[cmd-status]="/rpg-factory:status"; RAW[cmd-status]=1; EXPECT[cmd-status]=""; SHOWS[cmd-status]="[unity-package]|unity-package"
PROMPT[cmd-route]="/rpg-factory:route server backend/deploy/k8s/app/40-gateway.yaml"; RAW[cmd-route]=1; EXPECT[cmd-route]=""; SHOWS[cmd-route]="transport-security"

scenarios=("$@"); [ ${#scenarios[@]} -eq 0 ] && scenarios=(realtime-knob nakama-rpc wire-field netcode-change package-propagation client-integration k8s benchmark analyze-only plan-only validate-only cmd-status cmd-route tech-dotnet tech-go tech-unity)
run() {
  local n="$1" pd=()
  $installed || pd=(--plugin-dir "$ROOT")
  local prompt="${PROMPT[$n]} Do NOT edit any file and do NOT run git commands that change state. Use the rpg-factory skills, then answer with: the lead skill, co-leads and follow-up skills (by name), the files that must change, the validation (tier + command) and the human gates. Under 250 words."
  [ -n "${RAW[$n]:-}" ] && prompt="${PROMPT[$n]}"
  (cd "$WS" && timeout 900 claude "${pd[@]}" -p "$prompt" \
    --model "$model" --output-format stream-json --verbose --allowedTools "Skill,Read,Grep,Glob" </dev/null > "$OUT/$n.jsonl" 2>/dev/null)
  true
}
start=$(date +%s)
for n in "${scenarios[@]}"; do run "$n" & done; wait
elapsed=$(( $(date +%s) - start ))

pass=0; fail=0
printf '%-20s | %-26s | %-28s | %-40s | %s\n' scenario "loaded" "expected" "invoked" result
for n in "${scenarios[@]}"; do
  f="$OUT/$n.jsonl"; why=""
  loaded=$(grep '^{' "$f" | jq -r 'select(.type=="system" and .subtype=="init") | .plugins[]? | select(.name=="rpg-factory") | "\(.version) \(.source)|\(.path)"' | head -1)
  lv=${loaded%% *}; src=${loaded#* }; src=${src%%|*}; path=${loaded#*|}
  if $installed; then
    [ "$src" = "rpg-factory@rpg-factory" ] || why+="source=$src; "
    [ "$(realpath -m "$path")" = "$(realpath -m "$LOADS")" ] || why+="path=$path (install loads $LOADS); "
    [ "$lv" = "$VERSION" ] || why+="version=$lv; "
    [ -n "${RAW[$n]:-}" ] || grep -qE "rpg-factory runtime $VERSION \\(installed[^)]*\\), installed $VERSION, source $VERSION - install state \\*\\*CURRENT" "$f" || why+="snapshot runtime line missing/not CURRENT; "
  fi
  used=$(grep '^{' "$f" | jq -r 'select(.type=="assistant") | .message.content[] | select(.type=="tool_use" and .name=="Skill") | .input.skill' | sed 's/^rpg-factory://' | tr '\n' ' ')
  answer=$(grep '^{' "$f" | jq -r 'select(.type=="result") | .result // ""')
  [ -n "${RAW[$n]:-}" ] || grep -qw "factory-core" <<<"$used" || why+="factory-core not invoked; "
  cmds=$(grep '^{' "$f" | jq -r 'select(.type=="assistant") | .message.content[] | select(.type=="tool_use" and (.name=="Bash" or .name=="PowerShell")) | .input.command')
  if [ -n "${MODE[$n]:-}" ]; then  # declared via --mode, or recorded by the Skill hook in the session's state
    sid=$(grep '^{' "$f" | jq -r 'select(.type=="system" and .subtype=="init") | .session_id' | head -1)
    recorded=$(cat "/tmp/rpg-factory/$sid/MODE" 2>/dev/null)
    { grep -qE -- "--mode[= ]${MODE[$n]}\b" <<<"$cmds" || [ "$recorded" = "${MODE[$n]}" ]; } || why+="mode ${MODE[$n]} not declared (recorded: ${recorded:-none}); "
  fi
  if [ -n "${TOOLRUN[$n]:-}" ]; then grep -q "${TOOLRUN[$n]}" <<<"$cmds" || why+="${TOOLRUN[$n]} not run; "; fi
  if [ -n "${SHOWS[$n]:-}" ]; then  # command output is injected, not logged: grade the answer built from it
    hit=false; IFS='|' read -ra alts <<<"${SHOWS[$n]}"
    for a in "${alts[@]}"; do grep -qF -- "$a" <<<"$answer" && hit=true; done
    $hit || why+="answer does not reflect the command output (${SHOWS[$n]}); "
  fi
  writes=$(grep '^{' "$f" | jq -r 'select(.type=="assistant") | .message.content[] | select(.type=="tool_use" and (.name=="Write" or .name=="Edit" or .name=="MultiEdit")) | .name' | wc -l)
  [ "$writes" -eq 0 ] || why+="$writes file write tool call(s); "
  for e in ${EXPECT[$n]}; do
    hit=false; IFS='|' read -ra alts <<<"$e"
    for a in "${alts[@]}"; do grep -qw "$a" <<<"$used" && hit=true; done
    $hit || why+="expected $e not invoked; "
  done
  # a tech skill is supporting context: some owning (repo/cross-repo) skill must be invoked before it
  first_tech=""; owner_before=false
  for u in $used; do
    k=$(jq -r --arg s "$u" '.skills[$s].kind // ""' "$ROOT/registry.json")
    if [ "$k" = "tech" ]; then first_tech=$u; break; fi
    case "$k" in repo|cross-repo) owner_before=true;; esac
  done
  [ -z "$first_tech" ] || $owner_before || why+="tech skill $first_tech invoked before any owning skill; "
  for h in ${HANDOFF[$n]:-}; do grep -qw "$h" <<<"$used $answer" || why+="hand-off $h not named; "; done
  if [ -z "$why" ]; then pass=$((pass + 1)); r=PASS; else fail=$((fail + 1)); r="FAIL: $why"; fi
  printf '%-20s | %-26s | %-28s | %-40s | %s\n' "$n" "${lv:-?} ${src:-?}" "${EXPECT[$n]}${HANDOFF[$n]:+ > ${HANDOFF[$n]:-}}" "${used:-none}" "$r"
done
echo "dogfood: $((pass + fail)) run, $pass passed, $fail failed (model $model; $($installed && echo "installed $VERSION" || echo plugin-dir); ${elapsed}s wall, parallel; transcripts in $OUT)"
[ "$fail" -eq 0 ] && [ "$pass" -gt 0 ]
