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
  --status [id]      show open events (id, repo, command, ref values, recovery hints) and the ack command.
  --ack [id ...]     archive open events - all open at that moment, or the given event / session ids -
          then re-read and report CLEAR (exit 0) or still LATCHED / NOT cleared (exit 1; 2 = bad usage).
          For the user only (their terminal, or `! <ack command>`); the guard denies it to the agent.

Snapshot identity: --pre writes pre-<tool_use_id>.json and --post reads only its own call's snapshot.
A denied call (PreToolUse ran, PostToolUse never does) leaves a snapshot nobody consumes; it is
pruned after SNAP_TTL. Up to 0.5.0 one pre.json per session was consumed by whichever --post came
next, so a read-only command inherited a stale snapshot and was blamed for other sessions' git work.

Every incident is an EVENT file per WORKSPACE under the persistent state root (lib/fstate.py), never
overwritten and archived (not deleted) on ack, so a STOP survives a crashed or closed session and one
session's incident cannot erase another's. Git that another session's guard visibly ran (completed
commands in activity/) explains ref changes in that repo the same way the command's own git does;
tags are never explained.

State: per-session scratch in fstate.scratch()/<session>/, events, audit and activity in
fstate.persistent() - always absolute, never inside a repo.
"""
import hashlib
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(HERE)
sys.path.append(os.path.join(HERE, "lib"))  # appended: stdlib lookups must not stat /mnt/c first
import fstate  # noqa: E402


def pmap(fn, items):
    """Stat-heavy work over independent repos: /mnt/c (9p) latency dominates, so run it in threads."""
    items = list(items)
    if len(items) < 2:
        return [fn(i) for i in items]
    from concurrent.futures import ThreadPoolExecutor  # lazy: read-only hook calls never need it
    with ThreadPoolExecutor(max_workers=min(8, len(items))) as ex:
        return list(ex.map(fn, items))
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


_GUARD = None
_REGISTRY = None


def guard():
    """git-guard.py as a module - once per process (reused when git-guard.py itself is running)."""
    global _GUARD
    if _GUARD is not None:
        return _GUARD
    main = sys.modules.get("__main__")
    if main is not None and hasattr(main, "classify_gh") and hasattr(main, "find_workspace"):
        _GUARD = main
        return main
    sys.path.append(HERE)  # appended: stdlib lookups must not stat /mnt/c first
    import importlib.util
    spec = importlib.util.spec_from_file_location("git_guard", os.path.join(HERE, "git-guard.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _GUARD = mod
    return mod


def state_dir(payload):
    sid = re.sub(r"[^A-Za-z0-9_.-]", "_", str((payload or {}).get("session_id") or "default"))
    d = os.path.join(fstate.scratch(), sid)
    os.makedirs(d, exist_ok=True)
    return d


SNAP_TTL = 2 * 3600          # an unconsumed snapshot (denied / aborted call) is removed after this
ACTIVITY_TTL = 2 * 3600      # completed visible-git commands kept for cross-session attribution
ACKED_KEEP = 30 * 86400      # archived (acknowledged) events kept this long


def ack_command():
    return fstate.ack_command(PLUGIN_ROOT)


def call_key(payload):
    """Identity of one tool call: Claude Code's tool_use_id (shared by its PreToolUse and PostToolUse)."""
    tid = (payload or {}).get("tool_use_id")
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(tid))[:128] if tid else ""


def snap_file(sd, payload):
    key = call_key(payload)
    if not key:  # no tool_use_id: one snapshot per distinct command, so parallel calls do not share a file
        cmd = str(((payload or {}).get("tool_input") or {}).get("command") or "")
        key = "nokey-" + hashlib.sha1(cmd.encode("utf-8", "replace")).hexdigest()[:12]
    return os.path.join(sd, "pre-" + key + ".json")


