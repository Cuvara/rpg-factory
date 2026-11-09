#!/usr/bin/env python3
"""rpg-factory git guard - PreToolUse hook entry for the Bash and PowerShell tools.

The guard itself is scripts/lib/gitguard.py (its docstring has the rules). This entry stays small on purpose:
Python never caches the bytecode of the script it runs, so the module is imported and its compiled code is reused
from the state dir (lib/hookspeed.py). Every name of the guard stays importable from this file.
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))  # appended: stdlib lookups must not stat /mnt/c first
try:
    import hookspeed  # noqa: E402
    hookspeed.enable_bytecache()
except Exception:
    pass
import gitguard  # noqa: E402
globals().update({k: v for k, v in vars(gitguard).items() if not k.startswith("__")})


def batch():
    """Run JSONL hook inputs in isolation through the real fail-open hook entry.

    An optional envelope {"payload": <hook input>, "env": {name: value}} sets
    per-case environment variables (null unsets one). Plain hook inputs work too.
    Streams and environment are restored even when a malformed case crashes.
    """
    import contextlib
    import io
    import json
    import subprocess

    source, destination = sys.stdin, sys.stdout
    if hasattr(source, "reconfigure"):
        source.reconfigure(encoding="utf-8", errors="replace")
    for line in source:
        previous_env = os.environ.copy()
        output = io.StringIO()
        result = {}
        try:
            case = json.loads(line)
            payload = case
            if isinstance(case, dict) and "payload" in case:
                payload = case["payload"]
                for key, value in case.get("env", {}).items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
            # Plugin roots are captured at import time by the real hook. Keep
            # those rare overrides faithful by giving them a fresh import.
            if isinstance(case, dict) and "payload" in case and any(
                key in case.get("env", {}) for key in ("CLAUDE_PLUGIN_ROOT", "PLUGIN_ROOT")
            ):
                process = subprocess.run(
                    [sys.executable, os.path.abspath(__file__)],
                    input=json.dumps(payload), capture_output=True, encoding="utf-8",
                )
                result["rc"] = process.returncode
                output.write(process.stdout)
            else:
                sys.stdin = io.StringIO(json.dumps(payload))
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
                    result["rc"] = gitguard.run()
        except BaseException as exc:
            result.update(rc=1, error=f"{type(exc).__name__}: {exc}")
        finally:
            sys.stdin = source
            os.environ.clear()
            os.environ.update(previous_env)
        result["out"] = output.getvalue()
        destination.write(json.dumps(result) + "\n")
        destination.flush()
    return 0


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252: output is UTF-8 everywhere
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(batch() if sys.argv[1:] == ["--batch"] else gitguard.run())
