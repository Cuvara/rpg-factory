#!/usr/bin/env bash
# Domain and artifact-kind entry points on a throwaway registry and stand-in workspace.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP="$(mktemp_win)" || exit 1
trap 'rm -rf "$TMP"' EXIT
export TMPDIR="$TMP" RPG_FACTORY_STATE_DIR="$TMP/state"
REG="$TMP/registry.json"; WS="$TMP/ws"
jq '.repos.uitoolkit.optional = true
  | .domains.engineering.artifact_kinds = ["shared"]
  | .domains.design = {summary:"Design artifacts",status:"active",lead:"design-lead",repos:["uitoolkit"],artifact_kinds:["spec","shared"],quality_gates:["lint"],human_gates:["rules"],handoffs:["spec-to-code"]}
  | .skills["design-lead"] = {kind:"repo",domain:"design",order:999}
  | .skills["outside-lead"] = {kind:"repo",domain:"elsewhere",order:998}
  | .domains.design.repos += ["server"]
  | .contracts += [{id:"spec-to-code",kind:"handoff",domain:"design",summary:"fixture handoff",source:{repo:"server",path:"backend/content/"},copies:[{repo:"server",path:"backend/gameserver-dotnet/"}],driver:"design-lead",gate:null,evidence:"artifact-trace"}]' "$ROOT/registry.json" > "$REG"
jq '(.modules |= map(if .id == "server.content" then .domain = "design" else . end)) | .skills["server-realtime"].domain = "design"' "$REG" > "$TMP/ambiguous-registry.json"
mv "$TMP/ambiguous-registry.json" "$REG"
export RPG_FACTORY_REGISTRY="$REG" RPG_FACTORY_WORKSPACE="$WS" CLAUDE_PLUGIN_ROOT="$ROOT"
mkdir -p "$WS"
while IFS= read -r p; do
  [ "$p" = "uitoolkit" ] && continue
  path=$(jq -r --arg k "$p" '.repos[$k].path' "$REG")
  git init -q "$WS/$path" && git -C "$WS/$path" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init || exit 1
