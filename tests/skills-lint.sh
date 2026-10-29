#!/usr/bin/env bash
# Lint every skill against references/skill-contract.md. Mechanical checks only; the
# semantic review is the human/LLM review step.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
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
    kind=$(jq -r --arg s "$s" '.skills[$s].kind // ""' registry.json)
    if [ "$kind" = "tech" ]; then secs=("Applies when" "Scope" "Architecture" "Idioms" "Pitfalls" "Testing" "Tools")
    else secs=("Applies when" "Scope" "Validation" "Human gates" "Review checklist" "Report additions"); fi
    for sec in "${secs[@]}"; do
      grep -qE "^## .*${sec}" "$f" && ok || bad "$s: missing section '## ${sec}'"
    done
    [ -n "$kind" ] && ok || bad "$s: not registered in registry.skills"
    owned=$(jq --arg s "$s" '[.modules[] | select((.skills // []) | index($s))] + [.contracts[] | select(.driver == $s)] | length' registry.json)
    if [ "$kind" = "tech" ]; then
      grep -q '^> \*\*Supporting skill, never the owner:\*\* invoke the lead' "$f" && ok || bad "$s: tech skill lacks the 'invoke the lead first' guard"
      # reachable through routing.tech: every used_by skill must point the agent at it
      # every Pitfalls bullet cites the file (path or path:line) or issue (#n) that proves it
      uncited=$(python3 -B - "$f" <<'PYC'
import re, sys
m = re.search(r"^## Pitfalls\n(.*?)(?=^## |\Z)", open(sys.argv[1]).read(), re.M | re.S)
cite = re.compile(r"`[^`]*(/|\.(cs|md|go|json|ya?ml|asmdef|asset|csproj|sh|py|proto|sql|uxml|uss))[^`]*`|#\d+|:\d+")
for b in re.split(r"\n(?=- )", "\n" + (m.group(1).strip() if m else "")):
    if b.strip().startswith("- ") and not cite.search(b):
        print(b.strip()[:90])
PYC
)
      [ -z "$uncited" ] && ok || bad "$s: Pitfalls bullet without a cited file or issue: $(head -1 <<<"$uncited")"
      for u in $(jq -r --arg s "$s" '.skills[$s].used_by[]?' registry.json); do
        grep -q "rpg-factory:$s" "skills/$u/SKILL.md" && ok || bad "$s: used_by skill $u never names rpg-factory:$s"
      done
    else
      [ "$owned" -gt 0 ] && ok || bad "$s: owns no registry module or contract (unreachable by routing)"
    fi
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

# dev tools: every non-core skill has a ## Tools section; it names (backticked) every dev_tools id whose
# used_by lists the skill; every tool a bullet leads with is a registered dev_tools id
tools_out=$(python3 -B - "$ROOT" <<'PY3'
import glob, json, os, re, sys
root = sys.argv[1]
reg = json.load(open(f"{root}/registry.json"))
ids = {t["id"] for t in reg.get("dev_tools", [])}
for f in sorted(glob.glob(f"{root}/skills/*/SKILL.md")):
    s = os.path.basename(os.path.dirname(f))
    if reg["skills"].get(s, {}).get("kind") == "core":
        continue
    m = re.search(r"^## Tools\n(.*?)(?=^## |\Z)", open(f, encoding="utf-8").read(), re.M | re.S)
    if not m:
        print(f"{s}: missing section '## Tools'"); continue
    sec = m.group(1)
    for t in reg.get("dev_tools", []):
        if s in t.get("used_by", []) and f"`{t['id']}`" not in sec:
            print(f"{s}: ## Tools does not name dev tool `{t['id']}` (registry used_by lists {s})")
    for line in re.findall(r"^- (.*)$", sec, re.M):
        lead = line.split(":", 1)[0] if ":" in line else ""
        for name in re.findall(r"`([^`]+)`", lead):
            if name not in ids:
                print(f"{s}: ## Tools bullet names `{name}`, not a registry dev_tools id")
            elif s not in next(t for t in reg["dev_tools"] if t["id"] == name)["used_by"]:
                print(f"{s}: ## Tools names `{name}` but registry dev_tools.{name}.used_by lacks {s}")
PY3
); tools_rc=$?
if [ $tools_rc -ne 0 ]; then bad "dev tools sections: lint crashed (rc=$tools_rc): $(tail -1 <<<"$tools_out")"
elif [ -z "$tools_out" ]; then ok; else bad "dev tools sections:"; echo "$tools_out" | sed 's/^/      /' | head -20; fi

