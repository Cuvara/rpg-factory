#!/usr/bin/env bash
# Headless end-to-end dogfood: read-only routing sessions plus opt-in isolated write sessions.
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
# Usage: tests/dogfood.sh [--write|--all] [--installed] [--model sonnet] [scenario...]
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
WS="${RPG_FACTORY_WORKSPACE:-/mnt/c/Workspaces/UnityIndie}"
OUT="${DOGFOOD_OUT:-/tmp/rpgf-dogfood}"; mkdir -p "$OUT"
model=sonnet; installed=false; write_mode=false; all_mode=false
while [ $# -gt 0 ]; do case "$1" in
  --installed) installed=true; shift;;
  --write) write_mode=true; shift;;
  --all) all_mode=true; shift;;
  --model) model="$2"; shift 2;;
  *) break;;
esac; done
if $all_mode; then write_mode=true; fi
scenarios=("$@")
VERSION=$(jq -r .version "$ROOT/.claude-plugin/plugin.json")
LOADS=$(python3 -B "$ROOT/scripts/install-status.py" --json 2>/dev/null | jq -r '.installed.loads_from // empty')

# EXPECT: skills that must be invoked (space = all of, a|b = either).
# HANDOFF: skills the final answer must name as later / follow-up work (space = all of).
# MODE:    the Factory mode the session must declare (factory-context.sh --mode <m>), if set.
# TOOLRUN: a script the session must run (e.g. run-checks.py), if set.
# SHOWS:   text the transcript must contain (command output), if set; RAW scenarios send the prompt as-is.
declare -A PROMPT EXPECT HANDOFF MODE TOOLRUN SHOWS RAW CORRECTS
PROMPT[design-feature-spec]="Draft a feature spec for a crafting system with --domain design. Do not create files in product repos; the authoring repo may be absent."
PROMPT[ui-foundation]="Plan a settings screen flow for a crafting feature; route and draft only a UI flow artifact, with no production tooling."
PROMPT[art2d-foundation]="Draft a 2D art brief for an icon set referenced by a UI spec; include delivery metadata and no generated art."
PROMPT[art3d-foundation]="Draft a 3D art brief for a crafting workstation prop; describe handoffs to VFX and engineering without generating assets."
PROMPT[vfx-foundation]="Draft a VFX specification for a crafting completion effect; hand off implementation intent to engineering without creating effect assets."
EXPECT[design-feature-spec]="factory-core game-design"; HANDOFF[design-feature-spec]=""
EXPECT[ui-foundation]="ui-ux"; HANDOFF[ui-foundation]=""
EXPECT[art2d-foundation]="art-2d"; HANDOFF[art2d-foundation]=""
EXPECT[art3d-foundation]="art-3d"; HANDOFF[art3d-foundation]=""
EXPECT[vfx-foundation]="vfx"; HANDOFF[vfx-foundation]=""
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
PROMPT[tech-dots]="Analyze only: in the UnityDots package, should a new projectile cleanup system use Schedule or ScheduleParallel, and how do I prove in an EditMode test that it was installed into the right system group?"
EXPECT[tech-dots]="unity-package unity-dots"; HANDOFF[tech-dots]=""; SHOWS[tech-dots]="SystemOrderVerifier|ParallelScheduling"
PROMPT[tech-netcode]="Analyze only: in the Netcode package, why can a client running at 20 fps see snapshots up to 50 ms late before interpolation even starts, and which headless tests cover the KCP session?"
EXPECT[tech-netcode]="unity-package netcode-client"; HANDOFF[tech-netcode]=""; SHOWS[tech-netcode]="KcpTransport|PlayerLoop|frame"
# a tech skill requested before factory-core on purpose: the Skill hook loads factory-core instead (never
# blocks), and the session must still route to the lead, load go-backend and finish
PROMPT[tech-first]="Your very first action: invoke the Skill tool with skill rpg-factory:go-backend. Then, analyze only: in the rpg-mmo-server Go gateway, how do I run one gateway test with the race detector?"
EXPECT[tech-first]="server-services go-backend"; HANDOFF[tech-first]=""; CORRECTS[tech-first]="go-backend"; SHOWS[tech-first]="-race"
PROMPT[cmd-status]="/rpg-factory:status"; RAW[cmd-status]=1; EXPECT[cmd-status]=""; SHOWS[cmd-status]="[unity-package]|unity-package"
PROMPT[cmd-route]="/rpg-factory:route server backend/deploy/k8s/app/40-gateway.yaml"; RAW[cmd-route]=1; EXPECT[cmd-route]=""; SHOWS[cmd-route]="transport-security"

