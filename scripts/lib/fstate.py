"""Where rpg-factory keeps its own files. Every script resolves paths here - never from $TMPDIR directly.

Two roots, both always absolute:

  scratch()     per-session, disposable: tripwire snapshots and session baselines.
                $TMPDIR when it is an absolute, existing, writable directory; otherwise /tmp; otherwise
                the persistent root's `tmp/`. An empty or relative $TMPDIR used to make the tripwire
                write `rpg-factory/<session>/` into the current directory (a product repo).
  persistent()  survives the session and a crash: the workspace tripwire events, the stash audit, the
                cross-session git activity log and check evidence.
                $XDG_STATE_HOME/rpg-factory, else ~/.local/state/rpg-factory. Override (tests):
                $RPG_FACTORY_STATE_DIR (must be absolute).

Under persistent(), per workspace key (workspace_key):
  latch/<key>/<event-id>.json        open tripwire events (one file per incident, never overwritten)
  latch/<key>/acked/<event-id>.json  acknowledged events (archived, pruned after 30 days)
  latch/<key>.json                   legacy (<= 0.5.0) single-file latch; still read, migrated on --ack
  audit/<key>.jsonl                  visible `git stash` operations (the approved path)
  activity/<key>/<call>.json         completed commands that visibly ran git (cross-session attribution)

Nothing here is a database: files are small, self-describing JSON. Writes are atomic (write_json).
"""
import hashlib
import json
import os
import re
import threading


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


def latch_root():
    return os.path.join(persistent(), "latch")


def latch_dir(ws=None, key=None):
    return os.path.join(latch_root(), key or workspace_key(ws))


def legacy_latch_file(ws=None, key=None):
    return os.path.join(latch_root(), (key or workspace_key(ws)) + ".json")


def audit_file(ws):
    return os.path.join(persistent(), "audit", workspace_key(ws) + ".jsonl")


def activity_dir(ws):
    return os.path.join(persistent(), "activity", workspace_key(ws))


def has_open_events(ws):
    """Cheap check for the guards: any open event file (or a legacy latch) for this workspace."""
    if os.path.exists(legacy_latch_file(ws)):
        return True
    try:
        with os.scandir(latch_dir(ws)) as it:
            return any(e.name.endswith(".json") and e.is_file() for e in it)
    except OSError:
        return False


def write_json(path, obj):
    """Atomic: readers (and concurrent hooks) never see a half-written file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)
    os.replace(tmp, path)


def ack_command(plugin_root):
    """The one acknowledgement command every message prints: forward slashes and double quotes, so it
    survives Git Bash, WSL bash and PowerShell (a mixed `C:/x\\scripts\\tripwire.py` loses its
    backslashes in bash and the user's ack silently fails)."""
    p = plugin_root.replace("\\", "/").rstrip("/") + "/scripts/tripwire.py"
    return 'python3 "' + re.sub(r'(["$`])', r"\\\1", p) + '" --ack'
