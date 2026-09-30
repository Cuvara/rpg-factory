#!/usr/bin/env python3
"""Is the rpg-factory a Claude session loads the version you think it is?

Compares three things (read-only):
  source    the git checkout the marketplace points at (version, HEAD, dirty)
  installed ~/.claude/plugins/installed_plugins.json entry + its cache copy (version, commit,
            content hash of every tracked file vs the source HEAD tree)
  runtime   ${CLAUDE_PLUGIN_ROOT} of the calling session, if any (cache copy or --plugin-dir)

Why: Claude Code installs a *copy* of a directory-marketplace plugin into a cache keyed by
version. `claude plugin update` is a no-op while plugin.json's version is unchanged, so a new
commit with the same version never reaches real sessions (v0.2.0 ran as the v0.1.0 copy).

Usage: install-status.py [--json] [--session] [--source DIR]
  --session  SessionStart-hook mode: silent when CURRENT, otherwise emits additionalContext
Exit: 0 CURRENT, 1 STALE / CONTENT_MISMATCH / NOT_INSTALLED, 2 error. Writes nothing.
"""
import hashlib
import json
import os
import subprocess
import sys

PLUGIN_KEY = "rpg-factory@rpg-factory"
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(repo, *args):
    try:
        r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=20)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def plugin_version(root):
    try:
        return json.load(open(os.path.join(root, ".claude-plugin", "plugin.json"), encoding="utf-8")).get("version")
    except (OSError, json.JSONDecodeError):
        return None


def tree_hash(root, files):
    h = hashlib.sha256()
    missing = []
    for f in files:
        p = os.path.join(root, f)
        try:
            with open(p, "rb") as fh:
                h.update(f.encode() + b"\0" + hashlib.sha256(fh.read()).digest())
        except OSError:
            missing.append(f)
    return h.hexdigest()[:16], missing


def main():
    as_json = "--json" in sys.argv
    session = "--session" in sys.argv
    home = os.path.expanduser("~")
    source = None
    if "--source" in sys.argv:
        source = sys.argv[sys.argv.index("--source") + 1]
    try:
        installed_all = json.load(open(os.path.join(home, ".claude/plugins/installed_plugins.json"), encoding="utf-8"))
        entry = (installed_all.get("plugins", {}).get(PLUGIN_KEY) or [None])[0]
    except (OSError, json.JSONDecodeError):
        entry = None
    if source is None:
        try:
            mk = json.load(open(os.path.join(home, ".claude/plugins/known_marketplaces.json"), encoding="utf-8"))
            src = (mk.get("rpg-factory") or {}).get("source", {})
            source = src.get("path") if src.get("source") == "directory" else None
        except (OSError, json.JSONDecodeError):
            source = None
    source = source or HERE

    r = {"source": {"path": source, "version": plugin_version(source), "head": git(source, "rev-parse", "HEAD"),
                    "dirty": bool(git(source, "status", "--porcelain") or "")},
         "installed": None, "runtime": None, "state": None, "reasons": []}
    files = (git(source, "ls-files") or "").splitlines()
    src_hash, _ = tree_hash(source, files) if files else (None, [])

    if entry:
        ip = entry.get("installPath")
        inst_hash, missing = tree_hash(ip, files) if ip and files else (None, files)
        r["installed"] = {"path": ip, "version": entry.get("version"), "commit": entry.get("gitCommitSha"),
                          "cache_version": plugin_version(ip) if ip else None,
                          "content_matches_source_head": (inst_hash == src_hash and not missing),
                          "missing_files": missing[:10]}
    rt = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if rt:
        r["runtime"] = {"path": rt, "version": plugin_version(rt),
                        "kind": "installed-cache" if "/.claude/plugins/cache/" in rt else "plugin-dir/source"}

    inst = r["installed"]
    if not inst:
        r["state"] = "NOT_INSTALLED"
        r["reasons"].append("rpg-factory@rpg-factory is not in installed_plugins.json")
    else:
        if inst["version"] != r["source"]["version"]:
            r["reasons"].append(f"installed version {inst['version']} != source version {r['source']['version']}")
        if inst["commit"] and r["source"]["head"] and inst["commit"] != r["source"]["head"]:
            r["reasons"].append(f"installed commit {inst['commit'][:7]} != source HEAD {r['source']['head'][:7]}")
        if not inst["content_matches_source_head"]:
            r["reasons"].append("installed files differ from the source working tree"
                                + (f" (missing: {', '.join(inst['missing_files'][:3])})" if inst["missing_files"] else ""))
        if not r["reasons"]:
            r["state"] = "CURRENT"
        elif inst["version"] == r["source"]["version"]:
            r["state"] = "CONTENT_MISMATCH"
            r["reasons"].append("same version: `claude plugin update` is a no-op - bump the version (e.g. X.Y.Z-dev.N) "
                                "or reinstall: claude plugin uninstall rpg-factory@rpg-factory && claude plugin install rpg-factory@rpg-factory")
        else:
            r["state"] = "STALE"
    if r["source"]["dirty"]:
        r["reasons"].append("source has uncommitted changes (not installable until committed)")
    if r["runtime"] and inst and r["runtime"]["kind"] == "installed-cache" and os.path.realpath(r["runtime"]["path"]) != os.path.realpath(inst["path"] or ""):
        r["reasons"].append(f"this session loaded {r['runtime']['path']} but the install now points at {inst['path']} - restart the session")
        if r["state"] == "CURRENT":
            r["state"] = "RESTART_REQUIRED"

    fix = ("claude plugin marketplace update rpg-factory && claude plugin update rpg-factory@rpg-factory "
           "(then restart Claude)")
    if session:
        if r["state"] != "CURRENT":
            msg = (f"rpg-factory install state: {r['state']}. " + "; ".join(r["reasons"]) + f". Fix: {fix}. "
                   "Until then this session runs the installed copy, not the source.")
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": msg}}))
        return 0
    if as_json:
        print(json.dumps(r, indent=2))
    else:
        s, i, t = r["source"], r["installed"] or {}, r["runtime"] or {}
        print(f"source    {s['version']}  {str(s['head'])[:7]}  {'dirty' if s['dirty'] else 'clean'}  {s['path']}")
        print(f"installed {i.get('version')}  {str(i.get('commit'))[:7]}  content={'= source' if i.get('content_matches_source_head') else 'DIFFERS'}  {i.get('path')}")
        print(f"runtime   {t.get('version', '-')}  {t.get('kind', 'not in a Claude session')}  {t.get('path', '')}")
        print(f"state     {r['state']}")
        for x in r["reasons"]:
            print(f"  - {x}")
        if r["state"] != "CURRENT":
            print(f"  fix: {fix}")
    return 0 if r["state"] == "CURRENT" else 1


if __name__ == "__main__":
    sys.exit(main())
