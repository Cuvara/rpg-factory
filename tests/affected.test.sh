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
sel 0 "an agent file reaches skills-lint (EXTRA)" tests/skills-lint.sh agents/factory-explorer.md
sel 1 "skill text does not run the release gate" tests/release-check.test.sh skills/vfx/SKILL.md
sel 0 "an asset-gen engine module reaches the assetgen suite (EXTRA)" tests/assetgen.test.sh scripts/assetgen/png.py
sel 0 "core asset-gen templates reach the assetgen suite (EXTRA)" tests/assetgen.test.sh templates/assetgen/styles/pixel-art.json
sel 0 "the gen-run quality plugin reaches the assetgen suite (EXTRA)" tests/assetgen.test.sh scripts/checks/domains/assetgen.py
sel 1 "an unrelated quality plugin skips the assetgen suite" tests/assetgen.test.sh scripts/checks/domains/vfx.py
sel 0 "unreadable suite runs (unsure runs)" tests/no-such.test.sh README.md
sel 0 "UI data next to ui_plan.py selects ui-commands (tree rule)" tests/ui-commands.test.sh scripts/ui/data/intents.json
sel 0 "UI data next to ui_plan.py selects ui-skill-routing (tree rule)" tests/ui-skill-routing.test.sh scripts/ui/data/intents.json
sel 1 "UI data skips an unrelated suite" tests/changelog.test.sh scripts/ui/data/intents.json
sel 0 "a testlab scenario selects the testlab unit tests (tree rule)" testlab/tests/test_lab.py testlab/scenarios/S01-bootstrap.json
# select-many: the same answer as select for every suite, from one call (one import graph)
printf '%s\n' scripts/lib/plan_paths.py scripts/ui/data/intents.json skills/vfx/SKILL.md > "$TMP/many"
many=(tests/pipeline.test.sh tests/changelog.test.sh tests/skills-lint.sh tests/release-check.test.sh tests/ui-commands.test.sh
      tests/assetgen.test.sh tests/no-such.test.sh testlab/tests/test_lab.py tests/pipeline.test.sh)
want=$(for s in "${many[@]}"; do python3 -B "$A" select "$TMP/many" "$s" && echo "$s"; done | awk '!seen[$0]++')
got=$(python3 -B "$A" select-many "$TMP/many" "${many[@]}"); rc=$?
if [ "$rc" = 0 ] && [ -n "$want" ] && [ "$got" = "$want" ] && ! grep -qx tests/changelog.test.sh <<<"$got"; then
  pass=$((pass + 1)); echo "PASS  select-many equals per-suite select (deduplicated, in order)"
else fail=$((fail + 1)); echo "FAIL  select-many equals per-suite select (rc=$rc): want [$want] got [$got]"; fi
printf '%s\n' registry/core.json > "$TMP/many"
got=$(python3 -B "$A" select-many "$TMP/many" tests/changelog.test.sh tests/pipeline.test.sh)
if [ "$got" = $'tests/changelog.test.sh\ntests/pipeline.test.sh' ]; then pass=$((pass + 1)); echo "PASS  select-many: a global change selects every suite"
else fail=$((fail + 1)); echo "FAIL  select-many: a global change selects every suite: got [$got]"; fi
mapfile -t suites < <(bash "$ROOT/tests/run-all.sh" --list-suites)
printf '%s\n' tests/run-all.sh > "$TMP/many"
got=$(python3 -B "$A" select-many "$TMP/many" "${suites[@]}" | sort)
if [ "$got" = $'tests/affected.test.sh\ntests/run-all-parallel.test.sh' ]; then
  pass=$((pass + 1)); echo "PASS  runner change selects only runner and selector suites"
else fail=$((fail + 1)); echo "FAIL  runner change selects only runner and selector suites: got [$got]"; fi
printf '%s\n' tests/affected.py > "$TMP/many"
got=$(python3 -B "$A" select-many "$TMP/many" "${suites[@]}" | sort)
if [ "$got" = 'tests/affected.test.sh' ]; then
  pass=$((pass + 1)); echo "PASS  selector change selects only selector suite"
