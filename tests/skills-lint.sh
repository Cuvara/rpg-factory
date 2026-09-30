#!/usr/bin/env bash
# Lint every skill against references/skill-contract.md. Mechanical checks only; the
# semantic review is the human/LLM review step.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1
pass=0; fail=0
ok()  { pass=$((pass + 1)); }
bad() { fail=$((fail + 1)); echo "FAIL  $1"; }

fm() { # field value from YAML frontmatter
  awk -v k="$2" 'NR==1&&$0!="---"{exit} NR>1&&$0=="---"{exit} NR>1{ if (index($0, k": ")==1) { sub("^" k ": ", ""); print; exit } }' "$1"
}

for dir in skills/*/; do
  s=$(basename "$dir"); f="$dir/SKILL.md"
  [ -f "$f" ] || { bad "$s: SKILL.md missing"; continue; }
  [ "$(head -1 "$f")" = "---" ] && ok || bad "$s: no frontmatter"
  [ "$(fm "$f" name)" = "$s" ] && ok || bad "$s: frontmatter name != directory"
  desc=$(fm "$f" description)
  [ "${#desc}" -ge 120 ] && ok || bad "$s: description too short to be semantic (${#desc} chars)"
  grep -qiE "use (at|when)" <<<"$desc" && ok || bad "$s: description must say when to use it ('Use when ...')"
  { [ "$s" = "factory-core" ] || grep -qiE "\bnot\b" <<<"$desc"; } && ok || bad "$s: description must say what it is NOT for"
  [ -n "$(fm "$f" argument-hint)" ] && ok || bad "$s: argument-hint missing"
  grep -q 'factory-context.sh' <<<"$(fm "$f" allowed-tools)" && ok || bad "$s: allowed-tools must grant factory-context.sh"
  lines=$(wc -l < "$f")
  [ "$lines" -le 160 ] && ok || bad "$s: SKILL.md has $lines lines (> 160)"
  refs=$(ls "$dir/references" 2>/dev/null | wc -l)
  { [ "$s" = "factory-core" ] || [ "$refs" -le 3 ]; } && ok || bad "$s: $refs reference files (> 3)"
  for r in $(grep -oE 'references/[A-Za-z0-9_.-]+\.md' "$f" | sort -u); do
    [ -f "$dir/$r" ] && ok || bad "$s: links missing $r"
  done
  if grep -qE 'TODO|TBD|FIXME' "$f" "$dir"/references/*.md 2>/dev/null; then bad "$s: TODO/TBD left"; else ok; fi
  if [ "$s" != "factory-core" ]; then
    grep -q 'Prerequisite:\*\* follow `rpg-factory:factory-core`' "$f" && ok || bad "$s: missing Core prerequisite line"
    for sec in "Applies when" "Scope" "Validation" "Human gates" "Review checklist" "Report additions"; do
      grep -qE "^## .*${sec}" "$f" && ok || bad "$s: missing section '## ${sec}'"
    done
    jq -e --arg s "$s" '.skills[$s].kind != null' registry.json >/dev/null && ok || bad "$s: not registered in registry.skills"
    owned=$(jq --arg s "$s" '[.modules[] | select((.skills // []) | index($s))] + [.contracts[] | select(.driver == $s)] | length' registry.json)
    [ "$owned" -gt 0 ] && ok || bad "$s: owns no registry module or contract (unreachable by routing)"
  fi
  # agents never tag: a skill may mention tags only as the lead's action
  if grep -nE '(^|[`$ ])git (-C [^ ]+ )?tag [^-]|git push [^`]*--tags' "$f" "$dir"/references/*.md 2>/dev/null | grep -viE 'lead|human|deny|denies|denied|never|guard|not |no agent|agents never|by the lead' >/dev/null; then
    bad "$s: instructs an agent to create/push a tag"; grep -nE '(^|[`$ ])git (-C [^ ]+ )?tag [^-]|git push [^`]*--tags' "$f" "$dir"/references/*.md | head -3
  else ok; fi
  # never create another feature registry
  if grep -nE '(features\.yaml|docs/registry/|\.ai/)' "$f" "$dir"/references/*.md 2>/dev/null | grep -viE 'never|not |game-ai-workflows' >/dev/null; then
    bad "$s: references a feature registry"; else ok; fi
done
# registry is the single source of module rules: no skill may copy one (>=50% of its 8-word shingles)
dups=$(python3 -B - "$ROOT" <<'PY2'
import glob, json, re, sys
root = sys.argv[1]
reg = json.load(open(f"{root}/registry.json"))
sh = lambda t, n=8: (lambda w: {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)})(re.findall(r"[A-Za-z0-9_./#*-]+", t.lower()))
rules = [(m["id"], x, sh(x)) for m in reg["modules"] for x in m["rules"]] + [(g["id"], g["rule"], sh(g["rule"])) for g in reg["global_rules"]]
for f in sorted(glob.glob(f"{root}/skills/*/SKILL.md") + glob.glob(f"{root}/skills/*/references/*.md")):
    S = sh(open(f).read())
    for mid, x, s in rules:
        if s and len(s & S) / len(s) >= 0.5:
            print(f"{f.replace(root + '/', '')}: copies registry rule of {mid}: {x[:80]}")
PY2
)
if [ -z "$dups" ]; then ok; else bad "skill text duplicates registry rules:"; echo "$dups" | head -5; fi

total=$((pass + fail))
echo "skills lint: $total checks, $pass passed, $fail failed"
[ "$fail" -eq 0 ] && [ "$pass" -gt 0 ]
