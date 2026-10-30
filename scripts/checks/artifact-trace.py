#!/usr/bin/env python3
"""Check artifact revisions, trace coverage and immutable SSH-signed approvals."""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile


def run(cwd, *args):
    return subprocess.run(
        ["git", "-C", cwd, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )


def front(path):
    raw = open(path, encoding="utf-8").read()
    if path.endswith(".json"):
        return json.loads(raw)
    m = re.match(r"\A---json\s*\n(.*?)\n---(?:\s*\n|\Z)", raw, re.S)
    return json.loads(m.group(1)) if m else None


def git_blob(root, path):
    r = run(root, "rev-parse", f"HEAD:{path}")
    return r.stdout.strip() if r.returncode == 0 else ""


def spec_payload(raw):
    """Compare the implemented specification while ignoring lifecycle and trace bookkeeping."""
    try:
        obj = front_text(raw)
        if not isinstance(obj, dict):
            return None
        obj = dict(obj)
        obj.pop("trace", None)
        obj.pop("status", None)
        return obj
    except Exception:
        return None


def front_text(raw):
    m = re.match(r"\A---json\s*\n(.*?)\n---(?:\s*\n|\Z)", raw, re.S)
    return json.loads(m.group(1)) if m else (json.loads(raw) if raw.lstrip().startswith("{") else None)


def approval(root, artifact_path, obj, gate, reg):
    aid = obj["id"]
    rev = git_blob(root, artifact_path)
    path = f"approvals/{aid}/{gate}-{rev}.json"
    if run(root, "rev-parse", "--is-shallow-repository").stdout.strip() == "true":
        return "shallow clone"
    full = os.path.join(root, path)
    if not os.path.isfile(full):
        return "missing approval"
    try:
        data = json.load(open(full, encoding="utf-8"))
    except Exception:
        return "invalid approval JSON"
    if (
        data.get("artifact") != aid
        or data.get("gate") != gate
        or data.get("scope") != obj.get("domain")
        or data.get("rev") != rev
        or os.path.dirname(path).split("/")[-1] != data.get("artifact")
        or os.path.basename(path) != f"{data.get('gate')}-{data.get('rev')}.json"
    ):
        return "approval path/content/rev mismatch"
    try:
        datetime.datetime.fromisoformat(data.get("date", "").replace("Z", "+00:00"))
    except Exception:
        return "invalid approval date"
    adds = run(
        root, "log", "--no-renames", "--diff-filter=A", "--format=%H", "--", path
    ).stdout.splitlines()
    mods = run(
        root, "log", "--no-renames", "--diff-filter=MD", "--format=%H", "--", path
    ).stdout.splitlines()
    dels = run(
        root,
        "log",
        "--no-renames",
        "--diff-filter=D",
        "--format=%H",
        "--",
        "approvals/",
    ).stdout.splitlines()
    if len(adds) != 1 or mods or dels:
        return "approval is not immutable"
    domain = reg.get("domains", {}).get(obj.get("domain"), {})
    gates = domain.get("human_gates", [])
    if gate not in gates:
        return "gate not registered"
    keys = []
    revoked = set(domain.get("revoked_keys", []))
    for person in domain.get("approvers", []):
        key = person.get("ssh_public_key", "")
        if person.get("revoked") is True or not key:
            continue
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", delete=False
        ) as keyfile:
            keyfile.write(key.strip() + "\n")
            keypath = keyfile.name
        try:
            fp = subprocess.run(
                ["ssh-keygen", "-lf", keypath],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            fingerprint = (
                fp.stdout.split()[1]
                if fp.returncode == 0 and len(fp.stdout.split()) > 1
                else ""
            )
        finally:
            os.unlink(keypath)
        if fingerprint in revoked or key.split()[-1] in revoked:
            continue
        keys.append((person.get("principal", ""), key))
    if not keys:
        return "no trusted approver keys"
    with tempfile.TemporaryDirectory(prefix="artifact-signers-") as td:
        signers = os.path.join(td, "allowed signers")
        with open(signers, "w", encoding="utf-8") as f:
            for principal, key in keys:
                f.write(f'{principal} namespaces="git" {key.strip()}\n')
        opts = ["-c", "gpg.format=ssh", "-c", f"gpg.ssh.allowedSignersFile={signers}"]
        vr = run(root, *opts, "verify-commit", adds[0])
        if vr.returncode:
            return "approval signature untrusted or invalid"
        info = (
            run(root, *opts, "log", "-1", "--format=%G? %GS", adds[0])
            .stdout.strip()
            .split(maxsplit=1)
        )
        if len(info) != 2 or info[0] != "G" or info[1] != data.get("by"):
            return "approval principal mismatch"
        if not any(info[1] == pr for pr, _ in keys):
            return "approval principal untrusted"
    msg = run(root, "show", "-s", "--format=%B", adds[0]).stdout
    if re.search(r"^Co-Authored-By:.*\b(?:AI|Codex|Claude|agent)\b", msg, re.I | re.M):
        return "agent co-author rejected"
    return None


def main():
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("repo_dir")
    p.add_argument("--registry", required=True)
    p.add_argument("--repos", nargs="+", default=[])
    a = p.parse_args()
    root = os.path.abspath(a.repo_dir)
    reg = json.load(open(a.registry, encoding="utf-8"))
    repos = {}
    for x in a.repos:
        if "=" in x:
            k, v = x.split("=", 1)
            repos[k] = os.path.abspath(v)
    fails = 0
    humans = 0
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in (".git", "approvals")]
        for name in sorted(names):
            if not (name.endswith(".md") or name.endswith(".artifact.json")):
                continue
            path = os.path.join(base, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            try:
                obj = front(path)
            except Exception:
                obj = None
            if not isinstance(obj, dict) or "id" not in obj:
                continue
            aid = obj["id"]
            reason = None
            downstream_stale = None
            for up in obj.get("upstream", []):
                candidates = []
                for b, d, ns in os.walk(root):
                    d[:] = [x for x in d if x not in (".git", "approvals")]
                    for n in ns:
                        q = os.path.join(b, n)
                        try:
                            if front(q).get("id") == up["id"]:
                                candidates.append(
                                    os.path.relpath(q, root).replace(os.sep, "/")
                                )
                        except Exception:
                            pass
                if not candidates or up.get("rev") != git_blob(root, candidates[0]):
                    reason = f"upstream-changed {up.get('id')}"
                    break
            if reason is None:
                for contract in reg.get("contracts", []):
                    if contract.get("kind") != "handoff":
                        continue
                    source = contract.get("source", {})
                    if source.get("repo") != "authoring" or not rel.startswith(source.get("path", "")):
                        continue
                    engineering_repos = {end.get("repo") for end in contract.get("copies", [])
                                          if end.get("repo") in reg.get("domains", {}).get("engineering", {}).get("repos", [])}
                    # per engineering repo: stale only when no impl trace implements the current spec payload
                    # (older impl traces may stay in the list after a re-implementation)
                    current_payload = spec_payload(open(path, encoding="utf-8").read())
                    current_repos, stale_by_repo = set(), {}
                    for trace in obj.get("trace", []):
                        if trace.get("kind") != "impl" or trace.get("repo") not in engineering_repos:
                            continue
                        spec_rev = trace.get("spec_rev", "")
                        old = run(root, "cat-file", "blob", spec_rev) if spec_rev else None
                        if old is not None and not old.returncode and spec_payload(old.stdout) == current_payload:
                            current_repos.add(trace["repo"])
                        else:
                            stale_by_repo.setdefault(trace["repo"], trace.get("ref", ""))
                    for repo_key in sorted(set(stale_by_repo) - current_repos):
                        downstream_stale = f"downstream-stale {aid} impl {repo_key}@{stale_by_repo[repo_key]}"
                        break
                    if downstream_stale:
                        break
            if reason is None:
                for t in obj.get("trace", []):
                    repo = repos.get(t.get("repo"))
                    if (
                        not repo
                        or run(
                            repo, "cat-file", "-e", t.get("ref", "") + "^{commit}"
                        ).returncode
                    ):
                        reason = "unknown trace SHA"
                        break
            life = reg.get("artifact_lifecycles", {}).get(
                obj.get("kind"), reg.get("artifact_lifecycles", {}).get("default", {})
            )
            req = life.get("requirements", {}).get(obj.get("status"), {})
            if reason is None:
                coverage = {
                    (trace.get("kind"), ac_id)
                    for trace in obj.get("trace", [])
                    for ac_id in trace.get("ac", [])
                }
                for criterion in obj.get("acceptance", []):
                    criterion_required = set(req.get("needs_trace", []))
                    if criterion.get("verify") == "test":
                        criterion_required.update(req.get("needs_trace_for_test", []))
                    if any(
                        (kind, criterion.get("id")) not in coverage
                        for kind in criterion_required
                    ):
                        reason = "missing AC coverage"
                        break
            if reason is None:
                gates = list(req.get("needs_approval", []))
                conditional = req.get("approval_when_binding")
                if obj.get("binding_values") is True and conditional:
                    extra = (
                        conditional
                        if isinstance(conditional, list)
                        else reg.get("domains", {})
                        .get(obj.get("domain"), {})
                        .get("human_gates", [])
                    )
                    gates = list(dict.fromkeys(gates + extra))
                for gate in gates:
                    reason = approval(root, rel, obj, gate, reg)
                    if reason:
                        break
            human_reason = (
                reason is not None
                and reason not in ("missing AC coverage", "unknown trace SHA")
                and not reason.startswith("upstream-changed ")
            )
            state = (
                "PASS" if not reason else ("HUMAN_REQUIRED" if human_reason else "FAIL")
            )
            if human_reason:
                humans += 1
            if reason and state == "FAIL":
                fails += 1
            if downstream_stale:
                print(f"FAIL {downstream_stale}")
                fails += 1
            print(f"{state} {aid} {reason or 'trace and approvals verified'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