else fail=$((fail + 1)); echo "FAIL  selector change selects only selector suite: got [$got]"; fi
printf '%s\n' tests/affected.test.sh > "$TMP/many"
got=$(python3 -B "$A" select-many "$TMP/many" "${suites[@]}" | sort)
if [ "$got" = $'scripts/checks/english-only.py\ntests/affected.test.sh' ]; then
  pass=$((pass + 1)); echo "PASS  suite change selects itself and the global English check"
else fail=$((fail + 1)); echo "FAIL  suite change selects itself and the global English check: got [$got]"; fi
printf '%s\n' tests/parallel-policy.test.sh > "$TMP/many"
got=$(python3 -B "$A" select-many "$TMP/many" "${suites[@]}")
if [[ "$got" == *tests/parallel-policy.test.sh* ]] && [[ "$got" != *tests/git-guard.test.sh* ]]; then
  pass=$((pass + 1)); echo "PASS  parallel policy suite change skips git guard"
else fail=$((fail + 1)); echo "FAIL  parallel policy suite change skips git guard: got [$got]"; fi
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
         "scripts/entry.py": "import outer\n", "scripts/unrel/unrelated.py": "x = 1\n",
         "tests/example.test.sh": "python scripts/entry.py\n", "tests/other.test.sh": "python scripts/unrel/unrelated.py\n",
         "scripts/lib/dynamic.py": "import importlib\n", "scripts/lib/orphan.py": "x=1\n",
         "scripts/lib/compat.sh": "true\n", "tests/shell.test.sh": ". scripts/lib/compat.sh\n",
         "scripts/lib/pkg/__init__.py": "", "scripts/pkg-entry.py": "from pkg import thing\n",
         "tests/pkg.test.sh": "python scripts/pkg-entry.py\n", "scripts/checks/english-only.py": "pass\n",
         # lib -> non-lib helper -> entry script: only the entry is named by a suite
         "scripts/lib/deep.py": "X = 1\n", "scripts/helpers/helper.py": "from deep import X\n",
         "scripts/tool.py": "import helper\n", "tests/tool.test.sh": "python scripts/tool.py\n",
         # lib -> module loaded by path (spec_from_file_location) -> loader script
         "scripts/lib/via_path.py": "X = 1\n", "scripts/checks/plug-in.py": "import via_path\n",
         "scripts/checks/loader.py": "spec = importlib.util.spec_from_file_location('p', HERE / 'plug-in.py')\n",
         "tests/loader.test.sh": "python scripts/checks/loader.py\n",
         # a bare file name in a message is not a dependency
         "scripts/talk.py": "print('run plug-in.py first')\n", "tests/talk.test.sh": "python scripts/talk.py\n",
         # relative import inside a lib package
         "scripts/lib/rpkg/__init__.py": "from .part import Y\n", "scripts/lib/rpkg/part.py": "Y = 1\n",
         "scripts/rel-entry.py": "import rpkg\n", "tests/rel.test.sh": "python scripts/rel-entry.py\n",
         # lib -> module nothing imports or names (loaded by a computed path): unsure
         "scripts/lib/hidden.py": "X = 1\n", "scripts/plugins/dyn.py": "import hidden\n",
         # data a script reads next to it without naming the path; an unrelated data file in another tool's tree
         "scripts/ui/plan.py": "import json\n", "scripts/ui/data/intents.json": "{}\n", "tests/ui.test.sh": "python scripts/ui/plan.py\n",
         "scripts/other/tool2.py": "x = 1\n", "scripts/other/data/x.json": "{}\n",
         # in the same tree: a README.md the script may read and a helper it may run by a computed path (no code names
         # either); the scripts/ index doc lies in the tree of every script directly in scripts/ and stays named-only
         "scripts/ui/README.md": "# ui\n", "scripts/ui/helper.sh": "true\n", "scripts/README.md": "# scripts\n",
         # a non-scripts top-level directory is one project: testlab/lab code reads testlab/scenarios
         "testlab/lab/run.py": "x = 1\n", "testlab/scenarios/a.json": "{}\n", "tests/lab.test.sh": "python testlab/lab/run.py\n",
         # parenthesized multiline import of a package member module (the member has its own suite)
         "scripts/lib/leaf.py": "X = 1\n", "scripts/plib/__init__.py": "", "scripts/plib/member.py": "import leaf\n",
         "scripts/paren.py": "from plib import (\n    member,\n)\n", "tests/paren.test.sh": "python scripts/paren.py\n",
         "tests/member.test.sh": "python scripts/plib/member.py\n",
         # relative multiline package-member import
         "scripts/lib/leaf2.py": "X = 1\n", "scripts/rpkg2/__init__.py": "from . import (\n    sub,\n)\n",
         "scripts/rpkg2/sub.py": "import leaf2\n", "scripts/rel2.py": "import rpkg2\n", "tests/rel2.test.sh": "python scripts/rel2.py\n",
         "tests/sub.test.sh": "python scripts/rpkg2/sub.py\n",
         # a script runs helpers it names by subprocess (review r9): the helpers are named, their call edges are followed
         "scripts/uix/plan.py": "import os, subprocess\nsubprocess.run(['bash', os.path.join(HERE, 'run-helper.sh')])\n"
                                "subprocess.run(['jq', '-f', os.path.join(HERE, 'shape.jq')])\nALLOWED = {'listed.sh'}\n",
         "scripts/uix/run-helper.sh": "true\n", "scripts/uix/listed.sh": "true\n", "scripts/uix/shape.jq": ".\n", "tests/uix.test.sh": "python scripts/uix/plan.py\n",
         # mixed callers (review r10): another tree's script runs the helper by name, the script next to it by a computed path
         "scripts/uiy/plan.py": "import json\n", "scripts/uiy/step.sh": "true\n", "tests/uiy.test.sh": "python scripts/uiy/plan.py\n",
         "scripts/runner/run.py": "import os, subprocess\nsubprocess.run(['bash', os.path.join(ROOT, 'scripts/uiy/step.sh')])\n",
         "tests/runner.test.sh": "python scripts/runner/run.py\n",
         # transitive mixed callers (review r11): the helper next to a computed caller imports a library
         "scripts/uiz/plan.py": "import os, subprocess\nsubprocess.run(['python', os.path.join(HERE, STEP + '.py')])\n",
         "scripts/uiz/step.py": "from value import VALUE\n", "scripts/lib/value.py": "VALUE = 1\n",
         "tests/uiz.test.sh": "python scripts/uiz/plan.py\n",
         "scripts/runz/run.py": "import os, subprocess\nsubprocess.run(['python', os.path.join(ROOT, 'scripts/uiz/step.py')])\n",
         "tests/runz.test.sh": "python scripts/runz/run.py\n"}