# WRITE scenarios use an isolated game-authoring repository per session. The helper creates
# registry-routed folders, commits the empty layout, and grades disk state plus transcript.
declare -A W_PROMPT W_EXPECT W_KINDS W_DOMAIN W_PLAN W_SEEDS
W_PROMPT[design-write]="Create a game concept and a combat gameplay system for a small action RPG. Include one proposed damage number, clearly labelled as a proposal pending approval or TBD, never a binding value. Write the artifacts, run Factory artifact lint and the design quality checks, and report their IDs, revisions and human gates."
W_EXPECT[design-write]="game-design"; W_KINDS[design-write]="game-concept gameplay-system"; W_DOMAIN[design-write]=design
W_PROMPT[ui-write]="Using the supplied feature spec, create an inventory screen spec, a component spec and a UI handoff. Write the artifacts, run Factory artifact lint and UI quality checks, then report IDs, revisions and human gates."
W_EXPECT[ui-write]="ui-ux"; W_KINDS[ui-write]="screen-spec component-spec ui-handoff"; W_DOMAIN[ui-write]=ui; W_SEEDS[ui-write]=feature-spec
W_PROMPT[art2d-write]="Create 2D art direction and an asset spec for a coherent inventory icon set. No image generation is needed; omit any runtime export unless a real file exists. Validate the written artifacts with Factory checks and report IDs, revisions and human gates."
W_EXPECT[art2d-write]="art-2d"; W_KINDS[art2d-write]="art-direction-2d asset-spec-2d"; W_DOMAIN[art2d-write]=art2d
W_PROMPT[art3d-write]="Create 3D art direction, a model spec and a material spec for a crafting workstation prop. Validate the written artifacts with Factory checks and report IDs, revisions and human gates."
W_EXPECT[art3d-write]="art-3d"; W_KINDS[art3d-write]="art-direction-3d model-spec material-spec"; W_DOMAIN[art3d-write]=art3d
W_PROMPT[vfx-write]="Using the supplied design event, create a VFX spec for a crafting-complete effect with explicit budgets for every platform. Reference the event by artifact ID and revision. Validate with Factory checks and report IDs, revisions and human gates."
W_EXPECT[vfx-write]="vfx"; W_KINDS[vfx-write]="vfx-spec"; W_DOMAIN[vfx-write]=vfx; W_SEEDS[vfx-write]=design-event
W_PROMPT[xdomain-design-ui-eng]="From the supplied feature brief and gameplay system, produce a design feature spec, a UI screen spec and a technical handoff. Use the game-design and ui-ux production workflows for their respective artifacts. Put the gameplay system ID in spec.gameplay_systems and artifact sources. Make the screen depend on the feature spec, and make the technical handoff depend on the screen; keep references acyclic and record every revision with git hash-object <path>. Validate all artifacts, then run workflow plan and status on the produced artifacts. Report the required order from design through UI to engineering and all human gates."
W_EXPECT[xdomain-design-ui-eng]="game-design ui-ux"; W_KINDS[xdomain-design-ui-eng]="feature-spec screen-spec technical-handoff"; W_DOMAIN[xdomain-design-ui-eng]=design; W_PLAN[xdomain-design-ui-eng]=design-ui-eng; W_SEEDS[xdomain-design-ui-eng]=approved-feature
W_PROMPT[xdomain-art3d-vfx]="Using the supplied 3D asset record and gameplay system, create a VFX spec referencing both by ID and revision, and use the gameplay system ID as its trigger. Validate the artifacts and run workflow plan and status, confirming the 3D art work precedes VFX. Report any human gates."
W_EXPECT[xdomain-art3d-vfx]="vfx"; W_KINDS[xdomain-art3d-vfx]="vfx-spec"; W_DOMAIN[xdomain-art3d-vfx]=vfx; W_PLAN[xdomain-art3d-vfx]=art3d-vfx; W_SEEDS[xdomain-art3d-vfx]=asset-3d-vfx
W_PROMPT[xdomain-stale]="The supplied gameplay system has changed. Use the game-design workflow to update its upstream artifact, then use the VFX production workflow to inspect workflow status for the existing downstream VFX spec. Report that the downstream artifact is stale and needs revalidation, with both IDs and revisions. Do not create approvals."
W_EXPECT[xdomain-stale]="game-design vfx"; W_KINDS[xdomain-stale]="gameplay-system vfx-spec"; W_DOMAIN[xdomain-stale]=vfx; W_PLAN[xdomain-stale]=stale; W_SEEDS[xdomain-stale]=stale-pair

