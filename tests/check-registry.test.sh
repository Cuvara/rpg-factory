#!/usr/bin/env bash
# Regression coverage for domain metadata and optional repository path checks.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECKER="$ROOT/scripts/check-registry.sh"
TMP="$(mktemp_win)" || exit 1
trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
REAL="$ROOT/registry.json"

expect_fail() {
  local name="$1" filter="$2" expected="$3" out
  local file="$TMP/$name.json"
  if ! jq "$filter" "$REAL" > "$file"; then echo "FAIL $name: jq mutation failed"; fail=$((fail + 1)); return; fi
  if out=$("$CHECKER" --structure-only --registry "$file" 2>&1); then
    echo "FAIL $name: expected checker failure"; fail=$((fail + 1)); return
  fi
  if grep -Fq "$expected" <<<"$out"; then echo "PASS $name"; pass=$((pass + 1));
  else echo "FAIL $name: expected '$expected'"; printf '%s\n' "$out" | head -8; fail=$((fail + 1)); fi
}

if "$CHECKER" --structure-only --registry "$REAL" > "$TMP/clean.out" 2>&1; then
  echo "PASS unmodified registry"; pass=$((pass + 1))
else echo "FAIL unmodified registry"; cat "$TMP/clean.out"; fail=$((fail + 1)); fi

# a: domain assignment on skills/modules/contracts must resolve, and engineering is mandatory.
expect_fail a-unknown-skill-domain '.skills["server-realtime"].domain = "missing-domain"' 'skill server-realtime: unknown domain missing-domain'
expect_fail a-unknown-module-domain '.modules[0].domain = "missing-domain"' 'unknown domain missing-domain'
expect_fail a-unknown-contract-domain '(.contracts |= map(if .id == "wire-generated" then .domain = "missing-domain" else . end))' 'contract wire-generated: unknown domain missing-domain'
expect_fail a-engineering-required 'del(.domains.engineering)' 'missing domain: engineering'
# b: ids follow the domain slug grammar; status is one of active/planned/foundation.
expect_fail b-domain-id '.domains["Bad Domain"] = .domains.engineering' 'domain id Bad Domain must match'
expect_fail b-domain-status '.domains.engineering.status = "retired"' 'status must be active|planned|foundation'
# c: leads are registered repo or cross-repo skills assigned to this domain.
expect_fail c-lead-kind '.domains.engineering.lead = "factory-core"' 'lead factory-core must be a repo or cross-repo skill'
expect_fail c-lead-domain '(.domains.other = .domains.engineering) | (.domains.other.lead = "server-realtime")' 'lead server-realtime belongs to domain engineering'
# d: domain repos exist, and module repos belong to their domain.
expect_fail d-domain-repo '.domains.engineering.repos += ["unknown-repo"]' 'domain engineering: unknown repo unknown-repo'
expect_fail d-module-repo '(.domains.engineering.repos = ["server"]) | (.modules |= map(if .repo == "client" then .domain = "engineering" else . end))' 'repo client is not in domain engineering'
# e: quality gates, handoffs, and human gates resolve in their respective registries.
expect_fail e-quality-gate '.domains.engineering.quality_gates = ["not-a-check"]' 'unknown quality gate not-a-check'
expect_fail e-handoff '.domains.engineering.handoffs = ["not-a-contract"]' 'unknown handoff not-a-contract'
expect_fail e-human-gate '.domains.engineering.human_gates = ["not-a-gate"]' 'unknown human gate not-a-gate'
# g: phase declaration is a checked contract; feature-state paths need an owning domain.
expect_fail g-phase-shape '.phase.design.binding_values = null' 'phase: expected id'
expect_fail g-phase-engineering '.phase.engineering.gameplay_values = "existing-code-only"' 'phase: expected id'
expect_fail g-feature-path '(.modules |= map(if .id == "server.proto" then .paths = ["docs/features/"] else . end))' 'cannot own feature-state path docs/features/'
# f: artifact role is constrained when supplied.
expect_fail f-role '.modules[0].role = "observer"' 'role must be orchestrator|implementer|reference'
expect_fail f-skill-role '.skills["server-realtime"].role = "observer"' 'role must be orchestrator|implementer|reference'
expect_fail handoff-driver-domain '(.modules |= map(if .id == "authoring.design-features" then .domain = "engineering" else . end))' 'source module domain engineering differs from driver domain design'
expect_fail handoff-unmapped-copy '(.contracts |= map(if .id == "feature-spec-to-impl" then .copies[0].path = "missing/module/" else . end))' 'path server:missing/module/ does not resolve to a module'
expect_fail duplicate-domain-artifact-kind '.domains.engineering.artifact_kinds = ["feature-spec"]' 'artifact kind feature-spec is shared by domains engineering, design'
expect_fail cross-domain-path-overlap '(.domains.design.repos += ["server"]) | (.modules |= map(if .id == "authoring.design-features" then .repo = "server" | .paths = ["backend/shared/proto/"] else . end))' 'domain path conflict'
# g: absent optional repository paths are skipped and reported in a stand-in workspace.
G="$TMP/optional.json"
jq '(.repos.server.optional = true) | (.repos.server.path = "absent-server") | (.repos = {server:.repos.server, authoring:.repos.authoring}) | (.domains.engineering.repos = ["server"]) | (.domains.design.handoffs = []) | (.modules = [.modules[] | select((.repo == "server" and (.fallback == true or .id == "server.proto")) or .repo == "authoring")]) | (.contracts = []) | (.skills |= with_entries(.value.cite_roots = {})) | (.workspace.root_markers = ["marker"])' "$REAL" > "$G"
mkdir -p "$TMP/workspace"; touch "$TMP/workspace/marker"
if out=$(RPG_FACTORY_WORKSPACE="$TMP/workspace" "$CHECKER" --registry "$G" 2>&1); then
  if grep -Fq 'optional repo server absent (not checked)' <<<"$out"; then echo "PASS g-optional-repo-absent"; pass=$((pass + 1));
  else echo "FAIL g-optional-repo-absent: missing notice"; printf '%s\n' "$out" | head -8; fail=$((fail + 1)); fi
else echo "FAIL g-optional-repo-absent"; printf '%s\n' "$out" | head -12; fail=$((fail + 1)); fi

# h: a module without a docs array still gets its paths checked (no jq error, nothing skipped).
H="$TMP/nodocs.json"; jq '.modules |= map(del(.docs))' "$G" > "$H"
out=$(RPG_FACTORY_WORKSPACE="$TMP/workspace" "$CHECKER" --registry "$H" 2>&1); rc=$?
if [ "$rc" -eq 0 ] && ! grep -q 'jq: error' <<<"$out"; then echo "PASS h-missing-arrays-tolerated"; pass=$((pass + 1));
else echo "FAIL h-missing-arrays-tolerated (rc=$rc)"; printf '%s
' "$out" | head -6; fail=$((fail + 1)); fi
# i: a path query error fails the check instead of silently shortening the path list.
I="$TMP/badpaths.json"; jq '.modules[0].paths = 5' "$G" > "$I"
out=$(RPG_FACTORY_WORKSPACE="$TMP/workspace" "$CHECKER" --registry "$I" 2>&1); rc=$?
if [ "$rc" -ne 0 ] && grep -Fq 'path query failed' <<<"$out"; then echo "PASS i-path-query-error-fails"; pass=$((pass + 1));
else echo "FAIL i-path-query-error-fails (rc=$rc)"; printf '%s
' "$out" | head -6; fail=$((fail + 1)); fi

echo "check-registry: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
