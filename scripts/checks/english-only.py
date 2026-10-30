#!/usr/bin/env python3
"""Report or enforce the repository's English-only content policy."""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path


def scoped_files(root: Path) -> list[Path]:
    patterns = (
        "skills/**/*.md", "commands/*.md", "docs/**/*.md", "README.md",
        "CHANGELOG.md", ".claude/CLAUDE.md", ".claude/skills/**/*.md",
        "testlab/**/*.md",
    )
    found: set[Path] = set()
    for pattern in patterns:
        found.update(p for p in root.glob(pattern) if p.is_file())
    found.add(root / "registry.json")
    return sorted(p for p in found if p.is_file())


def content_lines(file: Path):
    """Yield decoded content lines; decode JSON string escapes in registry.json first."""
    source = file.read_text(encoding="utf-8")
    if file.name != "registry.json":
        yield from enumerate(source.splitlines(), 1)
        return
    decoder = json.JSONDecoder()
    index = 0
    while index < len(source):
        if source[index] != '"':
            index += 1
            continue
        try:
            value, end = decoder.raw_decode(source, index)
        except json.JSONDecodeError:
            index += 1
            continue
        start_line = source.count("\n", 0, index) + 1
        if isinstance(value, str):
            for offset, part in enumerate(value.splitlines() or [value]):
                yield start_line + offset, part
        index = end


def is_letter(char: str) -> bool:
    return unicodedata.category(char).startswith("L")


def classify(line: str) -> list[str]:
    letters = [char for char in line if is_letter(char)]
    reasons: list[str] = []
    foreign = [char for char in letters
               if "LATIN" not in unicodedata.name(char, "") and "ASCII" not in unicodedata.name(char, "")]
    if foreign:
        names = sorted({unicodedata.name(char, "UNKNOWN") for char in foreign})
        reasons.append("non-Latin letters: " + ", ".join(names))
    non_ascii_latin = [char for char in letters if ord(char) > 127 and "LATIN" in unicodedata.name(char, "")]
    if len(non_ascii_latin) >= 2 and letters and len(non_ascii_latin) / len(letters) >= 0.05:
        reasons.append(f"non-ASCII Latin letters: {len(non_ascii_latin)}/{len(letters)}")
    return reasons


def allowlist(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    if not path.exists():
        return entries
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([^:#]+):(\*|\d+)\s+#\s*(.+)", line)
        if not match:
            raise ValueError(f"{path}:{number}: expected path:line or path:* followed by # reason")
        key = f"{match.group(1).strip()}:{match.group(2)}"
        entries[key] = match.group(3).strip()
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--report", action="store_true", help="print findings and exit 0 (default)")
    mode.add_argument("--enforce", action="store_true", help="exit 1 when findings exist")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--allowlist", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    allow_path = args.allowlist or root / "tests/fixtures/english-allow.txt"
    allowed = allowlist(allow_path)
    files = scoped_files(root)
    findings = 0
    for file in files:
        rel = file.relative_to(root).as_posix()
        seen: set[tuple[int, tuple[str, ...]]] = set()
        for line_no, line in content_lines(file):
            reasons = classify(line)
            if not reasons:
                continue
            if f"{rel}:{line_no}" in allowed or f"{rel}:*" in allowed:
                continue
            finding = (line_no, tuple(reasons))
            if finding in seen:
                continue
            seen.add(finding)
            findings += 1
            print(f"{rel}:{line_no}: {'; '.join(reasons)}")
    print(f"english-only: {len(files)} files, {findings} findings")
    return 1 if args.enforce and findings else 0


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252: output is UTF-8 everywhere
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        raise SystemExit(main())
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        print(f"english-only: error: {exc}", file=sys.stderr)
        raise SystemExit(2)
