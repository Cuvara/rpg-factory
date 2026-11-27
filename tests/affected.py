#!/usr/bin/env python3
"""Which run-all suites a change affects (tests/run-all.sh --affected).

  affected.py changed [BASE]        the changed files: merge-base(BASE, HEAD)..work tree, plus untracked files
                                    (BASE default: origin/main, else main)
  affected.py select FILE SUITE     exit 0 when SUITE must run for the changed files listed in FILE, else 1
  affected.py select-many FILE SUITE...
                                    print each SUITE that must run (same rule as select), one per line; the
                                    import graph is built once (run-all --affected calls it once per run)
  affected.py cases [--base REF] FILE SUITE...
                                    print each selected suite and its affected cases, or ALL when uncertain: the
                                    case map must name every file the suite selects in the import closure of a
                                    changed file. REF (default as for changed) gives the changed line ranges for
                                    symbol reach, used only when FILE is exactly the changed set from REF
  affected.py hashes SUITE...       print suite and input hash (or '-' when reuse is unsafe)

Case maps (`# case-map: <group> <pattern>...` header lines of a suite) and symbol reach (cases only):
  - a plain pattern (a glob, or a directory ending in /) reaches the files it matches (file-level);
  - PATH::NAME names a top-level def, class or module-level assignment NAME of the Python file PATH (an exact path,
    no glob) that the group runs as an entry point (a CLI verb's cmd_* function, a function a test calls directly);
    PATH::* reaches the whole file. A group with any PATH:: pattern for a file matches that file only through them
    (its own plain globs are ignored for that file); a group whose plain pattern matches the file without one keeps
    the whole file. A glob in PATH or a NAME that is not `*` or an identifier makes the map invalid (ALL);
  - a changed Python file some group names by symbol: the changed top-level def/class names come from the hunks of
    `git diff -U0` against the merge-base (old side: `git show <merge-base>:PATH`, new side: the work tree), each
    hunk mapped with ast to the def/class whose span (the def/class line to its end, decorators excluded) holds it on
    both sides, the same name on both. File-level instead: a new or deleted file, a side that does not parse, a
    duplicate or a different set of def/class names (added, deleted or renamed), a hunk outside one def/class
    (imports, constants, decorators, comments or blank lines between defs, top-level code) or across two;
  - a changed symbol reaches a group that names it or a symbol whose in-module reference closure holds it: the edges
    are the top-level names a def, class or assignment may read (ast.Name, scope-aware: a parameter or a name local
    to a function, lambda or comprehension shadows a top-level one unless declared global). File-level instead: a
    changed symbol that the import-time code reaches without entering a named symbol (the module-level statements, the
    `if __name__ == "__main__":` block and so main() and the helpers it calls before dispatch, class bodies,
    decorators, argument defaults and annotations), one no named symbol reaches, one that is not named in a module
    that can look its names up dynamically (globals(), locals(), vars(), eval, exec, __import__,
    importlib.import_module, sys.modules: a dict of callables or getattr dispatch must be named), or a NAME the file
    does not define. Groups that reach the whole file (PATH::* or a plain pattern) are always selected;
  - file-level reach of a file is every group with any pattern for it (PATH::NAME included), none -> ALL. A file the
    import closure reaches that is not itself changed (an importer or caller of the changed file) gets no symbol
    reasoning of its own: when the changed file falls back to file-level, every reached file is matched file-level;
    when the changed file narrows to symbols, a reached file adds only the groups that match it file-level and have
    no pattern at all for the changed file (a group that names the changed file, plain glob or PATH::, is decided by
    the changed file's symbol reach, so it must name the entries it reaches through callers). A reached file that
    no group of the map matches at all is unmapped: ALL, as on file-level reach; only a reached file whose every
    matching group names the changed file adds nothing. select, select-many and hashes never use symbols.

A suite runs when one of these holds (anything unsure runs):
  - a global input changed (GLOBAL: registry, hooks, manifests) - every suite runs;
  - a runner or selector change runs its explicitly mapped suites;
  - a change to scripts/factory-pipeline.py, scripts/lib/pipeline_route.py or scripts/lib/english.py (PIPELINE_SUITES)
    runs its mapped suites (two for the pipeline files; english-only, file-guard, git-guard for english.py) and a
    suite that itself names the file (exact path in its text or an EXTRA pattern), not the ~19 suites its import
    closure reaches; only selection is narrowed, hashes (suite reuse) keep the conservative closure;
  - a change to scripts/lib/workspace.sh (CALLER_SUITES) runs the suites that are one of its direct callers, or name it
    or one of them, not the ~43 its transitive callers reach (factory-cmd.py runs check-registry.sh); only selection
    is narrowed, hashes keep the conservative closure;
  - a library or Python module change reaches a named script or suite through static imports, followed through
    every tracked Python module on the way (unresolved/dynamic libraries and unnamed leaves run all; a leaf a
    suite's EXTRA patterns cover counts as named by that suite, e.g. tests/fixtures/assetgen/* for the assetgen suite);
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
library module that touches sys.path or importlib is unsure for selection unless every use is the plugin's own
static idiom (static_idiom), read with ast: a sys.path.insert(i, X) / sys.path.append(X) whose X resolves to an
existing directory inside this repo, an `X in sys.path` test, and importlib.util.spec_from_file_location(name, FILE,
submodule_search_locations=[DIR]) with module_from_spec (the rpgf_guard package loader in scripts/lib/gitguard.py)
whose FILE and DIR resolve inside the repo. X resolves by static evaluation only: string literals, __file__,
os.path.abspath/realpath/normpath/dirname/join and str() of resolvable parts, and a name that every assignment in the
module (or in the tracked module it is imported from with `from .mod import NAME`) binds to one resolvable value.
The resolved directory is the module's import root; import edges are already resolved by module stem in
library_graph(), so the idiom needs no extra edge. Anything else stays unsure: a computed or unresolvable entry,
importlib.import_module, __import__, sys.path assigned, sliced or aliased, and a string or bytes literal (not a
docstring) that holds sys.path, importlib or __import__ code. A Python module that calls
spec_from_file_location(name, FILE, ...) gets an importer edge for FILE
when FILE resolves by static evaluation (static_value) to an existing tracked file inside the repo (loaded_files): a
change to scripts/lib/rpgf_guard/__init__.py selects the suites that reach its loader scripts/lib/gitguard.py. A FILE
that does not resolve statically (a computed path) gets no edge, so a loaded file nobody imports stays unsure. hashes
(suite reuse) keep the conservative rule: any such mention is unsure there (dynamic(path, conservative=True),
reaches(path, True)). A tracked Python file that does not parse makes every selection unsure. Unknown paths
otherwise run only suites with matching rules; unknown top-level files run all. The reuse hash of a suite covers
exactly the files that select it under the conservative tree rule (plus its literal named paths).
Two uses, two tree rules. select / select-many (task QA iteration) use the narrow rule above: a code file with
a caller edge follows its edges only, so a library change selects only its importers; a miss there is caught by
the integration full run. hashes (suite reuse at that full run, where a false PASS is the risk) use the
conservative rule, a fixpoint: every file in the tree of every code file a suite reaches is an input, code files
with caller edges included (a helper one script names and another runs by a computed path), plus every module an
included code file imports, loads or runs, plus the trees of those, until nothing new is added (a library a helper
in a reached script's tree imports is an input of that script's suites). Only the index docs stay named-only,
library modules are included by import as single files (not their scripts/lib tree), and suites directly in
tests/ are not tree data.
Workspace checks (run-all --workspace-only: routing replay, routing properties, facts, the live product-repo checks, the
two `claude plugin validate` lines) carry their plugin-side inputs in WORKSPACE_INPUTS next to EXTRA, keyed by the path
run-all runs (and the pseudo key claude-plugin-validate, which has no file). They are part of selects(), so needed(),
cases and the reuse hashes see them; a pseudo key is needed only by a global or top-level file or its own patterns,
every other missing file stays unsure and runs. A docs-only change therefore selects none of them.
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
    # shared English-only detection: the check (global, scripts/checks/english-only.py) and the guards import it
    "scripts/lib/english.py": {"tests/english-only.test.sh", "tests/file-guard.test.sh", "tests/git-guard.test.sh"},
}

# shell libraries whose transitive callers fan out (factory-cmd.py runs check-registry.sh, which sources the library):
# selection stops at one hop, the file's direct callers (one_hop), and the suites that are or name one of them; the
# reuse hashes (hashes) still use the conservative closure
CALLER_SUITES = {"scripts/lib/workspace.sh"}

SKILL_TEXT = ["skills/*", ".claude/skills/*"]
# indirect inputs: what a suite reads without naming the file
EXTRA = {
    "tests/skills-lint.sh": SKILL_TEXT + ["commands/*", "agents/*", "scripts/checks/*"],
    "tests/parallel-policy.test.sh": SKILL_TEXT + ["tests/skills-lint.sh", "scripts/orca-wait.sh",
                                                   "tests/orca-wait.test.sh"],
    "tests/new-skill.test.sh": SKILL_TEXT + ["scripts/new-skill.py", "scripts/skill-touchpoints.py",
                                             "tests/routing.test.sh", "evals/*", "tests/skills-lint.sh",
                                             "docs/architecture/overview.md"],
    "scripts/checks/english-only.py": ["*"],
    "tests/english-only.test.sh": ["scripts/checks/english-only.py"],
    # the portable-paths enforce line is global too: any tracked file may hold a machine-specific user path
    "scripts/checks/portable-paths.py": ["*"],
    "tests/portable-paths.test.sh": ["scripts/checks/portable-paths.py"],
    # the workspace readers guard greps only scripts/ and tests/ under its ROOT (run-all passes '.'); hooks and registry
    # select it through GLOBAL; skills, docs, commands and evals are not read, so they do not select it
    "scripts/checks/workspace-readers.sh": ["scripts/*", "tests/*"],
    # the netcode evidence prune case sources prune_evidence from the script through a computed path
    "tests/run-all-parallel.test.sh": ["scripts/checks/netcode-headless.sh"],
    "tests/routing.test.sh": SKILL_TEXT + ["scripts/factory_session.py"],
    "tests/routing-golden.test.sh": SKILL_TEXT,
    "tests/ui-skills.test.sh": ["skills/ui-*", "docs/architecture/*"],
    "tests/orca-commands.test.sh": ["skills/delivery/references/delivery.md",
                                   "skills/factory-core/references/parallel-work.md", "docs/pipeline-cli.md"],
    # absent until task checks-lows lands: run-all lists a suite only when its file exists (list_suites), so while it is
    # absent --list-suites and --only-suites never name it and no candidate list holds it
    "tests/plan-paths.test.sh": ["scripts/lib/plan_paths.py", "scripts/lib/compat.sh"],
    "tests/delivery-generic.test.sh": ["skills/delivery/*", "scripts/factory-pipeline.py",
                                       "scripts/lib/pipeline_route.py"],
    "scripts/checks/skill-citations.py": SKILL_TEXT,
    "tests/commands.test.sh": ["commands/*", "scripts/factory-*.py", "scripts/run-checks.py", "scripts/ui/*",
                               "scripts/assetgen/*", "scripts/vfx/*"],
    "tests/assetgen.test.sh": ["scripts/assetgen/*", "templates/assetgen/*", "scripts/checks/domains/assetgen.py",
                               "scripts/checks/domains/_api.py", "scripts/checks/artifact-*.py",
                               "tests/fixtures/assetgen/*", "docs/schemas/kinds/gen-run.schema.json"],
    "tests/vfx-production.test.sh": ["scripts/vfx/*", "scripts/adapters/vfx/*", "docs/schemas/kinds/vfx-style.schema.json",
                                     "templates/vfx/*", "registry/domains/vfx.json", "tests/fixtures/vfx/*",
                                     "commands/vfx-plan.md", "commands/vfx-lint.md", "scripts/factory-cmd.py"],
    "tests/changelog.test.sh": ["changelog.d/*", "CHANGELOG.md"],
    "tests/codex-plugin.test.sh": [".agents/*", "docs/codex.md"],
    "tests/dogfood-grader.test.sh": ["tests/dogfood/*", "evals/*"],
    "tests/release-check.test.sh": ["VERSION", "README.md", "CHANGELOG.md"],
}
# Workspace checks (run-all --workspace-only, the regions between '# workspace-list-begin' and '# workspace-list-end' and
# the check-registry.sh line): the plugin-side files each reads that its text does not name (data, skills, docs, schemas)
# and the code it runs. Keys are the paths run-all passes to its run/runl/run1/gated lines; "claude-plugin-validate"
# is a pseudo key (no file: the two `claude plugin validate --strict` lines). A key is needed when a changed file
# matches its patterns, besides every rule above (needed() / selects()); a pseudo key is needed only by a global or
# top-level file or its patterns. The product repos these checks read are not plugin files: only a plugin change is
# scoped here. Unsure means run: a check that reads something not listed here must list it.
ROUTING_INPUTS = SKILL_TEXT + ["scripts/factory-context.sh", "scripts/factory_session.py", "scripts/lib/routing*",
                               "scripts/lib/context.py", "scripts/lib/resolve.jq", "evals/*"]
WORKSPACE_INPUTS = {
    # routing replay (tests/routing.test.sh) and routing properties (tests/routing-properties.test.py): the routing
    # code, the registry (global), the skills the routing reads and the evals scenarios
    "tests/routing.test.sh": ROUTING_INPUTS,
    "tests/routing-properties.test.py": ROUTING_INPUTS,
    # registry facts re-probed in the repos: the registry (global) and the probes in check-registry.sh; it greps
    # skills/ for volatile values
    "tests/facts.test.sh": ["skills/*", "scripts/check-registry.sh", "scripts/lib/compat.sh"],
    # registry paths exist in the workspace: registry.json (global), the schemas, the quality plugins and the
    # {plugin_root} files the registry names (scripts/checks/*), the skill directories and the policy libraries
    "scripts/check-registry.sh": ["docs/schemas/*", "docs/registry.schema.json", "scripts/checks/*", "skills/*",
                                  "scripts/lib/model_policy.py", "scripts/lib/subagent_policy.py",
                                  "scripts/lib/compat.sh"],
    # orca commands cited in the policies are checked against `orca --help`
    "tests/orca-commands.test.sh": ["skills/delivery/references/delivery.md",
                                    "skills/factory-core/references/parallel-work.md", "docs/pipeline-cli.md"],
    # citations in the skills against the integration branches (cite_roots live in the registry, global)
    "scripts/checks/skill-citations.py": SKILL_TEXT + ["scripts/lib/workspace.py"],
    # read-only product-repo checks: the plugin side is the script, the registry (global) and the libraries it loads
    "scripts/checks/sgl-determinism.py": [],
    "scripts/checks/pin-status.py": ["scripts/lib/plugin_registry.py", "scripts/lib/workspace.py"],
    "scripts/checks/wire-parity.sh": ["scripts/lib/workspace.sh", "scripts/lib/compat.sh"],
    "scripts/checks/pin-plan.py": ["scripts/lib/plugin_registry.py", "scripts/lib/workspace.py"],
    "scripts/checks/package-ready.py": [],
    "scripts/checks/netcode-headless.sh": ["scripts/lib/fstate.py", "scripts/lib/workspace.sh",
                                           "scripts/lib/compat.sh"],
    # factory-context live snapshot of every repo (the script is global; the code it loads)
    "scripts/factory-context.sh": ["scripts/lib/context.py", "scripts/lib/resolve.jq"],
    # factory-status on the real workspace: the registry (global), the evidence and state libraries
    "scripts/factory-status.py": ["scripts/lib/evidence.py", "scripts/lib/fstate.py", "scripts/lib/artifacts.py",
                                  "scripts/lib/workspace.py", "scripts/lib/plugin_registry.py"],
    # `claude plugin validate --strict` reads the plugin manifests, the marketplace, the skills, commands, agents
    # and hooks
    "claude-plugin-validate": [".claude-plugin/*", ".codex-plugin/*", ".agents/*", "skills/*", "commands/*",
                               "agents/*", "hooks/*"],
}
PATH_RE = re.compile(
    r"(?<![\w.-])((?:scripts|skills|commands|templates|docs|testlab|evals|hooks|tests)/[A-Za-z0-9_./*-]+)")


def git(*args):
    r = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout if r.returncode == 0 else None


def merge_base_changed(base=None):
    """(merge-base commit, changed files): merge-base(BASE, HEAD)..work tree plus untracked files; None without a base
    (BASE default: origin/main, else main)."""
    for b in ([base] if base else ["origin/main", "main"]):
        mb = git("merge-base", b, "HEAD")
        if mb:
            break
    else:
        return None  # no base: caller runs everything
    mb = mb.strip()
    files = set((git("diff", "--name-only", mb) or "").split())
    files |= set((git("ls-files", "--others", "--exclude-standard") or "").split())
    return mb, sorted(files)


def changed(base=None):
    found = merge_base_changed(base)
    return None if found is None else found[1]


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


def loaded_files(path, text, known):
    """Tracked files (keys of known) that a module loads by importlib.util.spec_from_file_location(name, FILE, ...) when
    FILE resolves by static evaluation (static_value) to an existing file inside this repo. A computed FILE gives no
    edge. Uses only the lru_cached static helpers, never library_graph()."""
    if "spec_from_file_location" not in text or parsed(path) is None:
        return set()
    found = set()
    for node in ast.walk(parsed(path)):
        fn = node.func if isinstance(node, ast.Call) else None
        if not (isinstance(fn, ast.Attribute) and fn.attr == "spec_from_file_location" and len(node.args) >= 2):
            continue
        value = static_value(node.args[1], path)
        if inside_root(value) and os.path.isfile(value):
            rel = os.path.relpath(value, ROOT).replace(os.sep, "/")
            if rel in known:
                found.add(rel)
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
        # a package loaded by path is unsure: its __init__.py name is no mention
        for base in (set(PY_FILE.findall(text)) | set(HELPER_FILE.findall(text))) - {"__init__.py"}:
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
        if path.endswith(".py") and path not in broken:
            refs.update(loaded_files(path, text, reverse))
        for base in load_refs(path, text):
            refs.update(by_name.get(base, ()))
        for base in load_refs(path, text, HELPER_FILE):
            refs.update(helpers.get(base, ()))
        for ref in re.findall(r"\blib/([\w./-]+)", text):
            refs.update(p for p in libs
                        if p == "scripts/lib/" + ref or p.startswith("scripts/lib/" + ref.rstrip("/") + "/"))
        for target in refs:
            if path != target:
                reverse[target].add(path)
    return reverse, mentioned, frozenset(broken)


DYNAMIC_TEXT = re.compile(r"\b(importlib|__import__)\b|sys\.path")
SPEC_CALLS = {"spec_from_file_location", "module_from_spec"}


@lru_cache(None)
def parsed(path):
    raw = contents(path)
    try:
        return None if raw is None else ast.parse(raw)
    except (SyntaxError, ValueError):
        return None


def inside_root(value):
    """An absolute path equal to ROOT or under it (compared by normcase(normpath))."""
    if not isinstance(value, str) or not os.path.isabs(value):
        return False
    here, root = os.path.normcase(os.path.normpath(value)), os.path.normcase(os.path.normpath(ROOT))
    return here == root or here.startswith(root.rstrip(os.sep) + os.sep)


@lru_cache(None)
def bindings(path):
    """name -> every way the module binds it: ("expr", node) for a single-target `NAME = expr`, ("from", level,
    module, name) for an import-from, ("other",) for anything else (augmented or tuple assignment, loop and with
    targets, parameters, imports, def/class, walrus). "*" is present when a star import can bind any name."""
    found = {}

    def add(name, kind):
        found.setdefault(name, []).append(kind)

    def stores(target):
        for n in ast.walk(target):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                add(n.id, ("other",))

    for node in ast.walk(parsed(path)):
        if isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                add(node.targets[0].id, ("expr", node.value))
            else:
                for target in node.targets:
                    stores(target)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign, ast.For, ast.AsyncFor, ast.comprehension)):
            stores(node.target)
        elif isinstance(node, ast.NamedExpr):
            stores(node.target)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    stores(item.optional_vars)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            add(node.name, ("other",))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            if not isinstance(node, ast.Lambda):
                add(node.name, ("other",))
            args = node.args
            for a in args.posonlyargs + args.args + args.kwonlyargs + [x for x in (args.vararg, args.kwarg) if x]:
                add(a.arg, ("other",))
        elif isinstance(node, ast.ClassDef):
            add(node.name, ("other",))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                add(alias.asname or alias.name.split(".")[0], ("other",))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    add("*", ("other",))
                else:
                    add(alias.asname or alias.name, ("from", node.level, node.module or "", alias.name))
        elif isinstance(node, (getattr(ast, "MatchAs", ()), getattr(ast, "MatchStar", ()))) and node.name:
            add(node.name, ("other",))
        elif isinstance(node, getattr(ast, "MatchMapping", ())) and node.rest:
            add(node.rest, ("other",))
    return found


def imported_module(path, level, module):
    """The one tracked module `from .mod import NAME` / `from mod import NAME` names, else None."""
    files = set(inventory())
    if level:
        stem = "/".join(path.split("/")[:-level] + ([module.replace(".", "/")] if module else []))
        found = [p for p in ([f"{stem}.py"] if module else []) + [f"{stem}/__init__.py"] if p in files]
    else:
        rel = module.replace(".", "/")
        found = [p for d in {"scripts/lib", path.rsplit("/", 1)[0]} for p in (f"{d}/{rel}.py", f"{d}/{rel}/__init__.py")
                 if p in files]
    return found[0] if len(set(found)) == 1 else None


def name_value(path, name, active):
    """The one string a module-level or local name always holds, else None."""
    key = (path, name)
    found = bindings(path)
    if key in active or "*" in found or name not in found:
        return None
    values = {}
    for kind in found[name]:
        if kind[0] == "expr":
            value = static_value(kind[1], path, active + (key,))
        elif kind[0] == "from":
            target = imported_module(path, kind[1], kind[2])
            value = name_value(target, kind[3], active + (key,)) if target and parsed(target) else None
        else:
            return None
        if value is None:
            return None
        values.setdefault(os.path.normpath(value), value)
    return next(iter(values.values())) if len(values) == 1 else None


def static_value(node, path, active=()):
    """The string an expression evaluates to without running code: literals, __file__, os.path.abspath/realpath/
    normpath/dirname/join and str() of resolvable parts, and names (name_value). None when it does not resolve."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.Name):
        if node.id == "__file__":
            return os.path.join(ROOT, *path.split("/"))
        return name_value(path, node.id, active)
    if not isinstance(node, ast.Call) or node.keywords:
        return None
    fn = node.func
    if isinstance(fn, ast.Name) and fn.id == "str" and len(node.args) == 1:
        return static_value(node.args[0], path, active)
    if not (isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Attribute) and fn.value.attr == "path"
            and isinstance(fn.value.value, ast.Name) and fn.value.value.id == "os"):
        return None
    parts = [static_value(a, path, active) for a in node.args]
    if not parts or None in parts:
        return None
    if fn.attr == "join":
        return os.path.join(*parts)
    if len(parts) != 1:
        return None
    if fn.attr in ("abspath", "realpath"):
        return os.path.normpath(parts[0]) if os.path.isabs(parts[0]) else None  # a relative one depends on the cwd
    return {"normpath": os.path.normpath, "dirname": os.path.dirname}.get(fn.attr, lambda _: None)(parts[0])


