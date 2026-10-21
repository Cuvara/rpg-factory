#!/usr/bin/env python3
"""sgl-determinism.py - read-only guard for ADR-10's determinism budget in Shared.GameLogic.

Shared.GameLogic runs on the NativeAOT x64 server and the IL2CPP ARM64 client. Only IEEE-exact float
operations are allowed (+ - * /, comparisons, MathF.Min/Max/Abs/Sqrt); transcendentals and other
implementation-defined math are banned (backend/docs/ARCHITECTURE-DECISIONS.md, ADR-10 decision 5).
This scans every .cs file under the directory for calls to banned Math/MathF members, ignoring comments
and string literals, and reports each hit as path:line.

Usage: sgl-determinism.py [DIR]   (default: backend/gameserver-dotnet/Shared.GameLogic, from the server repo root)
Exit 0 = no banned call (prints "OK: sgl-determinism files=N banned=0"); 1 = banned calls (listed);
2 = the directory does not exist or holds no .cs file.
"""
import os
import re
import sys

BANNED = ("Sin", "Cos", "Tan", "Asin", "Acos", "Atan", "Atan2", "Sinh", "Cosh", "Tanh", "Asinh", "Acosh",
          "Atanh", "Exp", "Log", "Log10", "Log2", "Pow", "Cbrt", "ScaleB", "FusedMultiplyAdd", "SinCos")
CALL = re.compile(r"\b(?:System\.)?Math[F]?\s*\.\s*(" + "|".join(BANNED) + r")\s*\(")


def strip_code(text):
    """Blank out comments and string/char literals, keeping line breaks so line numbers survive."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i)); i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("".join(ch if ch == "\n" else " " for ch in text[i:j])); i = j
        elif c == '"' or c == "'":
            verbatim = i > 0 and text[i - 1] == "@"
            j = i + 1
            while j < n and text[j] != c:
                if text[j] == "\\" and not verbatim:
                    j += 1
                elif text[j] == "\n" and not verbatim:
                    break
                j += 1
            j = min(j + 1, n)
            out.append("".join(ch if ch == "\n" else " " for ch in text[i:j])); i = j
        else:
            out.append(c); i += 1
    return "".join(out)


def main(argv):
    root = argv[1] if len(argv) > 1 else "backend/gameserver-dotnet/Shared.GameLogic"
    if not os.path.isdir(root):
        print(f"ERROR: {root} is not a directory"); return 2
    files, hits = 0, []
    for d, dirs, names in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in ("bin", "obj", ".git"))
        for name in sorted(names):
            if not name.endswith(".cs"):
                continue
            path = os.path.join(d, name)
            files += 1
            with open(path, encoding="utf-8", errors="replace") as fh:
                code = strip_code(fh.read())
            for no, line in enumerate(code.splitlines(), 1):
                for m in CALL.finditer(line):
                    hits.append(f"{os.path.relpath(path, root)}:{no}: Math{'F' if 'MathF' in m.group(0) else ''}.{m.group(1)}")
    if files == 0:
        print(f"ERROR: no .cs files under {root}"); return 2
    if hits:
        print(f"FAIL: sgl-determinism files={files} banned={len(hits)} (ADR-10: only + - * /, comparisons, MathF.Min/Max/Abs/Sqrt)")
        for h in hits:
            print(f"  {h}")
        return 1
    print(f"OK: sgl-determinism files={files} banned=0")
    return 0


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252: output is UTF-8 everywhere
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv))
