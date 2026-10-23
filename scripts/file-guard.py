#!/usr/bin/env python3
"""rpg-factory file guard - PreToolUse hook for Claude's file tools (Write, Edit, MultiEdit, NotebookEdit, Read).

The shell guard (git-guard.py) only sees Bash/PowerShell. File tools write directly, so
this hook applies the same workspace rules to the target path. Inside the workspace only (RPG_FACTORY_WORKSPACE
helps locate it, but a path outside it gets no opinion); a linked worktree of a workspace repo (e.g.
<ws>/.wt-client-cleanup, found through its git common dir) gets that repo's rules - also when the worktree lies
outside the workspace root (an Orca worktree): then it is treated as its main checkout in the workspace. It never
approves, asks or blocks (1.0.3: advisory only - additionalContext "rpg-factory advisory (<level>)") and
never crashes a session (any error = no opinion).

  high  any write while the declared Factory mode is analyze/plan/review/validate
  warn  a write to:
          - an embedded package clone (client Packages/com.cuvara.*): the user's work, not the canonical repo
          - a git submodule's content (client com.gdk.*, unity-build-workflows): changes belong in its own repo
          - a generated path from the registry (proto bindings, Wire.cs copy, golden vectors, *.uxml.g.cs,
            imported samples): change it through its generator
          - secrets (.env, kubeconfig.local; case-insensitive)
  warn  a Read of secrets (.env, kubeconfig.local; case-insensitive)

Not covered (documented limitation): MCP tools that write files (e.g. Unity-MCP asset/scene tools)
have tool-specific inputs; they are not inspected here. The registry gate `unity-asset-edit` is policy.
"""
import fnmatch
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HERE)  # appended: stdlib lookups must not stat /mnt/c first
sys.path.append(os.path.join(HERE, "lib"))  # appended: stdlib lookups must not stat /mnt/c first

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
SECRET = re.compile(r"(^|/)(\.env(\.(?!example$|sample$|template$|dist$)[A-Za-z0-9_-]+)?|kubeconfig\.local)$", re.IGNORECASE)


def target(payload):
    ti = payload.get("tool_input") or {}
    p = ti.get("file_path") or ti.get("notebook_path") or ti.get("path")
    if not p:
        return None
    cwd = payload.get("cwd") or os.getcwd()
    return os.path.normpath(p if os.path.isabs(p) else os.path.join(cwd, p))


def generated_match(rel, pattern):
    if "*" in pattern:
        return fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(os.path.basename(rel), pattern.split("/")[-1])
    return rel == pattern.rstrip("/") or rel.startswith(pattern if pattern.endswith("/") else pattern + "/")


