#!/usr/bin/env bash
# tests/affected.py: which run-all suites a change selects (--affected). Pure: changed-file lists only, plus one
# throwaway repo for `changed` (merge-base diff + untracked).
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
A="$ROOT/tests/affected.py"
TMP="$(mktemp_win)" || exit 1; [ -d "$TMP" ] || exit 1; trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
# sel <want 0|1> <name> <suite> <changed files...>
sel() {
  local want="$1" name="$2" suite="$3"; shift 3
  printf '%s\n' "$@" > "$TMP/ch"; python3 -B "$A" select "$TMP/ch" "$suite"; local rc=$?
  if [ "$rc" = "$want" ]; then pass=$((pass + 1)); echo "PASS  $name"; else fail=$((fail + 1)); echo "FAIL  $name (rc=$rc)"; fi
}
sel 0 "the suite file itself" tests/pipeline.test.sh tests/pipeline.test.sh
sel 0 "a script the suite names" tests/pipeline.test.sh scripts/factory-pipeline.py
sel 1 "an unrelated script skips the suite" tests/pipeline.test.sh scripts/changelog.py
sel 0 "registry change runs everything" tests/changelog.test.sh registry/core.json
sel 0 "shared library change runs everything" tests/ui-workflow.test.sh scripts/lib/fstate.py
sel 0 "skill text reaches skills-lint (EXTRA)" tests/skills-lint.sh skills/vfx/SKILL.md
sel 1 "skill text does not run the release gate" tests/release-check.test.sh skills/vfx/SKILL.md
sel 0 "an asset-gen engine module reaches the assetgen suite (EXTRA)" tests/assetgen.test.sh scripts/assetgen/png.py
sel 0 "core asset-gen templates reach the assetgen suite (EXTRA)" tests/assetgen.test.sh templates/assetgen/styles/pixel-art.json
sel 0 "the gen-run quality plugin reaches the assetgen suite (EXTRA)" tests/assetgen.test.sh scripts/checks/domains/assetgen.py
sel 1 "an unrelated quality plugin skips the assetgen suite" tests/assetgen.test.sh scripts/checks/domains/vfx.py
sel 0 "unreadable suite runs (unsure runs)" tests/no-such.test.sh README.md
R="$TMP/r"; git init -q -b main "$R"; echo a > "$R/a"; git -C "$R" add a; git -C "$R" -c user.email=t@t -c user.name=t commit -qm a
git -C "$R" checkout -qb topic; echo b > "$R/b"; git -C "$R" add b; git -C "$R" -c user.email=t@t -c user.name=t commit -qm b; echo c > "$R/c"
out=$(cd "$R" && python3 -B - "$A" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("affected", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.ROOT = "."
print(",".join(m.changed("main")))
PY
)
[ "$out" = "b,c" ] && { pass=$((pass + 1)); echo "PASS  changed = committed since merge-base + untracked"; } || { fail=$((fail + 1)); echo "FAIL  changed: '$out'"; }
total=$((pass + fail)); echo "affected tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
