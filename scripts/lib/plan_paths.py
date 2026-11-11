"""Read-only plan repository path resolution.

Used by factory-pipeline.py repo_info. Bare relative paths are plan-relative;
paths prefixed with the registry workspace environment variable are workspace-relative.
The caller surfaces path_reason when workspace discovery fails.

On Windows Python an absolute path or a workspace root written in the Git Bash (`/c/ws`) or WSL (`/mnt/c/ws`)
spelling is converted with workspace.native_abs first, which also undoes the rewrite Git Bash applies to a WSL
argument or environment value before Windows Python sees it (`/mnt/c/ws` arrives as `C:/Program Files/Git/mnt/c/ws`);
elsewhere nothing changes (native_abs would turn `C:/...` into `/mnt/c/...` on POSIX, so it is gated on Windows).
"""
import os

from workspace import find_workspace, native_abs  # scripts/lib is on sys.path (factory-pipeline.py)


def _is_nt():
    return os.name == "nt"


def _native(p):
    """p in this platform's spelling: workspace.native_abs on Windows, p itself elsewhere."""
    return native_abs(p) if p and _is_nt() else p


def _find_workspace_native(plan_dir, registry):
    """find_workspace(env_first, use_default) with the env root in this platform's spelling.

    find_workspace reads the env root itself and tests its markers unconverted, so a converted root is shown to it
    through the environment for the duration of the call; its precedence (env root with every marker, then the
    ancestors of plan_dir, then the registry default) is kept."""
    variable = registry.get("workspace", {}).get("root_env")
    raw = os.environ.get(variable, "") if variable else ""
    converted = _native(raw)
    if not variable or converted == raw:
        return find_workspace(plan_dir, registry, env_first=True, use_default=True)
    os.environ[variable] = converted
    try:
        return find_workspace(plan_dir, registry, env_first=True, use_default=True)
    finally:
        os.environ[variable] = raw


def resolve_repo_path(path, plan_file, registry):
    """Return (normalized absolute path, None), or (None, discovery reason)."""
    if not path:
        return None, None
    plan_dir = os.path.dirname(os.path.abspath(plan_file))
    variable = registry.get("workspace", {}).get("root_env")
    for prefix in (("${" + variable + "}", "$" + variable) if variable else ()):
        if path == prefix or path.startswith(prefix + "/") or path.startswith(prefix + "\\"):
            root = _find_workspace_native(plan_dir, registry)
            if not root:
                return None, f"Workspace not found for {variable}"
            suffix = path[len(prefix):].lstrip("/\\").replace("\\", os.sep)
            return os.path.abspath(os.path.join(root, suffix)), None
    return os.path.abspath(os.path.join(plan_dir, _native(path))), None