def prune(d, prefix, ttl, suffix=".json"):
    cutoff = time.time() - ttl
    try:
        with os.scandir(d) as it:
            for e in it:
                if e.name.startswith(prefix) and e.name.endswith(suffix) and e.stat().st_mtime < cutoff:
                    try:
                        os.remove(e.path)
                    except OSError:
                        pass
    except OSError:
        pass


def new_event_id():
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + os.urandom(3).hex()


def load_json(p):
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def open_events(ws=None):
    """Open events, oldest first: [{"id", "key", "path", "legacy", "data"}]. data is None when the file is
    unreadable - it still counts as open (fail safe). All workspaces when ws is None."""
    root = fstate.latch_root()
    if ws:
        keys = [fstate.workspace_key(ws)]
    else:
        try:
            keys = sorted({n[:-5] if n.endswith(".json") else n for n in os.listdir(root)})
        except OSError:
            keys = []
    out = []
    for k in keys:
        lf = fstate.legacy_latch_file(key=k)
        if os.path.isfile(lf):
            out.append({"id": "legacy-" + k, "key": k, "path": lf, "legacy": True, "data": load_json(lf)})
        d = fstate.latch_dir(key=k)
        try:
            names = sorted(n for n in os.listdir(d) if n.endswith(".json") and os.path.isfile(os.path.join(d, n)))
        except OSError:
            names = []
        for n in names:
            out.append({"id": n[:-5], "key": k, "path": os.path.join(d, n), "legacy": False,
                        "data": load_json(os.path.join(d, n))})
    return out


def event_line(e):
    d = e["data"]
    if not isinstance(d, dict):
        return f"event {e['id']}: UNREADABLE event file {e['path']} (still open; inspect it, then ack it by id)"
    return (f"event {e['id']}{' (legacy latch)' if e['legacy'] else ''}: {d.get('message')} "
            f"[workspace {d.get('workspace')}, session {d.get('session')}, at {d.get('at')}]")


def session_latch(sd):
    """(message, event id or None) of a session LATCH file, or None. Files from 0.5.0 and earlier are plain text."""
    raw = read(os.path.join(sd, "LATCH"))
    if not raw:
        return None
    if raw.startswith("{"):
        try:
            d = json.loads(raw)
            return d.get("message") or raw, d.get("event")
        except ValueError:
            pass
    return raw, None


def payload_ws(payload):
    registry = load_registry()
    if not registry:
        return None
    return guard().find_workspace((payload or {}).get("cwd") or os.getcwd(), registry)