for path, text in files.items():
    p = root / path; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text)
m.ROOT = str(root)
def reset():
    for name in ("contents", "inventory", "library_graph", "reaches", "suite_patterns", "code_trees", "named", "owners", "closure", "selects"):
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
check("library reaches suite through a non-lib helper", m.needed(["scripts/lib/deep.py"], "tests/tool.test.sh"))
check("non-lib helper change reaches the entry's suite", m.needed(["scripts/helpers/helper.py"], "tests/tool.test.sh"))
check("helper chain skips unrelated suite", not m.needed(["scripts/lib/deep.py"], "tests/other.test.sh"))
check("library reaches suite through a module loaded by path", m.needed(["scripts/lib/via_path.py"], "tests/loader.test.sh"))
check("bare file name in a message is not an edge", not m.needed(["scripts/lib/via_path.py"], "tests/talk.test.sh"))
check("relative import reaches package importer", m.needed(["scripts/lib/rpkg/part.py"], "tests/rel.test.sh"))
check("relative import skips unrelated suite", not m.needed(["scripts/lib/rpkg/part.py"], "tests/other.test.sh"))
check("library reaching an unnamed module stays global", m.needed(["scripts/lib/hidden.py"], "tests/other.test.sh"))
reset(); tool_before = h("tests/tool.test.sh")
(root / "scripts/lib/deep.py").write_text("X = 2\n")
check("hash changes on a library reached through a helper", tool_before != h("tests/tool.test.sh"))
before = h(); check("hash stable on unchanged tree", before == h())
(root / "scripts/entry.py").write_text("import outer\nx=2\n")
after = h(); check("hash changes on direct input", after != before)
(root / "scripts/unrel/unrelated.py").write_text("x=2\n")
check("hash ignores unrelated script", after == h())
(root / "scripts/lib/inner.py").write_text("VALUE=2\n")
check("hash changes on transitive library", after != h())
check("unknown suite cannot reuse", h("tests/missing.test.sh") == "-")
check("wildcard EXTRA cannot reuse", h("scripts/checks/english-only.py") == "-")
before_delete = h()
(root / "scripts/entry.py").unlink()
check("hash changes on missing input", before_delete != h())
reset()
check("data next to a reached script selects its suite", m.needed(["scripts/ui/data/intents.json"], "tests/ui.test.sh"))
check("data next to a script skips an unrelated suite", not m.needed(["scripts/ui/data/intents.json"], "tests/other.test.sh"))
check("data in another tool's tree skips the suite", not m.needed(["scripts/other/data/x.json"], "tests/ui.test.sh"))
check("a README.md next to a reached script selects its suite", m.needed(["scripts/ui/README.md"], "tests/ui.test.sh"))
check("a README.md next to a script skips an unrelated suite", not m.needed(["scripts/ui/README.md"], "tests/other.test.sh"))
check("an unnamed helper .sh next to a reached script selects its suite", m.needed(["scripts/ui/helper.sh"], "tests/ui.test.sh"))
check("an unnamed helper .sh next to a script skips an unrelated suite", not m.needed(["scripts/ui/helper.sh"], "tests/other.test.sh"))
check("a named helper .sh a reached script runs selects its suite", m.needed(["scripts/uix/run-helper.sh"], "tests/uix.test.sh"))
check("a named helper .jq a reached script runs selects its suite", m.needed(["scripts/uix/shape.jq"], "tests/uix.test.sh"))
check("a helper only an allow-list names stays tree data and selects its suite", m.needed(["scripts/uix/listed.sh"], "tests/uix.test.sh"))
check("a named helper .sh skips an unrelated suite", not m.needed(["scripts/uix/run-helper.sh"], "tests/other.test.sh"))
check("the scripts/ index doc is named-only (does not select every suite)", not m.needed(["scripts/README.md"], "tests/example.test.sh"))
check("a deleted data file next to a reached script selects its suite", m.needed(["scripts/ui/data/gone.json"], "tests/ui.test.sh"))
check("data anywhere in a non-scripts project selects its suite", m.needed(["testlab/scenarios/a.json"], "tests/lab.test.sh"))
check("parenthesized package-member import is an edge", m.needed(["scripts/lib/leaf.py"], "tests/paren.test.sh"))
check("parenthesized import change skips unrelated suite", not m.needed(["scripts/lib/leaf.py"], "tests/other.test.sh"))
check("relative multiline package-member import is an edge", m.needed(["scripts/lib/leaf2.py"], "tests/rel2.test.sh"))
check("relative multiline import change skips unrelated suite", not m.needed(["scripts/lib/leaf2.py"], "tests/other.test.sh"))
ui_before, other_before, paren_before, rel_before = h("tests/ui.test.sh"), h("tests/other.test.sh"), h("tests/paren.test.sh"), h("tests/rel2.test.sh")
(root / "scripts/other/data/x.json").write_text("[1]\n")
check("hash ignores a data file in another tool's tree", ui_before == h("tests/ui.test.sh"))
(root / "scripts/ui/data/intents.json").write_text("[2]\n")
check("hash changes on data next to a reached script", ui_before != h("tests/ui.test.sh"))
check("hash of an unrelated suite ignores that data", other_before == h("tests/other.test.sh"))
ui_before, example_before = h("tests/ui.test.sh"), h()
(root / "scripts/ui/README.md").write_text("# ui 2\n")
check("hash changes on a README.md next to a reached script", ui_before != h("tests/ui.test.sh"))
check("hash of an unrelated suite ignores that README.md", other_before == h("tests/other.test.sh"))
ui_before = h("tests/ui.test.sh")
(root / "scripts/ui/helper.sh").write_text("false\n")
check("hash changes on an unnamed helper .sh next to a reached script", ui_before != h("tests/ui.test.sh"))
check("hash of an unrelated suite ignores that helper", other_before == h("tests/other.test.sh"))
uix_before, other_before = h("tests/uix.test.sh"), h("tests/other.test.sh")
(root / "scripts/uix/run-helper.sh").write_text("false\n")
check("hash changes on a named helper .sh a reached script runs", uix_before != h("tests/uix.test.sh"))
uix_before = h("tests/uix.test.sh")
(root / "scripts/uix/shape.jq").write_text(".a\n")
check("hash changes on a named helper .jq a reached script runs", uix_before != h("tests/uix.test.sh"))
check("hash of an unrelated suite ignores those helpers", other_before == h("tests/other.test.sh"))
check("mixed callers: select keeps the narrow rule (the named helper follows its edges only)",
      m.needed(["scripts/uiy/step.sh"], "tests/runner.test.sh") and not m.needed(["scripts/uiy/step.sh"], "tests/uiy.test.sh"))
