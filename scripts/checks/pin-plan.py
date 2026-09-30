#!/usr/bin/env python3
"""Compute the exact, reviewable edits for moving one client pin to a new upstream tag. Read-only.

Usage: pin-plan.py <package> <new-tag> [--workspace DIR] [--client-ref REF] [--json]
  --client-ref  read the client's manifest/lock at a git ref instead of the working tree
                (replaying historical bumps without touching the checkout)
  <package>  com.cuvara.netcode | com.cuvara.dots | com.cuvara.uitoolkit | com.rpgmmo.shared-gamelogic
  <new-tag>  vX.Y.Z (packages) or sgl-vX.Y.Z (shared-gamelogic)

Prints:
  - current pin (manifest + lock) and the new manifest string
  - the new lock entry fields: version (same string) and hash (= the tag's commit, as in #141)
  - upstream package.json version at the tag (must equal the tag) and dependency changes between
    the old and the new tag (a changed dependency set means the lock's own dependencies block
    must change too - let the Unity Editor re-resolve, or edit it to match)
  - for com.cuvara.netcode: whether Samples~/DOTSSample changed between the tags and the
    .sample-source lines to write (recopy byte-for-byte, .meta included)
  - the CHANGELOG line to add under [Unreleased]
Exit 0 = plan produced; 1 = blocking problem (tag missing, version mismatch); 2 = usage/IO error.
Uses the workspace clones only; run `git -C <repo> fetch --tags` yourself if a tag is missing.
"""
import json
import os
import subprocess
import sys

PKGS = {
    "com.cuvara.netcode": ("Netcode", "package.json", "https://github.com/Cuvara/Netcode.git"),
    "com.cuvara.dots": ("UnityDots", "package.json", "https://github.com/Cuvara/UnityDots.git"),
    "com.cuvara.uitoolkit": ("UIToolkit", "package.json", "https://github.com/Cuvara/UIToolkit.git"),
    "com.rpgmmo.shared-gamelogic": ("rpg-mmo-server", "backend/gameserver-dotnet/Shared.GameLogic/package.json",
                                    "https://github.com/Cuvara/rpg-mmo-server.git?path=/backend/gameserver-dotnet/Shared.GameLogic"),
}
SAMPLE = "Assets/Samples/Netcode/DOTS Sample"


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout.strip()


def pkg_json_at(repo, ref, path):
    rc, out = git(repo, "show", f"{ref}:{path}")
    return json.loads(out) if rc == 0 else None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ws = os.environ.get("RPG_FACTORY_WORKSPACE", "/mnt/c/Workspaces/UnityIndie")
    if "--workspace" in sys.argv:
        ws = sys.argv[sys.argv.index("--workspace") + 1]
        args = [a for a in args if a != ws]
    client_ref = None
    if "--client-ref" in sys.argv:
        client_ref = sys.argv[sys.argv.index("--client-ref") + 1]
        args = [a for a in args if a != client_ref]
    if len(args) != 2 or args[0] not in PKGS:
        print(__doc__)
        return 2
    name, new_tag = args
    d, pj, url = PKGS[name]
    up = os.path.join(ws, d)
    client = os.path.join(ws, "IndieRPGMMOAdventure")
    def client_json(rel):
        if client_ref:
            rc, out = git(client, "show", f"{client_ref}:{rel}")
            if rc != 0:
                raise SystemExit(f"cannot read {rel} at {client_ref}")
            return json.loads(out)
        return json.load(open(os.path.join(client, rel), encoding="utf-8"))
    manifest = client_json("Packages/manifest.json")["dependencies"]
    lock = client_json("Packages/packages-lock.json")["dependencies"]
    cur_m, cur_l = manifest.get(name), (lock.get(name) or {})
    old_tag = (cur_m or "").rsplit("#", 1)[-1] if cur_m and "#" in cur_m else None
    problems, plan = [], {"package": name, "upstream": d, "old_tag": old_tag, "new_tag": new_tag}

    rc, commit = git(up, "rev-parse", "-q", "--verify", f"refs/tags/{new_tag}^{{commit}}")
    if rc != 0:
        problems.append(f"tag {new_tag} not found in {d}/ - it must be created by the lead and fetched "
                        f"(`git -C {up} fetch --tags`); pin-bump never creates tags")
        commit = None
    new_spec = f"{url}#{new_tag}"
    plan["manifest"] = {"from": cur_m, "to": new_spec}
    plan["lock"] = {"from": {"version": cur_l.get("version"), "hash": cur_l.get("hash")},
                    "to": {"version": new_spec, "hash": commit}}
    if cur_m != cur_l.get("version"):
        problems.append(f"manifest and lock already disagree ({cur_m} vs {cur_l.get('version')}) - fix that first")

    if commit:
        new_pj = pkg_json_at(up, new_tag, pj) or {}
        want = new_tag.split("v", 1)[-1] if new_tag.startswith("v") else new_tag.replace("sgl-v", "")
        plan["upstream_version_at_tag"] = new_pj.get("version")
        if new_pj.get("version") != want:
            problems.append(f"{pj} at {new_tag} says {new_pj.get('version')}, tag says {want}")
        old_pj = pkg_json_at(up, old_tag, pj) if old_tag else None
        od, nd = (old_pj or {}).get("dependencies", {}), new_pj.get("dependencies", {})
        plan["dependency_changes"] = {k: {"from": od.get(k), "to": nd.get(k)} for k in sorted(set(od) | set(nd)) if od.get(k) != nd.get(k)}
        if name == "com.cuvara.netcode" and old_tag:
            rc, changed = git(up, "diff", "--name-status", f"{old_tag}", f"{new_tag}", "--", "Samples~/DOTSSample")
            files = [l for l in changed.splitlines() if l]
            plan["dots_sample"] = {"changed_files": files, "recopy_required": True,
                                   "sample_source": {"package": name, "version": new_tag, "commit": commit},
                                   "how": f"replace {SAMPLE}/ with `git -C {up} archive {new_tag} Samples~/DOTSSample` contents "
                                          f"(byte-for-byte incl. .meta), keep {SAMPLE}/.sample-source and update its version/commit lines"}
    plan["changelog"] = (f"- **`{name}` {old_tag} → {new_tag}**" + (", DOTS Sample recopied from the tag (`.sample-source` updated)" if name == "com.cuvara.netcode" else "")
                         + ". Manifest and lock both move; the lock is what resolves.")
    plan["problems"] = problems
    if "--json" in sys.argv:
        print(json.dumps(plan, indent=2))
    else:
        print(f"package      {name}  ({d})  {old_tag} -> {new_tag}")
        print(f"manifest     {plan['manifest']['to']}")
        print(f"lock         version={plan['lock']['to']['version']}  hash={commit}")
        if "upstream_version_at_tag" in plan:
            print(f"upstream     package.json at tag = {plan['upstream_version_at_tag']}")
        for k, v in (plan.get("dependency_changes") or {}).items():
            print(f"dep change   {k}: {v['from']} -> {v['to']}  (lock dependencies block must follow)")
        if "dots_sample" in plan:
            ds = plan["dots_sample"]
            print(f"DOTS Sample  {len(ds['changed_files'])} file(s) changed between tags; recopy required on every netcode move")
            for f in ds["changed_files"][:20]:
                print(f"             {f}")
            print(f"             .sample-source: version={new_tag} commit={commit}")
        print(f"CHANGELOG    {plan['changelog']}")
        for p in problems:
            print(f"BLOCKED: {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
