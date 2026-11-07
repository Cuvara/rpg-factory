"""Orca and Claude Code agent dispatch commands, shared by factory-workflow.py and factory-pipeline.py.

Nothing here runs Orca: it builds the exact argv the lead runs (or prints). Placement follows the worktree rule in
references/parallel-work.md: a repo with registry `worktrees: false`, or whose root holds a
`pipeline.no_worktree_markers` file (a Unity project), never gets a new worktree - the worker runs in the existing
main checkout (`--worktree path:<checkout>`); every other repo gets `--worktree new-top-level` from a base ref, or an
Orca child of the caller's worktree (`--worktree new-child`, child_placement) when the owner picks isolation.
Flags match `orca orchestration worker-start --help` (Orca 1.4): (--task <id> | --spec <text>) and
(--agent <id> | --terminal <handle>); creation flags (--repo, --base-branch, --name) only with new worktrees.
Printed commands use POSIX quoting (Claude Code's Bash tool, Git Bash); PowerShell needs its own quoting.
in_orca_session() and orca_reachable() tell whether the caller runs inside a reachable Orca (Orca first,
references/parallel-work.md section 5); orca_reachable() is the only call here that runs `orca` (read-only status).
"""
import json
import os
import shlex
import shutil
import subprocess

import fstate


# set by Orca in every terminal it starts (the first one found names the session in messages)
ORCA_SESSION_ENV = ("ORCA_WORKTREE_ID", "ORCA_AGENT_HOOK_ENDPOINT")


def in_orca_session(env=None):
    """The first ORCA_SESSION_ENV name set non-empty in env (default os.environ), or None."""
    env = os.environ if env is None else env
    return next((name for name in ORCA_SESSION_ENV if env.get(name)), None)


def orca_reachable():
    """True only when `orca status --json` reports result.runtime.reachable true; any error is False (never raises)."""
    exe = shutil.which("orca")
    if not exe:
        return False
    try:
        r = subprocess.run([exe, "status", "--json"], capture_output=True, text=True, timeout=30, encoding="utf-8",
                           errors="replace", stdin=subprocess.DEVNULL)
        data = json.loads(r.stdout or "")
        return data.get("result", {}).get("runtime", {}).get("reachable") is True
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        return False


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


CHILD_RULE = ("never create or remove a child worktree while a full tests/run-all.sh runs (shared .git/config); the owner "
              "merges the child branch into its parent branch and removes the child at once")


def child_placement(name, base, parent):
    """worker-start placement for an Orca child of the caller's worktree `parent` (run the command from there)."""
    return {"worktree": "new-child", "new": True, "name": name, "base": base, "child_of": parent,
            "reason": f"Orca child of {parent}"}


def worker_start(spec, agent, place, title=None):
    """argv for `orca orchestration worker-start --spec ...` (the spec creates its own Orca task)."""
    argv = ["orca", "orchestration", "worker-start", "--spec", spec, "--agent", agent, "--worktree", place["worktree"]]
    if place.get("new"):
        order = ((("--name", "name"), ("--base-branch", "base")) if place["worktree"] == "new-child" else
                 (("--repo", "repo"), ("--base-branch", "base"), ("--name", "name")))
        for flag, key in order:
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
    needed; otherwise the prompt names the repo, base and branch and the worker creates its worktree with git. An Orca
    child placement (new-child) always uses `isolation: worktree`: the session itself never creates a worktree."""
    runner = registry.get("pipeline", {}).get("agents", {}).get(agent, {}).get("agent_runner", "general-purpose")
    target = place.get("repo", "")[5:] if str(place.get("repo", "")).startswith("path:") else None
    here = _toplevel(cwd or os.getcwd())
    call = {"subagent_type": runner, "description": description, "prompt": prompt}
    if place.get("worktree") == "new-child":
        # only the dispatching tool creates worktrees: the Agent tool's own isolation copy of the caller's checkout
        # stands in for the Orca child; the session never runs `git worktree add`
        call["isolation"] = "worktree"
        base = place.get("base") or "HEAD"
        call["prompt"] = (f"Placement: an isolated worktree of {place.get('child_of') or 'the current checkout'} that the "
                          f"Agent tool created at the caller's HEAD (it stands in for the Orca child {place.get('name')}); "
                          "never create or remove a worktree yourself. First check that `git rev-parse HEAD` equals "
                          f"`git rev-parse {base}`; otherwise report NOT_INDEPENDENT and stop.\n" + prompt)
    elif place.get("new"):
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