uiy_before, runner_before, other_before = h("tests/uiy.test.sh"), h("tests/runner.test.sh"), h("tests/other.test.sh")
(root / "scripts/uiy/step.sh").write_text("false\n")
check("mixed callers: hash of the computed caller's suite changes (conservative tree rule)", uiy_before != h("tests/uiy.test.sh"))
check("mixed callers: hash of the explicit caller's suite changes", runner_before != h("tests/runner.test.sh"))
check("mixed callers: hash of an unrelated suite ignores the helper", other_before == h("tests/other.test.sh"))
reset()
check("transitive mixed callers: select stays narrow (the library selects only the explicit caller's suite)",
      m.needed(["scripts/lib/value.py"], "tests/runz.test.sh") and not m.needed(["scripts/lib/value.py"], "tests/uiz.test.sh"))
uiz_before, runz_before, other_before = h("tests/uiz.test.sh"), h("tests/runz.test.sh"), h("tests/other.test.sh")
(root / "scripts/lib/value.py").write_text("VALUE = 2\n")
check("transitive mixed callers: hash of the computed caller's suite changes on the helper's library", uiz_before != h("tests/uiz.test.sh"))
check("transitive mixed callers: hash of the explicit caller's suite changes", runz_before != h("tests/runz.test.sh"))
check("transitive mixed callers: hash of an unrelated suite ignores the library", other_before == h("tests/other.test.sh"))
(root / "scripts/README.md").write_text("# scripts 2\n")
check("hash ignores the scripts/ index doc", example_before == h())
(root / "scripts/lib/leaf.py").write_text("X = 2\n")
check("hash changes through a parenthesized package-member import", paren_before != h("tests/paren.test.sh"))
(root / "scripts/lib/leaf2.py").write_text("X = 2\n")
check("hash changes through a relative multiline import", rel_before != h("tests/rel2.test.sh"))
(root / "scripts/broken.py").write_text("def (:\n")
reset()
check("an unparsable Python file makes selection unsure", m.needed(["scripts/lib/leaf.py"], "tests/other.test.sh"))
check("an unparsable Python file disables reuse", h("tests/other.test.sh") == "-")
PY
)
while IFS= read -r line; do
  echo "$line"
  case "$line" in PASS*) pass=$((pass + 1));; *) fail=$((fail + 1));; esac
