#!/usr/bin/env python3
"""Which run-all suites a change affects (tests/run-all.sh --affected).

  affected.py changed [BASE]        the changed files: merge-base(BASE, HEAD)..work tree, plus untracked files
                                    (BASE default: origin/main, else main)
  affected.py select FILE SUITE     exit 0 when SUITE must run for the changed files listed in FILE, else 1
  affected.py select-many FILE SUITE...
                                    print each SUITE that must run (same rule as select), one per line; the
                                    import graph is built once (run-all --affected calls it once per run)
  affected.py cases FILE SUITE...   print each selected suite and its affected cases, or ALL when uncertain: the case map
                                    must name every file the suite selects in the import closure of a changed file
  affected.py hashes SUITE...       print suite and input hash (or '-' when reuse is unsafe)

A suite runs when one of these holds (anything unsure runs):
  - a global input changed (GLOBAL: registry, hooks, manifests) - every suite runs;
  - a runner or selector change runs its explicitly mapped suites;
  - a change to scripts/factory-pipeline.py or scripts/lib/pipeline_route.py (PIPELINE_SUITES) runs its two mapped
    suites and a suite that itself names the file (exact path in its text or an EXTRA pattern), not the ~19 suites its import
    closure reaches; only selection is narrowed, hashes (suite reuse) keep the conservative closure;
  - a library or Python module change reaches a named script or suite through static imports, followed through
    every tracked Python module on the way (unresolved/dynamic libraries, unnamed leaves run all);
  - the suite file itself changed;
  - a changed file is a path the suite's own text names (scripts/..., skills/..., commands/..., docs/..., ...);
  - a changed file matches one of the suite's EXTRA patterns (indirect inputs the text does not name);
  - a changed file lies in the tree of a code file that would select the suite: code reads data next to it
    without naming the path (scripts/ui/ui_plan.py reads scripts/ui/data/*.json) and runs helpers by a computed
    path. Every non-ignored file in the tree counts (README.md and other docs a tool may read included), and so
    does a code file (.py/.sh/.jq) without a caller edge (no import, load or run by name); a code file with one
    follows its edges to every caller (a helper .sh a script names reaches that script and its suites), so a
    library change still selects only its importers.
    The tree of a code file is its tool directory. Under scripts/ and tests/ (many independent tools) it is the
    first two path components (scripts/ui/** for scripts/ui/ui_plan.py and for scripts/ui/x/y.py); for a file
    directly in scripts/ or tests/ it is only the files directly in that directory (not scripts/ui/**).
    Any other top-level directory is one project: the whole directory (testlab/** for testlab/lab/scenarios.py).
    Exception: the repository-wide indexes scripts/README.md and tests/README.md lie in the tree of every
    script directly in scripts/ or tests/, so the tree rule would make them select every suite; they select only
    through the other rules (a suite that reads one names it). The root README.md is a top-level file: it runs all.
Python imports are read with the ast module (plain, dotted, parenthesized, multiline and relative forms; a
package member that is a module is an edge) and with a text scan that also sees imports inside strings. A
tracked Python file that does not parse makes every selection unsure. Unknown paths otherwise run only suites
with matching rules; unknown top-level files run all. The reuse hash of a suite covers exactly the files that
select it under the conservative tree rule (plus its literal named paths).
Two uses, two tree rules. select / select-many (task QA iteration) use the narrow rule above: a code file with
a caller edge follows its edges only, so a library change selects only its importers; a miss there is caught by
the integration full run. hashes (suite reuse at that full run, where a false PASS is the risk) use the
conservative rule, a fixpoint: every file in the tree of every code file a suite reaches is an input, code files
with caller edges included (a helper one script names and another runs by a computed path), plus every module an
included code file imports, loads or runs, plus the trees of those, until nothing new is added (a library a helper
in a reached script's tree imports is an input of that script's suites). Only the index docs stay named-only,
library modules are included by import as single files (not their scripts/lib tree), and suites directly in
tests/ are not tree data.
Read-only. Integration owns the full run before a PR.
"""
import ast
import fnmatch
import hashlib
import os
import re
import subprocess
import sys
from functools import lru_cache

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GLOBAL = ["registry.json", "registry/*", "hooks/*", ".claude-plugin/*", ".codex-plugin/*",
          "scripts/factory-context.sh", "docs/registry.schema.json"]