done < <(jq -r '.repos | keys[]' "$REG")
while IFS= read -r m; do mkdir -p "$WS/$(dirname "$m")"; touch "$WS/$m"; done < <(jq -r '.workspace.root_markers[]' "$REG")
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; }
ctx() { bash "$ROOT/scripts/factory-context.sh" "$@"; }
out=$(ctx --domain design --graph 2>&1); rc=$?
[ "$rc" -eq 0 ] && grep -q 'Dependency graph: design -> engineering' <<<"$out" && ok "handoff graph topological order" || no "handoff graph (rc=$rc): $out"
out=$(ctx --repo server --paths backend/content/ backend/shared/proto/wire.proto 2>&1); rc=$?
[ "$rc" -eq 3 ] && grep -q 'AMBIGUOUS: paths resolve to leads in multiple domains' <<<"$out" && grep -q 'design-lead:' <<<"$out" && grep -q 'wire-contract:' <<<"$out" && ok "cross-domain paths report both leads" || no "ambiguous paths (rc=$rc): $out"
out=$(ctx --repo server --lead wire-contract --paths backend/content/ backend/shared/proto/wire.proto 2>&1); rc=$?
[ "$rc" -eq 0 ] && grep -q 'wire-contract' <<<"$out" && ok "--lead resolves cross-domain paths" || no "lead override (rc=$rc)"
cycle_reg="$TMP/cycle-registry.json"
jq '.contracts += [{id:"reverse-handoff",kind:"handoff",domain:"engineering",summary:"reverse",source:{repo:"server",path:"backend/shared/proto/"},copies:[{repo:"authoring",path:"design/features/"}],driver:"wire-contract",gate:null,evidence:"artifact-trace"}]' "$REG" > "$cycle_reg"
export RPG_FACTORY_REGISTRY="$cycle_reg"
out=$(ctx --domain design --graph 2>&1); rc=$?
[ "$rc" -eq 3 ] && grep -q 'CYCLE: design -> engineering -> design' <<<"$out" && ok "graph cycle exits 3 with cycle" || no "graph cycle (rc=$rc): $out"
export RPG_FACTORY_REGISTRY="$REG"
out=$(ctx --domain engineering 2>&1); rc=$?
[ "$rc" -eq 0 ] && grep -q 'Domain' <<<"$out" && grep -q 'routes by --repo/--paths (module ownership)' <<<"$out" && ok "--domain engineering text" || no "--domain engineering text (rc=$rc)"
out=$(ctx --json --domain engineering 2>&1); rc=$?
[ "$rc" -eq 0 ] && jq -e '.domain.id == "engineering" and .domain.lead == null and (.domain.repos | length > 0)' <<<"$out" >/dev/null && ok "--domain engineering JSON" || no "--domain engineering JSON (rc=$rc)"
out=$(ctx --domain missing 2>&1); rc=$?
[ "$rc" -eq 2 ] && grep -q 'unknown domain missing; known:' <<<"$out" && ok "unknown domain exits 2" || no "unknown domain (rc=$rc)"
out=$(ctx --kind absent 2>&1); rc=$?
[ "$rc" -eq 2 ] && grep -q 'known: shared, spec' <<<"$out" && ok "unknown kind lists known kinds" || no "unknown kind (rc=$rc)"
out=$(ctx --kind spec 2>&1); rc=$?
[ "$rc" -eq 0 ] && grep -q 'id: design' <<<"$out" && ok "one-claim kind resolves" || no "one-claim kind (rc=$rc)"
out=$(ctx --kind shared 2>&1); rc=$?
[ "$rc" -eq 3 ] && grep -q 'AMBIGUOUS: kind shared is claimed by domains engineering, design' <<<"$out" && ok "two-claim kind is ambiguous" || no "ambiguous kind (rc=$rc)"
out=$(ctx --json --kind shared 2>&1); rc=$?
[ "$rc" -eq 3 ] && jq -e '.ambiguous and .domains == ["engineering","design"]' <<<"$out" >/dev/null && ok "ambiguous kind JSON" || no "ambiguous kind JSON (rc=$rc)"
out=$(ctx --kind shared --domain design 2>&1); rc=$?
[ "$rc" -eq 0 ] && grep -q 'id: design' <<<"$out" && ok "--domain resolves multi-claim kind" || no "--domain kind resolution (rc=$rc)"
out=$(ctx --kind shared --lead design-lead 2>&1); rc=$?
[ "$rc" -eq 0 ] && grep -q 'id: design' <<<"$out" && ok "--lead resolves multi-claim kind" || no "--lead kind resolution (rc=$rc)"
out=$(ctx --kind shared --lead outside-lead 2>&1); rc=$?
[ "$rc" -eq 2 ] && grep -q 'does not belong to a domain claiming kind shared' <<<"$out" && ok "invalid kind lead rejected" || no "invalid kind lead (rc=$rc)"
out=$(ctx --domain design --repo server --paths backend/shared/proto/wire.proto 2>&1); rc=$?
[ "$rc" -eq 0 ] && grep -q 'Warning: requested domain design differs from routed domain engineering' <<<"$out" && ok "domain mismatch warning" || no "domain mismatch warning (rc=$rc)"
out=$(ctx --repo server --json --paths backend/shared/proto/wire.proto 2>&1)
jq -e '.repos[0].routing.domain == "engineering"' <<<"$out" >/dev/null && ok "engineering path has routing.domain" || no "engineering path domain"
out=$(ctx --repo server --json --paths docs/architecture/ADR.md 2>&1)
jq -e '.repos[0].routing.lead == null and .repos[0].routing.domain == null' <<<"$out" >/dev/null && ok "no-lead path has null routing.domain" || no "no-lead domain"
out=$(ctx --repo all 2>&1); rc=$?
[ "$rc" -eq 0 ] && grep -q 'optional repo uitoolkit absent' <<<"$out" && ok "absent optional repo skipped in snapshot" || no "optional skip (rc=$rc)"
out=$(ctx --repo uitoolkit --paths Runtime/Widget.cs 2>&1); rc=$?
[ "$rc" -eq 2 ] && grep -q 'optional repo uitoolkit is not present at' <<<"$out" && grep -qi 'UIToolkit' <<<"$out" && ok "explicit absent optional repo exits 2" || no "optional explicit failure (rc=$rc)"
git init -q "$WS/UIToolkit" && git -C "$WS/UIToolkit" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init || exit 1
out=$(ctx --repo uitoolkit --json --paths Runtime/Widget.cs 2>&1)
jq -e '.repos[0].routing.lead == "unity-package" and .repos[0].routing.domain == "engineering"' <<<"$out" >/dev/null && ok "present optional repo routes normally" || no "optional present route"
out=$(python3 -B "$ROOT/scripts/factory-cmd.py" route --domain engineering 2>&1); rc=$?
[ "$rc" -eq 0 ] && grep -q 'routes by --repo/--paths' <<<"$out" && ok "factory-cmd route --domain" || no "factory-cmd route --domain (rc=$rc)"
out=$(python3 -B "$ROOT/scripts/factory-cmd.py" route --kind shared --lead design-lead 2>&1); rc=$?
[ "$rc" -eq 0 ] && grep -q 'id: design' <<<"$out" && ok "factory-cmd route --kind --lead resolves an ambiguous kind" || no "factory-cmd route --kind --lead (rc=$rc)"
out=$(python3 -B "$ROOT/scripts/factory-cmd.py" route --kind shared --repo server 2>&1); rc=$?
[ "$rc" -ne 0 ] && grep -q 'accepts only --domain, --kind and --lead' <<<"$out" && ok "factory-cmd route selector rejects other flags" || no "factory-cmd route selector flag check (rc=$rc)"
total=$((pass + fail)); echo "domains-routing: $total run, $pass passed, $fail failed"
[ "$fail" -eq 0 ]
