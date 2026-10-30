#!/usr/bin/env python3
"""Validate cross-domain ownership and handoff contract invariants."""
import json
import sys


def under(path, prefix):
    return path == prefix.rstrip("/") or path.startswith(prefix.rstrip("/") + "/")


def main(path):
    reg = json.load(open(path, encoding="utf-8"))
    domains = reg.get("domains", {})
    modules = reg.get("modules", [])
    errors = []
    kinds = {}
    for domain, data in domains.items():
        for kind in data.get("artifact_kinds", []):
            kinds.setdefault(kind, []).append(domain)
    for kind, owners in kinds.items():
        if len(owners) > 1:
            errors.append(f"artifact kind {kind} is shared by domains {', '.join(owners)}; kinds must be unique per domain")

    owned = [m for m in modules if not m.get("fallback")]
    for i, left in enumerate(owned):
        for right in owned[i + 1:]:
            ld, rd = left.get("domain", "engineering"), right.get("domain", "engineering")
            if ld == rd or left["repo"] != right["repo"]:
                continue
            for lp in left.get("paths", []):
                for rp in right.get("paths", []):
                    if under(lp, rp) or under(rp, lp):
                        errors.append(f"domain path conflict: {left['id']} ({ld}) {lp} overlaps {right['id']} ({rd}) {rp}")

    skills = reg.get("skills", {})
    for contract in reg.get("contracts", []):
        if contract.get("kind") != "handoff":
            continue
        cid = contract["id"]
        domain = contract.get("domain")
        if domain not in domains:
            errors.append(f"handoff {cid}: unknown or missing domain {domain}")
        driver = contract.get("driver")
        if not isinstance(contract.get("source"), dict) or not isinstance(contract.get("copies"), list):
            errors.append(f"handoff {cid}: source and copies must be registered ends")
            continue
        for end in [contract["source"], *contract["copies"]]:
            if end.get("repo") not in reg.get("repos", {}):
                errors.append(f"handoff {cid}: unknown repo {end.get('repo')}")
            elif end.get("path"):
                matches = [m for m in modules if m["repo"] == end["repo"] and
                           any(under(end["path"], p) or under(p, end["path"]) for p in m.get("paths", []))]
                if not matches:
                    errors.append(f"handoff {cid}: path {end['repo']}:{end['path']} does not resolve to a module")
        if driver not in skills:
            errors.append(f"handoff {cid}: unknown driver skill {driver}")
            continue
        source = contract["source"]
        matches = [m for m in modules if m["repo"] == source.get("repo") and any(under(source.get("path", ""), p) for p in m.get("paths", []))]
        if not matches:
            errors.append(f"handoff {cid}: source does not resolve to a module")
        else:
            owner = max(matches, key=lambda m: max(map(len, m.get("paths", [""]))))
            driver_domain = skills[driver].get("domain", "engineering")
            if owner.get("domain", "engineering") != driver_domain:
                errors.append(f"handoff {cid}: source module domain {owner.get('domain', 'engineering')} differs from driver domain {driver_domain}")
    for error in errors:
        print("FAIL: " + error)
    if not errors:
        print("PASS: domain ownership and handoff contracts")
    return bool(errors)


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252: output is UTF-8 everywhere
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1]))