def load_registry():
    global _REGISTRY
    if _REGISTRY is None:
        try:
            _REGISTRY = json.load(open(os.path.join(PLUGIN_ROOT, "registry.json"), encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
    return _REGISTRY


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


MODE_PHRASES = [  # explicit phrases only - an unqualified request is not a mode declaration
    (r"\bmode\s*[:=]?\s*(analy[sz]e|plan|implement|validate|review|resume)\b", None),
    (r"\b(analy[sz]e|analysis)[- ]only\b|\bonly analy[sz]e\b", "analyze"),
    (r"\bplan(ning)?[- ]only\b|\bonly plan\b|\bjust (a )?plan\b|\bdo not implement\b|\bdon'?t implement\b", "plan"),
    (r"\bvalidat(e|ion)[- ]only\b|\bonly validate\b", "validate"),
    (r"\breview[- ]only\b|\bonly review\b", "review"),
]


def mode_from_text(text):
    t = (text or "").lower()
    for pat, mode in MODE_PHRASES:
        m = re.search(pat, t)
        if m:
            got = mode or m.group(1)
            return "analyze" if got.startswith("analy") else got
    return None


def skill_hook(payload):
    """PreToolUse(Skill): when a Factory skill is invoked with an explicit mode in its arguments ("plan only",
    "mode: validate"), record it - so the mode holds even if the model never runs the Route command."""
    ti = payload.get("tool_input") or {}
    if not str(ti.get("skill", "")).startswith("rpg-factory:"):
        return 0
    m = mode_from_text(ti.get("args"))
    if m in MODES:
        open(os.path.join(state_dir(payload), "MODE"), "w", encoding="utf-8").write(m)
    return 0


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
            branch_flags = {"-a", "-r", "-v", "-vv", "--list", "-l", "--show-current", "--all"}
            if sub == "branch" and all(a in branch_flags for a in args):
                continue
            if sub == "branch" and {"--list", "-l"} & set(args) and all(a in branch_flags or not a.startswith("-") for a in args):
                continue  # `git branch --list 'backup/*'`: a pattern after --list only filters
            if sub == "stash" and args[:1] in (["list"], ["show"]):
                continue
            if sub == "reflog" and not {"expire", "delete", "drop", "write"} & set(args):
                continue  # show / list / exists / <ref>; expire, delete, drop and write rewrite reflogs  # inspecting reflogs is how a latch is investigated; expire/delete are not read-only
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
    cache = load_json(cf) or {}
    hit = cache.get(top)
    if hit and hit.get("sig") == sig:
        return hit["fp"]
    fp = fingerprint(top)
    cache[top] = {"sig": sig, "fp": fp}
    try:
        fstate.write_json(cf, cache)  # atomic: parallel calls of one session share this cache
    except OSError:
        pass  # only a cache: a lost write costs speed, never the comparison
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
    def one(top):
        if str(tops[top]).startswith("clone:"):
            # embedded clone (user state, often hundreds of dirty files): a spread sample only, compared
            # pre/post each command so the user's own concurrent edits in Unity are not flagged
            dirty = [p for _, p in porcelain(top)]
            step = max(1, len(dirty) // 24)
            return {"": ["clone-dirty", resolve_head(gitdir_of(top)) if gitdir_of(top) else "", len(dirty),
                              [r for r in dirty[::step][:24] if os.path.isfile(os.path.join(top, r))]]}
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
        return entries

    data = dict(zip(tops, pmap(one, list(tops))))  # independent repos: scan in parallel
    fstate.write_json(bf, data)
    return data


def _stat_or_none(p):
    try:
        st = os.stat(p)
        return [st.st_mtime_ns, st.st_size]
    except OSError:
        return None


def clone_stats(base):
    jobs = []
    for top, entries in (base or {}).items():
        e = entries.get("")
        if isinstance(e, list) and e[:1] == ["clone-dirty"]:
            jobs += [(top, r) for r in e[3]]
    vals = pmap(lambda j: _stat_or_none(os.path.join(*j)), jobs)
    out = {}
    for (top, r), v in zip(jobs, vals):
        out.setdefault(top, {})[r] = v
    for top, entries in (base or {}).items():  # clones with no dirty files still get an (empty) entry
        e = entries.get("")
        if isinstance(e, list) and e[:1] == ["clone-dirty"]:
            out.setdefault(top, {})
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
    """Why this call is latched, or None: this session's LATCH, else any open event of the workspace
    (the latch is global per workspace - a STOP from any session or worktree blocks every session)."""
    here = session_latch(state_dir(payload))
    if here:
        return here[0] + (f" (event {here[1]})" if here[1] else "")
    ws = payload_ws(payload)
    evs = open_events(ws) if ws else []
    if not evs:
        return None
    e = evs[0]
    d = e["data"] if isinstance(e["data"], dict) else {}
    more = f"; {len(evs) - 1} more open event(s)" if len(evs) > 1 else ""
    return (f"{d.get('message') or 'unreadable event file'} (event {e['id']}, detected {d.get('at')} in session "
            f"{d.get('session')}{more} - see `tripwire.py --status`)")


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
    prune(sd, "pre-", SNAP_TTL)  # snapshots of denied / aborted calls: never consumed, never reused
    baseline(sd, tops)
    sigs = dict(zip(tops, pmap(signature, tops)))
    snap = {"cmd": (payload.get("tool_input") or {}).get("command"), "call": call_key(payload),
            "at": time.time(), "tops": tops, "sig": sigs,
            "fp": {t: cached_fingerprint(sd, t, sigs[t]) for t in tops},
            "expected": expected_repos(payload, registry, ws),
            "clones": clone_stats(baseline(sd, tops)),
            "ms": round((time.perf_counter() - t0) * 1000, 1)}
    fstate.write_json(snap_file(sd, payload), snap)
    return 0


def take_snapshot(sd, payload):
    """This call's own snapshot, removed as it is read. None when there is none - a read-only call
    (--pre skipped it) or an unmatched call - so nothing is compared and nothing is blamed."""
    pf = snap_file(sd, payload)
    snap = load_json(pf)
    try:
        os.remove(pf)
    except OSError:
        pass
    if not isinstance(snap, dict):
        return None
    if snap.get("call", "") != call_key(payload):
        return None
    if not call_key(payload):
        # no tool_use_id (older Claude Code, manual runs): the snapshot must be for this very command and
        # recent - a denied call with another command never explains this one's window
        if snap.get("cmd") != (payload.get("tool_input") or {}).get("command") or time.time() - snap.get("at", 0) > SNAP_TTL:
            return None
    return snap


def repo_key(top):
    """Refs live in the common git dir: a worktree and its main checkout share them."""
    gd = gitdir_of(top)
    return os.path.normcase(os.path.abspath(common_dir(gd))) if gd else os.path.normcase(os.path.abspath(top))


def other_git(ws, payload, since):
    """{repo_key: {ref: {new values}}} that OTHER completed calls (other sessions, or parallel calls of this one)
    saw change while their own visible git ran in that repo, since `since`. A ref change here is explained only
    when the same ref reached the same value there - never by a read-only git command, never a tag, never a
    different ref (a script resetting `develop` is not explained by someone's `git commit` on a feature branch)."""
    out = {}
    if not ws:
        return out
    me = state_key(payload)
    d = fstate.activity_dir(ws)
    try:
        names = os.listdir(d)
    except OSError:
        return out
    now = time.time()
    for n in names:
        if not n.endswith(".json") or n[:-5] == me:
            continue
        rec = load_json(os.path.join(d, n))
        if not isinstance(rec, dict) or rec.get("end", 0) < since or rec.get("start", now + 1) > now:
            continue
        for rk, refs in (rec.get("explained") or {}).items():
            for ref, new in (refs or {}).items():
                out.setdefault(rk, {}).setdefault(ref, set()).add(new)
    return out


def state_key(payload):
    sid = re.sub(r"[^A-Za-z0-9_.-]", "_", str((payload or {}).get("session_id") or "default"))
    return sid + "--" + (call_key(payload) or "nokey")


def record_activity(ws, payload, snap, explained):
    """A completed call whose visible git changed refs: lets concurrent calls attribute exactly those changes."""
    if not ws or not explained:
        return
    d = fstate.activity_dir(ws)
    prune(d, "", ACTIVITY_TTL)
    fstate.write_json(os.path.join(d, state_key(payload) + ".json"),
                      {"session": payload.get("session_id"), "call": call_key(payload), "start": snap.get("at", 0),
                       "end": time.time(), "command": (payload.get("tool_input") or {}).get("command"),
                       "explained": explained})


BRANCH_MOVERS = {"commit", "merge", "reset", "rebase", "cherry-pick", "revert", "pull", "am", "stash"}
BRANCH_MAKERS = {"branch", "switch", "checkout", "worktree"}
REMOTE_WRITERS = {"fetch", "pull", "push", "remote"}
HEAD_WRITERS = {"switch", "checkout", "rebase", "bisect", "worktree", "merge", "pull"}


def can_explain(subs, ref, old, new, current):
    """Could git subcommands `subs` (run visibly by a call) have made this ref change? `current` = the branch
    refs that call's checkout pointed at. Only these changes are offered to concurrent calls as explained -
    a `git log`, or a `git switch -c feature`, never explains a hidden reset of `develop`."""
    subs = set(subs)
    if ref.startswith("refs/tags/"):
        return False
    if ref == "refs/stash":
        return "stash" in subs
    if ref.startswith("refs/remotes/"):
        return bool(subs & REMOTE_WRITERS)
    if ref == "HEAD":
        return bool(subs & HEAD_WRITERS)
    if ref.startswith("refs/heads/"):
        if old is None:                       # created
            return bool(subs & BRANCH_MAKERS)
        if new is None:                       # deleted
            return "branch" in subs
        return bool(subs & BRANCH_MOVERS) and ref in current   # moved: only the branch that call had checked out
    return False


def excuse(before, after, theirs, top):
    """`before` with every ref change another call explained (same ref, same new value) taken out."""
    if not before or not after or not theirs:
        return before
    ra, rb = dict(before["refs"]), after["refs"]
    for n in set(ra) | set(rb):
        if n.startswith("refs/tags/") or ra.get(n) == rb.get(n):
            continue
        if rb.get(n) in theirs.get(n, ()):
            if n in rb:
                ra[n] = rb[n]
            else:
                ra.pop(n, None)
    head = before.get("HEAD")
    if head != after.get("HEAD") and after.get("HEAD") in theirs.get("HEAD@" + top, ()):
        head = after.get("HEAD")
    return {"HEAD": head, "refs": ra}


def changed_refs(a, b):
    """{ref: [old, new]} for every ref (and HEAD) that differs - None means absent."""
    if not a or not b:
        return {}
    ra, rb = a["refs"], b["refs"]
    out = {n: [ra.get(n), rb.get(n)] for n in sorted(set(ra) | set(rb)) if ra.get(n) != rb.get(n)}
    if a.get("HEAD") != b.get("HEAD"):
        out["HEAD"] = [a.get("HEAD"), b.get("HEAD")]
    return out


def recovery_hints(top, refs):
    """Read-only first steps per changed ref; restoring is the user's decision. Old SHAs stay reachable
    (reflog, unreachable objects) until git gc - pin one with a branch before anything else."""
    q = '"' + top.replace("\\", "/") + '"'
    hints = []
    for n, (old, new) in refs.items():
        if n == "refs/stash":
            if old:
                hints.append(f"stash {old[:12]} left refs/stash: inspect `git -C {q} stash show -p {old}`; keep it with "
                             f"`git -C {q} branch rescue/stash-{old[:8]} {old}`; restore only after review with "
                             f"`git -C {q} stash apply {old}`")
            if new:
                hints.append(f"new stash {new[:12]} (not necessarily this session's): inspect `git -C {q} stash list` and "
                             f"`git -C {q} stash show -p {new}`; never drop it; restore after review with "
                             f"`git -C {q} stash apply {new}`")
        elif n.startswith("refs/tags/"):
            hints.append(f"tag {n[10:]} {'-> ' + new[:12] if new else 'deleted (was ' + str(old)[:12] + ')'}: "
                         f"agents never tag - leave it for the user")
        elif n == "HEAD":
            hints.append(f"HEAD changed: inspect `git -C {q} reflog -10`")
        elif old:
            hints.append(f"{n} was {old[:12]}: inspect `git -C {q} reflog show {n}`; the old commit is "
                         f"reachable as {old}")
    return hints


def diff(top, key, a, b, expected_subs, protected, refs_too=True):
    v = []
    if not a or not b:
        return v
    ra, rb = a["refs"], b["refs"]
    names = (set(ra) | set(rb)) if refs_too else set()
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


def audit_stash(ws, payload, top, key, refs):
    """The approved path: a `git stash` the guard saw. Recorded (append-only), never latched."""
    if not ws or "refs/stash" not in refs:
        return
    p = fstate.audit_file(ws)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    old, new = refs["refs/stash"]
    line = json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "session": payload.get("session_id"),
                       "tool_use_id": payload.get("tool_use_id"), "repo": key, "repo_top": top,
                       "command": (payload.get("tool_input") or {}).get("command"), "stash_before": old, "stash_after": new})
    with open(p, "a", encoding="utf-8") as fh:  # one short line per write: O_APPEND keeps lines whole
        fh.write(line + "\n")


def post(payload):
    sd = state_dir(payload)
    snap = take_snapshot(sd, payload)
    if not snap:
        return 0
    registry = load_registry() or {}
    g = guard()
    base = load_json(os.path.join(sd, "baseline.json")) or {}
    violations = []
    ws = g.find_workspace(payload.get("cwd") or os.getcwd(), registry) if registry else None
    try:
        others = other_git(ws, payload, snap.get("at", 0))
    except Exception:
        others = {}  # cannot read the activity log: explain nothing (fail closed)
    now_sigs = dict(zip(snap["tops"], pmap(signature, snap["tops"])))
    repos_hit, refs_hit, audited, explained, ref_diffed = {}, {}, set(), {}, set()
    # a worktree the command runs in first: its refs are shared with the main checkout, report them once there
    order = sorted(snap["tops"].items(), key=lambda kv: not str(kv[1]).startswith("worktree:"))
    for top, key in order:
        exp = snap["expected"].get(top, [])
        sig = now_sigs[top]
        if sig != snap.get("sig", {}).get(top):   # cheap-first: only re-read refs when something moved
            pats = g.protected_patterns(top, ws, registry) if ws and registry else g.DEFAULT_PROTECTED
            before, after = snap["fp"].get(top), cached_fingerprint(sd, top, sig)
            refs = changed_refs(before, after)
            rk = repo_key(top)
            if exp and refs:  # this call's own visible git: what it could have changed, for concurrent calls
                current = {h.split(":", 1)[1].strip() for h in ((before or {}).get("HEAD"), (after or {}).get("HEAD"))
                           if isinstance(h, str) and h.startswith("ref:")}
                for n, (old, new) in refs.items():
                    if can_explain(exp, n, old, new, current):
                        explained.setdefault(rk, {})["HEAD@" + top if n == "HEAD" else n] = new
            if "stash" in exp and "refs/stash" in refs and tuple(refs["refs/stash"]) not in audited:
                audited.add(tuple(refs["refs/stash"]))  # a worktree and its main checkout share refs/stash
                audit_stash(ws, payload, top, key, refs)
            v = diff(top, key, excuse(before, after, others.get(rk), top), after, exp,
                     lambda br, p=pats: g.is_protected(br, p), refs_too=rk not in ref_diffed)
            ref_diffed.add(rk)
            if v:
                violations += v
                repos_hit[top], refs_hit[top] = key, refs
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
    try:
        record_activity(ws, payload, snap, explained)
    except Exception:
        pass  # attribution help for other calls only; never costs this call its check
    if not violations:
        return 0
    msg = "; ".join(violations)
    eid = new_event_id()
    if ws:
        recovery = [h for top, refs in refs_hit.items() for h in recovery_hints(top, refs)]
        if any("user file" in v or "uncommitted work" in v for v in violations):
            recovery.append("user files changed: compare with `git status` / `git diff` and the editor's local history; "
                            "do not reset or check out anything to 'fix' it")
        fstate.write_json(os.path.join(fstate.latch_dir(ws), eid + ".json"), {
            "id": eid, "workspace": ws, "session": payload.get("session_id"), "tool_use_id": payload.get("tool_use_id"),
            "command": (payload.get("tool_input") or {}).get("command"), "cwd": payload.get("cwd"),
            "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "window_start": snap.get("at"),
            "repos": repos_hit, "violations": violations, "refs": refs_hit, "recovery": recovery, "message": msg,
            "note": "changes are those seen during this command's window; another session, a background job or the "
                    "user may have made them - check before assuming this command did"})
    fstate.write_json(os.path.join(sd, "LATCH"), {"event": eid if ws else None, "message": msg})
    stop = ("STOP - rpg-factory tripwire: repository state changed outside the git guard while this command ran"
            f" (event {eid}): " + msg +
            ". It may come from this command, a background job, another session or the user. Do not continue, do not try "
            "to repair or normalise this state, and do not stash, reset or drop anything. Report exactly what happened to "
            "the user (`tripwire.py --status` shows the event, ref values and recovery hints). Further mutating commands "
            "are denied until the user reviews the repos and runs: ! " + ack_command())
    print(json.dumps({"decision": "block", "reason": stop,
                      "hookSpecificOutput": {"hookEventName": payload.get("hook_event_name") or "PostToolUse",
                                             "additionalContext": stop}}))
    return 0


def rebuild_baseline(sd):
    """After an ack the reviewed state becomes the new baseline - rebuilt now, so file tools and the next
    command are protected immediately (not only after the next shell command)."""
    bf = os.path.join(sd, "baseline.json")
    if not os.path.exists(bf):
        return
    old = load_json(bf) or {}
    os.remove(bf)
    tops = {t: ("clone:" if "" in e else "repo") for t, e in old.items() if os.path.isdir(t)}
    if tops:
        baseline(sd, tops)


def session_latches():
    """{session: (message, event id or None)} for every session LATCH file in the scratch root."""
    root = fstate.scratch()
    out = {}
    for s in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        sl = session_latch(os.path.join(root, s))
        if sl:
            out[s] = sl
    return out


def archive_event(e):
    """Move an open event to acked/ (atomic rename, evidence kept), then stamp acked_at. A legacy single-file
    latch is migrated: written into acked/ first, removed only after that succeeded."""
    dst_dir = os.path.join(fstate.latch_dir(key=e["key"]), "acked")
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, e["id"] + ".json")
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    if e["legacy"]:
        if os.path.exists(dst):  # an older legacy latch was archived under the same id: keep both
            dst = os.path.join(dst_dir, f"{e['id']}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{os.urandom(2).hex()}.json")
        data = load_json(e["path"])
        if not isinstance(data, dict):
            data = {"raw": read(e["path"])}
        data.update({"id": e["id"], "migrated_from": e["path"], "acked_at": now})
        fstate.write_json(dst, data)
        os.remove(e["path"])
        return
    os.replace(e["path"], dst)  # raises FileNotFoundError when another ack already archived it
    data = load_json(dst)
    if isinstance(data, dict):
        data["acked_at"] = now
        try:
            fstate.write_json(dst, data)
        except OSError:
            pass  # the event is archived either way; the stamp is a convenience


