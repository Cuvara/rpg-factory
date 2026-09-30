#!/usr/bin/env python3
"""Read-only release-readiness check for a com.cuvara.* package repo (Netcode, UnityDots, UIToolkit).

Usage: package-ready.py <package-repo-dir> [--json]

"Ready to tag vX.Y.Z" requires (from each repo's release.yml / release-reminder.yml / RELEASE.md):
  - package.json version X.Y.Z, and no existing tag vX.Y.Z (else it is already released)
  - CHANGELOG.md has a '## [X.Y.Z] - YYYY-MM-DD' section (release.yml extracts notes from it;
    CI validate greps '[X.Y.Z]')
  - the repo's own .github/scripts/check_metas.py passes (every Unity-visible file has a .meta)
  - a clean working tree and the release branch checked out (Netcode: develop; UnityDots,
    UIToolkit: main - per their release docs/workflows)
Never creates a tag: prints the command the lead would run.
Exit 0 = ready; 1 = not ready (reasons printed); 2 = not a package repo.
"""
import json
import os
import re
import subprocess
import sys

RELEASE_BRANCH = {"com.cuvara.netcode": "develop", "com.cuvara.dots": "main", "com.cuvara.uitoolkit": "main"}


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=30)
    return r.returncode, r.stdout.strip()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    repo = os.path.abspath(sys.argv[1])
    as_json = "--json" in sys.argv
    try:
        pkg = json.load(open(os.path.join(repo, "package.json"), encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {repo} has no readable package.json: {exc}")
        return 2
    name, ver = pkg.get("name"), pkg.get("version")
    tag = f"v{ver}"
    reasons, facts = [], {"package": name, "version": ver, "tag": tag}

    rc, _ = git(repo, "rev-parse", "-q", "--verify", f"refs/tags/{tag}")
    facts["tag_exists"] = rc == 0
    if rc == 0:
        reasons.append(f"tag {tag} already exists - package.json has not been bumped since the last release")

    raw = open(os.path.join(repo, "CHANGELOG.md"), "rb").read().decode("utf-8", errors="replace")
    m = re.search(r"^## \[" + re.escape(ver) + r"\](.*)$", raw, re.M)
    facts["changelog_section"] = bool(m)
    if not m:
        reasons.append(f"CHANGELOG.md has no '## [{ver}]' section (release notes are extracted from it)")
    elif not re.search(r"\d{4}-\d{2}-\d{2}", m.group(1)):
        reasons.append(f"CHANGELOG.md '## [{ver}]' has no release date")
    if "�" in raw:
        facts["changelog_not_utf8"] = True

    branch = git(repo, "branch", "--show-current")[1]
    facts["branch"] = branch
    want = RELEASE_BRANCH.get(name)
    if want and branch != want:
        reasons.append(f"on branch '{branch}', releases of {name} are tagged from '{want}'")
    dirty = git(repo, "status", "--porcelain")[1]
    facts["dirty_paths"] = len(dirty.splitlines()) if dirty else 0
    if dirty:
        reasons.append(f"{facts['dirty_paths']} uncommitted path(s) - a tag must point at committed, pushed work")
    rc, ahead = git(repo, "rev-list", "--count", "@{u}..HEAD")
    if rc == 0 and ahead != "0":
        reasons.append(f"{ahead} commit(s) not pushed")

    metas = os.path.join(repo, ".github/scripts/check_metas.py")
    if os.path.isfile(metas):
        r = subprocess.run([sys.executable, "-B", metas], cwd=repo, capture_output=True, text=True, timeout=120,
                           env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        facts["check_metas"] = "pass" if r.returncode == 0 else "fail"
        if r.returncode != 0:
            reasons.append("check_metas.py failed: " + (r.stdout + r.stderr).strip().splitlines()[-1][:200])
    facts["ready"] = not reasons
    facts["reasons"] = reasons
    if as_json:
        print(json.dumps(facts, indent=2))
    else:
        for k in ("package", "version", "branch", "tag_exists", "changelog_section", "check_metas", "dirty_paths"):
            print(f"{k:18} {facts.get(k)}")
        if facts.get("changelog_not_utf8"):
            print("note               CHANGELOG.md is not valid UTF-8 (read with replacement)")
        if reasons:
            for r in reasons:
                print(f"NOT READY: {r}")
        else:
            print(f"READY to tag {tag} - human gate: the lead runs `git -C {repo} tag {tag} && git -C {repo} push origin {tag}`")
    return 0 if not reasons else 1


if __name__ == "__main__":
    sys.exit(main())