done <<< "$out"
out=$(python3 -B - "$A" "$TMP" <<'PY'
import importlib.util, pathlib, subprocess, sys
spec = importlib.util.spec_from_file_location("affected", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
root = pathlib.Path(sys.argv[2]) / "case-fixture"; root.mkdir()
subprocess.run(["git", "init", "-q", str(root)], check=True)
files = {
    "tests/mapped.sh": "#!/bin/bash\n# case-map: beta scripts/tool/b.py\n# case-map: alpha scripts/tool/\n# case-map: alpha scripts/tool/a.py\npython scripts/tool/a.py scripts/tool/b.py scripts/tool/c.py\n",
    "tests/plain.sh": "python scripts/tool/a.py\n",
    "tests/other.sh": "python scripts/other/x.py\n",
    "tests/bad.sh": "# case-map: INVALID scripts/tool/a.py\npython scripts/tool/a.py\n",
    "scripts/tool/a.py": "pass\n", "scripts/tool/b.py": "pass\n", "scripts/tool/c.py": "pass\n",
    "scripts/other/x.py": "pass\n",
    # a shared module imported by the scripts of two cases (and one only a second suite maps in part)
    "scripts/lib/shared.py": "VALUE = 1\n", "scripts/shx/x.py": "import shared\n", "scripts/shx/y.py": "import shared\n",
    "tests/shared.sh": "# case-map: one scripts/shx/x.py\n# case-map: two scripts/shx/y.py\n# case-map: one scripts/lib/shared.py\npython scripts/shx/x.py scripts/shx/y.py\n",
    "tests/shared-part.sh": "# case-map: one scripts/shx/x.py\npython scripts/shx/x.py scripts/shx/y.py\n",
}
for path, content in files.items():
    p = root / path; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content)
m.ROOT = str(root)
def check(label, value): print(("PASS  " if value else "FAIL  ") + label)
check("case map selects one case", m.affected_cases(["scripts/tool/a.py"], "tests/mapped.sh") == "alpha")
check("case map unions sorted unique cases", m.affected_cases(["scripts/tool/b.py", "scripts/tool/a.py"], "tests/mapped.sh") == "alpha,beta")
check("suite change runs all cases", m.affected_cases(["tests/mapped.sh"], "tests/mapped.sh") == "ALL")
check("no map runs all cases", m.affected_cases(["scripts/tool/a.py"], "tests/plain.sh") == "ALL")
check("invalid map runs all cases", m.affected_cases(["scripts/tool/a.py"], "tests/bad.sh") == "ALL")
check("global input runs all cases", m.affected_cases(["registry.json"], "tests/mapped.sh") == "ALL")
check("a shared module selects the cases of every importer the suite names", m.affected_cases(["scripts/lib/shared.py"], "tests/shared.sh") == "one,two")
check("a shared module imported by an unmapped script runs all cases", m.affected_cases(["scripts/lib/shared.py"], "tests/shared-part.sh") == "ALL")
check("a mapped script still selects only its case", m.affected_cases(["scripts/shx/x.py"], "tests/shared.sh") == "one")
(root / "tests/mapped.sh").write_text("# case-map: alpha scripts/tool/a.py\npython scripts/tool/a.py scripts/tool/c.py\n")
m.contents.cache_clear(); m.suite_patterns.cache_clear()
check("unmapped selecting input runs all cases", m.affected_cases(["scripts/tool/c.py"], "tests/mapped.sh") == "ALL")
changed = root / "changed"; changed.write_text("scripts/tool/a.py\n")
runner = "import importlib.util,sys; s=importlib.util.spec_from_file_location('a',sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); m.ROOT=sys.argv[2]; sys.exit(m.main(sys.argv[3:]))"
result = subprocess.run([sys.executable, "-B", "-c", runner, sys.argv[1], str(root), "cases", str(changed), "tests/mapped.sh", "tests/plain.sh", "tests/other.sh"], capture_output=True, text=True)
check("cases command prints selected suites only", result.returncode == 0 and result.stdout == "tests/mapped.sh\talpha\ntests/plain.sh\tALL\n")
PY
)
while IFS= read -r line; do
  echo "$line"
  case "$line" in PASS*) pass=$((pass + 1));; *) fail=$((fail + 1));; esac
done <<< "$out"
total=$((pass + fail)); echo "affected tests: $total run, $pass passed, $fail failed"
[ "$total" -gt 0 ] && [ "$fail" -eq 0 ]
