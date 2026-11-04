#!/usr/bin/env python3
"""Codex 0.164 hook input -> existing Factory guards -> context only.

Codex canonicalizes shell tools to Bash and patches to apply_patch, with
tool_input.command for both. Patch headers name all affected paths, including
both sides of a move. No command or patch is executed by this adapter.
"""
import contextlib
import importlib.util
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HERE)


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def paths(patch):
    """Parse structural patch headers, never text inside a hunk."""
    for line in patch.splitlines():
        for prefix in ("*** Add File: ", "*** Update File: ", "*** Delete File: ", "*** Move to: "):
            if line.startswith(prefix):
                path = line[len(prefix):].strip()
                if path:
                    yield path
                break


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"session-start", "pre-tool-use"}:
        return
    stream = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace") if hasattr(sys.stdin, "buffer") else sys.stdin
    payload = json.load(stream)
    if not isinstance(payload, dict):
        return
    if not all(isinstance(payload.get(k), str) and payload[k] for k in ("session_id", "cwd")):
        return
    event = "SessionStart" if sys.argv[1] == "session-start" else "PreToolUse"
    if payload.get("hook_event_name") != event:
        return
    # Capture imported code as well: stdout is one sanitized advisory or empty.
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(io.StringIO()):
        if event == "SessionStart":
            status = load("codex_install_status", "install-status.py")
            message = status.codex_session_advisory()
        else:
            if os.environ.get("RPG_FACTORY_GUARD", "").lower() in {"off", "0", "false"}:
                return
            tool = payload.get("tool_name")
            ti = payload.get("tool_input")
            if not isinstance(ti, dict) or not isinstance(ti.get("command"), str):
                return
            if not isinstance(payload.get("cwd", ""), str):
                return
            import factory_session
            registry = factory_session.load_registry()
            if not registry:
                return
            if tool == "Bash":
                guard = factory_session.guard()
                # Reuse the guard entry point, including its independent fail-safe rules.
                with stdin(dict(payload, _rpg_factory_codex=True)):
                    guard.main()
                advisory = json.loads(captured.getvalue()) if captured.getvalue() else {}
                message = advisory.get("hookSpecificOutput", {}).get("additionalContext")
            elif tool == "apply_patch":
                guard = load("codex_file_guard", "file-guard.py")
                reasons = []
                for path in dict.fromkeys(paths(ti["command"])):
                    try:
                        reasons += guard.evaluate(dict(payload, tool_name="Edit", tool_input={"file_path": path}), registry)
                    except Exception:
                        pass
                message = factory_session.guard().advisory("rpg-factory file guard", reasons)["hookSpecificOutput"]["additionalContext"] if reasons else None
            else:
                return
    if message:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": message}}))


@contextlib.contextmanager
def stdin(payload):
    original = sys.stdin
    try:
        sys.stdin = io.StringIO(json.dumps(payload))
        yield
    finally:
        sys.stdin = original


if __name__ == "__main__":
    try:
        for _stream in (sys.stdout, sys.stderr):
            if hasattr(_stream, "reconfigure"):
                _stream.reconfigure(encoding="utf-8", errors="replace")
        main()
    except BaseException:
        pass  # malformed input, missing files, and broken guards mean no opinion
    sys.exit(0)
