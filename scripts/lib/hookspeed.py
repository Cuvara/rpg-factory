"""What a hook call costs before it does any work: Python start-up and compiling the plugin modules.

  enable_bytecache()  The hooks run `python3 -B` (no __pycache__ in the plugin tree, which run-all keeps clean), so
                      every call used to compile the guard modules from source. This keeps the plugin tree clean but
                      caches the bytecode under the persistent state dir: sys.pycache_prefix =
                      <fstate.persistent()>/pycache. Python checks each cached file against its source (mtime and
                      size) and recompiles when the source changed; a cache write that fails is skipped by Python
                      itself. Call it in a hook entry point before it imports plugin modules. Any error: no cache,
                      the behaviour before. RPG_FACTORY_PYCACHE=off disables it. The script Python runs is never
                      cached, so hook entry points stay small (scripts/git-guard.py imports lib/gitguard.py).
  python_alias()      `python3` on PATH when it is the Windows Store alias (...\\WindowsApps\\python3.exe): the alias
                      adds about 70 ms to every hook call. alias_advice() is the text for doctor and SessionStart.
                      Detection only: nothing here changes PATH or the system.
"""
import os
import sys


def enable_bytecache():
    try:
        if os.environ.get("RPG_FACTORY_PYCACHE", "").lower() in {"off", "0", "false"}:
            return None
        import fstate
        prefix = os.path.join(fstate.persistent(), "pycache")
        if not os.path.isabs(prefix):
            return None
        sys.pycache_prefix = prefix
        sys.dont_write_bytecode = False
        return prefix
    except Exception:
        return None


def is_store_alias(path):
    return bool(path) and "\\windowsapps\\" in str(path).replace("/", "\\").lower()


def python_alias():
    """The `python3` the hooks start, when it is the Windows Store alias; else None. RPG_FACTORY_PYTHON3 (tests)
    names the path to judge instead of looking up PATH ("" = no python3 on PATH)."""
    p = os.environ.get("RPG_FACTORY_PYTHON3")
    if p is None:
        import shutil
        p = shutil.which("python3")
    return p if is_store_alias(p) else None


def alias_advice():
    """One sentence for doctor and the SessionStart advisory, or None when `python3` is not the alias."""
    p = python_alias()
    if not p:
        return None
    real = sys.executable if sys.executable and not is_store_alias(sys.executable) else None
    where = f" ({os.path.dirname(real)})" if real else ""
    return (f"`python3` on PATH is the Windows Store alias {p}: every hook call starts about 70 ms slower. Put the "
            f"real Python directory{where} before the WindowsApps directory on PATH, or turn off the python3 app "
            f"execution alias in Windows settings (nothing was changed)")
