#!/usr/bin/env python3
"""Changelog fragments: one file per change in changelog.d/, gathered into CHANGELOG.md at release time.

Every change adds `changelog.d/<topic>.md` instead of editing CHANGELOG.md, so parallel branches never edit the
same lines (CHANGELOG.md conflicted in most merges before fragments). A fragment holds Keep a Changelog
subsections and nothing else:

    ### Fixed

    - **Thing.** What changed and why.

Usage: changelog.py check    [--root DIR]   fragments are well formed and CHANGELOG.md [Unreleased] is empty (exit 0/1)
       changelog.py preview  [--root DIR]   print the assembled [Unreleased] body
       changelog.py release X.Y.Z [--date YYYY-MM-DD] [--summary TEXT] [--root DIR]
                                            write `## [X.Y.Z] - date` under [Unreleased] and delete the fragments
check and preview are read-only; release is the only command that writes (the release commit).
"""
import datetime
import os
import re
import sys

CATEGORIES = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADING = re.compile(r"^### (.+?)\s*$")


def fragments(root):
    d = os.path.join(root, "changelog.d")
    if not os.path.isdir(d):
        return []
    return sorted(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".md") and f != "README.md")


def parse(path):
    """({category: [lines]}, [problems]) for one fragment; lines keep their text, blank edges trimmed."""
    try:
        text = open(path, encoding="utf-8").read()
    except (OSError, UnicodeDecodeError) as e:
        return {}, [f"unreadable: {e}"]
    sections, problems, current = {}, [], None
    for n, line in enumerate(text.splitlines(), 1):
        m = HEADING.match(line)
        if m:
            current = m.group(1)
            if current not in CATEGORIES:
                problems.append(f"line {n}: unknown category '### {current}' (use {', '.join(CATEGORIES)})")
            elif current in sections:
                problems.append(f"line {n}: '### {current}' appears twice")
            sections.setdefault(current, [])
        elif line.startswith("#"):
            problems.append(f"line {n}: only '### <Category>' headings are allowed: {line[:60]}")
        elif current is None:
            if line.strip():
                problems.append(f"line {n}: text before the first '### <Category>' heading")
        else:
            sections[current].append(line)
    for cat, lines in sections.items():
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            problems.append(f"'### {cat}' has no entries")
    if not sections and not problems:
        problems.append("no '### <Category>' section")
    return sections, problems


def section(text, heading):
    """(start, end) of the body of `## [heading]` (up to the next `## `), or None."""
    m = re.search(r"^## \[" + re.escape(heading) + r"\][^\n]*\n", text, re.M)
    if not m:
        return None
    n = re.search(r"^## ", text[m.end():], re.M)
    return m.end(), m.end() + n.start() if n else len(text)


def assemble(root):
    """(markdown body, problems) of every fragment merged by category in Keep a Changelog order."""
    merged, problems = {c: [] for c in CATEGORIES}, []
    for path in fragments(root):
        sections, errs = parse(path)
        problems += [f"{os.path.relpath(path, root)}: {e}" for e in errs]
        for cat, lines in sections.items():
            if cat in merged and lines:
                merged[cat].append("\n".join(lines))
    body = "\n\n".join(f"### {c}\n\n" + "\n".join(merged[c]) for c in CATEGORIES if merged[c])
    return body, problems


def changelog(root):
    try:
        return open(os.path.join(root, "CHANGELOG.md"), encoding="utf-8").read()
    except OSError:
        return None


def check(root):
    _, problems = assemble(root)
    text = changelog(root)
    span = section(text or "", "Unreleased")
    if text is None:
        problems.append("CHANGELOG.md missing")
    elif span is None:
        problems.append("CHANGELOG.md has no '## [Unreleased]' heading")
    elif text[span[0]:span[1]].strip():
        problems.append("CHANGELOG.md [Unreleased] has entries: put them in changelog.d/<topic>.md instead")
    for p in problems:
        print(f"FAIL  {p}")
    n = len(fragments(root))
    print(f"changelog: {n} fragment(s), {len(problems)} problem(s)")
    return 1 if problems else 0


def release(root, version, date, summary):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version or ""):
        print(f"changelog release: version must be X.Y.Z, got {version!r}", file=sys.stderr)
        return 2
    body, problems = assemble(root)
    text = changelog(root)
    span = section(text or "", "Unreleased")
    if text is None or span is None:
        problems.append("CHANGELOG.md with a '## [Unreleased]' heading is required")
    elif text[span[0]:span[1]].strip():
        problems.append("CHANGELOG.md [Unreleased] has entries: move them to changelog.d/ first")
    if text and section(text, version) is not None:
        problems.append(f"CHANGELOG.md already has '## [{version}]'")
    if not body and not summary:
        problems.append("no fragments in changelog.d/ and no --summary: nothing to release")
    if problems:
        for p in problems:
            print(f"FAIL  {p}", file=sys.stderr)
        return 1
    parts = [p for p in (summary.strip() if summary else "", body) if p]
    new = f"## [{version}] - {date}\n\n" + "\n\n".join(parts) + "\n\n"
    out = text[:span[0]].rstrip("\n") + "\n\n" + new + text[span[1]:].lstrip("\n")
    with open(os.path.join(root, "CHANGELOG.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    for path in fragments(root):
        os.remove(path)
    print(f"changelog: wrote ## [{version}] - {date} and removed the fragments")
    return 0


def main(argv):
    args, root, date, summary = [], ROOT, datetime.date.today().isoformat(), None
    it = iter(argv)
    for a in it:
        if a in ("--root", "--date", "--summary"):
            v = next(it, None)
            if v is None:
                print(f"changelog: {a} needs a value", file=sys.stderr)
                return 2
            if a == "--root":
                root = v
            elif a == "--date":
                date = v
            else:
                summary = v
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            args.append(a)
    if args[:1] == ["check"] and len(args) == 1:
        return check(root)
    if args[:1] == ["preview"] and len(args) == 1:
        body, problems = assemble(root)
        for p in problems:
            print(f"FAIL  {p}", file=sys.stderr)
        print(body)
        return 1 if problems else 0
    if args[:1] == ["release"] and len(args) == 2:
        return release(root, args[1], date, summary)
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):  # UTF-8 and LF on every platform (Windows pipes default to cp1252, CRLF)
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace", newline="\n")
    sys.exit(main(sys.argv[1:]))
