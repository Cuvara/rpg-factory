#!/usr/bin/env bash
# scripts/new-skill.py and scripts/skill-touchpoints.py on a throwaway copy of this plugin: a scaffolded
# tech and lead skill pass check-registry and the SKILL.md structure lint, fail only on what the author must
# still write (SCAFFOLD markers, touchpoints, the leads naming a tech skill); refusals write nothing.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
P="$TMP/plugin"; mkdir -p "$P"
cp -R "$ROOT/." "$P/"
rm -rf "$P/.git"
pass=0; fail=0
ok() { pass=$((pass + 1)); echo "PASS  $1"; }
no() { fail=$((fail + 1)); echo "FAIL  $1"; [ -n "${2:-}" ] && echo "$2" | head -15 | sed 's/^/      /'; }
ns() { (cd "$P" && CLAUDE_PLUGIN_ROOT="$P" python3 -B scripts/new-skill.py "$@" 2>&1); }
tp() { (cd "$P" && CLAUDE_PLUGIN_ROOT="$P" python3 -B scripts/skill-touchpoints.py "$@" 2>&1); }
creg() { CLAUDE_PLUGIN_ROOT="$P" bash "$P/scripts/check-registry.sh" --structure-only 2>&1; }
lint() { (cd "$P" && CLAUDE_PLUGIN_ROOT="$P" bash tests/skills-lint.sh 2>&1); }

out=$(tp --all); [ $? -eq 0 ] && ok "the real plugin has every touchpoint (copy before any scaffold)" || no "touchpoints on the copy" "$out"

# refusals write nothing
before=$(md5sum < "$P/registry.json")
for args in "--name Bad_Name --kind tech --repos server --summary s --used-by server-services" \
            "--name x-tech --kind tech --repos server --summary s" \
            "--name x-tech --kind tech --repos server --summary s --used-by factory-core" \
            "--name x-tech --kind tech --repos nope --summary s --used-by server-services" \
            "--name x-tech --kind tech --repos server --summary s --used-by server-services --owns-modules server.gateway" \
            "--name x-lead --kind repo --repos server --summary s" \
            "--name x-lead --kind repo --repos server --summary s --owns-modules no.such.module" \
            "--name x-tech --kind tech --repos server --summary s --used-by server-services --tools no-such-tool" \
            "--name x-lead --kind repo --repos server --summary s --owns-modules server.proto --domain unknown-domain" \
            "--name go-backend --kind tech --repos server --summary s --used-by server-services"; do
  out=$(ns $args); rc=$?
  if [ $rc -eq 2 ] && grep -q '^REFUSED: ' <<<"$out" && [ "$(md5sum < "$P/registry.json")" = "$before" ] && [ ! -d "$P/skills/x-tech" ] && [ ! -d "$P/skills/x-lead" ]; then
    ok "refused, nothing written: $(sed 's/^REFUSED: //' <<<"$out" | cut -c1-70)"
  else no "not refused: $args (rc=$rc)" "$out"; fi
done
out=$(ns --name x-tech --kind tech --repos server --summary s --used-by server-services --dry-run)
[ $? -eq 0 ] && [ ! -d "$P/skills/x-tech" ] && [ "$(md5sum < "$P/registry.json")" = "$before" ] && ok "--dry-run writes nothing" || no "--dry-run" "$out"
cp "$P/registry.json" "$TMP/reg.bak"; sed -i 's/^  "repos": {/  "repos":  {/' "$P/registry.json"
out=$(ns --name x-tech --kind tech --repos server --summary s --used-by server-services); rc=$?
[ $rc -eq 2 ] && grep -q 'not in canonical form' <<<"$out" && [ ! -d "$P/skills/x-tech" ] && ok "a non-canonical registry is never rewritten" || no "canonical-form guard (rc=$rc)" "$out"
cp "$TMP/reg.bak" "$P/registry.json"

# scaffold a tech skill: registry entry exactly as asked, structure lint clean, author's work listed
out=$(ns --name demo-tech --kind tech --repos server --used-by server-services,wire-contract --tools go,lsp-go \
        --summary "How the demo Go code works" --cite-root "=server:backend/gateway"); rc=$?
