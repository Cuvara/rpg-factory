#!/usr/bin/env bash
# check-registry.sh — validate registry.json structure and that every path it names
# exists in the workspace. Read-only. Exit 0 only if zero problems and >0 items checked.
#
# Usage: check-registry.sh [--structure-only] [--registry <file>]
#   --structure-only  skip on-disk path checks (for machines without the workspace)
#   --registry <file> validate a registry other than the default
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/lib/compat.sh"

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
REGISTRY="$PLUGIN_ROOT/registry.json"
structure_only=false
while [ "$#" -gt 0 ]; do
  case "$1" in
    --structure-only) structure_only=true; shift ;;
    --registry) [ "$#" -ge 2 ] || { echo "FAIL: --registry needs a file"; exit 1; }; REGISTRY="$2"; shift 2 ;;
    *) echo "FAIL: unknown argument $1"; exit 1 ;;
  esac
done

if ! jq empty "$REGISTRY" 2>/dev/null; then echo "FAIL: $REGISTRY is not valid JSON"; exit 1; fi
# a duplicate key is valid JSON, and jq and Python both keep the last one silently
dups=$(python3 -B -c '
import json, sys
def hook(pairs):
    seen = set()
    for k, _ in pairs:
        if k in seen:
            print(k)
        seen.add(k)
    return dict(pairs)
json.load(open(sys.argv[1], encoding="utf-8"), object_pairs_hook=hook)' "$REGISTRY" 2>&1)
if [ -n "$dups" ]; then echo "FAIL: $REGISTRY has duplicate keys (the last one wins silently): $(sort -u <<<"$dups" | tr '\n' ' ')"; exit 1; fi

# ---- structure (jq emits one line per problem)
problems=$(jq -r '
  . as $r
  | ([.modules[].id]) as $ids
  | (
      (["schema_version","workspace","tiers","result_states","tools","repos","modules","global_rules"][]
        | select($r[.] == null) | "missing top-level key: \(.)"),
      ($ids | group_by(.) | map(select(length > 1))[] | "duplicate module id: \(.[0])"),
      (select(($r.domains.engineering // null) == null) | "missing domain: engineering"),
      (($r.domains // {}) | keys[] | select(test("^[a-z][a-z0-9-]*$") | not) | "domain id \(.) must match ^[a-z][a-z0-9-]*$"),
      (($r.domains // {}) | to_entries[] | select((.value.status // "") | IN("active","planned","foundation") | not) | "domain \(.key): status must be active|planned|foundation"),
      (($r.domains // {}) | to_entries[] as $d
        | (($d.value.repos // [])[] | select(($r.repos[.] // null) == null) | "domain \($d.key): unknown repo \(.)")),
      (($r.domains // {}) | to_entries[] as $d
        | select(($d.value.lead // null) != null) | $d.key as $did | $d.value.lead as $lead
        | if ($r.skills[$lead] // null) == null then "domain \($did): unknown lead skill \($lead)"
          elif (($r.skills[$lead].kind // "") | IN("repo","cross-repo") | not) then "domain \($did): lead \($lead) must be a repo or cross-repo skill"
          elif (($r.skills[$lead].domain // "engineering") != $did) then "domain \($did): lead \($lead) belongs to domain \($r.skills[$lead].domain // "engineering")"
          else empty end),
      (($r.skills // {}) | to_entries[] | .key as $id | (.value.domain // "engineering") as $d
        | select(($r.domains[$d] // null) == null) | "skill \($id): unknown domain \($d)"),
      ($r.modules[] | .id as $id | (.domain // "engineering") as $d
        | select(($r.domains[$d] // null) == null) | "\($id): unknown domain \($d)"),
      (($r.contracts // [])[] | .id as $id | (.domain // "engineering") as $d
        | select(($r.domains[$d] // null) == null) | "contract \($id): unknown domain \($d)"),
      ($r.modules[] as $m | ($m.domain // "engineering") as $d
        | select(($r.domains[$d].repos // []) | index($m.repo) == null)
        | "\($m.id): repo \($m.repo) is not in domain \($d)"),
      (($r.domains // {}) | to_entries[] as $d | $d.key as $did
        | (($d.value.quality_gates // [])[] as $gate
          | select([$r.modules[] | select((.domain // "engineering") == $did) | .checks[]?[]? | .id] | index($gate) == null)
          | "domain \($did): unknown quality gate \($gate)")),
      (($r.domains // {}) | to_entries[] as $d | $d.key as $did
        | (($d.value.handoffs // [])[] as $handoff
          | select([($r.contracts // [])[].id] | index($handoff) == null)
          | "domain \($did): unknown handoff \($handoff)")),
      (($r.domains // {}) | to_entries[] as $d | $d.key as $did
        | (($d.value.human_gates // [])[] as $gate
          | select([($r.human_gates // [])[].id] | index($gate) == null)
          | "domain \($did): unknown human gate \($gate)")),
      (([ (($r.skills // {}) | to_entries[] | {id:.key, role:.value.role}), ($r.modules[] | {id:.id, role:.role}), (($r.contracts // [])[] | {id:("contract " + .id), role:.role}) ][]) 
        | select(.role != null and (.role | IN("orchestrator","implementer","reference") | not))
        | "\(.id): role must be orchestrator|implementer|reference"),
      (.modules[] as $m
        | (["id","repo","paths","responsibility","depends_on","checks","rules","generated","tools","obligations"][]
             | select($m[.] == null) | "\($m.id // "?"): missing field \(.)"),
          (select(($r.repos[$m.repo] // null) == null) | "\($m.id): unknown repo \($m.repo)"),
          (select(($m.paths | length) == 0) | "\($m.id): empty paths"),
          ($m.depends_on[] | . as $d | select(($ids | index($d)) == null) | "\($m.id): depends_on unknown module \(.)"),
          ($m.tools[] | select(($r.tools[.] // null) == null) | "\($m.id): unknown tool \(.)"),
          (($m.skills // [])[] | select(($r.skills[.] // null) == null) | "\($m.id): unknown skill \(.)"),
          (($m.gates // [])[] | select(type != "string") | "\($m.id): gate must be a string"),
          (["fast","extended","external"][] as $t
            | ($m.checks[$t] // null) as $cs
            | if $cs == null then "\($m.id): checks.\($t) missing"
              else ($cs[] | (["id","run","evidence"][] as $f | select(.[$f] == null) | "\($m.id): \($t) check missing \($f)"),
                            (.run | [scan("\\{[a-z_]+\\}")] | .[] | select(. != "{dotnet}" and . != "{plugin_root}")
                               | "\($m.id): unknown placeholder \(.)"))
              end)
        ),
      (($r.contracts // [])[] as $c
        | (["id","summary","source","copies","driver","gate","evidence"][] | select(. as $k | $c | has($k) | not) | "contract \($c.id // "?"): missing field \(.)"),
          (([$c.source] + ($c.copies // []) + ($c.upstream // []) + ($c.watchers // []))[] | select(($r.repos[.repo] // null) == null) | "contract \($c.id): unknown repo \(.repo)"),
          (select(($c.driver // null) != null and ($r.skills[$c.driver] // null) == null) | "contract \($c.id): unknown driver skill \($c.driver)")),
      (($r.contracts // []) | map(.id) | group_by(.) | map(select(length > 1))[] | "duplicate contract id: \(.[0])"),
      (($r.skills // {}) | to_entries[] | select((.value.kind // "") | IN("repo","cross-repo","core","tech") | not) | "skill \(.key): kind must be repo|cross-repo|core|tech"),
      (($r.skills // {}) | to_entries[] | .key as $s | (.value.cite_roots // {}) | to_entries[]
        | select((.value | split(":")[0]) as $k | ($r.repos[$k] // null) == null)
        | "skill \($s): cite_roots \(.key | tojson) -> unknown repo in \(.value)"),
      (($r.skills // {}) | to_entries[] | select(.value.kind == "tech") as $t
        | (select(($t.value.used_by // []) | length == 0) | "tech skill \($t.key): used_by (repo/cross-repo skills) missing"),
          (($t.value.used_by // [])[] | select((($r.skills[.].kind) // "") | IN("repo","cross-repo") | not)
             | "tech skill \($t.key): used_by \(.) is not a repo/cross-repo skill"),
          (select([$r.modules[] | select((.skills // []) | index($t.key))] + [($r.contracts // [])[] | select(.driver == $t.key)] | length > 0)
             | "tech skill \($t.key): must not own a module or contract (tech skills are never routed as lead/leg)")),
      (($r.dev_tools // []) | map(.id) | group_by(.) | map(select(length > 1))[] | "duplicate dev_tools id: \(.[0])"),
      (($r.dev_tools // [])[] as $d
        | (["id","kind","probes","provides","used_by","required"][] | select(. as $k | $d | has($k) | not) | "dev_tools \($d.id // "?"): missing field \(.)"),
          (select((($d.kind // "") | IN("mcp","plugin","binary","service")) | not) | "dev_tools \($d.id): kind must be mcp|plugin|binary|service"),
          (($d.used_by // [])[] | select(($r.skills[.] // null) == null) | "dev_tools \($d.id): used_by unknown skill \(.)"),
          (($d.probes // [])[] | split("|")[] | . as $p | ($p | split(":")) as $pp
             | if ($pp | length) != 2 or ($pp[1] | length) == 0 or ($pp[0] | IN("bin","tool","service","mcp","plugin") | not)
                 then "dev_tools \($d.id): bad probe \($p) (bin|tool|service|mcp|plugin:<name>)"
               elif $pp[0] == "tool" and ($r.tools[$pp[1]] // null) == null then "dev_tools \($d.id): probe \($p) names an unknown tool"
               elif $pp[0] == "service" and (($r.services // {})[$pp[1]] // null) == null then "dev_tools \($d.id): probe \($p) names an unknown service"
               else empty end),
          (select(($d.fallback // "") | length == 0) | "dev_tools \($d.id): every tool needs a fallback (what a skill does when it is not OK)")),
      (($r.skills // {}) | to_entries[] | select((.value.order | type) != "number") | "skill \(.key): order (number) missing - lead precedence needs it"),
      (($r.skills // {}) | [to_entries[] | .value.order] | group_by(.) | map(select(length > 1))[] | "duplicate skill order \(.[0]) - routing would be ambiguous"),
      ($r.modules | map(select(.fallback != true)) | [ .[] | .repo as $rp | .id as $id | .paths[] | {k: "\($rp)|\(.)", id: $id} ]
        | group_by(.k) | map(select(length > 1))[] | "duplicate path \(.[0].k | split("|")[1]) in repo \(.[0].k | split("|")[0]): \(map(.id) | join(", ")) - mapping would depend on registry order"),
      ($r.modules | map(select(.fallback == true)) | group_by(.repo) | map(select(length > 1))[] | "repo \(.[0].repo) has more than one fallback module"),
      ($r.repos | keys[] as $k | select([$r.modules[] | select(.repo == $k and .fallback == true)] | length == 0) | "repo \($k) has no fallback (<repo>.root) module"),
      (($r.human_gates // [])[] | select(.id == null or .rule == null) | "human_gates entry missing id/rule"),
      (($r.human_gates // []) | map(.id)) as $gids
      | ($r.modules[] | .id as $mid | (.gates // [])[] | select(. as $g | $gids | index($g) | not) | "\($mid): unknown gate \(.)"),
      (($r.contracts // [])[] | select(.gate != null) | .id as $cid | .gate | select(. as $g | $gids | index($g) | not) | "contract \($cid): unknown gate \(.)")
    )
' "$REGISTRY")
structure_count=$(jq '[.modules[] | .checks[]?[]?] | length' "$REGISTRY")
modules_count=$(jq '.modules | length' "$REGISTRY")

# ---- on-disk paths
missing=""; path_count=0
if ! $structure_only; then
  ws="${RPG_FACTORY_WORKSPACE:-$(jq -r '.workspace.root_default' "$REGISTRY")}"
  optional_absent="|"
  while IFS=$'\t' read -r key rel; do
    if [ ! -d "$ws/$rel" ]; then
      echo "optional repo $key absent (not checked)"
      optional_absent+="$key|"
    fi
  done < <(jq -r '.repos | to_entries[] | select(.value.optional == true) | [.key, .value.path] | @tsv' "$REGISTRY")
  repo_skipped() { case "$optional_absent" in *"|$1|"*) return 0 ;; *) return 1 ;; esac; }
  while IFS=$'\t' read -r owner rel repo; do
    [ -z "$rel" ] && continue
    repo_skipped "$repo" && continue
    rel="${rel%%#*}"                 # strip doc anchors
    case "$rel" in *'*'*) continue ;; esac   # globs are patterns, not paths
    path_count=$((path_count + 1))
    [ -e "$ws/$rel" ] || missing+="$owner: missing path $rel"$'\n'
  done < <(jq -r '
      (.repos | to_entries[] | .key as $k | .value.path as $p
        | ["repo:" + $k, $p, $k], (.value.instructions[] | ["repo:" + $k, $p + "/" + ., $k])),
      (.repos as $repos | .modules[] | .repo as $k | $repos[$k].path as $p | .id as $id
        | (.paths[], (.claude_md // empty), (.changelog // empty), .docs[], .generated[])
        | [$id, $p + "/" + ., $k]),
      (.workspace.root_markers[] | ["workspace", ., ""])
      | @tsv' "$REGISTRY")
  while IFS=$'\t' read -r owner rel repo; do
    [ -z "$rel" ] && continue
    repo_skipped "$repo" && continue
    path_count=$((path_count + 1))
    [ -e "$ws/$rel" ] || missing+="$owner: missing path $rel"$'\n'
  done < <(jq -r '.repos as $repos | (.contracts // [])[] | .id as $id
      | ([.source] + (.copies // []) + (.upstream // []) + (.watchers // []))[]
      | ["contract " + $id, $repos[.repo].path + "/" + .path, .repo] | @tsv' "$REGISTRY")
  # every registered skill has a SKILL.md, and every skill dir is registered
  while IFS= read -r sk; do
    path_count=$((path_count + 1))
    [ -f "$PLUGIN_ROOT/skills/$sk/SKILL.md" ] || missing+="skill $sk: missing skills/$sk/SKILL.md"$'\n'
  done < <(jq -r '(.skills // {}) | keys[]' "$REGISTRY")
  for d in "$PLUGIN_ROOT"/skills/*/; do
    sk=$(basename "$d")
    jq -e --arg s "$sk" '(.skills // {})[$s] != null' "$REGISTRY" >/dev/null || missing+="skill dir $sk not registered in registry.skills"$'\n'
  done
  # plugin-relative files referenced via {plugin_root}
  while IFS= read -r rel; do
    path_count=$((path_count + 1))
    [ -e "$PLUGIN_ROOT/$rel" ] || missing+="plugin: missing $rel"$'\n'
  done < <(jq -r '.modules[].checks[][]?.run | scan("\\{plugin_root\\}/([^ \" ]+)") | .[0]' "$REGISTRY" | sort -u)
fi

# JSON Schema (docs/registry.schema.json) when python3-jsonschema is installed
schema_state="skipped (python3 jsonschema not installed)"
if python3 -c "import jsonschema" 2>/dev/null; then
  sch_err=$(python3 -B - "$REGISTRY" "$PLUGIN_ROOT/docs/registry.schema.json" <<'PY3'
import json, sys, jsonschema
r, s = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
for e in jsonschema.Draft202012Validator(s).iter_errors(r):
    print("schema: " + "/".join(str(p) for p in e.path) + ": " + e.message[:160])
PY3
)
  if [ -n "$sch_err" ]; then problems="${problems:+$problems$'\n'}$sch_err"; schema_state="FAILED"; else schema_state="valid"; fi
fi

# human_gates[].match must compile as Python regexes (the guard uses them)
rx_err=$(python3 -B - "$REGISTRY" <<'PY2'
import json, re, sys
for g in json.load(open(sys.argv[1])).get("human_gates", []):
    if g.get("match"):
        try: re.compile(g["match"])
        except re.error as e: print(f"human gate {g['id']}: bad regex: {e}")
PY2
)
[ -n "$rx_err" ] && problems="${problems:+$problems$'\n'}$rx_err"

all=$(printf '%s%s' "${problems:+$problems$'\n'}" "$missing" | sed '/^$/d')
if [ -n "$all" ]; then
  echo "$all"
  echo "FAIL: $(printf '%s\n' "$all" | wc -l) problem(s)"
  exit 1
fi
if [ "$modules_count" -eq 0 ] || [ "$structure_count" -eq 0 ]; then
  echo "FAIL: registry has $modules_count modules / $structure_count checks - nothing was validated"; exit 1
fi
if $structure_only; then
  echo "OK: $modules_count modules, $structure_count checks structurally valid, JSON Schema $schema_state (paths not checked)"
else
  echo "OK: $modules_count modules, $structure_count checks structurally valid, JSON Schema $schema_state; $path_count referenced paths exist"
fi
