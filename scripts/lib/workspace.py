"""Where the workspace and a checkout are: the one copy of the path helpers the hooks and the routing engine share.

  find_workspace(start, registry)  the workspace holding `start`, else the env root or native registry default
  main_checkout(top)               the main checkout of a work tree (parent of its common .git directory)
  linked_worktree(d)               (toplevel, main checkout) of a linked worktree, read from its `.git` file (no git call)
  plugin_checkout(d)              the rpg-factory checkout holding d, else None (no git call)
  native_path(p) / native_abs(p)   a path written in another shell's drive form as this platform resolves it
                                   (native_abs also undoes git-bash's MSYS rewrite, only under a Git install root)
  git_out(cwd, *args)              git's stripped stdout, "" on any failure
  git_result(cwd, *args)           (stdout, error): error is None, "timeout" or "failed"
  default_workspace(env, nt, registry)  the configured workspace or the registry default in native form
  registry_workspace_default(registry)  the registry's workspace default as written (raw, None when absent)

Stdlib only and cheap to import: the file guard loads it on every Read.
"""
import json
import os
import re
import subprocess

PLUGIN_NAME = "rpg-factory"
WSL_WORKSPACE_DEFAULT = "/mnt/c/Workspaces/UnityIndie"


def git_result(cwd, *args, timeout=5):
    """(stdout, error) of `git -C cwd args`: the raw stdout and None on exit 0; (None, "timeout") when git ran
    past `timeout` seconds; (None, "failed") on a nonzero exit or when git is missing or cannot be run."""
    try:
        r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except (OSError, subprocess.SubprocessError):
        return None, "failed"
    return (r.stdout, None) if r.returncode == 0 else (None, "failed")


def git_out(cwd, *args, timeout=5):
    """git's stripped stdout, or "" when git fails, times out or is missing (git_result tells them apart)."""
    out, _ = git_result(cwd, *args, timeout=timeout)
    return out.strip() if out is not None else ""


def native_path(p, nt=None):
    """A git-bash path as the OS resolves it. Python on Windows reads `/c/ws` as `C:\\c\\ws` (rooted on the
    current drive) and `/mnt/c/ws` as `C:\\mnt\\c\\ws`; git-bash and WSL mean `C:/ws`. Elsewhere unchanged."""
    if not p or not (os.name == "nt" if nt is None else nt):
        return p
    m = re.match(r"^/mnt/([A-Za-z])(/|$)", p) or re.match(r"^/([A-Za-z])(/|$)", p)
    return f"{m.group(1).upper()}:/{p[m.end():]}" if m else p


def registry_workspace_default(registry):
    """The registry's workspace default exactly as written (no platform conversion), or None when absent."""
    ws = registry.get("workspace") if registry else None
    return ws.get("root_default") if isinstance(ws, dict) else None


def default_workspace(env=None, nt=None, registry=None):
    """Return the configured workspace, or the registry default in native form."""
    env = os.environ if env is None else env
    ws = registry["workspace"] if registry is not None else {}
    return env.get(ws.get("root_env") or "RPG_FACTORY_WORKSPACE") or native_path(
        ws.get("root_default") or WSL_WORKSPACE_DEFAULT, nt
    )


def _is_git_install_root(prefix):
    """True when prefix (forward slashes) is a Git for Windows install root: it holds usr/bin/bash.exe or
    git-bash.exe. A directory merely named `Git` does not qualify."""
    return any(os.path.exists(prefix + "/" + marker) for marker in ("usr/bin/bash.exe", "git-bash.exe"))


def native_abs(p):
    """Map a forward-slash path written in another shell's drive form to this platform's form: on Windows
    the git-bash `/c/...` and WSL `/mnt/c/...` forms become `C:/...`; elsewhere `C:/...` becomes
    `/mnt/c/...`. Anything else is returned unchanged.

    On Windows `X:/<prefix>/mnt/<l>/rest` is also read as git-bash's MSYS rewrite of the WSL argument
    `/mnt/<l>/rest` (`C:/Program Files/Git/mnt/c/ws` is `/mnt/c/ws`), which it is only when it does not exist and
    <prefix> is a Git for Windows install root; a native path that merely contains a `/mnt/<l>/` segment
    (`C:/proj/mnt/d/new`) is returned unchanged."""
    if os.name == "nt":
        m = re.match(r"^/(?:mnt/)?([A-Za-z])(/.*)?$", p)
        if m:
            return f"{m.group(1).upper()}:{m.group(2) or '/'}"
        m = re.match(r"^([A-Za-z]:/.*?)/mnt/([A-Za-z])(/.*)?$", p)
        if m and not os.path.exists(p) and _is_git_install_root(m.group(1)):
            return f"{m.group(2).upper()}:{m.group(3) or '/'}"
    else:
        m = re.match(r"^([A-Za-z]):(/.*)?$", p)
        if m:
            return f"/mnt/{m.group(1).lower()}{m.group(2) or '/'}"
    return p


