"""Read-only plan repository path resolution.

Wire into factory-pipeline.py repo_info by replacing its isabs/join lines with:
    path, path_reason = plan_paths.resolve_repo_path(path, plan["_path"], reg)
The caller must surface path_reason when workspace discovery fails.
"""
import os

from workspace import find_workspace  # scripts/lib is on sys.path (factory-pipeline.py)


def resolve_repo_path(path, plan_file, registry):
    """Return (normalized absolute path, None), or (None, discovery reason)."""
    if not path:
        return None, None
    plan_dir = os.path.dirname(os.path.abspath(plan_file))
    variable = registry["workspace"]["root_env"]
    for prefix in ("${" + variable + "}", "$" + variable):
        if path == prefix or path.startswith(prefix + "/") or path.startswith(prefix + "\\"):
            root = find_workspace(plan_dir, registry, env_first=True, use_default=True)
            if not root:
                return None, f"Workspace not found for {variable}"
            suffix = path[len(prefix):].lstrip("/\\").replace("\\", os.sep)
            return os.path.abspath(os.path.join(root, suffix)), None
    return os.path.abspath(os.path.join(plan_dir, path)), None