def gitlinks(repo_dir):
    import subprocess
    try:
        out = subprocess.run(["git", "-C", repo_dir, "ls-files", "-s"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [l.split("\t", 1)[1] for l in out.splitlines() if l.startswith("160000 ")]


def within(path, root):
    """path is root or below it (normalised: Windows slashes and case)."""
    a, b = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(root))
    return a == b or a.startswith(b.rstrip("/\\") + os.sep)


_CHECKOUT = {}


def git_checkout(path):
    """(toplevel, main checkout) of the git work tree holding path (nearest existing directory), else (None, None).
    For a linked worktree the main checkout is the directory of its common .git directory."""
    if path not in _CHECKOUT:
        _CHECKOUT[path] = _git_checkout(path)
    return _CHECKOUT[path]


def _git_checkout(path):
    import subprocess
    d = os.path.dirname(path)
    while d and not os.path.isdir(d):
        parent = os.path.dirname(d)
        if parent == d:
            return None, None
        d = parent
    try:
        out = subprocess.run(["git", "-C", d, "rev-parse", "--path-format=absolute", "--show-toplevel", "--git-common-dir"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None, None
    lines = out.stdout.splitlines() if out.returncode == 0 else []
    if len(lines) != 2:
        return None, None
    top, common = lines[0].strip(), lines[1].strip().rstrip("/")
    main = os.path.dirname(common) if os.path.basename(common) == ".git" else top
    return os.path.abspath(top), os.path.abspath(main)


def repo_of(path, ws, registry):
    """(repo key, repo entry, work tree dir) whose rules apply to path: a registry repo directory containing it,
    else a linked worktree (e.g. <ws>/.wt-client-cleanup) whose main checkout is a registry repo."""
    for key, r in registry["repos"].items():
        rdir = os.path.abspath(os.path.join(ws, r["path"]))
        if within(path, rdir):
            return key, r, rdir
    top, main = git_checkout(path)
    if top and main and os.path.normcase(top) != os.path.normcase(main):
        for key, r in registry["repos"].items():
            if os.path.normcase(main) == os.path.normcase(os.path.abspath(os.path.join(ws, r["path"]))):
                return key, r, top
    return None, None, None


def evaluate(payload, registry):
    tool = payload.get("tool_name")
    path = target(payload)
    if not path:
        return []
    import factory_session as session  # noqa: E402  (shares the workspace and mode model)
    g = session.guard()
    ws = g.find_workspace(os.path.dirname(path), registry)
    shown = None
    if not ws or not within(path, ws):  # the env root only helps locate the workspace: never an opinion outside it
        top, main = git_checkout(path)  # unless path is in a linked worktree whose main checkout is in a workspace
        ws = g.find_workspace(main, registry) if top and main and os.path.normcase(top) != os.path.normcase(main) else None
        if not ws or not within(main, ws) or os.path.normcase(main) == os.path.normcase(ws):
            return []
        shown = f"{path} (worktree of {os.path.relpath(main, ws)})"  # the worktree may sit on another drive
    R = []
    if SECRET.search(path.replace("\\", "/")):
        R.append(("ask", f"{shown or os.path.relpath(path, ws)} holds secrets - human gate 'secrets'"))
    if tool not in WRITE_TOOLS:
        return R
    mode = session.current_mode(payload)
    if mode in session.READ_ONLY_MODES or mode == "validate":
        ctx = session.PLUGIN_ROOT.replace("\\", "/").rstrip("/") + "/scripts/factory-context.sh"  # pasted into bash
        R.append(("deny", f"Factory mode is `{mode}`: no file changes. Switch only when the user asked to implement: "
                          f"`bash \"{ctx}\" --mode implement`"))
    key, r, rdir = repo_of(path, ws, registry)
    if key:
        rel = os.path.relpath(path, rdir).replace("\\", "/")
        for c in r.get("embedded_clones", []):
            if rel == c["path"] or rel.startswith(c["path"].rstrip("/") + "/"):
                R.append(("ask", f"{r['path']}/{rel} is inside the embedded clone {c['path']} (of {c['of']}): the user's "
                                 f"work, not the canonical {c['of']} checkout"))
        for sub in gitlinks(rdir):
            if rel.startswith(sub.rstrip("/") + "/"):
                R.append(("ask", f"{r['path']}/{rel} is inside the git submodule {sub}: change it in its own repository"))
        for m in registry["modules"]:
            if m["repo"] != key:
                continue
            for gp in m.get("generated", []):
                if generated_match(rel, gp):
                    R.append(("ask", f"{r['path']}/{rel} is generated ({gp}, module {m['id']}): change it through its generator"))
                    break
    return R


def main():
    if os.environ.get("RPG_FACTORY_GUARD", "").lower() in {"off", "0", "false"}:
        return 0
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    try:
        import factory_session
        registry = factory_session.load_registry()
        if not registry:
            return 0
        reasons = evaluate(payload, registry)
    except Exception:
        return 0  # never break the session
    if not reasons:
        return 0
    level = "high" if any(d == "deny" for d, _ in reasons) else "warn"  # advisory only: never a permissionDecision
    json.dump({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                      "additionalContext": f"rpg-factory advisory ({level}): rpg-factory file guard: "
                                                           + "; ".join(dict.fromkeys(t for _, t in reasons))}},
              sys.stdout)
    return 0


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252: output is UTF-8 everywhere
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