DIRECT_SUITES = {
    "tests/run-all.sh": {"tests/run-all-parallel.test.sh", "tests/affected.test.sh"},
    "tests/affected.py": {"tests/affected.test.sh"},
}

# scripts that ~19 suites reach through the import closure but only these suites test: selection stops at the mapped
# suites and the suites that name the file; the reuse hashes (hashes) still use the conservative closure
PIPELINE_SUITES = {
    "scripts/factory-pipeline.py": {"tests/pipeline.test.sh", "tests/delivery-generic.test.sh"},
    "scripts/lib/pipeline_route.py": {"tests/pipeline.test.sh", "tests/delivery-generic.test.sh"},
}

SKILL_TEXT = ["skills/*", ".claude/skills/*"]
# indirect inputs: what a suite reads without naming the file
EXTRA = {
    "tests/skills-lint.sh": SKILL_TEXT + ["commands/*", "agents/*", "scripts/checks/*"],
    "tests/parallel-policy.test.sh": SKILL_TEXT + ["tests/skills-lint.sh", "scripts/orca-wait.sh", "tests/orca-wait.test.sh"],
    "tests/new-skill.test.sh": SKILL_TEXT + ["scripts/new-skill.py", "scripts/skill-touchpoints.py", "tests/routing.test.sh",
                                             "evals/*", "tests/skills-lint.sh", "docs/architecture/overview.md"],
    "scripts/checks/english-only.py": ["*"],
    "tests/english-only.test.sh": ["scripts/checks/english-only.py"],
    "tests/routing.test.sh": SKILL_TEXT + ["scripts/factory_session.py"],
    "tests/routing-golden.test.sh": SKILL_TEXT,
    "tests/ui-skills.test.sh": ["skills/ui-*", "docs/architecture/*"],
    "tests/orca-commands.test.sh": ["skills/delivery/references/delivery.md", "skills/factory-core/references/parallel-work.md",
                                   "docs/pipeline-cli.md"],
    "tests/delivery-generic.test.sh": ["skills/delivery/*", "scripts/factory-pipeline.py", "scripts/lib/pipeline_route.py"],
    "scripts/checks/skill-citations.py": SKILL_TEXT,
    "tests/commands.test.sh": ["commands/*", "scripts/factory-*.py", "scripts/run-checks.py", "scripts/ui/*", "scripts/assetgen/*"],
    "tests/assetgen.test.sh": ["scripts/assetgen/*", "templates/assetgen/*", "scripts/checks/domains/assetgen.py",
                               "scripts/checks/domains/_api.py", "scripts/checks/artifact-*.py", "tests/fixtures/assetgen/*",
                               "docs/schemas/kinds/gen-run.schema.json"],
    "tests/changelog.test.sh": ["changelog.d/*", "CHANGELOG.md"],
    "tests/codex-plugin.test.sh": [".agents/*", "docs/codex.md"],
    "tests/dogfood-grader.test.sh": ["tests/dogfood/*", "evals/*"],
    "tests/release-check.test.sh": ["VERSION", "README.md", "CHANGELOG.md"],
}
PATH_RE = re.compile(r"(?<![\w.-])((?:scripts|skills|commands|templates|docs|testlab|evals|hooks|tests)/[A-Za-z0-9_./*-]+)")


def git(*args):
    r = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout if r.returncode == 0 else None


def changed(base=None):
    for b in ([base] if base else ["origin/main", "main"]):
        mb = git("merge-base", b, "HEAD")
        if mb:
            break
    else:
        return None  # no base: caller runs everything
    files = set((git("diff", "--name-only", mb.strip()) or "").split())
    files |= set((git("ls-files", "--others", "--exclude-standard") or "").split())
    return sorted(files)


def hit(path, patterns):
    return any(fnmatch.fnmatch(path, p) or path.startswith(p.rstrip("*").rstrip("/") + "/") for p in patterns)


@lru_cache(None)
def contents(path):
    try:
        with open(os.path.join(ROOT, path), "rb") as fh:
            return fh.read()
    except OSError:
        return None


