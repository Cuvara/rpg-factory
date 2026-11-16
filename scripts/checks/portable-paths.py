#!/usr/bin/env python3
"""Report user-specific and machine-only paths in tracked repository text."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "lib"))  # appended: stdlib lookups must not stat /mnt/c first
from workspace import registry_root_default  # noqa: E402  (scripts/lib/workspace.py)

SEP = r"[/\\]+"
SEGMENT = r"[\w.$%{}<>~!-]+"
PATHS = re.compile(
    rf"(?<![\w/])(?:[a-z]:{SEP}users{SEP}|/mnt/[a-z]/users/|/[a-z]/users/|/users/|/home/)(?P<user>{SEGMENT})"
    rf"|(?<![\w/])[a-z]:{SEP}(?:tmp|temp)(?={SEP}|\b)", re.I)
URL = re.compile(r"https?://[^\s\"'<>]+", re.I)
FAKE = {"person", "example", "user", "username", "name", "me", "you", "someone", "..."}
CI_RUNNERS = {"runner", "runneradmin", "runner~1"}


def canonical(path: str) -> str:
    """Normalize drive, Git Bash and WSL forms for workspace comparisons."""
    path = re.sub(r"\\+", "/", path).rstrip("/")
    path = re.sub(r"^/mnt/([a-z])(?=/)", r"\1:", path, flags=re.I)
    path = re.sub(r"^/([a-z])(?=/)", r"\1:", path, flags=re.I)
    return path.casefold()


def load_allowlist(path: Path) -> list[tuple[str, re.Pattern[str] | None]]:
    entries = []
    if not path.exists():
        return entries
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        entry, marker, reason = line.rpartition(" #")
        if not marker or not reason.strip():
            raise ValueError(f"{path}:{number}: entry needs a reason")
        name, colon, pattern = entry.strip().partition(":")
        if not name or (colon and not pattern):
            raise ValueError(f"{path}:{number}: invalid entry")
        entries.append((name, re.compile(pattern) if colon else None))
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--report", action="store_true", help="print findings and exit 0 (default)")
    mode.add_argument("--enforce", action="store_true", help="exit 1 on findings")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--allowlist", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    allow = load_allowlist(args.allowlist or root / "tests/fixtures/portable-paths-allow.txt")
    registry = json.loads((root / "registry.json").read_text(encoding="utf-8"))
    default = registry_root_default(registry)
    workspace = canonical(default) if default else None
    result = subprocess.run(["git", "ls-files", "-z"], cwd=root, check=True, stdout=subprocess.PIPE)
    findings = files = 0
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8", errors="surrogateescape")
        if rel.startswith("docs/plans/"):
            continue
        try:
            data = (root / rel).read_bytes()
            if b"\0" in data:
                continue
            source = data.decode("utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        files += 1
        for number, line in enumerate(source.splitlines(), 1):
            urls = [m.span() for m in URL.finditer(line)]
            for match in PATHS.finditer(line):
                if any(start <= match.start() < end for start, end in urls):
                    continue
                user = match.group("user")
                if user and (user.casefold() in FAKE or
                             (rel.startswith(".github/") and user.casefold() in CI_RUNNERS) or
                             len(user) == 1 or
                             user.startswith(("<", "{", "$", "%", "~"))):
                    continue
                # Compare the whole path from the match, not just its home prefix.
                tail = re.match(r"[^\s\"'<>]*", line[match.start():]).group()
                candidate = canonical(tail).rstrip(".,;:)]}")
                if workspace and (candidate == workspace or candidate.startswith(workspace + "/")):
                    continue
                if any(name == rel and (pattern is None or pattern.search(line)) for name, pattern in allow):
                    continue
                findings += 1
                print(f"{rel}:{number}: {match.group()}")
    print(f"portable-paths: {files} files, {findings} findings")
    return 1 if args.enforce and findings else 0


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252: output is UTF-8 everywhere
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, re.error, subprocess.CalledProcessError) as exc:
        print(f"portable-paths: error: {exc}", file=sys.stderr)
        raise SystemExit(2)
