"""Shared English-only detection: the check, the file guard and the git guard use one definition.

A line is offending when it holds letters of a non-Latin script, or when at least 5 percent of its letters (and at
least two) are non-ASCII Latin letters (Vietnamese, French, ...). Symbols, arrows and punctuation are not letters.
Standard library only, no I/O at import: the hooks import this module on every call, so it stays cheap. Text that is
pure ASCII returns before any per-character work.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

NON_ASCII_LATIN_RATIO = 0.05


def is_letter(char: str) -> bool:
    return unicodedata.category(char).startswith("L")


def classify(line: str) -> list[str]:
    """Reasons a line is not English, in a stable order; an empty list means the line passes."""
    if line.isascii():
        return []
    letters = 0
    foreign: set[str] = set()
    non_ascii_latin = 0
    for char in line:
        if char < "\x80":
            if char.isalpha():
                letters += 1
            continue
        if not is_letter(char):
            continue
        letters += 1
        name = unicodedata.name(char, "")
        if "LATIN" in name:
            non_ascii_latin += 1
        elif "ASCII" not in name:
            foreign.add(unicodedata.name(char, "UNKNOWN"))
    reasons: list[str] = []
    if foreign:
        reasons.append("non-Latin letters: " + ", ".join(sorted(foreign)))
    if non_ascii_latin >= 2 and letters and non_ascii_latin / letters >= NON_ASCII_LATIN_RATIO:
        reasons.append(f"non-ASCII Latin letters: {non_ascii_latin}/{letters}")
    return reasons


def first_offending_line(text: str) -> tuple[int, str] | None:
    """(1-based line number, line) of the first line that is not English, or None."""
    if not text or text.isascii():
        return None
    for number, line in enumerate(text.splitlines(), 1):
        if classify(line):
            return number, line
    return None


def allowlist(path: Path) -> dict[str, str]:
    """Parse an allowlist file of `path:line # reason` or `path:* # reason` entries (comments and blanks skipped)."""
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
