"""Orca and Claude Code agent dispatch commands, shared by factory-workflow.py and factory-pipeline.py.

Nothing here runs Orca: it builds the exact argv the lead runs (or prints). Placement follows the worktree rule in
references/parallel-work.md: a repo with registry `worktrees: false`, or whose root holds a
`pipeline.no_worktree_markers` file (a Unity project), never gets a new worktree - the worker runs in the existing
main checkout (`--worktree path:<checkout>`); every other repo gets `--worktree new-top-level` from a base ref.
Flags match `orca orchestration worker-start --help` (Orca 1.4): (--task <id> | --spec <text>) and
(--agent <id> | --terminal <handle>); creation flags (--repo, --base-branch, --name) only with new worktrees.
Printed commands use POSIX quoting (Claude Code's Bash tool, Git Bash); PowerShell needs its own quoting.
"""
import os
import shlex
import subprocess

import fstate


def quote(argv):
    return " ".join(shlex.quote(str(a)) for a in argv)


def repo_checkout(registry, key):
    """Absolute path of a registry repo's canonical checkout, or None for an unknown key."""
    repo = registry.get("repos", {}).get(key)
    if not repo:
        return None
    return os.path.normpath(os.path.join(fstate.workspace(registry), repo["path"]))


def allows_worktree(registry, key=None, path=None):
    """(allowed, reason). The registry flag wins; the marker file catches unregistered Unity projects."""
    repo = registry.get("repos", {}).get(key) if key else None
    if repo is not None and repo.get("worktrees") is False:
        return False, repo.get("worktrees_reason") or f"repos.{key}.worktrees is false"
    path = path or (repo_checkout(registry, key) if key else None)
    for marker in registry.get("pipeline", {}).get("no_worktree_markers", []):
        if path and os.path.isfile(os.path.join(path, marker)):
            return False, f"{marker} present: Unity project (each worktree needs its own Library/ import)"
    return True, None


def placement(registry, key=None, path=None, base=None, name=None):
    """worker-start placement flags for one repo."""
    allowed, reason = allows_worktree(registry, key, path)
    checkout = path or (repo_checkout(registry, key) if key else None)
    if not allowed:
        return {"worktree": f"path:{checkout}" if checkout else "current", "new": False, "reason": reason}
    flags = {"worktree": "new-top-level", "new": True, "reason": None}
    if checkout:
        flags["repo"] = f"path:{checkout}"
    if base:
        flags["base"] = base
    if name:
        flags["name"] = name
    return flags


def worker_start(spec, agent, place, title=None):
    """argv for `orca orchestration worker-start --spec ...` (the spec creates its own Orca task)."""
    argv = ["orca", "orchestration", "worker-start", "--spec", spec, "--agent", agent, "--worktree", place["worktree"]]
    if place.get("new"):
        for flag, key in (("--repo", "repo"), ("--base-branch", "base"), ("--name", "name")):
            if place.get(key):
                argv += [flag, place[key]]
    if title:
        argv += ["--task-title", title]
    return argv + ["--json"]


def _toplevel(path):
    try:
        r = subprocess.run(["git", "-C", path, "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=30,
                           encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    return os.path.normcase(os.path.realpath(r.stdout.strip())) if r.returncode == 0 and r.stdout.strip() else None


def agent_task(registry, agent, prompt, place, description, cwd=None):
    """Claude Code Agent tool call (fallback when Orca is unavailable). `isolation: worktree` copies the lead's own
    repository at the lead's HEAD, so it is used only when the target is that repository and no other base is
    needed; otherwise the prompt names the repo, base and branch and the worker creates its worktree with git."""
    runner = registry.get("pipeline", {}).get("agents", {}).get(agent, {}).get("agent_runner", "general-purpose")
    target = place.get("repo", "")[5:] if str(place.get("repo", "")).startswith("path:") else None
    here = _toplevel(cwd or os.getcwd())
    call = {"subagent_type": runner, "description": description, "prompt": prompt}
    if place.get("new"):
        same = target is None or (here is not None and _toplevel(target) == here)
        if same and not place.get("base"):
            call["isolation"] = "worktree"
        else:
            name = place.get("name") or "pipeline-task"
            call["prompt"] = (f"Placement: repo {target or 'the current repository'}, base {place.get('base') or 'HEAD'}, "
                              f"branch {name}. Create your own worktree first: `git -C <repo> worktree add "
                              f"<repo>-wt/{name.replace('/', '-')} -b {name} {place.get('base') or 'HEAD'}` and work only "
                              "there (never a second clone).\n" + prompt)
    elif place.get("worktree", "").startswith("path:"):
        call["prompt"] = f"Placement: work in the existing checkout {place['worktree'][5:]} (no new worktree).\n" + prompt
    return call