def resolves_in_root(node, path, kind):
    value = static_value(node, path)
    return inside_root(value) and (os.path.isdir(value) if kind == "dir" else os.path.isfile(value))


@lru_cache(None)
def static_idiom(path):
    """Every sys.path / importlib / __import__ use of a module is the plugin's own idiom (see the module docstring)."""
    tree_ = parsed(path)
    if tree_ is None:
        return False
    parent = {child: node for node in ast.walk(tree_) for child in ast.iter_child_nodes(node)}
    docstrings = {n.body[0].value for n in ast.walk(tree_) if isinstance(n, (ast.Module, ast.FunctionDef,
                  ast.AsyncFunctionDef, ast.ClassDef)) and n.body and isinstance(n.body[0], ast.Expr)}
    for node in ast.walk(tree_):
        if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)) and node not in docstrings:
            text = node.value if isinstance(node.value, str) else node.value.decode("utf-8", "replace")
            if DYNAMIC_TEXT.search(text):
                return False  # code in a string or bytes literal (a -c script, a getattr name) is not analysed
        elif isinstance(node, ast.Attribute) and node.attr in ("__import__", "import_module"):
            return False
        elif isinstance(node, ast.Import):
            if any(a.asname and a.name.split(".")[0] in ("sys", "importlib") for a in node.names):
                return False
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and (node.module or "").split(".")[0] in ("sys", "importlib"):
                return False
        elif isinstance(node, ast.Name) and node.id == "__import__":
            return False
        elif isinstance(node, ast.Name) and node.id == "sys":
            up = parent.get(node)
            if not (isinstance(up, ast.Attribute) and up.value is node):
                return False
            if up.attr != "path":
                continue
            use = parent.get(up)
            if (isinstance(use, ast.Compare) and up in use.comparators
                    and all(isinstance(o, (ast.In, ast.NotIn)) for o in use.ops)):
                continue
            call = parent.get(use)
            if not (isinstance(use, ast.Attribute) and use.value is up and use.attr in ("insert", "append")
                    and isinstance(call, ast.Call) and call.func is use and not call.keywords
                    and len(call.args) == (2 if use.attr == "insert" else 1)
                    and resolves_in_root(call.args[-1], path, "dir")):
                return False
        elif isinstance(node, ast.Name) and node.id == "importlib":
            util = parent.get(node)
            fn = parent.get(util)
            call = parent.get(fn)
            if not (isinstance(util, ast.Attribute) and util.value is node and util.attr == "util"
                    and isinstance(fn, ast.Attribute) and fn.value is util and fn.attr in SPEC_CALLS
                    and isinstance(call, ast.Call) and call.func is fn):
                return False
            if fn.attr == "module_from_spec":
                if call.keywords or len(call.args) != 1:
                    return False
                continue
            if len(call.args) != 2 or not resolves_in_root(call.args[1], path, "file"):
                return False
            for kw in call.keywords:
                if kw.arg != "submodule_search_locations" or not isinstance(kw.value, (ast.List, ast.Tuple)) or not all(
                        resolves_in_root(e, path, "dir") for e in kw.value.elts):
                    return False
    return True


