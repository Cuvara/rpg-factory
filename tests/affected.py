#!/usr/bin/env python3
"""Which run-all suites a change affects (tests/run-all.sh --affected).

  affected.py changed [BASE]        the changed files: merge-base(BASE, HEAD)..work tree, plus untracked files
                                    (BASE default: origin/main, else main)
  affected.py select FILE SUITE     exit 0 when SUITE must run for the changed files listed in FILE, else 1

A suite runs when one of these holds (anything unsure runs):
  - a global input changed (GLOBAL: registry, shared libraries, hooks, manifests, run-all itself) - every suite runs;
  - the suite file itself changed;
  - a changed file is a path the suite's own text names (scripts/..., skills/..., commands/..., docs/..., ...);
  - a changed file matches one of the suite's EXTRA patterns (indirect inputs the text does not name).
Read-only. A full run (no --affected) stays the gate before a PR.
"""
import fnmatch
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GLOBAL = ["registry.json", "registry/*", "scripts/lib/*", "hooks/*", ".claude-plugin/*", ".codex-plugin/*",
          "tests/run-all.sh", "tests/affected.py", "scripts/factory-context.sh", "docs/registry.schema.json"]

SKILL_TEXT = ["skills/*", ".claude/skills/*"]
# indirect inputs: what a suite reads without naming the file
EXTRA = {
    "tests/skills-lint.sh": SKILL_TEXT + ["commands/*", "scripts/checks/*"],
    "tests/parallel-policy.test.sh": SKILL_TEXT + ["tests/skills-lint.sh"],
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


def needed(files, suite):
    if any(hit(f, GLOBAL) for f in files) or suite in files:
        return True
    try:
        text = open(os.path.join(ROOT, suite), encoding="utf-8", errors="replace").read()
    except OSError:
        return True
    named = {m.rstrip(".,;:)'\"`") for m in PATH_RE.findall(text)}
    for f in files:
        for n in named:
            if f == n or f.startswith(n.rstrip("/") + "/") or ("*" in n and fnmatch.fnmatch(f, n)):
                return True
    return any(hit(f, EXTRA.get(suite, [])) for f in files)


def main(argv):
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