if $write_mode; then
  write_scenarios=(design-write ui-write art2d-write art3d-write vfx-write xdomain-design-ui-eng xdomain-art3d-vfx xdomain-stale)
  [ ${#scenarios[@]} -gt 0 ] || scenarios=("${write_scenarios[@]}")
  for n in "${scenarios[@]}"; do
    case " ${write_scenarios[*]} " in *" $n "*) ;; *) continue;; esac
    out_abs="$(cd "$OUT" && pwd)"; ws="$out_abs/ws-$n"
    case "$ws" in "$out_abs"/ws-*) ;; *) echo "unsafe write workspace: $ws" >&2; exit 2;; esac
    rm -rf -- "$ws"; mkdir -p "$ws/game-authoring"
    python3 -B "$ROOT/tests/dogfood/write-setup.py" "$ROOT" "$ws/game-authoring" "${W_SEEDS[$n]:-}"
    ws_native="$(cygpath -m "$ws")"
    git -C "$ws/game-authoring" init -q
    git -C "$ws/game-authoring" config user.name "Factory Dogfood"
    git -C "$ws/game-authoring" config user.email "dogfood@example.invalid"
    git -C "$ws/game-authoring" add -- design ui art2d art3d vfx; git -C "$ws/game-authoring" commit -qm "Seed isolated authoring workspace"
    local_prompt="${W_PROMPT[$n]} Write artifacts only inside the game-authoring repository in the current workspace. Never write elsewhere and never create approval records. For every upstream reference, record its current Git blob revision using git hash-object <path>. Run schema, lifecycle, lint, trace, workflow and domain quality checks; fix every FAIL and rerun the checks until none remain. Validate with scripts/checks/artifact-lint.py and scripts/checks/artifact-quality.py --domain ${W_DOMAIN[$n]} --json; run workflow plan and status when requested."
    pd=(); $installed || pd=(--plugin-dir "$ROOT")
    (cd "$ws" && RPG_FACTORY_WORKSPACE="$ws_native" timeout 900 claude "${pd[@]}" -p "$local_prompt" --model "$model" --output-format stream-json --verbose --allowedTools "Skill,Read,Grep,Glob,Write,Edit,Bash" </dev/null > "$OUT/$n.jsonl" 2>/dev/null) || true
    grade_args=(); $installed && grade_args+=(--installed --version "$VERSION" --loads "$LOADS")
    python3 -B "$ROOT/tests/dogfood/write-grade.py" --root "$ROOT" --workspace "$ws" --scenario "$n" --transcript "$OUT/$n.jsonl" --expected-skills "${W_EXPECT[$n]}" --expected-kinds "${W_KINDS[$n]}" --domain "${W_DOMAIN[$n]}" --plan "${W_PLAN[$n]:-}" "${grade_args[@]}" || fail=$(( ${fail:-0} + 1 ))
  done
  if ! $all_mode; then exit $(( ${fail:-0} > 0 ? 1 : 0 )); fi
  scenarios=()
fi