@lru_cache(None)
def dynamic(path, conservative=False):
    """The module may import by a path the graph cannot see. conservative (reuse hashes): any sys.path, importlib or
    __import__ mention in the code. Otherwise (selection): only a use that is not the plugin's static idiom."""
    raw = contents(path)
    code = re.sub(rb"(?m)#.*$", b"", raw or b"")
    if raw is None:
        return True
    if re.search(rb"\b(importlib|__import__)\b|sys\.path", code) is None:
        return False
    return conservative or not static_idiom(path)


def extra_covered(path):
    """A suite's EXTRA patterns cover the path: the suite reads it without naming the file (a computed name), so
    that is a mention by the suite. Only suites under tests/ count, not the patterns of the global guards
    (scripts/checks/english-only.py, scripts/checks/portable-paths.py, scripts/checks/workspace-readers.sh)."""
    return any(suite.startswith("tests/") and hit(path, patterns) for suite, patterns in EXTRA.items())


@lru_cache(None)
def reaches(path, conservative=False):
    """Every file a change to path can reach through static edges, path included; None when unsure.

    Library modules and the code files they reach are followed to their importers and callers. A dynamic
    library, a library nobody imports, and a reached code file that has no importer and that no other file
    names (loaded or run by a computed path) are unsure, unless a suite's EXTRA patterns cover it (that suite
    mentions it: selects() then picks the suite); a suite directly in tests/ has no caller (run-all runs it).
    conservative (reuse hashes) keeps the blanket dynamic() rule; selection uses the static-idiom rule."""
    graph, mentioned = library_graph()[:2]
    if path not in graph:
        return frozenset([path])
    todo, seen = [path], set()
    while todo:
        current = todo.pop()
        if current in seen:
            continue
        seen.add(current)
        if current.startswith("scripts/lib/") and dynamic(current, conservative):
            return None
        importers = graph.get(current, ())
        if (current != path and current.endswith(SCANNED) and not importers and tree(current) != ("tests/", False)
                and not mentioned.get(current.rsplit("/", 1)[-1], set()) - {current} and not extra_covered(current)):
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
        reached = reaches(start, True)
        if reached is None:
            return None
        new = reached - found
        found |= reached
        todo.extend(owner for p in new for owner in owners(p, True) if owner not in found)
    return frozenset(found)


