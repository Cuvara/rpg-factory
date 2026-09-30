#!/usr/bin/env python3
"""rpg-factory tripwire - catches git state changes that bypassed the text guard.

The PreToolUse guard reads the command text, so git run *inside* a script file or a program
(python, node, a build script) is invisible to it. The tripwire looks at the effect instead:

  --pre   (PreToolUse, Bash|PowerShell) cheap-first: read-only commands are skipped. Otherwise it
          fingerprints every workspace repo straight from its .git files (HEAD, loose refs,
          packed-refs; no subprocess) and records which repos the command's own recognised git
          invocations may legitimately change.
  --post  (PostToolUse) re-fingerprints and diffs. Unexplained changes are violations:
            - any tag ref created, moved or deleted (agents never tag)
            - HEAD / branch refs / stash / remote-tracking refs changed in a repo the command
              did not visibly run git in (a script committed, reset, switched, pushed)
            - a pre-existing (baseline) user file modified or deleted
          On a violation it blocks (decision "block"), injects a STOP message and LATCHES:
          git-guard.py then denies every non-read-only command in this session.
  --status / --ack   show / clear the latch. --ack is for the user (in their own terminal,
          or `! python3 <this> --ack`); the guard denies it for the agent while latched.

  A latch is also written per WORKSPACE under the persistent state root (lib/fstate.py), so a STOP
  survives a crashed or closed session: the next session starts latched and is told why.

State: per-session scratch in fstate.scratch()/<session>/, the workspace latch in
fstate.persistent()/latch/ - always absolute, never inside a repo.
"""
import hashlib
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "lib"))
import fstate  # noqa: E402
READ_ONLY_PROGS = {"ls", "cat", "head", "tail", "grep", "egrep", "rg", "jq", "wc", "echo", "printf", "pwd", "stat", "file",
                   "which", "type", "diff", "cmp", "sort", "uniq", "cut", "tr", "less", "more", "tree", "du", "df", "date",
                   "basename", "dirname", "realpath", "readlink", "env", "printenv", "true", "false", "test", "[", "sha256sum",
                   "md5sum", "column", "nl", "fold", "id", "whoami", "hostname", "uname", "get-childitem", "get-content",
                   "select-string", "get-location", "test-path", "get-item", "write-output", "write-host", "measure-object",
                   "select-object", "where-object", "sleep", "cd", "pushd", "popd", "set-location", "gci", "gc", "dir"}
READ_ONLY_FACTORY = {"factory-context.sh", "check-registry.sh", "pin-status.py", "pin-plan.py", "wire-parity.sh",
                     "package-ready.py", "install-status.py", "factory-status.py", "tripwire.py", "unity-package-pins.py"}
READ_ONLY_GIT = {"status", "log", "diff", "show", "rev-parse", "ls-files", "ls-remote", "ls-tree", "cat-file", "describe",
                 "blame", "grep", "shortlog", "for-each-ref", "check-ignore", "merge-base", "rev-list", "name-rev",
                 "count-objects", "help", "version", "range-diff", "diff-tree", "whatchanged", "var"}


