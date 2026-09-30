#!/usr/bin/env bash
# factory-context.sh — live Factory snapshot of the RPG MMO workspace.
#
# Read-only. Computes everything on every run and persists nothing: branch,
# working tree, branch diff, touched modules (+ dependents), required checks by
# tier, obligations, toolchain and service availability.
#
# Usage: factory-context.sh [--repo <key>|all] [--base <ref>] [--json]
#                            [--paths <repo-relative path>...]
#   --repo   limit to one repo (default: all)
#   --paths  resolve ONLY these paths (requires --repo) instead of git status. Use it
#            when the tree holds pre-existing user changes, so that validation is
#            derived from the task's own files. Everything after --paths is a path.
#   --base   ref to diff the current branch against (default: origin/<default_branch>,
#            falling back to <default_branch>)
#   --json   machine-readable output instead of markdown
#
# Env: RPG_FACTORY_WORKSPACE  workspace root override.
set -uo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
REGISTRY="$PLUGIN_ROOT/registry.json"
RESOLVE_JQ="$PLUGIN_ROOT/scripts/lib/resolve.jq"

want_repo="all"; base_override=""; format="md"; only_paths=()
while [ $# -gt 0 ]; do
  case "$1" in
    --paths) shift; only_paths=("$@"); break ;;
    --repo) want_repo="${2:-all}"; shift 2 ;;
    --base) base_override="${2:-}"; shift 2 ;;
    --json) format="json"; shift ;;
    -h|--help) sed -n '2,18p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "factory-context: unknown argument '$1'" >&2; exit 2 ;;
  esac
done