@lru_cache(None)
def selects(path, suite):
    """A reached path selects the suite: it is the suite, a path its text names, one of its EXTRA patterns or (a
    workspace check) one of its WORKSPACE_INPUTS patterns. WORKSPACE_INPUTS is part of selects(), so the reuse hash
    (hashes) covers it too."""
    return (path == suite or hit(path, suite_patterns(suite) or ()) or hit(path, EXTRA.get(suite, []))
            or hit(path, WORKSPACE_INPUTS.get(suite, [])))


def names(path, suite):
    """The suite itself names the file: its text holds the exact path, or one of its EXTRA patterns matches. A
    directory or glob the text mentions (scripts/lib, scripts/*.py) does not name a file in it."""
    return path == suite or path in suite_patterns(suite) or hit(path, EXTRA.get(suite, []))


def one_hop(path):
    """The file and its direct importers/callers (one edge of the graph, no transitive closure)."""
    return frozenset([path]) | frozenset(library_graph()[0].get(path, ()))


def always(path):
    return hit(path, GLOBAL) or "/" not in path


def needed(files, suite):
    if any(always(f) for f in files) or suite in files:
        return True
    if library_graph()[2]:
        return True
    if suite_patterns(suite) is None:
        # a pseudo workspace check (no file: claude-plugin-validate) runs for a global/top-level file (above) or when
        # a changed file is one of its inputs; any other missing file is unsure and runs
        if suite in WORKSPACE_INPUTS and "/" not in suite:
            return any(hit(f, WORKSPACE_INPUTS[suite]) for f in files)
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
        if f in CALLER_SUITES:
            if any(names(p, suite) for p in one_hop(f)):
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
            for pattern in patterns.split():
                symbol = split_symbol(pattern)
                if symbol and not valid_symbol(*symbol):
                    return None
            cases.setdefault(name, []).extend(patterns.split())
    return cases or None