# allowed-tools covers every plugin script a skill tells the agent to run (else unattended runs hit a
# permission prompt). Uses: `${CLAUDE_PLUGIN_ROOT}/scripts/<path>` in SKILL.md or references/ (all skills), and
# a backticked bare script name that is a file in scripts/ or scripts/checks/ (non-core skills; factory-core's
# references also document maintainer tools and guards it never runs). An entry `Bash(<interp> ${CLAUDE_PLUGIN_ROOT}/
# scripts/<pattern>:*)` covers a use when <pattern> matches its path under scripts/ (fnmatch: `*` is a wildcard, so
# `checks/*` covers every check) and, when the use names an interpreter, it equals <interp> (Claude Code
# matches the command prefix, so `python3 -B` is not covered by a `python3` entry).
allow_out=$(python3 -B - "$ROOT" <<'PY4'
import fnmatch, glob, os, re, sys
root = sys.argv[1]
names = {os.path.relpath(p, f"{root}/scripts").replace(os.sep, "/")
         for p in glob.glob(f"{root}/scripts/*") + glob.glob(f"{root}/scripts/checks/*") if os.path.isfile(p)}
by_base = {}
for n in names:
    by_base.setdefault(os.path.basename(n), set()).add(n)
for f in sorted(glob.glob(f"{root}/skills/*/SKILL.md")):
    d = os.path.dirname(f); s = os.path.basename(d)
    lines = open(f, encoding="utf-8").read().splitlines()
    end = lines.index("---", 1) if lines[:1] == ["---"] and "---" in lines[1:] else 0
    allowed = next((l[len("allowed-tools: "):] for l in lines[1:end] if l.startswith("allowed-tools: ")), "")
    entries = re.findall(r"Bash\(([^ ()]+) \$\{CLAUDE_PLUGIN_ROOT\}/scripts/([^:()]+):\*\)", allowed)
    srcs = [(f, lines, end)] + [(r, open(r, encoding="utf-8").read().splitlines(), 0) for r in sorted(glob.glob(f"{d}/references/*.md"))]
    for src, text, skip in srcs:
        for i, line in enumerate(text[skip:], skip + 1):
            uses = {(m.group(1), m.group(2)) for m in
                    re.finditer(r"(?:\b((?:bash|sh|python3?)(?: -B)?) )?\$\{CLAUDE_PLUGIN_ROOT\}/scripts/([A-Za-z0-9_./-]+)", line)}
            if s != "factory-core":
                for code in re.findall(r"`([^`]+)`", line):
                    if "CLAUDE_PLUGIN_ROOT" in code:
                        continue
                    for tok in re.findall(r"(?:^|[\s/])([A-Za-z0-9_-]+\.(?:py|sh))\b", code):
                        uses |= {(None, p) for p in by_base.get(tok, ())}
            for interp, path in sorted(uses, key=str):
                if path in names and not any(fnmatch.fnmatchcase(path, pat) and interp in (None, cmd) for cmd, pat in entries):
                    rel = os.path.relpath(src, root).replace(os.sep, "/")
                    print(f"{s}: {rel}:{i} runs {(interp + ' ') if interp else ''}scripts/{path}, not covered by allowed-tools")
PY4
); allow_rc=$?
if [ $allow_rc -ne 0 ]; then bad "allowed-tools coverage: lint crashed (rc=$allow_rc): $(tail -1 <<<"$allow_out")"
elif [ -z "$allow_out" ]; then ok; else while IFS= read -r l; do bad "allowed-tools coverage: $l"; done <<<"$allow_out"; fi

# every skill appears everywhere the plugin lists, routes, tests and documents skills (and no SCAFFOLD: left)
tp_out=$(cd "$ROOT" && CLAUDE_PLUGIN_ROOT="$ROOT" python3 -B scripts/skill-touchpoints.py --all 2>&1)
if [ $? -eq 0 ]; then ok; else bad "skill touchpoints (skill-touchpoints.py --all):"; grep '^MISSING' <<<"$tp_out" | sed 's/^MISSING  /      /' | head -20; fi

