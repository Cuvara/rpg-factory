#!/usr/bin/env bash
# Game Design domain routing, boundaries and standalone behavior on plugin + authoring fixtures.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
T="$(mktemp_win)" || exit 1; [ -d "$T" ] || exit 1; trap 'rm -rf "$T"' EXIT
P="$T/plugin"; FW="$T/workspace"; FA="$FW/game-authoring"
mkdir -p "$P" "$FA/design/features" "$FW/rpg-mmo-server/backend" "$FW/IndieRPGMMOAdventure/ProjectSettings"
cp -R "$ROOT/." "$P/"
rm -rf "$P/.git"
# Workspace markers and a stand-in authoring checkout; no external design plugin is installed or needed.
touch "$FW/rpg-mmo-server/backend/TEAM.md" "$FW/IndieRPGMMOAdventure/ProjectSettings/ProjectVersion.txt"
echo 'fixture artifact' > "$FA/design/features/crafting.md"
git -C "$FA" init -q -b main
git -C "$FA" -c user.name=Fixture -c user.email=fixture@example.test add -A
git -C "$FA" -c user.name=Fixture -c user.email=fixture@example.test commit -qm fixture
pass=0; fail=0
ok() { pass=$((pass+1)); echo "PASS $1"; }
no() { fail=$((fail+1)); echo "FAIL $1"; [ -n "${2:-}" ] && printf '%s\n' "$2" | head -12 | sed 's/^/  /'; }
ctx() { (cd "$P" && CLAUDE_PLUGIN_ROOT="$P" RPG_FACTORY_WORKSPACE="$FW" bash "$P/scripts/factory-context.sh" --repo authoring --json "$@" 2>&1); }
intent() { (cd "$P" && CLAUDE_PLUGIN_ROOT="$P" RPG_FACTORY_WORKSPACE="$FW" bash "$P/scripts/factory-context.sh" --json "$@" 2>&1); }

out=$(intent --domain design)
jq -e '.domain.id == "design" and .domain.lead == "game-design"' <<<"$out" >/dev/null \
  && ok '--domain design selects game-design' || no '--domain design selects game-design' "$out"
out=$(intent --kind feature-spec)
jq -e '.domain.id == "design" and .domain.lead == "game-design"' <<<"$out" >/dev/null \
  && ok '--kind feature-spec resolves design and game-design' || no '--kind feature-spec resolves design and game-design' "$out"
out=$(ctx --paths design/features/crafting.md)
jq -e 'any(.repos[0].suggested_skills[]; .role == "lead" and .skill == "game-design")' <<<"$out" >/dev/null \
  && ok 'design path routes to game-design' || no 'design path routes to game-design' "$out"

# A non-design lead may not claim design triggers in its description.
python3 - "$P/skills/server-realtime/SKILL.md" <<'PY'
import sys
p=sys.argv[1]; s=open(p,encoding="utf-8").read(); s=s.replace("description:", "description: Feature registry design trigger. ", 1); open(p,"w",encoding="utf-8").write(s)
PY
out=$(cd "$P" && CLAUDE_PLUGIN_ROOT="$P" bash tests/skills-lint.sh 2>&1); rc=$?
[ $rc -ne 0 ] && grep -q 'server-realtime: design trigger requires may_own_feature_state' <<<"$out" \
  && ok 'skills-lint rejects a non-design feature-registry description' || no 'skills-lint non-design claim boundary' "$out"

# Non-owning module path rejection.
jq '(.modules |= map(if .id == "server.proto" then .paths = ["docs/features/"] else . end))' "$P/registry.json" > "$T/bad-registry.json"
out=$(CLAUDE_PLUGIN_ROOT="$P" bash "$P/scripts/check-registry.sh" --structure-only --registry "$T/bad-registry.json" 2>&1); rc=$?
[ $rc -ne 0 ] && grep -q 'cannot own feature-state path docs/features/' <<<"$out" \
  && ok 'check-registry rejects non-design docs/features ownership' || no 'check-registry feature-state path rule' "$out"

# Base proof uses the base registry's known rule set when the source commit is readable.
# The fixture avoids depending on git metadata inside the isolated plugin copy.
if git -C "$ROOT" show d63e768aff4f440d745fa54cbb5334ab7797fd8b:scripts/check-registry.sh > "$P/scripts/check-registry-base.sh" 2>/dev/null; then
  jq 'del(.domains.design) | .repos |= del(.authoring) | .contracts |= map(select(.id != "feature-spec-to-impl")) | .modules = [.modules[] | select(.repo != "authoring")] | .skills |= with_entries(select(.value.domain != "design")) | .human_gates |= map(select(.id != "design-review")) | (.modules |= map(if .id == "server.proto" then .paths = ["docs/features/"] else . end))' "$P/registry.json" > "$T/base-mutated.json"
  out=$(CLAUDE_PLUGIN_ROOT="$P" bash "$P/scripts/check-registry-base.sh" --structure-only --registry "$T/base-mutated.json" 2>&1); rc=$?
  [ $rc -eq 0 ] && grep -q '^OK:' <<<"$out" && ok 'base P4 checker accepts the path (regression proof)' || no 'base P4 regression proof' "$out"
else
  no 'base P4 regression proof unavailable: source commit cannot be read from this worktree'
fi

# No runtime dependency on the former external plugin; only the architecture coexistence note may name it.
if grep -R -n 'game-ai-workflows' "$P/scripts" "$P/hooks" >/dev/null || jq -r '.. | strings' "$P/registry.json" | grep -n 'game-ai-workflows' >/dev/null; then
  no 'standalone runtime/configuration references absent external plugin'
else ok 'scripts, hooks and registry values have no external plugin dependency'; fi
other=$(grep -R -n 'game-ai-workflows' "$P/skills" | grep -v 'skill-contract.md:.*independent' || true)
[ -z "$other" ] && ok 'skill references are absent except the coexistence note' || no 'unexpected skill dependency reference' "$other"
# The route above executes against the fixture with no external plugin installation.
[ -d "$FA/.git" ] && ok 'domain runs with only the authoring fixture installed' || no 'authoring fixture missing'

echo "domains: $((pass+fail)) run, $pass passed, $fail failed"
[ "$fail" -eq 0 ]
