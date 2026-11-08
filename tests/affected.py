#!/usr/bin/env python3
"""Which run-all suites a change affects (tests/run-all.sh --affected).

  affected.py changed [BASE]        the changed files: merge-base(BASE, HEAD)..work tree, plus untracked files
                                    (BASE default: origin/main, else main)
  affected.py select FILE SUITE     exit 0 when SUITE must run for the changed files listed in FILE, else 1
  affected.py hashes SUITE...       print suite and input hash (or '-' when reuse is unsafe)

A suite runs when one of these holds (anything unsure runs):
  - a global input changed (GLOBAL: registry, hooks, manifests, run-all itself) - every suite runs;
  - a library or Python module change reaches a named script or suite through static imports, followed through
    every tracked Python module on the way (unresolved/dynamic libraries, unnamed leaves run all);
  - the suite file itself changed;
  - a changed file is a path the suite's own text names (scripts/..., skills/..., commands/..., docs/..., ...);
  - a changed file matches one of the suite's EXTRA patterns (indirect inputs the text does not name).
Unknown paths otherwise run only suites with matching rules; unknown top-level files run all.
Read-only. Integration owns the full run before a PR.
"""
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
PY_FILE = re.compile(r"[\w-]+\.py\b")
LOADER = re.compile(r"spec_from_file_location|run_path|exec_module")
LOAD_LINE = re.compile(r"join\(|/\s*['\"]|['\"]/|__file__|\b(HERE|ROOT|SCRIPTS)\b|subprocess|sys\.executable|\bexec")


def load_refs(path, text):
    """Python file names that code loads or runs: every name in a shell/jq file or in a Python module that loads
    files (spec_from_file_location), else only names on a line that builds a path or runs a process (a bare
    name in a message or an allow-list is not a dependency)."""
    if not path.endswith(".py") or LOADER.search(text):
        return set(PY_FILE.findall(text))
    return {base for line in text.splitlines() if LOAD_LINE.search(line) for base in PY_FILE.findall(line)}


@lru_cache(None)
def library_graph():
    """Reverse static edges over scripts/lib/* and every tracked Python module; scan each file once.

    An edge A -> B means A imports B by name, names B's file (spec_from_file_location, exec, a shell call) or,
    for scripts/lib, references lib/<B>. Also returns the file names any tracked text file mentions."""
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
    mentioned = {}
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
        if not path.endswith(SCANNED) or path in NOT_IMPORTERS:
            continue
        names = set(re.findall(r"\bfrom\s+([\w.]+)\s+import\b", text))
        for clause in re.findall(r"\bimport\s+([\w., ]+)", text):
            names.update(part.strip().split(" ")[0] for part in clause.split(","))
        refs = set()
        for name in names:
            refs.update(aliases.get(name, ()))
        for dots, module, clause in re.findall(r"\bfrom\s+(\.+)([\w.]*)\s+import\s+([\w., ]+)", text):
            package = "/".join(path.split("/")[:-len(dots)])
            stems = [module.replace(".", "/")] if module else [part.strip().split(" ")[0] for part in clause.split(",")]
            refs.update(p for stem in stems for p in (f"{package}/{stem}.py", f"{package}/{stem}/__init__.py") if p in reverse)
        for base in load_refs(path, text):
            refs.update(by_name.get(base, ()))
        for ref in re.findall(r"\blib/([\w./-]+)", text):
            refs.update(p for p in libs if p == "scripts/lib/" + ref or p.startswith("scripts/lib/" + ref.rstrip("/") + "/"))
        for target in refs:
            if path != target:
                reverse[target].add(path)
    return reverse, mentioned


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
    graph, mentioned = library_graph()
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


def needed(files, suite):
    if any(hit(f, GLOBAL) or "/" not in f for f in files) or suite in files:
        return True
    named = suite_patterns(suite)
    if named is None:
        return True
    for f in files:
        reached = reaches(f)
        if reached is None:
            return True
        if suite in reached or any(hit(p, named) or hit(p, EXTRA.get(suite, [])) for p in reached):
            return True
    return any(hit(f, EXTRA.get(suite, [])) for f in files)


def hashes(suites):
    versions = [sys.version]
    for cmd in (["git", "--version"], ["bash", "--version"], ["jq", "--version"]):
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=10)
            versions.append(result.stdout.splitlines()[0].decode("utf-8", errors="replace") if result.stdout else "absent")
        except (OSError, subprocess.TimeoutExpired):
            versions.append("absent")
    files = inventory()
    for suite in suites:
        if suite_patterns(suite) is None or "*" in EXTRA.get(suite, []):
            print(suite, "-")
            continue
        digest = hashlib.sha256(repr(versions).encode())
        inputs = {f for f in files if needed([f], suite)} | {suite}
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
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
