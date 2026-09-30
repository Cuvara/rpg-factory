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
                                                         .../logs/<module>__<check>-<stamp>.log (full output)
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


def store(ws, repo, result, output):
    d = repo_dir_for(ws, repo)
    name = f"{_slug(result['module'])}__{_slug(result['check'])}"
    log = os.path.join(d, "logs", f"{name}-{result['timestamp']}.log")
    with open(log, "w", encoding="utf-8", errors="replace") as fh:
        fh.write(output or "")
    rec = dict(result, log=log)
    json.dump(rec, open(os.path.join(d, name + ".json"), "w", encoding="utf-8"), indent=2)
    return log


def latest(ws, repo, module, check_id):
    p = os.path.join(repo_dir_for(ws, repo, create=False), f"{_slug(module)}__{_slug(check_id)}.json")
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def all_latest(ws, repo):
    d = repo_dir_for(ws, repo, create=False)
    out = []
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if f.endswith(".json"):
            try:
                out.append(json.load(open(os.path.join(d, f), encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                pass
    return out


def assess(rec, repo_dir, check):
    """Current state of a stored result against the tree as it is now: (state, detail)."""
    if not rec:
        return "NOT_RUN", "no evidence recorded"
    now = identity(repo_dir, rec.get("scopes") or check.get("cwd", "."), check)
    if rec.get("identity", {}).get("tree") == now["tree"]:
        return rec["state"], f"at {now['head'][:7]} (current tree)"
    why = "check definition changed" if rec.get("identity", {}).get("definition") != now["definition"] else \
        ("HEAD moved " + rec.get("identity", {}).get("head", "")[:7] + " -> " + now["head"][:7]
         if rec.get("identity", {}).get("head") != now["head"] else "working tree changed since the run")
    return "STALE", f"was {rec['state']} ({rec.get('timestamp')}); {why}"
