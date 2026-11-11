"""Factory execution mode detection and advisories."""
import os
import shlex
import sys

from .common import INTERPRETERS, PLUGIN_ROOT, SCRIPTS, SHELLS, find_workspace
from .shell import expand, prog

def _needs_mode(payload):
    """Cheap file check first - factory_session.py is only imported when a mode exists or the command declares one
    (read-only hook calls stay fast on /mnt/c)."""
    import fstate  # noqa: E402
    sid = fstate.session_key(payload.get("session_id"))  # the same directory factory_session writes MODE to
    command = (payload.get("tool_input") or {}).get("command") or ""
    return os.path.exists(os.path.join(fstate.scratch(), sid, "MODE")) or "--mode" in command


MODE_SCRIPTS = {"factory-context.sh", "context.py"}


def mode_runner(payload):
    """The first expanded argv that executes factory-context.sh (or lib/context.py) with --mode: the script
    itself as the program, or a shell / interpreter whose first non-option argument is the script."""
    command = (payload.get("tool_input") or {}).get("command") or ""
    if "--mode" not in command:
        return None
    shell = "powershell" if payload.get("tool_name") == "PowerShell" else "bash"
    for argv in expand(command, shell=shell):
        p = prog(argv[0])
        if p in MODE_SCRIPTS:
            script = 0
        elif p in SHELLS or p in INTERPRETERS:
            script = next((k for k, a in enumerate(argv[1:], 1) if not a.startswith("-")), None)
            if script is None or prog(argv[script]) not in MODE_SCRIPTS:
                continue
        else:
            continue
        if any(a == "--mode" or a.startswith("--mode=") for a in argv[script + 1:]):
            return [prog(argv[script])] + argv[script + 1:]
    return None


def mode_hits(payload, registry):
    """Factory execution mode (declared with `factory-context.sh --mode <m>`): analyze/plan/review are
    read-only; validate may additionally run run-checks.py. implement/resume (or no mode) = normal rules."""
    sys.path.append(SCRIPTS)  # appended: stdlib lookups must not stat /mnt/c first
    import factory_session as session  # noqa: E402
    session._REGISTRY = session._REGISTRY or registry
    # a mode switch counts wherever it runs (a stale read-only mode must not outlive `--mode implement` run from
    # outside the workspace), but only when the command really runs the script - `grep factory-context.sh --mode
    # review README.md` or `echo ... --mode plan` only mention it
    runner = mode_runner(payload)
    declared = session.record_mode(dict(payload, tool_name="Bash", tool_input={"command": shlex.join(runner)})) if runner else None
    ws = find_workspace(payload.get("cwd") or os.getcwd(), registry)
    if not ws:
        return []
    mode = declared or session.current_mode(payload)
    if not mode or declared or session.is_read_only(payload):
        return []
    how = ("switch only when the user asked for it: `bash \"" + PLUGIN_ROOT.replace("\\", "/").rstrip("/")
           + "/scripts/factory-context.sh\""  # forward slashes: the command is pasted into bash
           + " --mode implement` (or validate)")
    if mode in session.READ_ONLY_MODES:
        return [("deny", f"Factory mode is `{mode}` (read-only): this command changes state - {how}")]
    if mode == "validate" and not session.runs_checks(payload):
        return [("deny", "Factory mode is `validate`: only read-only commands and run-checks.py - " + how)]
    return []
