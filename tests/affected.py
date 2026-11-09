#!/usr/bin/env python3
"""Which run-all suites a change affects (tests/run-all.sh --affected).

  affected.py changed [BASE]        the changed files: merge-base(BASE, HEAD)..work tree, plus untracked files
                                    (BASE default: origin/main, else main)
  affected.py select FILE SUITE     exit 0 when SUITE must run for the changed files listed in FILE, else 1
  affected.py select-many FILE SUITE...
                                    print each SUITE that must run (same rule as select), one per line; the
                                    import graph is built once (run-all --affected calls it once per run)
  affected.py hashes SUITE...       print suite and input hash (or '-' when reuse is unsafe)

A suite runs when one of these holds (anything unsure runs):
  - a global input changed (GLOBAL: registry, hooks, manifests, run-all itself) - every suite runs;
  - a library or Python module change reaches a named script or suite through static imports, followed through
    every tracked Python module on the way (unresolved/dynamic libraries, unnamed leaves run all);
  - the suite file itself changed;
  - a changed file is a path the suite's own text names (scripts/..., skills/..., commands/..., docs/..., ...);
  - a changed file matches one of the suite's EXTRA patterns (indirect inputs the text does not name);
  - a changed file lies in the tree of a code file that would select the suite: code reads data next to it
    without naming the path (scripts/ui/ui_plan.py reads scripts/ui/data/*.json) and runs helpers by a computed
    path. Every non-ignored file in the tree counts (README.md and other docs a tool may read included), and so
    does a code file (.py/.sh/.jq) that no other code file names (no import, no file name in code); a code file
    that code names follows only the import and name edges, so a library change still selects only its importers.
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
select it (plus its literal named paths), so --affected and suite reuse agree.
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
          "tests/run-all.sh", "tests/affected.py", "scripts/factory-context.sh", "docs/registry.schema.json"]

SKILL_TEXT = ["skills/*", ".claude/skills/*"]
# indirect inputs: what a suite reads without naming the file
EXTRA = {
    "tests/skills-lint.sh": SKILL_TEXT + ["commands/*", "scripts/checks/*"],
    "tests/parallel-policy.test.sh": SKILL_TEXT + ["tests/skills-lint.sh", "scripts/orca-wait.sh", "tests/orca-wait.test.sh"],
    "tests/new-skill.test.sh": SKILL_TEXT + ["scripts/new-skill.py", "scripts/skill-touchpoints.py", "tests/routing.test.sh",
                                             "evals/*", "tests/skills-lint.sh"],
    "scripts/checks/english-only.py": ["*"],
    "tests/english-only.test.sh": ["scripts/checks/english-only.py"],
    "tests/routing.test.sh": SKILL_TEXT + ["scripts/factory_session.py"],
    "tests/routing-golden.test.sh": SKILL_TEXT,
    "tests/ui-skills.test.sh": ["skills/ui-*", "docs/architecture/*"],
    "tests/orca-commands.test.sh": ["skills/factory-core/references/parallel-work.md"],
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


# this file's tables name scripts it never runs; run-all runs suites, a suite change selects itself (both GLOBAL)
NOT_IMPORTERS = {"tests/affected.py", "tests/run-all.sh"}
# repository-wide indexes in the scripts/ and tests/ trees: named-only (see the module docstring)
INDEX_DOCS = {"scripts/README.md", "tests/README.md"}
PY_FILE = re.compile(r"[\w-]+\.py\b")
CODE_FILE = re.compile(r"[\w-][\w.-]*\.(?:py|sh|jq)\b")
LOADER = re.compile(r"spec_from_file_location|run_path|exec_module")
LOAD_LINE = re.compile(r"join\(|/\s*['\"]|['\"]/|__file__|\b(HERE|ROOT|SCRIPTS)\b|subprocess|sys\.executable|\bexec")


def load_refs(path, text):
    """Python file names that code loads or runs: every name in a shell/jq file or in a Python module that loads
    files (spec_from_file_location), else only names on a line that builds a path or runs a process (a bare
    name in a message or an allow-list is not a dependency)."""
    if not path.endswith(".py") or LOADER.search(text):
        return set(PY_FILE.findall(text))
    return {base for line in text.splitlines() if LOAD_LINE.search(line) for base in PY_FILE.findall(line)}


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
    """Reverse static edges over scripts/lib/* and every tracked Python module; scan each file once.

    An edge A -> B means A imports B by name, names B's file (spec_from_file_location, exec, a shell call) or,
    for scripts/lib, references lib/<B>. Also returns the file names any tracked text file mentions, the code
    file names other code mentions (comments stripped; this file's tables do not count) and the unparsable files."""
    files = inventory()
    nodes = [p for p in files if p.startswith("scripts/lib/") or p.endswith(".py")]
    aliases, by_name = {}, {}
    for p in nodes:
        if p.endswith(".py"):
            for name in module_names(p):
                aliases.setdefault(name, set()).add(p)
            base = p.rsplit("/", 1)[-1]
            if base != "__init__.py":
                by_name.setdefault(base, set()).add(p)
    libs = [p for p in nodes if p.startswith("scripts/lib/")]
    reverse = {p: set() for p in nodes}
    mentioned, code_named, broken = {}, {}, set()
    for path in files:
        if not path.endswith(MENTIONS):
            continue
        raw = contents(path)
        if raw is None or b"\0" in raw:
            continue
        text = raw.decode("utf-8", errors="replace")
        if path.endswith(SCANNED):
            text = code_only(path, text)
        for base in set(PY_FILE.findall(text)) - {"__init__.py"}:  # a package loaded by path is unsure
            mentioned.setdefault(base, set()).add(path)
        if path.endswith(SCANNED) and path != "tests/affected.py":
            for base in set(CODE_FILE.findall(text)):
                code_named.setdefault(base, set()).add(path)
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
        for ref in re.findall(r"\blib/([\w./-]+)", text):
            refs.update(p for p in libs if p == "scripts/lib/" + ref or p.startswith("scripts/lib/" + ref.rstrip("/") + "/"))
        for target in refs:
            if path != target:
                reverse[target].add(path)
    return reverse, mentioned, code_named, frozenset(broken)


def dynamic(path):
    raw = contents(path)
    code = re.sub(rb"(?m)#.*$", b"", raw or b"")
    return raw is None or re.search(rb"\b(importlib|__import__)\b|sys\.path", code) is not None


@lru_cache(None)
def reaches(path):
    """Every file a change to path can reach through static imports, path included; None when unsure.

    Library modules and the Python modules they reach are followed to their importers. A dynamic library, a
    library nobody imports, and a reached module that has no importer and that no other file names (loaded by a
    computed path) are unsure."""
    graph, mentioned = library_graph()[:2]
    if path not in graph or not (path.startswith("scripts/lib/") or path.endswith(".py")):
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
        if (current != path and current.endswith(".py") and not importers
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
    """Other code imports the file or names it: its edges are known, it is not tree data."""
    graph, _, code_named, _ = library_graph()
    return bool(graph.get(path)) or bool(code_named.get(path.rsplit("/", 1)[-1], set()) - {path})


@lru_cache(None)
def owners(path):
    """Code files whose tree holds a file (deleted ones too): every file but a named code file or an index doc."""
    if "/" not in path or path in INDEX_DOCS or (path.endswith(SCANNED) and named(path)):
        return ()
    return tuple(p for root, code in code_trees().items() if in_tree(path, root) for p in code if p != path)


@lru_cache(None)
def closure(path):
    """Every file a change to path can reach, the code files whose tree holds it included; None when unsure."""
    found = set()
    for start in (path,) + owners(path):
        reached = reaches(start)
        if reached is None:
            return None
        found |= reached
    return frozenset(found)


@lru_cache(None)
def selects(path, suite):
    """A reached path selects the suite: it is the suite, a path its text names or one of its EXTRA patterns."""
    return path == suite or hit(path, suite_patterns(suite)) or hit(path, EXTRA.get(suite, []))


def always(path):
    return hit(path, GLOBAL) or "/" not in path


def needed(files, suite):
    if any(always(f) for f in files) or suite in files:
        return True
    if suite_patterns(suite) is None or library_graph()[3]:
        return True
    for f in files:
        reached = closure(f)
        if reached is None or any(selects(p, suite) for p in reached):
            return True
    return False


def hashes(suites):
    versions = [sys.version]
    for cmd in (["git", "--version"], ["bash", "--version"], ["jq", "--version"]):
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=10)
            versions.append(result.stdout.splitlines()[0].decode("utf-8", errors="replace") if result.stdout else "absent")
        except (OSError, subprocess.TimeoutExpired):
            versions.append("absent")
    # one pass over the tree: the files every suite depends on, and per reached path the files that reach it
    files = inventory()
    common, reached_by = set(), {}
    for f in files:
        reached = None if always(f) else closure(f)
        if reached is None:
            common.add(f)
            continue
        for p in reached:
            reached_by.setdefault(p, set()).add(f)
    for suite in suites:
        if suite_patterns(suite) is None or "*" in EXTRA.get(suite, []) or library_graph()[3]:
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