# symbol-level case reach (`PATH::NAME` case-map patterns, see the module docstring)
IDENT = re.compile(r"[A-Za-z_]\w*")
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", re.M)
DEFS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def split_symbol(pattern):
    """(PATH, NAME) of a `PATH::NAME` case-map pattern, else None (a plain glob)."""
    return tuple(pattern.split("::", 1)) if "::" in pattern else None


def valid_symbol(path, name):
    """PATH is an exact path of a Python file (no glob, no directory); NAME is `*` or an identifier."""
    return (path.endswith(".py") and not any(c in path for c in "*?[") and not path.startswith("/")
            and (name == "*" or IDENT.fullmatch(name) is not None))


def plain_hit(path, pattern):
    return fnmatch.fnmatchcase(path, pattern + "*" if pattern.endswith("/") else pattern)


def group_reach(path, patterns):
    """How one case group reaches a file: "whole" (a plain pattern matches it and the group has no `PATH::` pattern for
    it, or `PATH::*`), the frozenset of NAMEs of its `PATH::NAME` patterns, or None (the group does not run it).
    `PATH::` patterns override the group's own plain globs for that file."""
    names = frozenset(s[1] for s in map(split_symbol, patterns) if s and s[0] == path)
    if names:
        return "whole" if "*" in names else names
    return "whole" if any(plain_hit(path, p) for p in patterns if "::" not in p) else None


