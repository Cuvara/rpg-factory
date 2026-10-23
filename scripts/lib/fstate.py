"""Where rpg-factory keeps its own files. Every script resolves paths here - never from $TMPDIR directly.

Two roots, both always absolute:

  scratch()     per-session, disposable: the declared execution mode and the skills run (MODE, SKILLS.d/).
                $TMPDIR when it is an absolute, existing, writable directory; otherwise /tmp; otherwise
                the persistent root's `tmp/`; otherwise the platform temp dir. A candidate whose
                `rpg-factory/` cannot be created is skipped. An empty or relative $TMPDIR must never make
                a hook write `rpg-factory/<session>/` into the current directory (a product repo).
  persistent()  survives the session and a crash: check evidence.
                $XDG_STATE_HOME/rpg-factory, else ~/.local/state/rpg-factory, else <platform temp>/rpg-factory-state.
                Override (tests): $RPG_FACTORY_STATE_DIR (must be absolute).

Under scratch(), per session: session_key(session_id) - a name that is always one safe path component.
Under persistent(), per workspace key (workspace_key):
  evidence/<key>/...                 check evidence (lib/evidence.py)

Nothing here is a database: files are small, self-describing JSON. Writes are atomic (write_json, write_text).
"""
import hashlib
import json
import os
import re
import tempfile
import threading
import time
import uuid


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
    if not os.path.isabs(root):  # HOME unset/relative: never fall back to the cwd (tempfile's dir is absolute)
        root = os.path.join(tempfile.gettempdir(), "rpg-factory-state")
    return root


def scratch():
    cands = [os.path.join(c, "rpg-factory") for c in (os.environ.get("TMPDIR", ""), "/tmp") if _usable(c)]
    cands += [os.path.join(persistent(), "tmp"), os.path.join(tempfile.gettempdir(), "rpg-factory")]
    err = None
    for root in cands:
        if not os.path.isabs(root):
            continue
        try:
            os.makedirs(root, exist_ok=True)  # FileExistsError when `root` is a file, PermissionError on ACLs
            if os.path.isdir(root):
                return root
        except OSError as e:
            err = e
    raise err or OSError("rpg-factory: no usable scratch directory")


_SAFE_SID = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}")


def session_key(sid):
    """The session id as one safe path component. A plain id (what Claude Code sends: a UUID) is used as is;
    anything else - empty-ish, ".", "..", longer than 100 characters, or holding characters outside
    [A-Za-z0-9_.-] (which a substitution would collide: "a/b" and "a:b") - becomes "s-<sha1>"."""
    raw = "default" if sid is None or str(sid) == "" else str(sid)
    if _SAFE_SID.fullmatch(raw):
        return raw
    return "s-" + hashlib.sha1(raw.encode("utf-8", "surrogatepass")).hexdigest()[:24]


def workspace_key(ws):
    """Stable per workspace: the real path, case-folded where the file system is (Windows), so `C:/W` and
    `c:\\w` share evidence."""
    return hashlib.sha1(os.path.normcase(os.path.realpath(ws or "-")).encode()).hexdigest()[:12]


def workspace(registry):
    """The workspace root: $<root_env> when it names a directory, else the registry default. One rule for
    run-checks.py and factory-status.py, so both read the same evidence."""
    env = os.environ.get(registry["workspace"]["root_env"])
    return env if env and os.path.isdir(env) else registry["workspace"]["root_default"]


def unique_suffix():
    return f"{os.getpid()}-{uuid.uuid4().hex[:8]}"


_WINDOWS = os.name == "nt"
LOCK_BUDGET_S = 2.0  # Windows: how long a file held open by another process is retried


def _lock_wait(attempt, start, tries, step):
    """After a PermissionError: sleep and return True to retry, False when the budget is spent. On Windows a
    reader holding `path` open makes os.replace fail and a replace in flight makes open fail; under machine
    load that lasts longer than a fixed attempt count, so the budget is time-based (LOCK_BUDGET_S, backoff
    capped at 50 ms). Elsewhere a PermissionError is a real denial: `tries` attempts, linear `step` backoff."""
    if _WINDOWS:
        if time.monotonic() - start >= LOCK_BUDGET_S:
            return False
        time.sleep(min(0.005 * (attempt + 1), 0.05))
        return True
    if attempt >= tries - 1:
        return False
    time.sleep(step * (attempt + 1))
    return True


def write_text(path, text):
    """Atomic: readers (and concurrent hooks) never see a half-written file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:6]}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        start, attempt = time.monotonic(), 0
        while True:
            try:
                os.replace(tmp, path)
                return
            except PermissionError:  # Windows: another hook process has `path` open for a moment
                if not _lock_wait(attempt, start, 5, 0.02):
                    raise
                attempt += 1
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def write_json(path, obj, indent=None):
    write_text(path, json.dumps(obj, indent=indent))


def read_json(path, default=None):
    """The parsed file, or `default` when it is missing or not JSON. On Windows a file that is being replaced
    (write_text) cannot be opened for a moment: that is retried for up to LOCK_BUDGET_S, never reported as
    missing within that budget."""
    start, attempt = time.monotonic(), 0
    while True:
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except PermissionError:
            if not _lock_wait(attempt, start, 8, 0.01):
                return default
            attempt += 1
        except (OSError, ValueError):
            return default
