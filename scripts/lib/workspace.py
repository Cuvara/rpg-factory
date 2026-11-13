"""Where the workspace and a checkout are: the one copy of the path helpers the hooks and the routing engine share.

  find_workspace(start, registry)  the workspace holding `start` (nearest ancestor with every root marker), else the env root
  main_checkout(top)               the main checkout of a work tree (parent of its common .git directory)
  linked_worktree(d)               (toplevel, main checkout) of a linked worktree, read from its `.git` file (no git call)
  native_path(p) / native_abs(p)   a path written in another shell's drive form as this platform resolves it
  default_workspace(env, nt)      the configured workspace or the platform's default path

Stdlib only and cheap to import: the file guard loads it on every Read.
"""
import os
import re
import subprocess

WSL_WORKSPACE_DEFAULT = "/mnt/c/Workspaces/UnityIndie"


def git_out(cwd, *args, timeout=5):
    """git's stripped stdout, or "" when git fails or is missing."""
    try:
        r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def native_path(p, nt=None):
    """A git-bash path as the OS resolves it. Python on Windows reads `/c/ws` as `C:\\c\\ws` (rooted on the
    current drive) and `/mnt/c/ws` as `C:\\mnt\\c\\ws`; git-bash and WSL mean `C:/ws`. Elsewhere unchanged."""
    if not p or not (os.name == "nt" if nt is None else nt):
        return p
    m = re.match(r"^/mnt/([A-Za-z])(/|$)", p) or re.match(r"^/([A-Za-z])(/|$)", p)
    return f"{m.group(1).upper()}:/{p[m.end():]}" if m else p


def default_workspace(env=None, nt=None):
    """Return the configured workspace, or the default in the native path form."""
    env = os.environ if env is None else env
    return env.get("RPG_FACTORY_WORKSPACE") or native_path(WSL_WORKSPACE_DEFAULT, nt)


def native_abs(p):
    """Map a forward-slash path written in another shell's drive form to this platform's form: on Windows
    the git-bash `/c/...` and WSL `/mnt/c/...` forms become `C:/...`; elsewhere `C:/...` becomes
    `/mnt/c/...`. Anything else is returned unchanged."""
    if os.name == "nt":
        m = re.match(r"^/(?:mnt/)?([A-Za-z])(/.*)?$", p)
        if m:
            return f"{m.group(1).upper()}:{m.group(2) or '/'}"
        # git-bash rewrites an argument /mnt/c/x into <Git install>/mnt/c/x (MSYS path conversion)
        m = re.match(r"^[A-Za-z]:/.*?/mnt/([A-Za-z])(/.*)?$", p)
        if m and not os.path.exists(p):
            return f"{m.group(1).upper()}:{m.group(2) or '/'}"
    else:
        m = re.match(r"^([A-Za-z]):(/.*)?$", p)
        if m:
            return f"/mnt/{m.group(1).lower()}{m.group(2) or '/'}"
    return p


def _markers_ok(d, markers):
    return bool(d) and all(os.path.exists(os.path.join(d, m)) for m in markers)


def find_workspace(start, registry, env_first=False, use_default=False):
    """The workspace containing `start` (nearest ancestor with every root marker), else the env root.
    The cwd wins: an env root exported for one workspace must never hide another workspace the command
    actually runs in (the guard would see "outside the workspace" and let a tag through).
    The routing engine (context.py) asks the other way round: env_first=True tries the env root before the
    ancestors of `start`, use_default=True falls back to the registry root_default."""
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
    if use_default and _markers_ok(ws.get("root_default"), markers):
        return ws["root_default"]
    return None


def main_checkout(top, timeout=5):
    """The main checkout for a worktree (or the repo itself): parent of the common .git dir."""
    common = git_out(top, "rev-parse", "--path-format=absolute", "--git-common-dir", timeout=timeout).rstrip("/")
    if common and os.path.basename(common) == ".git":
        return os.path.dirname(common)
    return top


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
                with open(dot, encoding="utf-8", errors="replace") as f:
                    line = f.readline().strip()
                if not line.startswith("gitdir:"):
                    return None
                gd = os.path.normpath(os.path.join(d, line[7:].strip()))
                parts = gd.replace("\\", "/").rsplit("/.git/worktrees/", 1)
                return (os.path.abspath(d), os.path.abspath(parts[0])) if len(parts) == 2 else None
            parent = os.path.dirname(d)
            d = "" if parent == d else parent
    except (OSError, ValueError):
        return None
    return None
