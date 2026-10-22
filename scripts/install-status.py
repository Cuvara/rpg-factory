#!/usr/bin/env python3
"""Is the rpg-factory a Claude session loads the version you think it is?

Compares three things (read-only):
  source    the git checkout the marketplace points at (version, HEAD, dirty)
  installed ~/.claude/plugins/installed_plugins.json entry (version, commit) and its load path
  runtime   ${CLAUDE_PLUGIN_ROOT} of the calling session, if any

Two load modes (observed with Claude Code 2.1.280, 2026-09-30):
  directory  a `directory` marketplace (this workspace's setup): sessions load the plugin IN PLACE
             from the marketplace directory (`installLocation`); the version-keyed cache copy is
             not what runs. Source edits reach the next session; the installed *record* (version
             shown by `claude plugin list`) only changes on `claude plugin update`, which is a
             no-op while plugin.json's version is unchanged.
  cache      any other marketplace (e.g. GitHub; not verified here): sessions are expected to load the cache copy
             ~/.claude/plugins/cache/<mkt>/<plugin>/<version>; new content needs a version bump
             (or uninstall + install) and a restart.

States: CURRENT, STALE (record/copy older than source), CONTENT_MISMATCH (cache mode, same version,
different files), RESTART_REQUIRED (this session runs another copy, or a runtime whose version differs
from the source), NOT_INSTALLED.
Notes (informational, never a state change): the source HEAD is not the commit of tag v<VERSION>, e.g.
"source 1.0.4 + 3 commits past v1.0.4" - directory mode then runs unreleased code under the release label.

Usage: install-status.py [--json] [--session] [--source DIR]
  --session  SessionStart-hook mode: silent when CURRENT, otherwise emits additionalContext; always
             exits 0 and never prints a traceback (malformed plugin records mean "no advisory")
Exit: 0 CURRENT, 1 otherwise, 2 error. Writes nothing.
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
        r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=20, encoding="utf-8", errors="replace")
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


def fwd(p):
    """Forward-slash form for substring tests (Windows paths arrive with backslashes)."""
    return (p or "").replace("\\", "/")


def load_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def release_note(source, version):
    """Directory mode runs whatever is checked out: say when that is not the released commit of VERSION.
    Informational only - never changes the state."""
    if not version:
        return None
    tag = f"v{version}"
    if git(source, "rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{commit}}") is None:
        return f"source {version} has no tag {tag}: the code that runs is unreleased"
    n = git(source, "rev-list", "--count", f"{tag}..HEAD")
    behind = git(source, "rev-list", "--count", f"HEAD..{tag}")
    if n and n != "0":
        return f"source {version} + {n} commits past {tag}: the code that runs is unreleased (label {version})"
    if behind and behind != "0":
        return f"source HEAD is not {tag} ({behind} commits of {tag} missing)"
    return None


def main():
    as_json = "--json" in sys.argv
    session = "--session" in sys.argv
    home = os.path.expanduser("~")
    source = None
    if "--source" in sys.argv:
        i = sys.argv.index("--source") + 1
        if i >= len(sys.argv):
            print("install-status: --source needs a directory", file=sys.stderr)
            return 2
        source = sys.argv[i]
    entry = None
    installed_all = load_json(os.path.join(home, ".claude/plugins/installed_plugins.json"))
    plugins = installed_all.get("plugins") if isinstance(installed_all, dict) else None
    entries = plugins.get(PLUGIN_KEY) if isinstance(plugins, dict) else None
    if isinstance(entries, list) and entries and isinstance(entries[0], dict):
        entry = entries[0]
    mode, load_path = "cache", None
    mk = load_json(os.path.join(home, ".claude/plugins/known_marketplaces.json"))
    m = mk.get("rpg-factory") if isinstance(mk, dict) else None
    msrc = m.get("source") if isinstance(m, dict) else None
    if isinstance(msrc, dict) and msrc.get("source") == "directory":
        mode = "directory"
        load_path = m.get("installLocation") or msrc.get("path")
        load_path = load_path if isinstance(load_path, str) and load_path else None
    source = source or load_path or HERE

    r = {"source": {"path": source, "version": plugin_version(source), "head": git(source, "rev-parse", "HEAD"),
                    "dirty": bool(git(source, "status", "--porcelain") or "")},
         "mode": mode, "installed": None, "runtime": None, "state": None, "reasons": []}
    files = (git(source, "ls-files") or "").splitlines()
    src_hash, _ = tree_hash(source, files) if files else (None, [])

    if entry:
        ip = entry.get("installPath")
        ip = ip if isinstance(ip, str) and ip else None
        loads = load_path if mode == "directory" else ip
        inst_hash, missing = tree_hash(loads, files) if loads and files else (None, files)
        r["installed"] = {"path": ip, "loads_from": loads, "version": entry.get("version"), "commit": entry.get("gitCommitSha"),
                          "cache_version": plugin_version(ip) if ip else None,
                          "content_matches_source_head": (inst_hash == src_hash and not missing),
                          "missing_files": missing[:10]}
    rt = os.environ.get("CLAUDE_PLUGIN_ROOT")
    inst = r["installed"]
    if rt:
        same = inst and inst["loads_from"] and os.path.realpath(rt) == os.path.realpath(inst["loads_from"])
        kind = ("installed: directory marketplace, in place" if same and mode == "directory" else
                "installed-cache" if same else
                "stale cache copy" if "/.claude/plugins/cache/" in fwd(rt) else "--plugin-dir / other checkout")
        r["runtime"] = {"path": rt, "version": plugin_version(rt), "kind": kind, "is_installed_load_path": bool(same)}

    if not inst:
        r["state"] = "NOT_INSTALLED"
        r["reasons"].append("rpg-factory@rpg-factory is not in installed_plugins.json")
    else:
        if inst["version"] != r["source"]["version"]:
            r["reasons"].append(f"installed record version {inst['version']} != source version {r['source']['version']}"
                                + (" (sessions already load the source in place; `claude plugin list` and the record are stale)" if mode == "directory" else ""))
        if mode == "cache":
            if inst["commit"] and r["source"]["head"] and inst["commit"] != r["source"]["head"]:
                r["reasons"].append(f"installed commit {inst['commit'][:7]} != source HEAD {r['source']['head'][:7]}")
            if not inst["content_matches_source_head"]:
                r["reasons"].append("installed files differ from the source HEAD tree"
                                    + (f" (missing: {', '.join(inst['missing_files'][:3])})" if inst["missing_files"] else ""))
        if not r["reasons"]:
            r["state"] = "CURRENT"
        elif mode == "cache" and inst["version"] == r["source"]["version"]:
            r["state"] = "CONTENT_MISMATCH"
            r["reasons"].append("same version: `claude plugin update` is a no-op - bump the version (e.g. X.Y.Z-dev.N) "
                                "or reinstall: claude plugin uninstall rpg-factory@rpg-factory && claude plugin install rpg-factory@rpg-factory")
        else:
            r["state"] = "STALE"
    if r["source"]["dirty"]:
        r["reasons"].append("source has uncommitted changes" + (" - sessions load them as-is (directory marketplace)" if mode == "directory" else " (not installable until committed)"))
    if r["runtime"] and inst and not r["runtime"]["is_installed_load_path"]:
        r["reasons"].append(f"this session loaded {r['runtime']['path']}, the install loads {inst['loads_from']}"
                            + (" - restart the session" if "cache" in r["runtime"]["kind"] else " (--plugin-dir?)"))
        if r["state"] == "CURRENT" and "cache" in r["runtime"]["kind"]:
            r["state"] = "RESTART_REQUIRED"
    rv = (r["runtime"] or {}).get("version")
    if rv and r["source"]["version"] and rv != r["source"]["version"]:
        r["reasons"].append(f"this session runs rpg-factory {rv}, the source is {r['source']['version']} - restart the session")
        if r["state"] == "CURRENT":
            r["state"] = "RESTART_REQUIRED"
    note = release_note(source, r["source"]["version"]) if r["source"]["head"] else None
    r["notes"] = [note] if note else []

    fix = ("claude plugin marketplace update rpg-factory && claude plugin update rpg-factory@rpg-factory "
           "(then restart Claude)")
    if session:
        if r["state"] != "CURRENT":
            msg = (f"rpg-factory install state: {r['state']}. " + "; ".join(r["reasons"]) + f". Fix: {fix}. "
                   + ("Sessions load the source directory in place; the stale part is the install record."
                      if r["mode"] == "directory" else "Until then this session runs the installed copy, not the source."))
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": msg}}))
        return 0
    if as_json:
        print(json.dumps(r, indent=2))
    else:
        s, i, t = r["source"], r["installed"] or {}, r["runtime"] or {}
        print(f"source    {s['version']}  {str(s['head'])[:7]}  {'dirty' if s['dirty'] else 'clean'}  {s['path']}")
        print(f"installed {i.get('version')}  {str(i.get('commit'))[:7]}  mode={r['mode']}  loads {i.get('loads_from')}  content={'= source HEAD' if i.get('content_matches_source_head') else 'DIFFERS'}")
        print(f"runtime   {t.get('version', '-')}  {t.get('kind', 'not in a Claude session')}  {t.get('path', '')}")
        print(f"state     {r['state']}")
        for x in r["reasons"]:
            print(f"  - {x}")
        for x in r["notes"]:
            print(f"  note: {x}")
        if r["state"] != "CURRENT":
            print(f"  fix: {fix}")
    return 0 if r["state"] == "CURRENT" else 1


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252: output is UTF-8 everywhere
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    if "--session" in sys.argv:  # a SessionStart hook never fails a session: any error means "no advisory"
        try:
            main()
        except Exception:
            pass
        sys.exit(0)
    sys.exit(main())
