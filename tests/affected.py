#!/usr/bin/env python3
"""Which run-all suites a change affects (tests/run-all.sh --affected).

  affected.py changed [BASE]        the changed files: merge-base(BASE, HEAD)..work tree, plus untracked files
                                    (BASE default: origin/main, else main)
  affected.py select FILE SUITE     exit 0 when SUITE must run for the changed files listed in FILE, else 1
  affected.py hashes SUITE...       print suite and input hash (or '-' when reuse is unsafe)

A suite runs when one of these holds (anything unsure runs):
  - a global input changed (GLOBAL: registry, hooks, manifests, run-all itself) - every suite runs;
  - a library change reaches a named script or suite through static imports (unresolved/dynamic libraries run all);
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


@lru_cache(None)
def library_graph():
    """Reverse static edges; scan each file once, including shell/jq references."""
    libs = [p for p in inventory() if p.startswith("scripts/lib/")]
    aliases = {}
    for p in libs:
        rel = p[len("scripts/lib/"):]
        module = rel.removesuffix(".py").replace("/", ".").removesuffix(".__init__")
        for name in {module, module.split(".")[0]}:
            aliases.setdefault(name, set()).add(p)
    reverse = {p: set() for p in libs}
    for path in inventory():
        if not path.endswith((".py", ".sh", ".jq")):
            continue
        raw = contents(path)
        if raw is None or b"\0" in raw:
            continue
        text = raw.decode("utf-8", errors="replace")
        names = set(re.findall(r"\bfrom\s+([\w.]+)\s+import\b", text))
        for clause in re.findall(r"\bimport\s+([\w., ]+)", text):
            names.update(part.strip().split(" ")[0] for part in clause.split(","))
        refs = set()
        for name in names:
            refs.update(aliases.get(name, ()))
        for ref in re.findall(r"\blib/([\w./-]+)", text):
            refs.update(p for p in libs if p == "scripts/lib/" + ref or p.startswith("scripts/lib/" + ref.rstrip("/") + "/"))
        for lib in refs:
            if path != lib:
                reverse[lib].add(path)
    return reverse


@lru_cache(None)
def reaches(path):
    if not path.startswith("scripts/lib/"):
        return frozenset([path])
    graph = library_graph()
    todo, seen = [path], set()
    while todo:
        current = todo.pop()
        if current in seen:
            continue
        seen.add(current)
        if current.startswith("scripts/lib/"):
            raw = contents(current)
            code = re.sub(rb"(?m)#.*$", b"", raw or b"")
            if raw is None or re.search(rb"\b(importlib|__import__)\b|sys\.path", code):
                return None
            todo.extend(graph.get(current, ()))
    if not any(not p.startswith("scripts/lib/") for p in seen):
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
