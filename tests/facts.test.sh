#!/usr/bin/env bash
# Registry facts stay true: every facts[] probe is re-run (read-only) in its repo and must print
# the recorded value; toolchain "expected" pins must agree with the facts; skills must not
# hard-code volatile values that belong in facts[] or in the live scripts.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
R="$ROOT/registry.json"
WS="${RPG_FACTORY_WORKSPACE:-$(jq -r .workspace.root_default "$R")}"
pass=0; fail=0; skip=0
while read -r enc; do
  id=$(base64 -d <<<"$enc" | jq -r .id); value=$(base64 -d <<<"$enc" | jq -r .value)
  repo=$(base64 -d <<<"$enc" | jq -r .repo); probe=$(base64 -d <<<"$enc" | jq -r .probe)
  dir="$WS/$(jq -r --arg r "$repo" '.repos[$r].path' "$R")"
  if [ ! -d "$dir" ]; then skip=$((skip + 1)); echo "SKIP  $id (repo $repo not present)"; continue; fi
  got=$(cd "$dir" && PYTHONDONTWRITEBYTECODE=1 timeout 120 bash -c "$probe" 2>/dev/null | head -1 | tr -d '\r')
  if [ "$got" = "$value" ]; then pass=$((pass + 1)); echo "PASS  $id = $value"
  else fail=$((fail + 1)); echo "FAIL  $id: registry says '$value', repo says '$got' - refresh registry facts (and anything that relies on them)"; fi
done < <(jq -r '.facts[] | @base64' "$R")
# toolchain pins agree with facts
for pair in "protoc:protoc-ci-pin" "protoc-gen-go:protoc-gen-go-ci-pin"; do
  tool=${pair%%:*}; fact=${pair##*:}
  exp=$(jq -r --arg t "$tool" '.tools[$t].expected // ""' "$R"); val=$(jq -r --arg f "$fact" '.facts[] | select(.id == $f) | .value' "$R")
  case "$exp" in *"$val"*) pass=$((pass + 1)); echo "PASS  tools.$tool.expected contains fact $fact ($val)";;
    *) fail=$((fail + 1)); echo "FAIL  tools.$tool.expected '$exp' does not contain fact $fact '$val'";; esac
done
# skills carry no volatile values (they drift silently); historical examples are labelled
bad=$(grep -rnE "Total 12|[0-9]+ document\(s\) validated, [1-9]|30 discovered|CIs? (bootstrap|pin) \`?sgl-v[0-9]|currently sgl-v|at \`?5023a3d\`?:|protoc 29\.[0-9]|Google\.Protobuf 3\.[0-9]" "$ROOT/skills" || true)
if [ -z "$bad" ]; then pass=$((pass + 1)); echo "PASS  skills carry no volatile point-in-time values"
else fail=$((fail + 1)); echo "FAIL  volatile values in skills:"; echo "$bad" | head -5; fi
total=$((pass + fail + skip)); echo "facts tests: $total run, $pass passed, $fail failed, $skip skipped"
[ "$pass" -gt 0 ] && [ "$fail" -eq 0 ]