[ ${#scenarios[@]} -eq 0 ] && scenarios=(design-feature-spec ui-foundation art2d-foundation art3d-foundation vfx-foundation realtime-knob nakama-rpc wire-field netcode-change package-propagation client-integration k8s benchmark analyze-only plan-only validate-only cmd-status cmd-route tech-dotnet tech-go tech-unity tech-dots tech-netcode tech-first)
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
  # the skills that loaded, in order ("Launching skill: rpg-factory:X" results): an auto-corrected call
  # (requested a tech skill, the Skill hook loaded factory-core) counts as what loaded; an errored call loaded nothing
  used=$(grep '^{' "$f" | jq -r 'select(.type=="user") | .message.content[]? | objects | select(.type=="tool_result" and (.is_error | not))
    | (.content | if type == "array" then map(.text? // "") | join(" ") else tostring end) | capture("Launching skill: (?<s>[^ \\n\"]+)")? | .s' | sed 's/^rpg-factory://' | tr '\n' ' ')
  corrected=$(grep '^{' "$f" | jq -rs '[.[] | select(.type=="user") | .message.content[]? | objects | select(.type=="tool_result")
      | {id: .tool_use_id, got: ((.content | if type == "array" then map(.text? // "") | join(" ") else tostring end) | capture("Launching skill: (?<s>[^ \\n\"]+)")? | .s)}] as $r
    | .[] | select(.type=="assistant") | .message.content[] | select(.type=="tool_use" and .name=="Skill") | .id as $i | .input.skill as $want
    | ($r[] | select(.id == $i) | .got) as $got | select($got != null and $got != $want) | "\($want | sub("^rpg-factory:"; ""))>\($got | sub("^rpg-factory:"; ""))"' | tr '\n' ' ')
  answer=$(grep '^{' "$f" | jq -r 'select(.type=="result") | .result // ""')
  outcome=$(grep '^{' "$f" | jq -r 'select(.type=="result") | .subtype // ""' | tail -1)
  sid=$(grep '^{' "$f" | jq -r 'select(.type=="system" and .subtype=="init") | .session_id' | head -1)
  # the headless session's hooks may resolve another scratch root than this shell (Python 3.14 on Windows: TMPDIR
  # "/tmp" is not absolute, so they fall back to persistent()/tmp): probe both, prefer the one holding the session
  sdir=$(python3 -B -c "
import os, sys
sys.path.insert(0, sys.argv[1])
import fstate
key = fstate.session_key(sys.argv[2])
roots = list(dict.fromkeys([fstate.scratch(), os.path.join(fstate.persistent(), 'tmp')]))
cands = [os.path.join(r, key) for r in roots]
print(next((d for d in cands if os.path.isdir(d)), cands[0]))" "$ROOT/scripts/lib" "${sid:-none}")
  # the reader knows the on-disk layout (ADVISORIES.d/ + legacy file) and probes both roots itself
  advisories=$(python3 -B "$ROOT/scripts/factory_session.py" --advisories "${sid:-none}" 2>/dev/null | tr -d '\r' | tr '\n' ';')
  [ -n "${RAW[$n]:-}" ] || grep -qw "factory-core" <<<"$used" || why+="factory-core not invoked; "
  cmds=$(grep '^{' "$f" | jq -r 'select(.type=="assistant") | .message.content[] | select(.type=="tool_use" and (.name=="Bash" or .name=="PowerShell")) | .input.command')
  if [ -n "${MODE[$n]:-}" ]; then  # declared via --mode, or recorded by the Skill hook in the session's state
    recorded=$(cat "$sdir/MODE" 2>/dev/null)
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
  # a tech skill is supporting context. Hooks never block (1.0.3), so a tech skill that loads before any
  # owning skill passes only if the Skill hook warned the session about it, one of its used_by leads loaded
  # later, and the session finished; otherwise the lead's rules and gates never applied
  first_tech=""; owner_before=false; note=""
  for u in $used; do
    k=$(jq -r --arg s "$u" '.skills[$s].kind // ""' "$ROOT/registry.json")
    if [ "$k" = "tech" ]; then first_tech=$u; break; fi
    case "$k" in repo|cross-repo) owner_before=true;; esac
  done
  if [ -n "$first_tech" ] && ! $owner_before; then
    leads=$(jq -r --arg s "$first_tech" '.skills[$s].used_by[]' "$ROOT/registry.json")
    after=${used#*"$first_tech"}; lead_after=""
    for l in $leads; do grep -qw "$l" <<<"$after" && lead_after=$l; done
    grep -q "$first_tech warn" <<<"$advisories" || why+="tech skill $first_tech loaded before any owning skill without a Skill-hook advisory; "
    [ -n "$lead_after" ] || why+="tech skill $first_tech loaded first and none of its leads ($(tr '\n' ' ' <<<"$leads")) ran afterwards; "
    note=" (tech-first $first_tech: warned, lead $lead_after ran after)"
  fi
  [ "$outcome" = success ] || why+="session did not finish (result: ${outcome:-none}); "
  if [ -n "${CORRECTS[$n]:-}" ]; then  # this scenario requests a tech skill before factory-core on purpose
    grep -q "${CORRECTS[$n]}>factory-core" <<<"$corrected" || why+="${CORRECTS[$n]} requested first was not auto-corrected to factory-core (corrected: ${corrected:-none}); "
    grep -q "${CORRECTS[$n]} autocorrect factory-core" <<<"$advisories" || why+="no autocorrect advisory logged for ${CORRECTS[$n]}; "
    note="$note (auto-corrected ${corrected% })"
  fi
  for h in ${HANDOFF[$n]:-}; do grep -qw "$h" <<<"$used $answer" || why+="hand-off $h not named; "; done
  if [ -z "$why" ]; then pass=$((pass + 1)); r="PASS$note"; else fail=$((fail + 1)); r="FAIL: $why"; fi
  printf '%-20s | %-26s | %-28s | %-40s | %s\n' "$n" "${lv:-?} ${src:-?}" "${EXPECT[$n]}${HANDOFF[$n]:+ > ${HANDOFF[$n]:-}}" "${used:-none}" "$r"
done
echo "dogfood: $((pass + fail)) run, $pass passed, $fail failed (model $model; $($installed && echo "installed $VERSION" || echo plugin-dir); ${elapsed}s wall, parallel; transcripts in $OUT)"
[ "$fail" -eq 0 ] && [ "$pass" -gt 0 ]
