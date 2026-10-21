"""Where rpg-factory keeps its own files. Every script resolves paths here - never from $TMPDIR directly.

Two roots, both always absolute:

  scratch()     per-session, disposable: the declared execution mode and the skills run (MODE, SKILLS).
                $TMPDIR when it is an absolute, existing, writable directory; otherwise /tmp; otherwise
                the persistent root's `tmp/`. An empty or relative $TMPDIR must never make a hook
                write `rpg-factory/<session>/` into the current directory (a product repo).
  persistent()  survives the session and a crash: check evidence.
                $XDG_STATE_HOME/rpg-factory, else ~/.local/state/rpg-factory. Override (tests):
                $RPG_FACTORY_STATE_DIR (must be absolute).

Under persistent(), per workspace key (workspace_key):
  evidence/<key>/...                 check evidence (lib/evidence.py)

Nothing here is a database: files are small, self-describing JSON. Writes are atomic (write_json).
"""
import hashlib
import json
import os
import threading
import time


def _usable(d):
    return bool(d) and os.path.isabs(d) and os.path.isdir(d) and os.access(d, os.W_OK | os.X_OK)


def persistent():
    override = os.environ.get("RPG_FACTORY_STATE_DIR", "")
    if override and os.path.isabs(override):
        root = override
    else:
        xdg = os.environ.get("XDG_STATE_HOME", "")
        base = xdg if xdg and os.path.isabs(xdg) else os.path.join(os.path.expanduser("~"), ".local", "state")
        root = os.path.join(base, "rpg-factory")
    if not os.path.isabs(root):  # HOME unset/relative: never fall back to the cwd
        root = "/tmp/rpg-factory-state"
    return root


def scratch():
    for cand in (os.environ.get("TMPDIR", ""), "/tmp"):
        if _usable(cand):
            root = os.path.join(cand, "rpg-factory")
            break
    else:
        root = os.path.join(persistent(), "tmp")
        os.makedirs(os.path.dirname(root), exist_ok=True)
    os.makedirs(root, exist_ok=True)
    return root


def workspace_key(ws):
    return hashlib.sha1(os.path.abspath(ws or "-").encode()).hexdigest()[:12]


def write_json(path, obj):
    """Atomic: readers (and concurrent hooks) never see a half-written file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)
        for attempt in range(5):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:  # Windows: another hook process has `path` open for a moment
                if attempt == 4:
                    raise
                time.sleep(0.02 * (attempt + 1))
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
