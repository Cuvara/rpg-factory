#!/usr/bin/env python3
"""Release gate for rpg-factory itself (read-only: never fetches, tags, writes or pushes).

Before tagging (default):
  - VERSION == .claude-plugin/plugin.json == marketplace.json plugin entry == README "Version X (see `VERSION`)"
  - CHANGELOG.md has a `## [X.Y.Z]` section and `## [Unreleased]` is empty
  - tag vX.Y.Z does not exist locally, nor on origin (`git ls-remote --tags`, skipped with --no-remote)
  - HEAD is main (on branch main, or detached at the merge commit) and equals origin/main
    (the remote-tracking ref; with remote checks also the live `git ls-remote origin refs/heads/main`)
  - the working tree is clean
After tagging (--verify-tag):
  - tag vX.Y.Z exists, is annotated, its message is "rpg-factory X.Y.Z", it points to HEAD, and VERSION at
    the tag is X.Y.Z (plus the version consistency checks above, read at HEAD); with remote checks, a tag
    already on origin must be the same tag object (not pushed yet is only a note)

Usage: release-check.py [--repo DIR] [--no-remote] [--notes] [--verify-tag]
  --notes   print the CHANGELOG section of X.Y.Z (the release notes body) to stdout; check lines go to stderr
            e.g. release-check.py --notes > notes.md && gh release create vX.Y.Z --verify-tag -F notes.md
Exit: 0 every check passed, 1 otherwise.
Order (see .claude/CLAUDE.md "Releases"): merge the release PR -> check out the merge commit -> release-check ->
run-all --release + dogfood --installed -> annotated tag -> release-check --verify-tag -> gh release create.
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(repo, *args, timeout=30):
    try:
        r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def changelog_section(text, heading):
    """Body of the `## [heading]` section (up to the next `## `), or None when the heading is missing."""
    m = re.search(r"^## \[" + re.escape(heading) + r"\][^\n]*\n", text or "", re.M)
    if not m:
        return None
    rest = text[m.end():]
    n = re.search(r"^## ", rest, re.M)
    return (rest[:n.start()] if n else rest).strip("\n")


def versions(repo):
    v = {}
    v["VERSION"] = (read(os.path.join(repo, "VERSION")) or "").strip() or None
    try:
        v["plugin.json"] = json.loads(read(os.path.join(repo, ".claude-plugin", "plugin.json")) or "{}").get("version")
    except ValueError:
        v["plugin.json"] = None
    try:
        mk = json.loads(read(os.path.join(repo, ".claude-plugin", "marketplace.json")) or "{}")
        v["marketplace.json"] = next((p.get("version") for p in mk.get("plugins", []) if p.get("name") == "rpg-factory"), None)
    except (ValueError, AttributeError):
        v["marketplace.json"] = None
    m = re.search(r"^Version ([0-9][0-9A-Za-z.+-]*) \(see `VERSION`\)", read(os.path.join(repo, "README.md")) or "", re.M)
    v["README"] = m.group(1) if m else None
    return v


def main(argv):
    repo, remote, notes, verify = ROOT, True, False, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--repo" and i + 1 < len(argv):
            repo = argv[i + 1]
            i += 1
        elif a == "--no-remote":
            remote = False
        elif a == "--notes":
            notes = True
        elif a == "--verify-tag":
            verify = True
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            print(f"release-check: unknown argument '{a}'", file=sys.stderr)
            return 1
        i += 1
    out = sys.stderr if notes else sys.stdout
    results = []

    def check(ok, what, detail=""):
        results.append(ok)
        print(f"{'OK  ' if ok else 'FAIL'}  {what}" + (f" - {detail}" if detail and not ok else ""), file=out)

    if git(repo, "rev-parse", "--is-inside-work-tree") != "true":
        check(False, f"{repo} is a git work tree")
        return 1
    v = versions(repo)
    ver = v["VERSION"]
    check(bool(ver) and all(x == ver for x in v.values()),
          f"version {ver}: VERSION == plugin.json == marketplace.json == README",
          ", ".join(f"{k}={x}" for k, x in v.items()))
    cl = read(os.path.join(repo, "CHANGELOG.md")) or ""
    section = changelog_section(cl, ver) if ver else None
    check(bool(section and section.strip()), f"CHANGELOG has a non-empty ## [{ver}] section")
    unreleased = changelog_section(cl, "Unreleased")
    check(unreleased is not None and not unreleased.strip(), "CHANGELOG ## [Unreleased] is present and empty",
          "missing" if unreleased is None else f"{len(unreleased.strip().splitlines())} line(s) still unreleased")
    tag = f"v{ver}"
    head = git(repo, "rev-parse", "HEAD")
    local_tag = git(repo, "rev-parse", "-q", "--verify", f"refs/tags/{tag}")
    origin = git(repo, "remote", "get-url", "origin")
    if remote and not origin:
        check(False, "remote checks need a remote named origin", "use --no-remote for an offline check")
    if not verify:
        check(local_tag is None, f"tag {tag} does not exist locally", f"refs/tags/{tag} -> {str(local_tag)[:12]}")
        if remote and origin:
            rt = git(repo, "ls-remote", "--tags", "origin", f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}", timeout=60)
            check(rt == "", f"tag {tag} does not exist on origin", "ls-remote failed" if rt is None else (rt.splitlines() or [""])[0])
        branch = git(repo, "branch", "--show-current") or ""
        om = git(repo, "rev-parse", "-q", "--verify", "refs/remotes/origin/main")
        check(branch in ("main", ""), "HEAD is main (branch main or detached at the merge commit)", f"on branch {branch}")
        check(bool(head) and head == om, "HEAD == origin/main (remote-tracking ref)", f"HEAD {str(head)[:12]} origin/main {str(om)[:12]}")
        if remote and origin:
            lm = git(repo, "ls-remote", "origin", "refs/heads/main", timeout=60)
            live = (lm or "").split("\t")[0] or None
            check(bool(head) and head == live, "HEAD == main on origin (ls-remote)", f"origin main {str(live)[:12]}")
        dirty = git(repo, "status", "--porcelain")
        check(dirty == "", "working tree clean", "git status failed" if dirty is None else f"{len(dirty.splitlines())} change(s)")
    else:
        check(local_tag is not None, f"tag {tag} exists locally")
        if local_tag:
            kind = git(repo, "cat-file", "-t", f"refs/tags/{tag}")
            check(kind == "tag", f"tag {tag} is annotated", f"object type {kind}")
            subject = git(repo, "tag", "-l", "--format=%(contents:subject)", tag)
            check(subject == f"rpg-factory {ver}", f"tag message is 'rpg-factory {ver}'", f"got '{subject}'")
            target = git(repo, "rev-parse", f"refs/tags/{tag}^{{commit}}")
            check(bool(head) and target == head, f"tag {tag} points to HEAD", f"tag {str(target)[:12]} HEAD {str(head)[:12]}")
            tv = (git(repo, "show", f"refs/tags/{tag}:VERSION") or "").strip()
            check(tv == ver, f"VERSION at {tag} is {ver}", f"got '{tv}'")
            if remote and origin:
                rt = git(repo, "ls-remote", "--tags", "origin", f"refs/tags/{tag}", timeout=60)
                live = (rt or "").split("\t")[0] or None
                if live is None:  # not pushed yet: fine here, `gh release create --verify-tag` needs it pushed
                    print(f"note  tag {tag} is not on origin yet: push it before gh release create --verify-tag", file=out)
                else:
                    check(live == local_tag, f"origin has the same tag object for {tag}", f"origin {live[:12]} local {local_tag[:12]}")
    ok = all(results)
    print(f"release-check {tag}: {'PASS' if ok else 'FAIL'} ({sum(results)}/{len(results)} checks)", file=out)
    if notes and section:
        print(section.strip("\n"))
    return 0 if ok else 1


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252: output is UTF-8 everywhere
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
