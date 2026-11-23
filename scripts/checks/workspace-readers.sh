#!/usr/bin/env bash
# workspace-readers.sh - the workspace reader guard. Read-only: it only greps ROOT, never writes.
#
# Usage: workspace-readers.sh [ROOT]      (ROOT defaults to the current directory)
#
# Rules, applied to scripts/ and tests/ under ROOT:
#   1. A jq reader of the registry's default workspace key must map the path on the same line
#      (rpgf_platform_path); fixtures under tests/fixtures/ are exempt except check-registry-p4.sh.
#   2. A Python file under scripts/ must not read that key itself: scripts/lib/workspace.py and
#      scripts/lib/fstate.py own the read.
#   3. A Python file under scripts/ must not call the default-workspace function directly except
#      the shared helpers under scripts/lib/.
# Output: one 'file:line:text' line per violation. Exit 0 = clean, 1 = at least one violation,
# 2 = usage error (missing ROOT directory, extra arguments).
set -uo pipefail

if [ "$#" -gt 1 ]; then
  echo "usage: workspace-readers.sh [ROOT]" >&2
  exit 2
fi
root=${1:-.}
if [ ! -d "$root" ]; then
  echo "workspace-readers.sh: not a directory: $root" >&2
  exit 2
fi

# The patterns are assembled so this file's own source never matches them.
key='root_''default'
jq_pattern='jq.*\.workspace\.'"$key"
fn_pattern='default_workspace\(\)'

found=0
report() {
  printf '%s:%s:%s\n' "$1" "$2" "$3"
  found=1
}

# jq readers must map on the same line.
while IFS=: read -r file line text; do
  case "$file" in tests/fixtures/*) [ "$file" = tests/fixtures/check-registry-p4.sh ] || continue ;; esac
  case "$text" in *rpgf_platform_path*) continue ;; esac
  report "$file" "$line" "$text"
done < <(cd "$root" && grep -rInE "$jq_pattern" scripts tests 2>/dev/null || true)

# Python readers must use the shared helper.
while IFS=: read -r file line text; do
  case "$file" in scripts/lib/workspace.py|scripts/lib/fstate.py) continue ;; esac
  report "$file" "$line" "$text"
done < <(cd "$root" && grep -rIn --include='*.py' "$key" scripts 2>/dev/null || true)

while IFS=: read -r file line text; do
  case "$file" in scripts/lib/*) continue ;; esac
  report "$file" "$line" "$text"
done < <(cd "$root" && grep -rInE --include='*.py' "$fn_pattern" scripts 2>/dev/null || true)

[ "$found" -eq 0 ]