@lru_cache(None)
def inventory():
    return sorted(set((git("ls-files", "-z", "--cached", "--others", "--exclude-standard") or "").split("\0")) - {""})


SCANNED = (".py", ".sh", ".jq")
MENTIONS = SCANNED + (".md", ".json", ".yml", ".yaml", ".toml", ".txt")


def module_names(path):
    """Import names a tracked module answers to: lib-relative dotted names, else its stem and dotted parents."""
    if path.startswith("scripts/lib/"):
        module = path[len("scripts/lib/"):].removesuffix(".py").replace("/", ".").removesuffix(".__init__")
        return {module, module.split(".")[0]}
    parts = path.removesuffix(".py").split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return {".".join(parts[i:]) for i in range(len(parts))} if parts else set()


def code_only(path, text):
    """Drop comments and Python docstrings: prose that names a script is not an edge."""
    if path.endswith(".py"):
        text = re.sub(r"(?m)^[ \t]*[rRbBuU]?(\"\"\"|''')[\s\S]*?\1", "", text)
    return re.sub(r"(?m)(^|\s)#.*$", r"\1", text)


# This file's tables name scripts it never runs; run-all runs suites rather than importing them.
NOT_IMPORTERS = {"tests/affected.py", "tests/run-all.sh"}
# repository-wide indexes in the scripts/ and tests/ trees: named-only (see the module docstring)
INDEX_DOCS = {"scripts/README.md", "tests/README.md"}
PY_FILE = re.compile(r"[\w-]+\.py\b")
HELPER_FILE = re.compile(r"[\w-][\w.-]*\.(?:sh|jq)\b")
LOADER = re.compile(r"spec_from_file_location|run_path|exec_module")
LOAD_LINE = re.compile(r"join\(|/\s*['\"]|['\"]/|__file__|\b(HERE|ROOT|SCRIPTS)\b|subprocess|sys\.executable|\bexec")


def load_refs(path, text, pattern=PY_FILE):
    """File names (pattern) that code loads or runs: every name in a shell/jq file or in a Python module that
    loads files (spec_from_file_location), else only names on a line that builds a path or runs a process (a
    bare name in a message or an allow-list is not a dependency)."""
    if not path.endswith(".py") or LOADER.search(text):
        return set(pattern.findall(text))
    return {base for line in text.splitlines() if LOAD_LINE.search(line) for base in pattern.findall(line)}


FROM_RE = re.compile(r"\bfrom\s+(\.*)([\w.]*)\s+import\s+(?:\(([^)]*)\)|([\w., ]+))")
IMPORT_RE = re.compile(r"\bimport\s+([\w., ]+)")


def text_imports(text):
    """(level, module, members) of every import a text scan finds, imports inside strings included."""
    found = set()
    for dots, module, grouped, clause in FROM_RE.findall(text):
        members = {part.strip().split(" ")[0] for part in (grouped or clause).split(",")} - {"", "*"}
        found.add((len(dots), module, tuple(sorted(members))))
    for clause in IMPORT_RE.findall(text):
        found.update((0, part.strip().split(" ")[0], ()) for part in clause.split(",") if part.strip())
    return found


