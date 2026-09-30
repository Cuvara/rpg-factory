#!/usr/bin/env bash
# check-registry.sh — validate registry.json structure and that every path it names
# exists in the workspace. Read-only. Exit 0 only if zero problems and >0 items checked.
#
# Usage: check-registry.sh [--structure-only]
#   --structure-only  skip on-disk path checks (for machines without the workspace)
set -uo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
REGISTRY="$PLUGIN_ROOT/registry.json"
structure_only=false
[ "${1:-}" = "--structure-only" ] && structure_only=true

if ! jq empty "$REGISTRY" 2>/dev/null; then echo "FAIL: $REGISTRY is not valid JSON"; exit 1; fi

# ---- structure (jq emits one line per problem)
problems=$(jq -r '
  . as $r
  | ([.modules[].id]) as $ids
  | (
      (["schema_version","workspace","tiers","result_states","tools","repos","modules","global_rules"][]
        | select($r[.] == null) | "missing top-level key: \(.)"),
      ($ids | group_by(.) | map(select(length > 1))[] | "duplicate module id: \(.[0])"),
      (.modules[] as $m
        | (["id","repo","paths","responsibility","depends_on","checks","rules","generated","tools","obligations"][]
             | select($m[.] == null) | "\($m.id // "?"): missing field \(.)"),
          (select(($r.repos[$m.repo] // null) == null) | "\($m.id): unknown repo \($m.repo)"),
          (select(($m.paths | length) == 0) | "\($m.id): empty paths"),
          ($m.depends_on[] | . as $d | select(($ids | index($d)) == null) | "\($m.id): depends_on unknown module \(.)"),
          ($m.tools[] | select(($r.tools[.] // null) == null) | "\($m.id): unknown tool \(.)"),
          (["fast","extended","external"][] as $t
            | ($m.checks[$t] // null) as $cs
            | if $cs == null then "\($m.id): checks.\($t) missing"
              else ($cs[] | (["id","run","evidence"][] as $f | select(.[$f] == null) | "\($m.id): \($t) check missing \($f)"),
                            (.run | [scan("\\{[a-z_]+\\}")] | .[] | select(. != "{dotnet}" and . != "{plugin_root}")
                               | "\($m.id): unknown placeholder \(.)"))
              end)
        )
    )
' "$REGISTRY")
structure_count=$(jq '[.modules[] | .checks[]?[]?] | length' "$REGISTRY")
modules_count=$(jq '.modules | length' "$REGISTRY")

# ---- on-disk paths
missing=""; path_count=0
if ! $structure_only; then
  ws="${RPG_FACTORY_WORKSPACE:-$(jq -r '.workspace.root_default' "$REGISTRY")}"
  while IFS=$'\t' read -r owner rel; do
    [ -z "$rel" ] && continue
    rel="${rel%%#*}"                 # strip doc anchors
    case "$rel" in *'*'*) continue ;; esac   # globs are patterns, not paths
    path_count=$((path_count + 1))
    [ -e "$ws/$rel" ] || missing+="$owner: missing path $rel"$'\n'
  done < <(jq -r '
      (.repos | to_entries[] | .value.path as $p
        | ["repo:" + .key, $p], (.value.instructions[] | ["repo:" , $p + "/" + .])),
      (.repos as $repos | .modules[] | $repos[.repo].path as $p | .id as $id
        | (.paths[], (.claude_md // empty), (.changelog // empty), .docs[], .generated[])
        | [$id, $p + "/" + .]),
      (.workspace.root_markers[] | ["workspace", .])
      | @tsv' "$REGISTRY")
  # plugin-relative files referenced via {plugin_root}
  while IFS= read -r rel; do
    path_count=$((path_count + 1))
    [ -e "$PLUGIN_ROOT/$rel" ] || missing+="plugin: missing $rel"$'\n'
  done < <(jq -r '.modules[].checks[][]?.run | scan("\\{plugin_root\\}/([^ \"]+)") | .[0]' "$REGISTRY" | sort -u)
fi

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
  echo "OK: $modules_count modules, $structure_count checks structurally valid (paths not checked)"
else
  echo "OK: $modules_count modules, $structure_count checks structurally valid; $path_count referenced paths exist"
fi
