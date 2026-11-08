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
sel 0 "library reaches its importer suite" tests/pipeline.test.sh scripts/lib/plan_paths.py
sel 1 "library skips unrelated suite" tests/changelog.test.sh scripts/lib/plan_paths.py
sel 0 "dynamic library stays global" tests/changelog.test.sh scripts/lib/gitguard.py
sel 0 "unknown top-level path runs everything" tests/changelog.test.sh new-unknown-file
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
out=$(python3 -B - "$A" "$TMP" <<'PY'
import contextlib, importlib.util, io, os, pathlib, subprocess, sys
spec = importlib.util.spec_from_file_location("affected", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
root = pathlib.Path(sys.argv[2]) / "hash-fixture"; root.mkdir()
subprocess.run(["git", "init", "-q", str(root)], check=True)
files = {"scripts/lib/inner.py": "VALUE = 1\n", "scripts/lib/outer.py": "from inner import VALUE\n",
         "scripts/entry.py": "import outer\n", "scripts/unrelated.py": "x = 1\n",
         "tests/example.test.sh": "python scripts/entry.py\n", "tests/other.test.sh": "python scripts/unrelated.py\n",
         "scripts/lib/dynamic.py": "import importlib\n", "scripts/lib/orphan.py": "x=1\n",
         "scripts/lib/compat.sh": "true\n", "tests/shell.test.sh": ". scripts/lib/compat.sh\n",
         "scripts/lib/pkg/__init__.py": "", "scripts/pkg-entry.py": "from pkg import thing\n",
         "tests/pkg.test.sh": "python scripts/pkg-entry.py\n", "scripts/checks/english-only.py": "pass\n"}
for path, text in files.items():
    p = root / path; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text)
m.ROOT = str(root)
def reset():
    for name in ("contents", "inventory", "library_graph", "reaches", "suite_patterns"):
        getattr(m, name).cache_clear()
def h(suite="tests/example.test.sh"):
    reset(); output = io.StringIO()
    with contextlib.redirect_stdout(output): m.hashes([suite])
    return output.getvalue().strip().split()[-1]
def check(name, ok):
    print(("PASS  " if ok else "FAIL  ") + name)
check("transitive library reaches outer importer", m.needed(["scripts/lib/inner.py"], "tests/example.test.sh"))
check("transitive library skips unrelated suite", not m.needed(["scripts/lib/inner.py"], "tests/other.test.sh"))
check("unimported library remains global", m.needed(["scripts/lib/orphan.py"], "tests/other.test.sh"))
check("dynamic library remains global in fixture", m.needed(["scripts/lib/dynamic.py"], "tests/other.test.sh"))
check("shell library reaches importer", m.needed(["scripts/lib/compat.sh"], "tests/shell.test.sh"))
check("package reaches importer", m.needed(["scripts/lib/pkg/__init__.py"], "tests/pkg.test.sh"))
before = h(); check("hash stable on unchanged tree", before == h())
(root / "scripts/entry.py").write_text("import outer\nx=2\n")
after = h(); check("hash changes on direct input", after != before)
(root / "scripts/unrelated.py").write_text("x=2\n")
check("hash ignores unrelated script", after == h())
(root / "scripts/lib/inner.py").write_text("VALUE=2\n")
check("hash changes on transitive library", after != h())
check("unknown suite cannot reuse", h("tests/missing.test.sh") == "-")
check("wildcard EXTRA cannot reuse", h("scripts/checks/english-only.py") == "-")
before_delete = h()
(root / "scripts/entry.py").unlink()
check("hash changes on missing input", before_delete != h())
PY
)
while IFS= read -r line; do
  echo "$line"
  case "$line" in PASS*) pass=$((pass + 1));; *) fail=$((fail + 1));; esac
done <<< "$out"
total=$((pass + fail)); echo "affected tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