[ $rc -eq 0 ] && grep -q 'wrote skills/demo-tech/SKILL.md and registry skills.demo-tech (order 95)' <<<"$out" && ok "tech skill scaffolded with the next tech order" || no "scaffold tech (rc=$rc)" "$out"
d=$(jq -c '.skills["demo-tech"]' "$P/registry.json")
[ "$d" = '{"kind":"tech","repos":["server"],"order":95,"used_by":["server-services","wire-contract"],"summary":"How the demo Go code works","cite_roots":{"":"server:backend/gateway"}}' ] \
  && ok "registry entry is exactly kind/repos/order/used_by/summary/cite_roots" || no "registry entry" "$d"
jq -e '[.dev_tools[] | select(.id == "go" or .id == "lsp-go") | .used_by | index("demo-tech")] | all' "$P/registry.json" >/dev/null \
  && ok "dev_tools go and lsp-go list it in used_by" || no "dev_tools used_by"
changed=$(diff <(jq -S 'del(.skills["demo-tech"]) | .dev_tools |= map(.used_by -= ["demo-tech"])' "$TMP/reg.bak") \
               <(jq -S 'del(.skills["demo-tech"]) | .dev_tools |= map(.used_by -= ["demo-tech"])' "$P/registry.json"))
[ -z "$changed" ] && ok "nothing else in the registry changed" || no "unexpected registry change" "$changed"
out=$(creg); [ $? -eq 0 ] && ok "check-registry accepts the scaffolded tech skill" || no "check-registry after tech scaffold" "$out"
out=$(lint); fails=$(grep -E '^FAIL|^      ' <<<"$out")
grep -q 'demo-tech/SKILL.md:[0-9]* still has a SCAFFOLD: marker' <<<"$fails" && grep -q 'used_by skill server-services never names rpg-factory:demo-tech' <<<"$fails" \
  && ! grep -qiE 'frontmatter|missing section|prerequisite|Supporting skill|Pitfalls|description|## Tools|unanchored' <<<"$fails" \
  && ok "lint fails only on SCAFFOLD markers and the leads that must name it, not on structure" || no "lint after tech scaffold" "$fails"
out=$(tp demo-tech); [ $? -eq 1 ] && grep -q "factory-core SKILL.md 'Skills' section does not name this tech skill" <<<"$out" \
  && grep -q 'tests/routing.test.sh has no scenario asserting $(tech demo-tech)' <<<"$out" && grep -q 'no eval grader evals/\*/graders/demo-tech-fired.md' <<<"$out" \
  && grep -q "'Skills:' says 5 tech skills, the registry has 6" <<<"$out" \
  && ok "touchpoints list the author's remaining places (factory-core, routing, evals, CLAUDE.md count, ...)" || no "touchpoints after tech scaffold" "$out"

# scaffold a lead that takes over a module
out=$(ns --name demo-lead --kind repo --repos server --owns-modules server.loadtest --summary "Demo lead"); rc=$?
o=$(jq -r '.skills["demo-lead"].order' "$P/registry.json")
[ $rc -eq 0 ] && [ "$(jq -r '.modules[] | select(.id == "server.loadtest") | .skills[0]' "$P/registry.json")" = demo-lead ] \
  && ! jq -e --argjson o "$o" '[.skills[] | select(.order == $o)] | length > 1' "$P/registry.json" >/dev/null \
  && [ "$o" = 96 ] && ok "lead scaffolded: primary owner of server.loadtest, order $o (after every existing lead)" || no "scaffold lead (rc=$rc)" "$out"
out=$(creg); [ $? -eq 0 ] && ok "check-registry accepts the scaffolded lead" || no "check-registry after lead scaffold" "$out"
out=$(ns --name demo-domain --kind repo --repos authoring --summary "Demo design lead" --owns-modules authoring.root --domain design); rc=$?
[ $rc -eq 0 ] && [ "$(jq -r '.skills["demo-domain"].domain' "$P/registry.json")" = design ] && ok "--domain assigns a registered domain to the scaffolded skill" || no "--domain assignment (rc=$rc)" "$out"
out=$(tp demo-lead); grep -q "factory-core SKILL.md 'Skills' table has no row for this lead" <<<"$out" && grep -q 'README skill map table has no row' <<<"$out" \
  && grep -q 'description says 13 specialised skills, the registry has 15' <<<"$out" \
  && ok "touchpoints for a lead: Skills table row, README skill map, plugin.json lead count" || no "touchpoints after lead scaffold" "$out"

echo "new-skill tests: $((pass + fail)) run, $pass passed, $fail failed"
[ "$fail" -eq 0 ]
