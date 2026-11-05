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

if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252: output is UTF-8 everywhere
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(gitguard.run())
