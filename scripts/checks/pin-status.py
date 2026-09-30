#!/usr/bin/env python3
"""Read-only status of every git-URL pin in the Unity client, checked against the upstream repos.

Usage: pin-status.py [--workspace DIR] [--remote] [--json]

For each git-URL dependency in <client>/Packages/manifest.json it reports:
  - manifest pin vs packages-lock.json pin (must be identical; the lock is what resolves)
  - the upstream repo it maps to in the workspace and whether the pinned tag exists there
    (local clone tags; with --remote also `git ls-remote --tags`, which needs network)
  - the newest release tag in the local clone and the upstream package.json version
  - for com.cuvara.netcode: whether Assets/Samples/Netcode/DOTS Sample/.sample-source
    records the same version (and the tag's commit)
Also flags file: pins (never committable).

Exit 0 when nothing blocks; 1 on a hard problem (manifest != lock, file: pin, missing tag
confirmed, sample-source mismatch); 2 on usage/IO errors. Writes nothing.
"""
import argparse
import json
import os
import re
import subprocess
import sys

# upstream repo name (from the git URL) -> workspace dir, tag prefix, package.json path in that repo
UPSTREAMS = {
    "Netcode": ("Netcode", "v", "package.json"),
    "UnityDots": ("UnityDots", "v", "package.json"),
    "UIToolkit": ("UIToolkit", "v", "package.json"),
    "rpg-mmo-server": ("rpg-mmo-server", "sgl-v", "backend/gameserver-dotnet/Shared.GameLogic/package.json"),
}
SAMPLE_SOURCE = "Assets/Samples/Netcode/DOTS Sample/.sample-source"


def git(repo, *args):
    try:
        r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=30)
        return r.returncode, r.stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 99, str(exc)


def vkey(tag, prefix):
    nums = re.findall(r"\d+", tag[len(prefix):])
    return tuple(int(n) for n in nums)


