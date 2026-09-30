#!/usr/bin/env python3
"""Local mirror of the first step of the client's 02-package-pins.yml, plus a file: guard.

Usage: unity-package-pins.py <unity-project-root>

Checks, without network access:
  1. every git-URL dependency in Packages/manifest.json is pinned identically in
     Packages/packages-lock.json (the lock is what Unity resolves);
  2. no dependency uses a file: path (allowed locally, never committed);
  3. at least one git-URL dependency was checked - a gate that matches nothing fails.

CI additionally verifies that pinned refs exist on their remotes and that the DOTS
Sample .sample-source agrees; those need network and stay in CI.
"""
import json
import os
import sys


def main() -> int:
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    manifest_path = os.path.join(root, "Packages", "manifest.json")
    lock_path = os.path.join(root, "Packages", "packages-lock.json")
    try:
        manifest = json.load(open(manifest_path, encoding="utf-8"))["dependencies"]
        lock = json.load(open(lock_path, encoding="utf-8"))["dependencies"]
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read manifest/lock under {root}: {exc}")
        return 1

    problems = []
    checked = 0
    for name, spec in manifest.items():
        if isinstance(spec, str) and spec.startswith("file:"):
            problems.append(f"{name}: file: path '{spec}' must never be committed (toggle-packages.sh dev mode?)")
            continue
        if not isinstance(spec, str) or not spec.startswith(("https://", "git@", "ssh://")):
            continue
        checked += 1
        locked = (lock.get(name) or {}).get("version")
        if locked is None:
            problems.append(f"{name}: in manifest.json but ABSENT from packages-lock.json")
        elif locked != spec:
            problems.append(f"{name}: manifest {spec} != lock {locked} (the lock is what resolves)")

    if checked == 0 and not problems:
        print("ERROR: no git-URL dependencies found - the check is not running, not passing")
        return 1
    if problems:
        for p in problems:
            print(f"ERROR: {p}")
        print(f"FAILED: {len(problems)} problem(s), {checked} git-URL dependencies checked")
        return 1
    print(f"OK: {checked} git-URL dependencies pinned identically in manifest.json and packages-lock.json; no file: paths")
    return 0


if __name__ == "__main__":
    sys.exit(main())