def status(want):
    """--status [id ...]: open events (all workspaces) and session latches, with the exact ack command."""
    all_evs = open_events()
    evs = [e for e in all_evs if not want or e["id"] in want
           or (isinstance(e["data"], dict) and e["data"].get("session") in want)]
    sl = {s: v for s, v in session_latches().items() if not want or s in want or v[1] in want}
    for e in evs:
        print("OPEN " + event_line(e))
        d = e["data"] if isinstance(e["data"], dict) else {}
        if d.get("command"):
            print(f"  command: {d['command']}")
        for top, refs in (d.get("refs") or {}).items():
            for n, (old, new) in refs.items():
                print(f"  {top}: {n} {old or '(none)'} -> {new or '(none)'}")
        for h in d.get("recovery") or []:
            print(f"  recovery: {h}")
    for s, (msg, eid) in sl.items():
        print(f"session {s}: LATCHED - {msg}" + (f" (event {eid})" if eid else ""))
    wss = sorted({e["data"].get("workspace") for e in evs if isinstance(e["data"], dict) and e["data"].get("workspace")})
    for ws in wss:
        try:
            with open(fstate.audit_file(ws), encoding="utf-8") as fh:
                lines = fh.read().splitlines()[-5:]
        except OSError:
            lines = []
        for line in lines:
            print(f"audit (visible git stash, {ws}): {line}")
    if not evs and not sl:
        print("no latched session or workspace; latch is CLEAR")
        return 0
    print("Review the repos first. Only the user (never the agent) clears all open events with: ! " + ack_command()
          + "   - or one event with: ! " + ack_command() + " <event-id>")
    return 0