def guard():
    sys.path.insert(0, HERE)
    import importlib.util
    spec = importlib.util.spec_from_file_location("git_guard", os.path.join(HERE, "git-guard.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def state_dir(payload):
    sid = re.sub(r"[^A-Za-z0-9_.-]", "_", str((payload or {}).get("session_id") or "default"))
    d = os.path.join(fstate.scratch(), sid)
    os.makedirs(d, exist_ok=True)
    return d


def ws_latch_file(ws, create=False):
    d = os.path.join(fstate.persistent(), "latch")
    if create:
        os.makedirs(d, exist_ok=True)
    return os.path.join(d, fstate.workspace_key(ws) + ".json")


def ws_latch(ws):
    try:
        return json.load(open(ws_latch_file(ws), encoding="utf-8")) if ws else None
    except (OSError, json.JSONDecodeError):
        return None


def payload_ws(payload):
    registry = load_registry()
    if not registry:
        return None
    return guard().find_workspace((payload or {}).get("cwd") or os.getcwd(), registry)


def load_registry():
    try:
        return json.load(open(os.path.join(PLUGIN_ROOT, "registry.json"), encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


MODES = ("analyze", "plan", "implement", "validate", "review", "resume")
READ_ONLY_MODES = {"analyze", "plan", "review"}


def record_mode(payload):
    """`factory-context.sh --mode <m>` declares the Factory execution mode for this session (seen by the
    PreToolUse hook, which knows the session id). Returns the mode it recorded, if any."""
    command = (payload.get("tool_input") or {}).get("command") or ""
    if "--mode" not in command:
        return None
    g = guard()
    shell = "powershell" if payload.get("tool_name") == "PowerShell" else "bash"
    for argv in g.expand(command, shell=shell):
        if any(os.path.basename(a) in ("factory-context.sh", "context.py") for a in argv[:3]):
            for i, a in enumerate(argv):
                m = a.split("=", 1)[1] if a.startswith("--mode=") else (argv[i + 1] if a == "--mode" and i + 1 < len(argv) else None)
                if m in MODES:
                    open(os.path.join(state_dir(payload), "MODE"), "w", encoding="utf-8").write(m)
                    return m
    return None


def current_mode(payload):
    return (read(os.path.join(state_dir(payload), "MODE")) or "").strip() or None


def runs_checks(payload):
    command = (payload.get("tool_input") or {}).get("command") or ""
    g = guard()
    argvs = list(g.expand(command, shell="powershell" if payload.get("tool_name") == "PowerShell" else "bash"))
    return bool(argvs) and all(any(os.path.basename(a) in ("run-checks.py", "factory-cmd.py") for a in argv[:3]) or
                               g.prog(argv[0]) in READ_ONLY_PROGS for argv in argvs)


def is_read_only(payload):
    command = (payload.get("tool_input") or {}).get("command") or ""
    if not command.strip():
        return True
    command = re.sub(r"\d*>{1,2}\s*/dev/null|\d*>&\d", " ", command)  # discarding output is not a write
    if re.search(r"(^|[^>])>{1,2}[^>&]|\btee\b|\bsed\b[^|;]*\s-i|\bmv\b|\brm\b|\bcp\b|\btouch\b|\bmkdir\b", command):
        return False
    g = guard()
    shell = "powershell" if payload.get("tool_name") == "PowerShell" else "bash"
    try:
        argvs = list(g.expand(command, shell=shell))
    except Exception:
        return False
    for argv in argvs:
        p = g.prog(argv[0])
        if p in ("git", "git.exe"):
            parsed = g.parse_git(argv)
            if not parsed:
                continue
            _, sub, args, _ = parsed
            if sub in READ_ONLY_GIT:
                continue
            if sub == "branch" and all(a in {"-a", "-r", "-v", "-vv", "--list", "-l", "--show-current", "--all"} for a in args):
                continue
            if sub == "stash" and args[:1] == ["list"]:
                continue
            if sub == "tag" and (not args or set(args) & {"-l", "--list"}):
                continue
            if sub in {"remote", "config", "worktree"} and args[:1] in (["-v"], ["--get"], ["list"], ["get-url"], ["--list"], ["show"]):
                continue
            return False
        if p == "find" and not any(a in {"-exec", "-execdir", "-delete", "-ok", "-okdir"} for a in argv):
            continue
        script = next((a for a in argv[:3] if "/" in a or a.endswith((".py", ".sh"))), "")
        if os.path.basename(script) in READ_ONLY_FACTORY and "--ack" not in argv:
            continue
        if os.path.basename(script) == "factory-cmd.py" and not ("check" in argv and "--status" not in argv):
            continue
        if p not in READ_ONLY_PROGS:
            return False
    return True


def gitdir_of(top):
    g = os.path.join(top, ".git")
    if os.path.isfile(g):
        try:
            line = open(g, encoding="utf-8").read().strip()
            if line.startswith("gitdir:"):
                p = line.split(":", 1)[1].strip()
                return os.path.normpath(os.path.join(top, p))
        except OSError:
            return None
    return g if os.path.isdir(g) else None


def common_dir(gitdir):
    c = os.path.join(gitdir, "commondir")
    if os.path.isfile(c):
        try:
            return os.path.normpath(os.path.join(gitdir, open(c, encoding="utf-8").read().strip()))
        except OSError:
            pass
    return gitdir


def read(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    except OSError:
        return None


def resolve_head(gitdir):
    """Commit a (sub)module HEAD points at, reading loose refs / packed-refs; no subprocess."""
    head = read(os.path.join(gitdir, "HEAD")) or ""
    if not head.startswith("ref:"):
        return head
    ref = head.split(":", 1)[1].strip()
    cd = common_dir(gitdir)
    val = read(os.path.join(cd, ref))
    if val:
        return val
    for line in (read(os.path.join(cd, "packed-refs")) or "").splitlines():
        if line.endswith(" " + ref):
            return line.split(" ", 1)[0]
    return head


def fingerprint(top):
    """{'HEAD': ..., 'refs': {name: value}} from .git files, no subprocess."""
    gd = gitdir_of(top)
    if not gd:
        return None
    cd = common_dir(gd)
    refs = {}
    packed = read(os.path.join(cd, "packed-refs")) or ""
    for line in packed.splitlines():
        if line and not line.startswith(("#", "^")):
            parts = line.split(" ", 1)
            if len(parts) == 2:
                refs[parts[1]] = parts[0]
    base = os.path.join(cd, "refs")
    for root, _dirs, files in os.walk(base):
        for f in files:
            full = os.path.join(root, f)
            name = "refs/" + os.path.relpath(full, base).replace(os.sep, "/")
            refs[name] = read(full)
    return {"HEAD": read(os.path.join(gd, "HEAD")), "refs": refs}


def signature(top):
    """Cheap change detector: mtime/size of HEAD, packed-refs and every refs/ directory.
    Git updates refs by writing <ref>.lock and renaming it, so any ref write moves a directory mtime."""
    gd = gitdir_of(top)
    if not gd:
        return None
    cd = common_dir(gd)
    out = {}
    for p in {os.path.join(gd, "HEAD"), os.path.join(cd, "packed-refs"), os.path.join(cd, "HEAD")}:
        try:
            st = os.stat(p)
            out[p] = [st.st_mtime_ns, st.st_size]
        except OSError:
            out[p] = None
    stack = [os.path.join(cd, "refs")]
    while stack:
        d = stack.pop()
        try:
            out[d] = [os.stat(d).st_mtime_ns]
            with os.scandir(d) as it:
                for e in it:
                    if e.is_dir(follow_symlinks=False):
                        stack.append(e.path)
        except OSError:
            pass
    return out


def cached_fingerprint(sd, top, sig):
    """Full fingerprint, re-read only when the cheap signature changed since the last read."""
    cf = os.path.join(sd, "fpcache.json")
    cache = json.load(open(cf, encoding="utf-8")) if os.path.exists(cf) else {}
    hit = cache.get(top)
    if hit and hit.get("sig") == sig:
        return hit["fp"]
    fp = fingerprint(top)
    cache[top] = {"sig": sig, "fp": fp}
    json.dump(cache, open(cf, "w", encoding="utf-8"))
    return fp


def repos(payload, registry):
    g = guard()
    cwd = payload.get("cwd") or os.getcwd()
    ws = g.find_workspace(cwd, registry)
    if not ws:
        return None, {}
    tops = {}
    for key, r in registry.get("repos", {}).items():
        p = os.path.join(ws, r["path"])
        if os.path.exists(os.path.join(p, ".git")):
            tops[os.path.abspath(p)] = key
        for c in r.get("embedded_clones", []):  # user state inside the repo: fingerprint + baseline them too
            cp = os.path.join(p, c["path"])
            if os.path.exists(os.path.join(cp, ".git")):
                tops[os.path.abspath(cp)] = f"clone:{c['of']}@{key}/{c['path']}"
    # the worktree the command runs in, if it is not one of the main checkouts
    top = g.git_out(cwd, "rev-parse", "--show-toplevel") if os.path.isdir(cwd) else ""
    if top and os.path.abspath(top) not in tops and os.path.abspath(top).startswith(ws):
        tops[os.path.abspath(top)] = "worktree:" + os.path.relpath(top, ws)
    return ws, tops


def slow_git(cwd, *args, timeout=50):
    import subprocess
    try:
        r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def porcelain(cwd, *extra):
    """[(status, path)] from `git status --porcelain=v1 -z` - NUL-separated, so paths with spaces, quotes
    or non-ASCII characters stay exact and the first entry keeps its leading status space."""
    parts = slow_git(cwd, "status", "--porcelain=v1", "-z", *extra).split("\0")
    out, i = [], 0
    while i < len(parts):
        e = parts[i]
        if len(e) > 3:
            out.append((e[:2], e[3:]))
            i += 2 if e[0] in "RC" else 1  # rename/copy entries carry the original path next
        else:
            i += 1
    return out


def baseline(sd, tops):
    """Once per session: the user's pre-existing dirty files and their stats."""
    bf = os.path.join(sd, "baseline.json")
    if os.path.exists(bf):
        return json.load(open(bf, encoding="utf-8"))
    g = guard()
    data = {}
    for top in tops:
        if str(tops[top]).startswith("clone:"):
            # embedded clone (user state, often hundreds of dirty files): a spread sample only, compared
            # pre/post each command so the user's own concurrent edits in Unity are not flagged
            dirty = [p for _, p in porcelain(top)]
            step = max(1, len(dirty) // 24)
            data[top] = {"": ["clone-dirty", resolve_head(gitdir_of(top)) if gitdir_of(top) else "", len(dirty),
                              [r for r in dirty[::step][:24] if os.path.isfile(os.path.join(top, r))]]}
            continue
        # --ignore-submodules=all: the client's submodule scan alone costs ~10 s on /mnt/c;
        # submodule pointers are compared separately (gitlink in the index vs the submodule HEAD).
        entries = {}
        for _st, path in porcelain(top, "--untracked-files=normal", "--ignore-submodules=all"):
            full = os.path.join(top, path)
            st = os.stat(full) if os.path.exists(full) else None
            entries[path] = [st.st_mtime_ns, st.st_size] if st and os.path.isfile(full) else ("dir" if st else None)
        for line in g.git_out(top, "ls-files", "-s").splitlines():
            if line.startswith("160000 "):
                sha, path = line.split()[1], line.split("\t", 1)[1]
                sgd = gitdir_of(os.path.join(top, path))
                head = resolve_head(sgd) if sgd else ""
                if head and head != sha:
                    entries[path] = ["submodule", head]
                elif sgd:
                    # uncommitted work *inside* the submodule (the client's com.gdk.* hold ~1.9k files):
                    # remember its index stat + a spread sample of dirty files; a reset/checkout rewrites them
                    dirty = [p for _, p in porcelain(os.path.join(top, path))]
                    if dirty:
                        step = max(1, len(dirty) // 24)
                        sample = {}
                        for rel in dirty[::step][:24]:
                            f = os.path.join(top, path, rel)
                            if os.path.isfile(f):
                                st = os.stat(f)
                                sample[rel] = [st.st_mtime_ns, st.st_size]
                        entries[path] = ["submodule-dirty", head, len(dirty), sample]
        data[top] = entries
    json.dump(data, open(bf, "w", encoding="utf-8"))
    return data


def clone_stats(base):
    out = {}
    for top, entries in (base or {}).items():
        e = entries.get("")
        if isinstance(e, list) and e[:1] == ["clone-dirty"]:
            out[top] = {r: ([os.stat(os.path.join(top, r)).st_mtime_ns, os.stat(os.path.join(top, r)).st_size]
                            if os.path.isfile(os.path.join(top, r)) else None) for r in e[3]}
    return out


def expected_repos(payload, registry, ws):
    """Repos the command's visible git invocations may change, with their subcommands."""
    g = guard()
    command = (payload.get("tool_input") or {}).get("command") or ""
    shell = "powershell" if payload.get("tool_name") == "PowerShell" else "bash"
    cwd = payload.get("cwd") or os.getcwd()
    exp = {}
    for argv in g.expand(command, shell=shell):
        p = g.prog(argv[0])
        if p in g.CD_WORDS:
            t = next((x for x in argv[1:] if not x.startswith("-")), None)
            if t:
                cwd = os.path.normpath(os.path.join(cwd, os.path.expanduser(t.replace("\\", "/"))))
            continue
        parsed = g.parse_git(argv)
        if not parsed:
            continue
        cdir, sub, _args, _cfg = parsed
        eff = os.path.normpath(os.path.join(cwd, cdir)) if cdir else cwd
        top = g.git_out(eff, "rev-parse", "--show-toplevel")
        if top:
            for t in {os.path.abspath(top), os.path.abspath(g.main_checkout(top))}:
                exp.setdefault(t, set()).add(sub)
    return {k: sorted(v) for k, v in exp.items()}


def latched(payload):
    lf = os.path.join(state_dir(payload), "LATCH")
    here = read(lf)
    if here:
        return here
    wl = ws_latch(payload_ws(payload))
    if wl:
        return (f"{wl.get('message')} (detected {wl.get('at')} in session {wl.get('session')} - "
                "unresolved from an earlier session)")
    return None


def pre(payload):
    if is_read_only(payload):
        return 0
    registry = load_registry()
    if not registry:
        return 0
    ws, tops = repos(payload, registry)
    if not ws:
        return 0
    sd = state_dir(payload)
    t0 = time.perf_counter()
    baseline(sd, tops)
    sigs = {t: signature(t) for t in tops}
    snap = {"cmd": (payload.get("tool_input") or {}).get("command"), "tops": tops, "sig": sigs,
            "fp": {t: cached_fingerprint(sd, t, sigs[t]) for t in tops},
            "expected": expected_repos(payload, registry, ws),
            "clones": clone_stats(baseline(sd, tops)),
            "ms": round((time.perf_counter() - t0) * 1000, 1)}
    json.dump(snap, open(os.path.join(sd, "pre.json"), "w", encoding="utf-8"))
    return 0


def diff(top, key, a, b, expected_subs, protected):
    v = []
    if not a or not b:
        return v
    ra, rb = a["refs"], b["refs"]
    names = set(ra) | set(rb)
    changed = sorted(n for n in names if ra.get(n) != rb.get(n))
    git_seen = bool(expected_subs)
    for n in changed:
        what = "created" if n not in ra else "deleted" if n not in rb else "moved"
        if n.startswith("refs/tags/"):
            v.append(f"[{key}] tag {n[10:]} {what} (agents never tag)")
        elif not git_seen and n.startswith("refs/heads/"):
            br = n[11:]
            v.append(f"[{key}] branch {br} {what} by a command that did not visibly run git here"
                     + (" (PROTECTED branch)" if protected(br) else ""))
        elif not git_seen and n.startswith("refs/remotes/"):
            v.append(f"[{key}] remote-tracking ref {n[13:]} {what} outside git (a push or fetch by a script)")
        elif not git_seen and n == "refs/stash":
            v.append(f"[{key}] stash {what} outside git (user changes moved)")
    if a["HEAD"] != b["HEAD"] and not git_seen:
        v.append(f"[{key}] HEAD changed from {a['HEAD']} to {b['HEAD']} by a command that did not visibly run git here")
    return v


def post(payload):
    sd = state_dir(payload)
    pf = os.path.join(sd, "pre.json")
    if not os.path.exists(pf):
        return 0
    snap = json.load(open(pf, encoding="utf-8"))
    os.remove(pf)
    registry = load_registry() or {}
    g = guard()
    base = json.load(open(os.path.join(sd, "baseline.json"), encoding="utf-8")) if os.path.exists(os.path.join(sd, "baseline.json")) else {}
    violations = []
    ws = g.find_workspace(payload.get("cwd") or os.getcwd(), registry) if registry else None
    for top, key in snap["tops"].items():
        exp = snap["expected"].get(top, [])
        sig = signature(top)
        if sig != snap.get("sig", {}).get(top):   # cheap-first: only re-read refs when something moved
            pats = g.protected_patterns(top, ws, registry) if ws and registry else g.DEFAULT_PROTECTED
            violations += diff(top, key, snap["fp"].get(top), cached_fingerprint(sd, top, sig), exp,
                               lambda br, p=pats: g.is_protected(br, p))
        git_restore = set(exp) & {"checkout", "restore", "reset", "stash", "clean", "switch", "merge", "rebase", "pull", "cherry-pick", "revert"}
        if top in snap.get("clones", {}):
            if top not in snap["expected"]:
                now = clone_stats({top: base.get(top) or {}}).get(top, {})
                changed = [r for r, v in snap["clones"][top].items() if now.get(r) != v]
                if changed:
                    violations.append(f"[{key}] the user's uncommitted work inside embedded clone {os.path.relpath(top, ws) if ws else top} "
                                      f"changed during this command ({len(changed)} of {len(now)} sampled files, e.g. {changed[0]})")
            continue
        for path, st in (base.get(top) or {}).items():
            full = os.path.join(top, path)
            if st is None or st == "dir":
                continue
            if isinstance(st, list) and st[:1] == ["submodule-dirty"]:
                if full in snap["expected"] or git_restore:
                    continue
                changed = [rel for rel, v in st[3].items()
                           if not os.path.isfile(os.path.join(full, rel))
                           or [os.stat(os.path.join(full, rel)).st_mtime_ns, os.stat(os.path.join(full, rel)).st_size] != v]
                if changed:
                    violations.append(f"[{key}] user's uncommitted work inside submodule {path} changed "
                                      f"({len(changed)} of {len(st[3])} sampled files, e.g. {changed[0]}) - "
                                      f"{st[2]} dirty files may have been reset")
                continue
            if isinstance(st, list) and st[:1] == ["submodule"]:
                sgd = gitdir_of(full)
                head = resolve_head(sgd) if sgd else ""
                if head and head != st[1] and not git_restore and "submodule" not in exp:
                    violations.append(f"[{key}] user's submodule {path} moved from {st[1][:10]} to {head[:10]}")
                continue
            now = os.stat(full) if os.path.isfile(full) else None
            if (now is None or [now.st_mtime_ns, now.st_size] != st) and not git_restore:
                violations.append(f"[{key}] pre-existing user file {path} was " + ("deleted" if now is None else "modified"))
    if not violations:
        return 0
    msg = "; ".join(violations)
    open(os.path.join(sd, "LATCH"), "w", encoding="utf-8").write(msg)
    if ws:
        json.dump({"workspace": ws, "session": payload.get("session_id"), "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                   "message": msg}, open(ws_latch_file(ws, create=True), "w", encoding="utf-8"))
    stop = ("STOP - rpg-factory tripwire: repository state changed outside the git guard: " + msg +
            ". Do not continue, do not try to repair or normalise this state. Report exactly what happened to the user. "
            "Further mutating commands are denied until the user runs: python3 " + os.path.join(PLUGIN_ROOT, "scripts", "tripwire.py") + " --ack")
    print(json.dumps({"decision": "block", "reason": stop,
                      "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": stop}}))
    return 0


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--status"
    if os.environ.get("RPG_FACTORY_GUARD", "").lower() in {"off", "0", "false"} and mode in {"--pre", "--post"}:
        return 0
    if mode == "--session-start":
        try:
            payload = json.load(sys.stdin)
            registry = load_registry()
            ws, tops = repos(payload, registry) if registry else (None, {})
            if ws:
                baseline(state_dir(payload), tops)
                wl = ws_latch(ws)
                if wl:
                    msg = (f"rpg-factory tripwire: an earlier session ({wl.get('session')}, {wl.get('at')}) hit a STOP that "
                           f"was never cleared: {wl.get('message')}. Mutating commands stay denied. Tell the user; after "
                           f"reviewing the repos they clear it with: ! python3 {os.path.join(PLUGIN_ROOT, 'scripts', 'tripwire.py')} --ack")
                    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": msg}}))
        except Exception:
            pass
        return 0
    if mode in {"--pre", "--post"}:
        try:
            payload = json.load(sys.stdin)
        except (json.JSONDecodeError, ValueError):
            return 0
        if payload.get("tool_name") not in (None, "Bash", "PowerShell"):
            return 0
        try:
            return pre(payload) if mode == "--pre" else post(payload)
        except Exception:
            return 0  # the tripwire must never break the session
    sid = sys.argv[2] if len(sys.argv) > 2 else None
    root = fstate.scratch()
    sessions = [sid] if sid else (sorted(os.listdir(root)) if os.path.isdir(root) else [])
    found = False
    for s in sessions:
        lf = os.path.join(root, s, "LATCH")
        if os.path.exists(lf):
            found = True
            print(f"session {s}: LATCHED - {read(lf)}")
            if mode == "--ack":
                os.remove(lf)
                bf = os.path.join(root, s, "baseline.json")
                if os.path.exists(bf):
                    # the reviewed state becomes the new baseline - rebuilt now, so file tools and the
                    # next command are protected immediately (not only after the next shell command)
                    try:
                        old = json.load(open(bf, encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        old = {}
                    os.remove(bf)
                    tops = {t: ("clone:" if "" in e else "repo") for t, e in old.items() if os.path.isdir(t)}
                    if tops:
                        baseline(os.path.join(root, s), tops)
                print(f"session {s}: latch cleared by the user")
    ldir = os.path.join(fstate.persistent(), "latch")
    for f in sorted(os.listdir(ldir)) if os.path.isdir(ldir) else []:
        p = os.path.join(ldir, f)
        try:
            wl = json.load(open(p, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            wl = {}
        if sid and wl.get("session") != sid:
            continue
        found = True
        print(f"workspace {wl.get('workspace')}: LATCHED since {wl.get('at')} (session {wl.get('session')}) - {wl.get('message')}")
        if mode == "--ack":
            os.remove(p)
            print(f"workspace {wl.get('workspace')}: latch cleared by the user")
    if not found:
        print("no latched session or workspace")
    return 0


if __name__ == "__main__":
    sys.exit(main())
