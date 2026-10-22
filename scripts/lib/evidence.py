"""Check evidence bound to the tree it was produced on (no database: one small JSON per check).

identity(repo_dir, scope, check) = sha256 of
  HEAD commit
  + `git diff HEAD --binary -- <scope>`            (staged + unstaged tracked changes)
  + untracked files under <scope>: name, size, mtime (contents are not hashed: the client's
    untracked Unity samples are large; any edit changes mtime)
  + the check definition (command, cwd, parser, evidence text)
scope = the check's working directory inside the repo ("." = the whole repo) PLUS the paths of every
module its module depends on (transitively, same repo) - a PASS of the gateway's tests goes STALE when
backend/shared changes. scopes_for() computes it from the registry; the record stores it.

A stored PASS whose identity differs from the current one is STALE - it proves nothing about
the tree as it is now. A declared check with no stored evidence is NOT_RUN.

Layout: <fstate.persistent()>/evidence/<workspace-key>/<repo>/<module>__<check>.json (latest)
                                                         .../logs/<module>__<check>-<stamp>-<pid>-<id>.log (full output; newest 20 per check kept)
The workspace key is the case-folded real path (fstate.workspace_key).
"""
import hashlib
import json
import os
import re
import subprocess

import fstate


def _git(d, *args, binary=False):
    try:
        r = subprocess.run(["git", "-C", d, *args], capture_output=True, timeout=120)
        return r.stdout if r.returncode == 0 else b""
    except (OSError, subprocess.SubprocessError):
        return b""


def definition_hash(check):
    d = {k: check.get(k) for k in ("run", "cwd", "parser", "evidence")}
    return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:16]


def scopes_for(registry, module_id, cwd):
    """The check's directory + the paths of its module's transitive same-repo dependencies."""
    mods = {m["id"]: m for m in registry.get("modules", [])}
    m0 = mods.get(module_id)
    out, seen, todo = [cwd or "."], set(), [module_id]
    while todo:
        mid = todo.pop()
        if mid in seen or mid not in mods:
            continue
        seen.add(mid)
        m = mods[mid]
        if m0 and m["repo"] != m0["repo"]:
            continue
        if mid != module_id:
            out += [p for p in m.get("paths", []) if p not in ("./", ".")]
        todo += m.get("depends_on", [])
    return sorted(set(p.rstrip("/") or "." for p in out))


def identity(repo_dir, scope, check):
    scopes = scope if isinstance(scope, list) else [scope or "."]
    h = hashlib.sha256()
    head = _git(repo_dir, "rev-parse", "HEAD").strip()
    h.update(b"HEAD " + head + b"\n")
    h.update(_git(repo_dir, "diff", "HEAD", "--binary", "--no-ext-diff", "--no-color", "--", *scopes))
    for rel in sorted(_git(repo_dir, "ls-files", "--others", "--exclude-standard", "-z", "--", *scopes).split(b"\0")):
        if not rel:
            continue
        p = os.path.join(repo_dir, rel.decode(errors="replace"))
        try:
            st = os.stat(p)
            h.update(rel + f" {st.st_size} {st.st_mtime_ns}\n".encode())
        except OSError:
            h.update(rel + b" gone\n")
    h.update(b"DEF " + definition_hash(check).encode())
    return {"head": head.decode(), "tree": h.hexdigest()[:20], "definition": definition_hash(check)}


def _slug(s):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", s)


def repo_dir_for(ws, repo, create=True):
    d = os.path.join(fstate.persistent(), "evidence", fstate.workspace_key(ws), _slug(repo))
    if create:
        os.makedirs(os.path.join(d, "logs"), exist_ok=True)
    return d


LOGS_KEPT = 20  # per check; older logs are pruned (never the one the latest record points to)


def _prune_logs(logdir, name, keep_path):
    pat = re.compile(re.escape(name) + r"-\d{8}T\d{6}(-[A-Za-z0-9_-]+)?\.log")
    try:
        logs = [f for f in os.listdir(logdir) if pat.fullmatch(f)]
    except OSError:
        return

    def mtime(f):
        try:
            return os.stat(os.path.join(logdir, f)).st_mtime_ns
        except OSError:
            return 0
    logs.sort(key=lambda f: (mtime(f), f), reverse=True)
    keep = os.path.normcase(os.path.abspath(keep_path))
    for f in logs[LOGS_KEPT:]:
        p = os.path.join(logdir, f)
        if os.path.normcase(os.path.abspath(p)) == keep:
            continue
        try:
            os.remove(p)
        except OSError:
            pass


def store(ws, repo, result, output):
    d = repo_dir_for(ws, repo)
    name = f"{_slug(result['module'])}__{_slug(result['check'])}"
    # unique per run: two runs in the same second (or in parallel) never share or truncate a log
    log = os.path.join(d, "logs", f"{name}-{result['timestamp']}-{fstate.unique_suffix()}.log")
    with open(log, "w", encoding="utf-8", errors="replace") as fh:
        fh.write(output or "")
    rec = dict(result, log=log)
    fstate.write_json(os.path.join(d, name + ".json"), rec, indent=2)  # atomic: a reader never sees half a record
    _prune_logs(os.path.join(d, "logs"), name, log)
    return log


def valid(rec):
    """A usable evidence record: a dict with a dict identity and a string state. Anything else (hand-edited,
    truncated, another tool's JSON) counts as no evidence - never a crash."""
    return isinstance(rec, dict) and isinstance(rec.get("identity"), dict) and isinstance(rec.get("state"), str)


def _load(p):
    rec = fstate.read_json(p)
    return rec if valid(rec) else None


def latest(ws, repo, module, check_id):
    return _load(os.path.join(repo_dir_for(ws, repo, create=False), f"{_slug(module)}__{_slug(check_id)}.json"))


def all_latest(ws, repo):
    d = repo_dir_for(ws, repo, create=False)
    out = []
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if f.endswith(".json"):
            rec = _load(os.path.join(d, f))
            if rec is not None:
                out.append(rec)
    return out


def assess(rec, repo_dir, check):
    """Current state of a stored result against the tree as it is now: (state, detail)."""
    if not valid(rec):
        return "NOT_RUN", "no evidence recorded"
    scopes = rec.get("scopes")
    if not (isinstance(scopes, list) and scopes and all(isinstance(s, str) for s in scopes)):
        scopes = check.get("cwd") or "."
    now = identity(repo_dir, scopes, check)
    ident = rec["identity"]
    if ident.get("tree") == now["tree"]:
        return rec["state"], f"at {now['head'][:7]} (current tree)"
    why = "check definition changed" if ident.get("definition") != now["definition"] else \
        ("HEAD moved " + str(ident.get("head") or "")[:7] + " -> " + now["head"][:7]
         if ident.get("head") != now["head"] else "working tree changed since the run")
    return "STALE", f"was {rec['state']} ({rec.get('timestamp')}); {why}"