def file_groups(path, mapping):
    """Every group with any pattern for the file (file-level reach)."""
    return {g for g, patterns in mapping.items() if group_reach(path, patterns) is not None}


def top_level(tree_):
    """name -> the top-level statements that bind it: def, class, and Assign/AnnAssign/AugAssign name targets."""
    found = {}
    for node in tree_.body:
        if isinstance(node, DEFS):
            found.setdefault(node.name, []).append(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                for n in ast.walk(target):
                    if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                        found.setdefault(n.id, []).append(node)
    return found


def import_time_parts(node):
    """The parts of a top-level statement that run when the module is imported: a def's decorators, argument defaults
    and annotations; a class's decorators, bases, keywords and body (its methods by the def rule); any other statement
    whole."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        args = node.args
        parts = list(node.decorator_list) + list(args.defaults) + [d for d in args.kw_defaults if d is not None]
        parts += [a.annotation for a in args.posonlyargs + args.args + args.kwonlyargs + [x for x in (args.vararg,
                  args.kwarg) if x] if a.annotation is not None]
        return parts + ([node.returns] if node.returns is not None else [])
    if isinstance(node, ast.ClassDef):
        parts = list(node.decorator_list) + list(node.bases) + [k.value for k in node.keywords]
        return parts + [p for stmt in node.body for p in import_time_parts(stmt)]
    return [node]


COMPS = (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)


def scope_names(fn):
    """(locals, globals) of a function or lambda scope: its parameters and the names its own body binds (assignment,
    for/with/except/match targets, local def/class, import aliases; nested scopes and comprehensions excluded), minus
    the names it declares global or nonlocal; and the names it declares global. A binding missed here only adds edges."""
    args = fn.args
    bound = {a.arg for a in args.posonlyargs + args.args + args.kwonlyargs + [x for x in (args.vararg, args.kwarg) if x]}
    declared, globals_ = set(), set()
    todo = list(fn.body) if isinstance(fn.body, list) else [fn.body]
    while todo:
        n = todo.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(n.name)
            continue
        if isinstance(n, (ast.Lambda,) + COMPS):
            continue
        if isinstance(n, (ast.Global, ast.Nonlocal)):
            declared.update(n.names)
            if isinstance(n, ast.Global):
                globals_.update(n.names)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            bound.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            bound.update(a.asname or a.name.split(".")[0] for a in n.names if a.name != "*")
        elif isinstance(n, ast.ExceptHandler) and n.name:
            bound.add(n.name)
        elif isinstance(n, (getattr(ast, "MatchAs", ()), getattr(ast, "MatchStar", ()))) and n.name:
            bound.add(n.name)
        elif isinstance(n, getattr(ast, "MatchMapping", ())) and n.rest:
            bound.add(n.rest)
        todo.extend(ast.iter_child_nodes(n))
    return bound - declared, globals_


def module_refs(node, shadow=frozenset()):
    """ast.Name ids in node that may read module scope: a name local to an enclosing function, lambda or comprehension
    scope is not one (unless declared global there). Decorators, defaults and annotations read the enclosing scope;
    a class body is not a scope for its methods, and its own bindings do not shadow (conservative)."""
    found = set()

    def visit(n, shadow):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            args = n.args
            outer = list(args.defaults) + [d for d in args.kw_defaults if d is not None]
            if not isinstance(n, ast.Lambda):
                outer += list(n.decorator_list) + [a.annotation for a in args.posonlyargs + args.args + args.kwonlyargs
                                                   + [x for x in (args.vararg, args.kwarg) if x] if a.annotation]
                outer += [n.returns] if n.returns is not None else []
            for x in outer:
                visit(x, shadow)
            local, globals_ = scope_names(n)
            inner = (shadow - globals_) | local
            for x in (n.body if isinstance(n.body, list) else [n.body]):
                visit(x, inner)
            return
        if isinstance(n, COMPS):
            targets = {t.id for g in n.generators for t in ast.walk(g.target) if isinstance(t, ast.Name)}
            visit(n.generators[0].iter, shadow)   # the first iterable runs in the enclosing scope
            rest = [n.key, n.value] if isinstance(n, ast.DictComp) else [n.elt]
            rest += [x for i, g in enumerate(n.generators) for x in ([g.target] + list(g.ifs) + ([g.iter] if i else []))]
            for x in rest:
                visit(x, shadow | targets)
            return
        if isinstance(n, ast.Name):
            if n.id not in shadow:
                found.add(n.id)
            return
        for child in ast.iter_child_nodes(n):
            visit(child, shadow)

    visit(node, frozenset(shadow))
    return found


def dynamic_module(tree_):
    """The module can reach its own names by a computed name: globals(), locals() or vars() without an argument, eval,
    exec, __import__, importlib.import_module or sys.modules."""
    for n in ast.walk(tree_):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("globals", "locals", "vars") \
                and not n.args and not n.keywords:
            return True
        if isinstance(n, ast.Name) and n.id in ("eval", "exec", "__import__"):
            return True
        if isinstance(n, ast.Attribute) and (n.attr == "import_module" or n.attr == "modules" and isinstance(
                n.value, ast.Name) and n.value.id == "sys"):
            return True
        if isinstance(n, ast.ImportFrom) and (n.module or "") in ("sys", "importlib") \
                and any(a.name in ("modules", "import_module") for a in n.names):
            return True
    return False


@lru_cache(None)
def symbol_index(path):
    """(top-level names, reference edges, import-time root references, dynamic) of the work-tree file; None when it
    does not parse. An edge name -> every top-level name of the same file that a statement binding name may read
    (module_refs: a function-local name that shadows a top-level one is no edge)."""
    tree_ = parsed(path)
    if tree_ is None:
        return None
    tops = top_level(tree_)
    edges = {name: frozenset(r for node in nodes for r in module_refs(node) if r in tops)
             for name, nodes in tops.items()}
    roots = frozenset(r for stmt in tree_.body for part in import_time_parts(stmt) for r in module_refs(part)
                      if r in tops)
    return frozenset(tops), edges, roots, dynamic_module(tree_)


def symbol_closure(starts, edges, stop=frozenset()):
    """Every name reachable from starts through edges; names in stop are neither entered nor included."""
    seen, todo = set(), [s for s in starts if s not in stop]
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        todo.extend(x for x in edges.get(name, ()) if x not in seen and x not in stop)
    return seen


def def_spans(tree_):
    """[(name, first line, last line)] of the top-level def/class statements (decorators excluded); None when a name
    is defined twice."""
    spans = [(n.name, n.lineno, n.end_lineno) for n in tree_.body if isinstance(n, DEFS)]
    return spans if len({s[0] for s in spans}) == len(spans) else None


def def_at(spans, start, count):
    """The top-level def/class whose span holds one side of a hunk (count 0: an insertion point after line start,
    strictly inside the span), else None."""
    for name, first, last in spans:
        if (first <= start < last) if count == 0 else (first <= start and start + count - 1 <= last):
            return name
    return None


@lru_cache(None)
def changed_symbols(path, mb):
    """The top-level def/class names a change to the Python file touches (merge-base mb against the work tree), or
    None (file-level): a new or deleted file, a side that does not parse, a duplicate or a different set of def/class
    names (added, deleted or renamed), a hunk outside one def/class on either side or mapping to two names, no hunk."""
    old_raw, new_raw = git("show", f"{mb}:{path}"), contents(path)
    if old_raw is None or new_raw is None:
        return None
    try:
        old_tree, new_tree = ast.parse(old_raw), ast.parse(new_raw)
    except (SyntaxError, ValueError):
        return None
    old_spans, new_spans = def_spans(old_tree), def_spans(new_tree)
    if old_spans is None or new_spans is None or {s[0] for s in old_spans} != {s[0] for s in new_spans}:
        return None
    diff = git("diff", "-U0", "--no-color", "--no-ext-diff", mb, "--", path)
    if diff is None:
        return None
    found = set()
    for a, b, c, d in HUNK.findall(diff):
        old = def_at(old_spans, int(a), 1 if b == "" else int(b))
        new = def_at(new_spans, int(c), 1 if d == "" else int(d))
        if old is None or old != new:
            return None
        found.add(old)
    return frozenset(found) or None


def symbol_groups(path, mapping, mb):
    """The groups a change to the changed Python file reaches through its changed top-level symbols, or None
    (file-level): see the module docstring for the rules."""
    reach = {g: group_reach(path, patterns) for g, patterns in mapping.items()}
    named = frozenset(n for r in reach.values() if isinstance(r, frozenset) for n in r)
    if not named or mb is None:
        return None
    index = symbol_index(path)
    touched = changed_symbols(path, mb)
    if index is None or touched is None:
        return None
    tops, edges, roots, dynamic_ = index
    if not named <= tops:
        return None  # a NAME the file does not define: the map is invalid for this file
    common = symbol_closure(roots, edges, stop=named)
    hits = {g for g, r in reach.items() if r == "whole"}
    for symbol in touched:
        if symbol in common or (dynamic_ and symbol not in named):
            return None
        groups = {g for g, r in reach.items() if isinstance(r, frozenset)
                  and any(symbol in symbol_closure([n], edges) for n in r)}
        if not groups:
            return None
        hits |= groups
    return hits


def affected_cases(files, suite, mb=None):
    """The comma list of the suite's affected case groups, or ALL. mb: the merge-base commit the changed list files
    was computed from (cases checks it is exactly that list); with it, a changed Python file the map names by symbol
    (`PATH::NAME`) narrows to the groups its changed top-level symbols reach. None: file-level reach only."""
    mapping = case_map(suite)
    if mapping is None or suite in files or any(always(f) for f in files) or library_graph()[2]:
        return "ALL"
    selected = set()
    for path in files:
        if not needed([path], suite):
            continue
        if path in PIPELINE_SUITES:
            reached = frozenset([path])
        elif path in CALLER_SUITES:
            reached = one_hop(path)
        else:
            reached = closure(path)
        if reached is None:
            return "ALL"
        # a shared module reaches every file that imports it: each reached file the suite selects must be mapped
        # (the suite itself is reached through its own named scripts and says nothing about a case)
        symbols = symbol_groups(path, mapping, mb) if mb and path.endswith(".py") else None
        for hit_path in sorted(p for p in reached if p != suite and selects(p, suite)):
            if symbols is None:
                matched = file_groups(hit_path, mapping)
            elif hit_path == path:
                matched = symbols
            else:
                # the changed file narrowed to symbols: a caller or importer of it (no cross-module symbol reasoning)
                # adds only the groups that run the caller and have no pattern for the changed file; a group that
                # names the changed file is decided by its symbol reach (it names the entries it reaches via callers).
                # A caller no group matches at all is unmapped: ALL, as on file-level reach
                callers = file_groups(hit_path, mapping)
                matched = {g for g in callers if group_reach(path, mapping[g]) is None}
                if callers and not matched:
                    continue
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
            versions.append(
                result.stdout.splitlines()[0].decode("utf-8", errors="replace") if result.stdout else "absent")
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
        inputs.update(p for p in suite_patterns(suite)
                      if not any(c in p for c in "*?[") and not os.path.isdir(os.path.join(ROOT, p)))
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
    if argv[:1] == ["cases"] and len(argv) >= 2 and (argv[1] != "--base" or len(argv) >= 4):
        ref, args = (argv[2], argv[3:]) if argv[1] == "--base" else (None, argv[1:])
        with open(args[0], encoding="utf-8") as fh:
            files = [x.strip() for x in fh if x.strip()]
        # line ranges only when FILE is exactly the changed set from that base (else every file is file-level)
        found = merge_base_changed(ref)
        mb = found[0] if found is not None and set(found[1]) == set(files) else None
        lines = [suite + "\t" + affected_cases(files, suite, mb) + "\n"
                 for suite in dict.fromkeys(args[1:]) if needed(files, suite)]
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