# line citations: backticked and anchored (needs no repos; tests/skill-citations.test.sh and the live
# run in run-all.sh check them against the code)
cite_out=$(cd "$ROOT" && CLAUDE_PLUGIN_ROOT="$ROOT" python3 -B scripts/checks/skill-citations.py --offline 2>&1); cite_rc=$?
if [ $cite_rc -eq 0 ]; then ok; else bad "line citations (skill-citations.py --offline):"; grep '^FAIL' <<<"$cite_out" | sed 's/^FAIL  /      /' | head -20; tail -1 <<<"$cite_out" | sed 's/^/      /'; fi

# plugin boundaries: factory-core must hand design work to game-ai-workflows and web projects to
# web-game-factory, and no Factory skill may claim their triggers
desc=$(sed -n 's/^description: //p' "$ROOT/skills/factory-core/SKILL.md")
case "$desc" in *game-ai-workflows*web-game-factory*) ok;; *) bad "factory-core description lacks the game-ai-workflows / web-game-factory boundary";; esac
claims=$(grep -lE "^description: .*(game design document|GDD|feature registry|web game)" "$ROOT"/skills/*/SKILL.md | grep -v factory-core || true)
if [ -z "$claims" ]; then ok; else bad "skills claim other plugins' triggers: $claims"; fi

# English-only is report-only during baseline cleanup; show findings as informational output.
english_out=$(cd "$ROOT" && python3 -B scripts/checks/english-only.py --report 2>&1)
if [ $? -eq 0 ]; then
  while IFS= read -r line; do echo "INFO  $line"; done <<<"$english_out"
else
  echo "INFO  English-only report unavailable: $english_out"
fi

# parallel-work policy: one canonical copy in factory-core/references/parallel-work.md, linked from the
# files that defer to it, never blocking, and keeping the release and human-gate rules
pw="skills/factory-core/references/parallel-work.md"
if [ -f "$pw" ]; then
  ok
  for f in skills/factory-core/SKILL.md skills/factory-core/references/git-safety.md skills/factory-core/references/report.md; do
    grep -q 'parallel-work\.md' "$f" && ok || bad "parallel-work: $f does not link parallel-work.md"
  done
  for p in 'Lead/Integrator' 'worker-start' 'stable candidate commit'; do
    copies=$(grep -liF -- "$p" skills/*/SKILL.md skills/*/references/*.md 2>/dev/null | grep -vxF "$pw")
    [ -z "$copies" ] && ok || bad "parallel-work: policy phrase '$p' copied outside $pw: $(echo $copies)"
  done
  blocking=$(grep -niE 'ask the user|prompt the user|wait for (the user.s |user |explicit )?(approval|confirmation)|(get|obtain|need|needs|require|requires) (the user.s |user |explicit )?(approval|confirmation)|confirm with the user|until the user|permissionDecision' "$pw")
  [ -z "$blocking" ] && ok || bad "parallel-work: blocking wording in $pw: $(head -1 <<<"$blocking")"
  gates=$(grep -n 'gate-create' "$pw" | grep -viE '\bnever\b')
  [ -z "$gates" ] && ok || bad "parallel-work: gate-create outside a 'never' sentence: $(head -1 <<<"$gates")"
  if grep -qF 'orca worktree rm' "$pw"; then  # it also deletes merged local branches; the policy keeps branches
    grep -qF 'also deletes the checked-out local branch' "$pw" && ok       || bad "parallel-work: $pw cites orca worktree rm without its branch-deletion caveat"
  fi
  for p in 'rule 5' 'explicit release authorization' 'human_gates'; do
    grep -qF -- "$p" "$pw" && ok || bad "parallel-work: safety rule missing from $pw: '$p'"
  done
else
  bad "parallel-work: $pw missing"
fi

total=$((pass + fail))
echo "skills lint: $total checks, $pass passed, $fail failed"
[ "$fail" -eq 0 ] && [ "$pass" -gt 0 ]