def ack(want):
    """--ack [id ...]: archive the events open NOW (or the given event / session ids), then re-read and report.
    Exit 0 = latch CLEAR; 1 = something still open, an unknown id, or an error; 2 = bad usage."""
    if any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", w) for w in want):
        print("NOT cleared: invalid id (ids are event ids from --status, or session ids)")
        return 2
    evs = open_events()
    latches = session_latches()
    unknown, targets, sessions = [], [], set()
    if want:
        for w in want:
            hit = [e for e in evs if e["id"] == w or (isinstance(e["data"], dict) and e["data"].get("session") == w)]
            if not hit and w not in latches:
                unknown.append(w)
            targets += [e for e in hit if e not in targets]
            if w in latches:
                sessions.add(w)
    else:
        if not evs and not latches:
            print("no open tripwire events; latch is CLEAR")
            return 0
        targets, sessions = evs, set(latches)  # exactly what is open now; later events stay open
    errors, acked = [], set()
    for e in targets:
        try:
            archive_event(e)
            acked.add(e["id"])
            print(f"acked {event_line(e)}")
        except FileNotFoundError:
            acked.add(e["id"])  # archived meanwhile by another ack: idempotent
            print(f"event {e['id']}: already acknowledged")
        except OSError as x:
            errors.append(f"event {e['id']}: {x}")
    root = fstate.scratch()
    for s, (msg, eid) in latches.items():
        if not (s in sessions or (eid and eid in acked)):
            continue
        if eid and eid not in acked and eid in {e["id"] for e in targets}:
            continue  # its event could not be archived: the session stays latched
        sd = os.path.join(root, s)
        if session_latch(sd) != (msg, eid):
            continue  # re-read: this session latched again after the ack began - that new STOP stays
        try:
            os.remove(os.path.join(sd, "LATCH"))
            print(f"session {s}: latch cleared by the user")
            rebuild_baseline(sd)
        except FileNotFoundError:
            pass
        except OSError as x:
            errors.append(f"session {s}: {x}")
    for k in {e["key"] for e in targets}:  # keep the archive bounded
        prune(os.path.join(fstate.latch_dir(key=k), "acked"), "", ACKED_KEEP)
    for w in unknown:
        print(f"NOT cleared: unknown event or session id {w}")
    for x in errors:
        print(f"NOT cleared: {x}")
    still = [e["id"] for e in open_events()] + [f"session {s}" for s in session_latches()]
    if still:
        print("still LATCHED: " + ", ".join(still) + " - see --status (nothing that appeared after this ack began "
              "was acknowledged)")
        return 1
    if unknown or errors:
        return 1
    print(f"cleared: {len(acked)} event(s); latch is now CLEAR")
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
                evs = open_events(ws)
                if evs:
                    msg = (f"rpg-factory tripwire: {len(evs)} STOP event(s) from an earlier or concurrent session were "
                           "never cleared: " + " | ".join(event_line(e) for e in evs) + ". Mutating commands stay denied. "
                           "Tell the user; `tripwire.py --status` shows ref values and recovery hints. After reviewing "
                           "the repos the user clears them with: ! " + ack_command())
                    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": msg}}))
        except Exception:
            pass
        return 0
    if mode == "--skill":
        try:
            return skill_hook(json.load(sys.stdin))
        except Exception:
            return 0  # never break the session
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
    if mode not in {"--status", "--ack"}:
        print("usage: tripwire.py --status [id ...] | --ack [event-or-session-id ...]")
        return 2
    try:
        return ack(sys.argv[2:]) if mode == "--ack" else status(set(sys.argv[2:]))
    except Exception as x:  # the user must never believe a failed ack worked
        print(f"NOT cleared: {type(x).__name__}: {x}" if mode == "--ack" else f"status failed: {type(x).__name__}: {x}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