def ast_imports(raw):
    """(level, module, members) of every import statement in Python source; None when it does not parse."""
    try:
        tree = ast.parse(raw)
    except (SyntaxError, ValueError):
        return None
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update((0, alias.name, ()) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.add((node.level, node.module or "", tuple(sorted(a.name for a in node.names if a.name != "*"))))
    return found


@lru_cache(None)
def library_graph():
    """Reverse static edges over scripts/lib/* and every tracked code file (.py/.sh/.jq); scan each file once.

    An edge A -> B means A imports B by name, names B's .py, .sh or .jq file where it loads or runs files
    (spec_from_file_location, exec, a shell call: load_refs) or, for scripts/lib, references lib/<B>. Every code file
    (.py/.sh/.jq) is a node, so a helper a script runs by name is followed to the script. Also returns the file
    names any tracked text file mentions and the unparsable files."""
    files = inventory()
    nodes = [p for p in files if p.startswith("scripts/lib/") or p.endswith(SCANNED)]
    aliases, by_name, helpers = {}, {}, {}
    for p in nodes:
        base = p.rsplit("/", 1)[-1]
        if p.endswith(".py"):
            for name in module_names(p):
                aliases.setdefault(name, set()).add(p)
            if base != "__init__.py":
                by_name.setdefault(base, set()).add(p)
        elif p.endswith(SCANNED):
            helpers.setdefault(base, set()).add(p)
    libs = [p for p in nodes if p.startswith("scripts/lib/")]
    reverse = {p: set() for p in nodes}
    mentioned, broken = {}, set()
    for path in files:
        if not path.endswith(MENTIONS):
            continue
        raw = contents(path)
        if raw is None or b"\0" in raw:
            continue
        text = raw.decode("utf-8", errors="replace")
        if path.endswith(SCANNED):
            text = code_only(path, text)
        for base in (set(PY_FILE.findall(text)) | set(HELPER_FILE.findall(text))) - {"__init__.py"}:  # a package loaded by path is unsure
            mentioned.setdefault(base, set()).add(path)
        if not path.endswith(SCANNED) or path in NOT_IMPORTERS:
            continue
        imports = text_imports(text)
        if path.endswith(".py"):
            parsed = ast_imports(raw)
            if parsed is None:
                broken.add(path)
            else:
                imports |= parsed
        refs = set()
        for level, module, members in imports:
            if level == 0:
                for name in [module] + [f"{module}.{m}" if module else m for m in members]:
                    refs.update(aliases.get(name, ()))
                continue
            package = "/".join(path.split("/")[:-level])
            stem = "/".join(x for x in (package, module.replace(".", "/")) if x)
            candidates = [f"{stem}.py", f"{stem}/__init__.py"]
            candidates += [p for m in members for p in (f"{stem}/{m}.py", f"{stem}/{m}/__init__.py")]
            refs.update(p for p in candidates if p in reverse)
        for base in load_refs(path, text):
            refs.update(by_name.get(base, ()))
        for base in load_refs(path, text, HELPER_FILE):
            refs.update(helpers.get(base, ()))
        for ref in re.findall(r"\blib/([\w./-]+)", text):
            refs.update(p for p in libs if p == "scripts/lib/" + ref or p.startswith("scripts/lib/" + ref.rstrip("/") + "/"))
        for target in refs:
            if path != target:
                reverse[target].add(path)
    return reverse, mentioned, frozenset(broken)


def dynamic(path):
    raw = contents(path)
    code = re.sub(rb"(?m)#.*$", b"", raw or b"")
    return raw is None or re.search(rb"\b(importlib|__import__)\b|sys\.path", code) is not None


@lru_cache(None)
def reaches(path):
    """Every file a change to path can reach through static edges, path included; None when unsure.

    Library modules and the code files they reach are followed to their importers and callers. A dynamic
    library, a library nobody imports, and a reached code file that has no importer and that no other file
    names (loaded or run by a computed path) are unsure; a suite directly in tests/ has no caller (run-all runs it)."""
    graph, mentioned = library_graph()[:2]
    if path not in graph:
        return frozenset([path])
    todo, seen = [path], set()
    while todo:
        current = todo.pop()
        if current in seen:
            continue
        seen.add(current)
        if current.startswith("scripts/lib/") and dynamic(current):
            return None
        importers = graph.get(current, ())
        if (current != path and current.endswith(SCANNED) and not importers and tree(current) != ("tests/", False)
                and not mentioned.get(current.rsplit("/", 1)[-1], set()) - {current}):
            return None
        todo.extend(importers)
    if path.startswith("scripts/lib/") and not any(not p.startswith("scripts/lib/") for p in seen):
        return None
    return frozenset(seen)


@lru_cache(None)
def suite_patterns(suite):
    raw = contents(suite)
    if raw is None:
        return None
    return {m.rstrip(".,;:)'\"`") for m in PATH_RE.findall(raw.decode("utf-8", errors="replace"))}


def tree(path):
    """(prefix, deep) of the tree whose data files a code file may read unnamed (see the module docstring)."""
    parts = path.split("/")
    if parts[0] not in ("scripts", "tests"):
        return parts[0] + "/", True
    if len(parts) >= 3:
        return "/".join(parts[:2]) + "/", True
    return parts[0] + "/", False


def in_tree(path, root):
    prefix, deep = root
    return path.startswith(prefix) and (deep or "/" not in path[len(prefix):])


@lru_cache(None)
def code_trees():
    """Tree -> the tracked code files it belongs to."""
    roots = {}
    for p in inventory():
        if p.endswith(SCANNED) and "/" in p:
            roots.setdefault(tree(p), []).append(p)
    return roots


@lru_cache(None)
def named(path):
    """Other code imports, loads or runs the file: reaches() follows those edges, it is not tree data. A code file
    only prose names (a message, a doc) has no edge and stays in its tree."""
    return bool(library_graph()[0].get(path))


@lru_cache(None)
def run_all_suites():
    """Paths named on run-all's run lines, without running the suite list command."""
    raw = contents("tests/run-all.sh") or b""
    lines = raw.decode("utf-8", errors="replace").splitlines()
    return {p for line in lines if re.search(r"\brun(?:p|l|1)?\s+", line.split("#", 1)[0])
            for p in PATH_RE.findall(line.split("#", 1)[0])}


@lru_cache(None)
def owners(path, conservative=False):
    """Code files whose tree holds a file (deleted ones too): every file but an index doc and a code file with a
    caller edge. conservative (reuse hashes): a code file with a caller edge is tree data too, except a library
    module (scripts/lib: the import graph narrows it) and a code file directly in tests/ (a suite run-all runs)."""
    if "/" not in path or path in INDEX_DOCS:
        return ()
    if path.endswith(SCANNED):
        if conservative:
            if path.startswith("scripts/lib/") and named(path) or tree(path) == ("tests/", False):
                return ()
        elif named(path) or tree(path) == ("tests/", False) and path in run_all_suites():
            return ()
    return tuple(p for root, code in code_trees().items() if in_tree(path, root) for p in code if p != path)


@lru_cache(None)
def closure(path, conservative=False):
    """Every file a change to path can reach, the code files whose tree holds it included; None when unsure.

    narrow (selection): the tree owners of path itself only. conservative (reuse hashes): a fixpoint - the owners of
    every reached file are reached too, and their callers and owners in turn, so a library change reaches a script
    whose tree holds a helper that imports it (owners() keeps named library modules single files)."""
    if not conservative:
        found = set()
        for start in (path,) + owners(path):
            reached = reaches(start)
            if reached is None:
                return None
            found |= reached
        return frozenset(found)
    found, todo = set(), [path]
    while todo:
        start = todo.pop()
        if start in found:
            continue
        reached = reaches(start)
        if reached is None:
            return None
        new = reached - found
        found |= reached
        todo.extend(owner for p in new for owner in owners(p, True) if owner not in found)
    return frozenset(found)


@lru_cache(None)
def selects(path, suite):
    """A reached path selects the suite: it is the suite, a path its text names or one of its EXTRA patterns."""
    return path == suite or hit(path, suite_patterns(suite)) or hit(path, EXTRA.get(suite, []))


def names(path, suite):
    """The suite itself names the file: its text holds the exact path, or one of its EXTRA patterns matches. A
    directory or glob the text mentions (scripts/lib, scripts/*.py) does not name a file in it."""
    return path == suite or path in suite_patterns(suite) or hit(path, EXTRA.get(suite, []))


def always(path):
    return hit(path, GLOBAL) or "/" not in path


def needed(files, suite):
    if any(always(f) for f in files) or suite in files:
        return True
    if suite_patterns(suite) is None or library_graph()[2]:
        return True
    for f in files:
        if f in DIRECT_SUITES:
            if suite in DIRECT_SUITES[f]:
                return True
            continue
        if f in PIPELINE_SUITES:
            if suite in PIPELINE_SUITES[f] or names(f, suite):
                return True
            continue
        reached = closure(f)
        if reached is None or any(selects(p, suite) for p in reached):
            return True
    return False


def case_map(suite):
    raw = contents(suite)
    if raw is None:
        return None
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return None
    cases = {}
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            break
        if re.match(r"#\s*case-map\b", stripped):
            match = re.fullmatch(r"#\s*case-map:\s+([a-z0-9-]+)\s+(\S+(?:\s+\S+)*)\s*", stripped)
            if not match:
                return None
            name, patterns = match.groups()
            cases.setdefault(name, []).extend(patterns.split())
    return cases or None


def affected_cases(files, suite):
    mapping = case_map(suite)
    if mapping is None or suite in files or any(always(f) for f in files) or library_graph()[2]:
        return "ALL"
    selected = set()
    for path in files:
        if not needed([path], suite):
            continue
        reached = frozenset([path]) if path in PIPELINE_SUITES else closure(path)
        if reached is None:
            return "ALL"
        # a shared module reaches every file that imports it: each reached file the suite selects must be mapped
        # (the suite itself is reached through its own named scripts and says nothing about a case)
        for hit_path in sorted(p for p in reached if p != suite and selects(p, suite)):
            matched = {name for name, patterns in mapping.items() for pattern in patterns
                       if fnmatch.fnmatchcase(hit_path, pattern + "*" if pattern.endswith("/") else pattern)}
            if not matched:
                return "ALL"
            selected.update(matched)
    return ",".join(sorted(selected)) if selected else "ALL"


def hashes(suites):
    versions = [sys.version]
    # a bare "bash" resolves to the WSL launcher on Windows (CreateProcess): find_bash() or absent
    sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
    try:
        from shells import find_bash
        bash = find_bash()
    finally:
        sys.path.pop(0)
    for cmd in (["git", "--version"], [bash, "--version"] if bash else None, ["jq", "--version"]):
        if cmd is None:
            versions.append("absent")
            continue
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=10)
            versions.append(result.stdout.splitlines()[0].decode("utf-8", errors="replace") if result.stdout else "absent")
        except (OSError, subprocess.TimeoutExpired):
            versions.append("absent")
    # one pass over the tree: the files every suite depends on, and per reached path the files that reach it
    files = inventory()
    common, reached_by = set(), {}
    for f in files:
        reached = None if always(f) else closure(f, conservative=True)
        if reached is None:
            common.add(f)
            continue
        for p in reached:
            reached_by.setdefault(p, set()).add(f)
    for suite in suites:
        if suite_patterns(suite) is None or "*" in EXTRA.get(suite, []) or library_graph()[2]:
            print(suite, "-")
            continue
        digest = hashlib.sha256(repr(versions).encode())
        inputs = common | {suite}
        for p, sources in reached_by.items():
            if selects(p, suite):
                inputs |= sources
        # Literal named inputs remain inputs even when deleted/untracked-absent.
        inputs.update(p for p in suite_patterns(suite) if not any(c in p for c in "*?[") and not os.path.isdir(os.path.join(ROOT, p)))
        for path in sorted(inputs):
            raw = contents(path)
            digest.update(path.encode() + b"\0")
            digest.update(b"absent\0" if raw is None else b"present\0" + len(raw).to_bytes(8, "big") + raw)
        print(suite, digest.hexdigest()[:16])