def _markers_ok(d, markers):
    return bool(d) and all(os.path.exists(os.path.join(d, m)) for m in markers)


def find_workspace(start, registry, env_first=False, use_default=False, nt=None):
    """The workspace containing `start` (nearest ancestor with every root marker), else the env root.
    The cwd wins: an env root exported for one workspace must never hide another workspace the command
    actually runs in (the guard would see "outside the workspace" and let a tag through).
    The routing engine (context.py) asks the other way round: env_first=True tries the env root before the
    ancestors of `start`, use_default=True falls back to the registry root_default in native form."""
    ws = registry["workspace"]
    markers = ws["root_markers"]
    env_root = os.environ.get(ws.get("root_env", ""), "")
    if env_first and _markers_ok(env_root, markers):
        return os.path.abspath(env_root)
    d = os.path.abspath(start)
    while True:
        if _markers_ok(d, markers):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    if not env_first and _markers_ok(env_root, markers):
        return os.path.abspath(env_root)
    if use_default:
        rd = native_path(ws.get("root_default"), nt)
        if _markers_ok(rd, markers):
            return rd
    return None


def main_checkout(top, timeout=5):
    """The main checkout for a worktree (or the repo itself): parent of the common .git dir."""
    common = git_out(top, "rev-parse", "--path-format=absolute", "--git-common-dir", timeout=timeout).rstrip("/")
    if common and os.path.basename(common) == ".git":
        return os.path.dirname(common)
    return top


def _linked_worktree_at(d):
    """Parse a linked worktree's .git file at d, returning its top and main checkout."""
    with open(os.path.join(d, ".git"), encoding="utf-8", errors="replace") as f:
        line = f.readline().strip()
    if not line.startswith("gitdir:"):
        return None
    gd = os.path.normpath(os.path.join(d, line[7:].strip()))
    parts = gd.replace("\\", "/").rsplit("/.git/worktrees/", 1)
    return (os.path.abspath(d), os.path.abspath(parts[0])) if len(parts) == 2 else None


def linked_worktree(d):
    """(toplevel, main checkout) when directory d is inside a linked worktree, read from its `.git` file
    (`gitdir: <main>/.git/worktrees/<name>`) without running git; else None. A `.git` directory (a main checkout),
    a submodule's `.git` file (`.git/modules/`) or no `.git` at all is None. Any error is None."""
    try:
        while d and not os.path.isdir(d):
            d = os.path.dirname(d) if os.path.dirname(d) != d else ""
        while d:
            dot = os.path.join(d, ".git")
            if os.path.isdir(dot):
                return None
            if os.path.isfile(dot):
                return _linked_worktree_at(d)
            parent = os.path.dirname(d)
            d = "" if parent == d else parent
    except (OSError, ValueError):
        return None
    return None


def plugin_checkout(d):
    """The rpg-factory checkout containing d, including linked worktrees and installed copies, else None."""
    try:
        d = os.path.abspath(d)
        for _ in range(32):
            if os.path.isdir(d):
                break
            parent = os.path.dirname(d)
            if parent == d:
                return None
            d = parent
        else:
            return None

        def has_manifest(top):
            manifest = os.path.join(top, ".claude-plugin", "plugin.json")
            if not os.path.isfile(manifest):
                return False
            with open(manifest, encoding="utf-8") as f:
                data = json.load(f)
            return isinstance(data, dict) and data.get("name") == PLUGIN_NAME

        for _ in range(32):
            if has_manifest(d):
                return d
            dot = os.path.join(d, ".git")
            if os.path.lexists(dot):
                linked = _linked_worktree_at(d) if os.path.isfile(dot) else None
                return d if linked and has_manifest(linked[1]) else None
            parent = os.path.dirname(d)
            if parent == d:
                return None
            d = parent
    except (OSError, ValueError):
        return None
    return None
