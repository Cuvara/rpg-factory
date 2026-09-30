#!/usr/bin/env python3
"""rpg-factory file guard - PreToolUse hook for Claude's file tools (Write, Edit, MultiEdit, NotebookEdit, Read).

The shell guard (git-guard.py) and the tripwire only see Bash/PowerShell. File tools write directly, so
this hook applies the same workspace rules to the target path. Inside the workspace only; it never
approves anything and never crashes a session (any error = no opinion).

  deny  any write while the tripwire is latched (an unresolved STOP, this or an earlier session), or while the
        declared Factory mode is analyze/plan/review/validate
  ask   a write to:
          - an embedded package clone (client Packages/com.cuvara.*): the user's work, not the canonical repo
          - a git submodule's content (client com.gdk.*, unity-build-workflows): changes belong in its own repo
          - a generated path from the registry (proto bindings, Wire.cs copy, golden vectors, *.uxml.g.cs,
            imported samples): change it through its generator
          - a file that was already modified/untracked when the session started (the user's baseline)
          - secrets (.env, kubeconfig.local)
  ask   a Read of secrets (.env, kubeconfig.local)

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
SECRET = re.compile(r"(^|/)(\.env(\.(?!example$|sample$|template$|dist$)[A-Za-z0-9_-]+)?|kubeconfig\.local)$")


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
        out = subprocess.run(["git", "-C", repo_dir, "ls-files", "-s"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [l.split("\t", 1)[1] for l in out.splitlines() if l.startswith("160000 ")]


def evaluate(payload, registry):
    tool = payload.get("tool_name")
    path = target(payload)
    if not path:
        return []
    import tripwire  # noqa: E402  (shares the workspace/latch model)
    g = tripwire.guard()
    ws = g.find_workspace(os.path.dirname(path), registry)
    if not ws:
        return []
    R = []
    if SECRET.search(path.replace("\\", "/")):
        R.append(("ask", f"{os.path.relpath(path, ws)} holds secrets - human gate 'secrets'"))
    if tool not in WRITE_TOOLS:
        return R
    latch = tripwire.latched(payload)
    if latch:
        R.append(("deny", f"tripwire latched - {latch}. Stop and report it to the user"))
    mode = tripwire.current_mode(payload)
    if mode in tripwire.READ_ONLY_MODES or mode == "validate":
        R.append(("deny", f"Factory mode is `{mode}`: no file changes. Switch only when the user asked to implement: "
                          f"`bash {os.path.join(tripwire.PLUGIN_ROOT, 'scripts', 'factory-context.sh')} --mode implement`"))
    for key, r in registry["repos"].items():
        rdir = os.path.abspath(os.path.join(ws, r["path"]))
        if not (path == rdir or path.startswith(rdir + os.sep)):
            continue
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
        base = {}
        try:
            base = json.load(open(os.path.join(tripwire.state_dir(payload), "baseline.json"), encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
        for top, entries in base.items():
            if path.startswith(os.path.abspath(top) + os.sep):
                trel = os.path.relpath(path, top).replace("\\", "/")
                e = entries.get(trel, "absent")
                in_new_dir = any(v == "dir" and trel.startswith(k.rstrip("/") + "/") for k, v in entries.items())
                if e is None or in_new_dir or (isinstance(e, list) and len(e) == 2 and all(isinstance(x, int) for x in e)):
                    R.append(("ask", f"{r['path']}/{rel} already had changes when the session started (the user's baseline)"))
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
        import tripwire
        registry = tripwire.load_registry()
        if not registry:
            return 0
        reasons = evaluate(payload, registry)
    except Exception:
        return 0  # never break the session
    if not reasons:
        return 0
    decision = "deny" if any(d == "deny" for d, _ in reasons) else "ask"
    json.dump({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                      "permissionDecisionReason": "rpg-factory file guard: " + "; ".join(dict.fromkeys(t for _, t in reasons))}},
              sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