if [ ${#only_paths[@]} -gt 0 ] && [ "$want_repo" = "all" ]; then
  echo "factory-context: --paths requires --repo <$(jq -r '.repos | keys | join("|")' "$REGISTRY")>" >&2; exit 2
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "factory-context: jq is required (sudo apt install jq)" >&2; exit 3
fi
if [ ! -f "$REGISTRY" ]; then
  echo "factory-context: registry not found at $REGISTRY" >&2; exit 3
fi

# ---------------------------------------------------------------- workspace root
has_markers() {
  local dir="$1" m
  while IFS= read -r m; do [ -e "$dir/$m" ] || return 1; done < <(jq -r '.workspace.root_markers[]' "$REGISTRY")
  return 0
}
find_workspace() {
  local env_var; env_var=$(jq -r '.workspace.root_env' "$REGISTRY")
  if [ -n "${!env_var:-}" ] && has_markers "${!env_var}"; then echo "${!env_var}"; return 0; fi
  local d="$PWD"
  while [ "$d" != "/" ]; do has_markers "$d" && { echo "$d"; return 0; }; d=$(dirname "$d"); done
  local def; def=$(jq -r '.workspace.root_default' "$REGISTRY")
  has_markers "$def" && { echo "$def"; return 0; }
  return 1
}
WORKSPACE=$(find_workspace) || {
  echo "factory-context: not inside the RPG MMO workspace (markers not found; set RPG_FACTORY_WORKSPACE)" >&2; exit 4; }

# ---------------------------------------------------------------- toolchain
tools_json="{}"; tools_versions="{}"
while IFS= read -r tool; do
  resolved=""
  while IFS= read -r cand; do
    if p=$(command -v "$cand" 2>/dev/null); then resolved="$p"; break; fi
  done < <(jq -r --arg t "$tool" '.tools[$t].candidates[]' "$REGISTRY")
  version=""
  if [ -n "$resolved" ]; then
    args=$(jq -r --arg t "$tool" '.tools[$t].version_args' "$REGISTRY")
    # shellcheck disable=SC2086
    version=$(timeout 10 "$resolved" $args 2>&1 </dev/null | head -n1 | tr -d '\r')
  fi
  tools_json=$(jq -c --arg t "$tool" --arg p "$resolved" '. + {($t): (if $p == "" then null else $p end)}' <<<"$tools_json")
  tools_versions=$(jq -c --arg t "$tool" --arg v "$version" '. + {($t): $v}' <<<"$tools_versions")
done < <(jq -r '.tools | keys[]' "$REGISTRY")

dotnet_bin=$(jq -r '.dotnet // empty' <<<"$tools_json"); dotnet_bin=${dotnet_bin##*/}
subst=$(jq -cn --arg d "${dotnet_bin:-<dotnet-not-found>}" --arg p "$PLUGIN_ROOT" '{"{dotnet}": $d, "{plugin_root}": $p}')

# ---------------------------------------------------------------- services
services_json="{}"
while IFS=$'\t' read -r name probe; do
  state="unreachable"
  if [[ "$probe" == tcp://* ]]; then
    hp=${probe#tcp://}; host=${hp%:*}; port=${hp##*:}
    if timeout 1 bash -c "exec 3<>/dev/tcp/$host/$port" 2>/dev/null; then state="reachable"; fi
  fi
  services_json=$(jq -c --arg n "$name" --arg s "$state" '. + {($n): $s}' <<<"$services_json")
done < <(jq -r '.services | to_entries[] | [.key, .value.probe] | @tsv' "$REGISTRY")

# ---------------------------------------------------------------- per repo
is_protected() {
  local branch="$1"; shift
  local pat
  for pat in "$@"; do
    # shellcheck disable=SC2053
    [[ "$branch" == $pat ]] && return 0
  done
  return 1
}

repo_snapshot() {
  local key="$1" rel dir
  rel=$(jq -r --arg k "$key" '.repos[$k].path' "$REGISTRY")
  dir="$WORKSPACE/$rel"
  if ! git -C "$dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    jq -cn --arg k "$key" --arg d "$dir" '{repo: $k, path: $d, error: "not a git work tree"}'
    return
  fi
  local default branch head upstream ahead="" behind="" base protected=false
  default=$(jq -r --arg k "$key" '.repos[$k].default_branch' "$REGISTRY")
  branch=$(git -C "$dir" branch --show-current)
  [ -z "$branch" ] && branch="(detached)"
  head=$(git -C "$dir" rev-parse --short HEAD)
  mapfile -t prot < <(jq -r --arg k "$key" '.repos[$k].protected_branches[]' "$REGISTRY")
  is_protected "$branch" "${prot[@]}" && protected=true
  if upstream=$(git -C "$dir" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null); then
    read -r behind ahead < <(git -C "$dir" rev-list --left-right --count "$upstream...HEAD" 2>/dev/null || echo "? ?")
  else
    upstream=""
  fi
  if [ -n "$base_override" ]; then base="$base_override"
  elif git -C "$dir" rev-parse --verify -q "origin/$default" >/dev/null; then base="origin/$default"
  else base="$default"; fi

  # Working tree (NUL-separated to survive spaces/quotes in Unity paths).
  local files="[]" entry status path
  if [ ${#only_paths[@]} -gt 0 ]; then
    for path in "${only_paths[@]}"; do
      files=$(jq -c --arg p "${path#./}" '. + [{path: $p, status: "--", source: "given"}]' <<<"$files")
    done
  else
  while IFS= read -r -d '' entry; do
    status="${entry:0:2}"; path="${entry:3}"
    if [[ "$status" == R* || "$status" == C* ]]; then IFS= read -r -d '' _orig; fi
    files=$(jq -c --arg s "$status" --arg p "$path" '. + [{path: $p, status: $s, source: "worktree"}]' <<<"$files")
  done < <(git -C "$dir" status --porcelain=v1 -z --untracked-files=normal)
  fi

  # Commits on this branch not yet in base (only for non-default branches).
  local base_ok=false
  if [ ${#only_paths[@]} -eq 0 ] && [ "$branch" != "$default" ] && git -C "$dir" rev-parse --verify -q "$base" >/dev/null; then
    base_ok=true
    while IFS= read -r -d '' path; do
      files=$(jq -c --arg p "$path" 'if any(.[]; .path == $p) then . else . + [{path: $p, status: "C ", source: "branch"}] end' <<<"$files")
    done < <(git -C "$dir" diff -z --name-only "$base...HEAD" 2>/dev/null)
  fi

  local subs="[]" line
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    subs=$(jq -c --arg l "$line" '. + [{state: ($l[0:1]), sha: ($l[1:] | split(" ")[0]), path: ($l[1:] | split(" ")[1])}]' <<<"$subs")
  done < <(git -C "$dir" submodule status 2>/dev/null)

  local resolved
  resolved=$(jq -c --arg repo "$key" --argjson files "$files" --argjson subst "$subst" \
    --argjson tools "$tools_json" -f "$RESOLVE_JQ" "$REGISTRY")

  jq -cn --arg k "$key" --arg d "$dir" --arg b "$branch" --arg h "$head" --arg u "$upstream" \
    --arg ahead "$ahead" --arg behind "$behind" --arg base "$base" --argjson base_ok "$base_ok" \
    --arg def "$default" --argjson prot "$protected" --argjson subs "$subs" --argjson r "$resolved" \
    '{repo: $k, path: $d, branch: $b, default_branch: $def, protected: $prot, head: $h,
      upstream: (if $u == "" then null else {ref: $u, ahead: $ahead, behind: $behind} end),
      branch_diff_base: (if $base_ok then $base else null end),
      submodules: $subs} + $r'
}

repos_json="[]"
while IFS= read -r key; do
  [ "$want_repo" != "all" ] && [ "$want_repo" != "$key" ] && continue
  repos_json=$(jq -c --argjson s "$(repo_snapshot "$key")" '. + [$s]' <<<"$repos_json")
done < <(jq -r '.repos | keys[]' "$REGISTRY")

snapshot=$(jq -cn --arg w "$WORKSPACE" --arg t "$(date -Iseconds)" --arg pr "$PLUGIN_ROOT" \
  --argjson tools "$tools_json" --argjson tv "$tools_versions" --argjson svc "$services_json" \
  --argjson repos "$repos_json" --slurpfile reg "$REGISTRY" \
  '{generated_at: $t, workspace: $w, plugin_root: $pr,
    toolchain: [$tools | to_entries[] | {tool: .key, resolved: .value, version: $tv[.key],
                expected: ($reg[0].tools[.key].expected // null)}],
    services: $svc, repos: $repos,
    global_rules: $reg[0].global_rules,
    human_gates: ($reg[0].human_gates // []),
    known_issues: ($reg[0].known_issues // [])}')

if [ "$format" = "json" ]; then echo "$snapshot"; exit 0; fi

# ---------------------------------------------------------------- markdown
jq -r '
def bullet(s): "- " + s;
def code(s): "`" + s + "`";
"# Factory context  (" + .generated_at + ")",
"",
"Live snapshot - recompute, never reuse across tasks. Workspace: " + code(.workspace),
"",
"## Toolchain",
"| tool | resolved | version | expected |",
"|---|---|---|---|",
(.toolchain[] | "| \(.tool) | \(.resolved // "**missing**") | \(.version // "") | \(.expected // "") |"),
"",
"## Services",
(.services | to_entries[] | bullet("\(.key): **\(.value)**")),
"",
"## Project-wide rules (registry global_rules)",
(.global_rules[] | bullet("**" + .id + "** - " + .rule + " _(source: " + .source + ")_")),
"",
"## Human gates (always require explicit user authorization)",
(.human_gates[] | bullet("**" + .id + "** - " + .rule)),
"",
"## Known project issues (registry known_issues)",
(.known_issues[] | bullet("**" + .id + "** (" + .scope + ") - " + .summary)),
(.repos[] |
  "",
  "## Repo `\(.repo)` - \(.path)",
  if .error then bullet("ERROR: " + .error) else
  bullet("Branch: **\(.branch)**" + (if .protected then "  (PROTECTED - create a feature branch before committing)" else "" end) + "  HEAD \(.head)"),
  bullet("Upstream: " + (if .upstream then "\(.upstream.ref) ahead \(.upstream.ahead) / behind \(.upstream.behind) (as of last fetch; no fetch performed)" else "none" end)),
  bullet("Branch diff base: " + (.branch_diff_base // "n/a (on default branch or base missing)")),
  "",
  "### Changed paths (\(.files | length))" + (if any(.files[]; .source == "given") then " - resolved from --paths" else " - at the start of a task these are PRE-EXISTING user changes: do not touch, stage, or clean them" end),
  (if (.files | length) == 0 then "_clean_" else
    (.files[] | bullet(code(.status) + " " + code(.path) + " -> " + (.module // "**unmapped**") + (if .source == "branch" then " (committed on branch)" elif .source == "given" then " (given via --paths)" else "" end)))
  end),
  (if (.submodules | map(select(.state != " ")) | length) > 0 then
    "", "### Submodules not at recorded commit",
    (.submodules[] | select(.state != " ") | bullet(code(.state) + " " + code(.path) + " " + .sha[0:10]))
  else empty end),
  "",
  "### Modules",
  bullet("Touched: " + (if (.touched | length) == 0 then "none" else (.touched | map(code(.)) | join(", ")) end)),
  bullet("Dependents (must also validate): " + (if (.dependents | length) == 0 then "none" else (.dependents | map(code(.)) | join(", ")) end)),
  (if (.unmapped | length) > 0 then bullet("Unmapped paths (no registry module - decide manually): " + (.unmapped | map(code(.)) | join(", "))) else empty end),
  (if (.cross_repo_dependents | length) > 0 then
    bullet("Cross-repo dependents (advisory - validate in that repo, via its skill): " + (.cross_repo_dependents | map(code(.id) + " [" + .repo + "]") | join(", ")))
  else empty end),
  (if (.suggested_skills | length) > 0 then
    "", "### Suggested Factory skills (lead drives; legs run inside it; follow-ups belong to later tasks in other repos)",
    (.suggested_skills[] | bullet("**" + .role + "** " + code("rpg-factory:" + .skill) + " - " + (.reasons | join("; "))))
  else empty end),
  (if (.contracts | length) > 0 then
    "", "### Contracts touched (keep every end in sync; its driver skill coordinates the chain)",
    (.contracts[] | bullet(code(.id) + " - " + .summary
        + (if .driver then "  driver: " + code("rpg-factory:" + .driver) else "" end)),
      (.hits[] | "  - " + .role + ": " + code(.path)),
      (.other_ends[] | "  - other end: " + code(.path) + " [" + .repo + "]"),
      (.upstream[] | "  - upstream: " + code(.path) + " [" + .repo + "] - " + (.how // "")),
      (.watchers[] | "  - also pinned (informational): " + code(.path) + " [" + .repo + "] - " + (.how // "")))
  else empty end),
  (if (.gates | length) > 0 then
    "", "### Human gates for this change",
    (.gates[] | bullet(.gate + "  (" + (.sources | join(", ")) + ")"))
  else empty end),
  (if (.generated_hits | length) > 0 then
    "", "### Generated paths touched (change only via their generator)",
    (.generated_hits[] | bullet(code(.path) + " (generated: " + .generated_by + ")"))
  else empty end),
  "",
  "### Required validation",
  (if (.checks | length) == 0 then "_no checks registered for the touched modules (report: not-required)_" else
    (["fast", "extended", "external"][] as $t
     | [ .checks[] | select(.tier == $t) ] as $cs
     | if ($cs | length) == 0 then empty else
         "**" + $t + "**" + (if $t == "fast" then " - required" elif $t == "extended" then " - ask before running" else " - ask, or report not-run:external" end),
         ($cs[] | bullet("[" + .module + (if .via == "dependent" then " (dependent)" else "" end) + "] " + code(.run)
             + (if .cwd != "." then "  (cwd " + code(.cwd) + ")" else "" end)
             + (if .trigger then "  trigger: " + .trigger else "" end)
             + (if (.missing_tools | length) > 0 then "  **MISSING TOOLS: " + (.missing_tools | join(", ")) + "**" else "" end)
             + "\n  evidence: " + .evidence))
       end)
  end),
  (if (.obligations | length) > 0 then
    "", "### Obligations for touched modules",
    (.obligations[] |
      bullet(code(.module) + ": read " + ((.claude_md // "repo CLAUDE.md") | code(.))
        + (if .changelog then "; CHANGELOG " + code(.changelog) + " under [Unreleased]" else "" end)
        + (if (.docs | length) > 0 then "; docs " + (.docs | map(code(.)) | join(", ")) else "" end)),
      (.rules[] | "  - rule: " + .),
      (.obligations[] | "  - must: " + .))
  else empty end)
  end
)
' <<<"$snapshot"
