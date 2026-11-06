"""Shared guard configuration and workspace helpers."""
import json
import os
import sys

from pluginroot import plugin_root
from workspace import find_workspace, git_out, linked_worktree, main_checkout, native_path

DEFAULT_PROTECTED = ["develop", "staging", "main", "master", "release-*"]
TAG_REF = r"^(refs/tags/|v\d|sgl-v\d|core-baseline)"
SEPARATORS = {";", "&&", "||", "|", "&", "(", ")", "\n"}
GLOBAL_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "bash.exe", "sh.exe", "wsl", "wsl.exe"}
POWERSHELLS = {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}
CMDS = {"cmd", "cmd.exe"}
INTERPRETERS = {"python", "python3", "python.exe", "py", "node", "node.exe", "perl", "ruby", "php", "deno", "bun"}
CD_WORDS = {"cd", "pushd", "set-location", "sl", "push-location", "chdir"}
MUTATING_GIT_WORDS = {"reset", "clean", "checkout", "restore", "stash", "branch", "push", "add", "commit", "tag",
                      "submodule", "rebase", "merge", "cherry-pick", "revert", "am", "update-ref", "gc", "reflog",
                      "switch", "worktree", "filter-branch", "filter-repo", "pull", "rm", "mv", "apply", "prune"}
GIT_BUILTINS = MUTATING_GIT_WORDS | {"status", "log", "diff", "show", "fetch", "remote", "config", "rev-parse",
                                     "ls-files", "ls-remote", "ls-tree", "cat-file", "describe", "blame", "grep",
                                     "shortlog", "for-each-ref", "symbolic-ref", "check-ignore", "archive", "bisect",
                                     "clone", "init", "notes", "count-objects", "fsck", "help", "version", "diff-tree",
                                     "name-rev", "merge-base", "rev-list", "var", "whatchanged", "range-diff",
                                     "sparse-checkout", "maintenance", "repack", "replace", "format-patch",
                                     "request-pull", "bundle", "filter-repo"}
MAX_DEPTH = 4
MAX_COMMAND = 200_000  # characters; longer commands are not analysed (shlex on them takes minutes)
# git subcommands whose classification never depends on the branch or the repo: no git calls needed for them
STATELESS_READ_GIT = {"status", "log", "diff", "show", "rev-parse", "ls-files", "ls-remote", "ls-tree", "cat-file",
                      "describe", "blame", "grep", "shortlog", "for-each-ref", "check-ignore", "merge-base", "rev-list",
                      "name-rev", "count-objects", "help", "version", "range-diff", "diff-tree", "whatchanged", "var"}
# shell reserved words that can start a segment in front of the command that really runs
RESERVED_LEAD = {"{", "}", "!", "if", "then", "else", "elif", "do", "while", "until", "elseif", "try", "finally"}


LIB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.dirname(LIB)  # factory_session.py lives here
if LIB not in sys.path:
    sys.path.append(LIB)  # appended: stdlib lookups must not stat /mnt/c first
from pluginroot import plugin_root
from workspace import find_workspace, git_out, linked_worktree, main_checkout, native_path  # noqa: E402,F401  (public: scripts/git-guard.py re-exports them)
PLUGIN_ROOT = plugin_root()


def load_registry():
    try:
        with open(os.path.join(PLUGIN_ROOT, "registry.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def within(path, root):
    """True when `path` is `root` or below it. Compares normalised paths (Windows: forward vs back slashes,
    case), not strings: a payload cwd of `C:/ws/x` must match a workspace found with backslashes."""
    a, b = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(root))
    return a == b or a.startswith(b.rstrip("/\\") + os.sep)


def outside_workspace(eff, registry, cache):
    """(workspace, main checkout) for a directory outside every workspace that is a linked worktree whose main
    checkout lies in a workspace (an Orca worktree of a workspace repo): git there gets that checkout's rules.
    No git call (the worktree's `.git` file names its main checkout), memoised per hook call; any error or a main
    checkout outside the workspace = None (no opinion)."""
    if eff not in cache:
        cache[eff] = None
        lw = linked_worktree(eff)
        if lw:
            main = lw[1]
            ws = find_workspace(main, registry)
            if ws and within(main, ws) and os.path.normcase(main) != os.path.normcase(os.path.abspath(ws)):
                cache[eff] = (ws, main)
    return cache[eff]


def protected_patterns(repo_top, workspace, registry):
    main = os.path.abspath(main_checkout(repo_top)) if repo_top else None
    for repo in registry.get("repos", {}).values():
        if os.path.abspath(os.path.join(workspace, repo["path"])) in (repo_top, main):
            return repo.get("protected_branches", DEFAULT_PROTECTED)
    return DEFAULT_PROTECTED


def is_protected(branch, patterns):
    for p in patterns:
        if p.endswith("*") and branch.startswith(p[:-1]):
            return True
        if branch == p:
            return True
    return False