def main(argv):
    if argv[:1] == ["hashes"] and len(argv) > 1:
        hashes(argv[1:])
        return 0
    if argv[:1] == ["changed"]:
        files = changed(argv[1] if len(argv) > 1 else None)
        if files is None:
            print("affected: no base found (origin/main, main)", file=sys.stderr)
            return 2
        print("\n".join(files))
        return 0
    if argv[:1] == ["select"] and len(argv) == 3:
        with open(argv[1], encoding="utf-8") as fh:
            files = [x.strip() for x in fh if x.strip()]
        return 0 if needed(files, argv[2]) else 1
    if argv[:1] == ["cases"] and len(argv) >= 2:
        with open(argv[1], encoding="utf-8") as fh:
            files = [x.strip() for x in fh if x.strip()]
        lines = [suite + "\t" + affected_cases(files, suite) + "\n"
                 for suite in dict.fromkeys(argv[2:]) if needed(files, suite)]
        sys.stdout.buffer.write("".join(lines).encode())
        return 0
    if argv[:1] == ["select-many"] and len(argv) >= 2:
        with open(argv[1], encoding="utf-8") as fh:
            files = [x.strip() for x in fh if x.strip()]
        picked = [suite for suite in dict.fromkeys(argv[2:]) if needed(files, suite)]
        sys.stdout.buffer.write("".join(suite + "\n" for suite in picked).encode())   # LF on Windows too
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