def parse_pin(spec):
    """https://github.com/Cuvara/Netcode.git?path=/x#v1.2.3 -> (repo_name, ref)"""
    m = re.match(r"^(?:https://|git@|ssh://)[^#]*?/([^/?#]+?)(?:\.git)?(?:\?[^#]*)?(?:#(.+))?$", spec)
    return (m.group(1), m.group(2)) if m else (None, None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=os.environ.get("RPG_FACTORY_WORKSPACE", "/mnt/c/Workspaces/UnityIndie"))
    ap.add_argument("--remote", action="store_true", help="also confirm tags with git ls-remote (network)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    client = os.path.join(a.workspace, "IndieRPGMMOAdventure")
    try:
        manifest = json.load(open(os.path.join(client, "Packages/manifest.json"), encoding="utf-8"))["dependencies"]
        lock = json.load(open(os.path.join(client, "Packages/packages-lock.json"), encoding="utf-8"))["dependencies"]
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read client manifest/lock: {exc}")
        return 2

    rows, problems, warnings = [], [], []
    for name, spec in sorted(manifest.items()):
        if isinstance(spec, str) and spec.startswith("file:"):
            problems.append(f"{name}: file: pin '{spec}' must never be committed")
            rows.append({"package": name, "manifest": spec, "state": "file-pin"})
            continue
        if not isinstance(spec, str) or not spec.startswith(("https://", "git@", "ssh://")):
            continue
        repo_name, ref = parse_pin(spec)
        locked = (lock.get(name) or {}).get("version")
        row = {"package": name, "manifest": spec, "lock": locked, "ref": ref, "upstream": repo_name}
        if locked != spec:
            problems.append(f"{name}: manifest '{spec}' != lock '{locked}'")
        up = UPSTREAMS.get(repo_name)
        if up:
            d, prefix, pkg_json = up
            path = os.path.join(a.workspace, d)
            row["upstream_dir"] = d
            if os.path.isdir(os.path.join(path, ".git")):
                rc, _ = git(path, "rev-parse", "-q", "--verify", f"refs/tags/{ref}^{{commit}}")
                row["tag_local"] = rc == 0
                rc, commit = git(path, "rev-parse", "-q", "--verify", f"refs/tags/{ref}^{{commit}}")
                row["tag_commit"] = commit if rc == 0 else None
                rc, tags = git(path, "tag", "-l", f"{prefix}*")
                rel = [t for t in tags.splitlines() if re.match(re.escape(prefix) + r"\d", t)]
                row["latest_local_tag"] = max(rel, key=lambda t: vkey(t, prefix)) if rel else None
                try:
                    row["upstream_version"] = json.load(open(os.path.join(path, pkg_json), encoding="utf-8")).get("version")
                except (OSError, json.JSONDecodeError):
                    row["upstream_version"] = None
                if ref and row["latest_local_tag"] and vkey(row["latest_local_tag"], prefix) > vkey(ref, prefix):
                    row["newer_tag_available"] = row["latest_local_tag"]
            else:
                row["tag_local"] = None
                warnings.append(f"{name}: upstream clone {d}/ not in workspace; tag not checked locally")
            if a.remote:
                url = spec.split("?")[0].split("#")[0]
                try:
                    r = subprocess.run(["git", "ls-remote", "--tags", url, f"refs/tags/{ref}"],
                                       capture_output=True, text=True, timeout=60)
                    row["tag_remote"] = bool(r.stdout.strip()) if r.returncode == 0 else None
                except (OSError, subprocess.SubprocessError):
                    row["tag_remote"] = None
                if row["tag_remote"] is False:
                    problems.append(f"{name}: tag {ref} does not exist on {url}")
            if row.get("tag_local") is False and not a.remote:
                warnings.append(f"{name}: tag {ref} not in local clone {d}/ (fetch tags or re-run with --remote)")
        rows.append(row)

    # DOTS Sample stamp
    sample = {"path": SAMPLE_SOURCE}
    try:
        stamp = dict(l.split("=", 1) for l in open(os.path.join(client, SAMPLE_SOURCE), encoding="utf-8").read().splitlines()
                     if l and not l.startswith("#") and "=" in l)
        sample.update(stamp)
        pin = next((r for r in rows if r.get("package") == stamp.get("package")), None)
        if pin is None:
            problems.append(f"{SAMPLE_SOURCE}: package {stamp.get('package')!r} is not pinned")
        else:
            pinned = (pin.get("lock") or "").rsplit("#", 1)[-1]
            sample["pinned"] = pinned
            if stamp.get("version") != pinned:
                problems.append(f"{SAMPLE_SOURCE}: version {stamp.get('version')} != netcode pin {pinned} (recopy Samples~/DOTSSample)")
            if pin.get("tag_commit") and stamp.get("commit") and stamp["commit"] != pin["tag_commit"]:
                problems.append(f"{SAMPLE_SOURCE}: commit {stamp['commit'][:10]} != {pinned} commit {pin['tag_commit'][:10]}")
    except FileNotFoundError:
        problems.append(f"{SAMPLE_SOURCE} missing")

    checked = sum(1 for r in rows if r.get("ref") is not None)
    if checked == 0 and not problems:
        problems.append("no git-URL pins found - the check is not running, not passing")
    result = {"pins": rows, "sample_source": sample, "problems": problems, "warnings": warnings, "checked": checked}
    if a.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{'package':32} {'pin':14} {'lock=manifest':13} {'tag local':9} {'latest tag':12} upstream pkg.json")
        for r in rows:
            if r.get("ref") is None:
                print(f"{r['package']:32} {r.get('state', '?')}")
                continue
            print(f"{r['package']:32} {r['ref']:14} {str(r['lock'] == r['manifest']):13} {str(r.get('tag_local')):9} "
                  f"{str(r.get('latest_local_tag')):12} {r.get('upstream_version')}"
                  + (f"  (newer: {r['newer_tag_available']})" if r.get("newer_tag_available") else "")
                  + (f"  remote-tag={r['tag_remote']}" if "tag_remote" in r else ""))
        print(f"DOTS Sample .sample-source: version={sample.get('version')} pinned={sample.get('pinned')}")
        for w in warnings:
            print(f"WARN: {w}")
        for p in problems:
            print(f"ERROR: {p}")
        print(("FAILED" if problems else "OK") + f": {checked} git-URL pins checked, {len(problems)} problem(s), {len(warnings)} warning(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
