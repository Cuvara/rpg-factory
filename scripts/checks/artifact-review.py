#!/usr/bin/env python3
"""Git identity and optional SSH signature checks shared by artifact validators."""
import os
import subprocess
import tempfile


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                          text=True, encoding="utf-8")


def author_emails(root, path):
    result = git(root, "log", "--follow", "--format=%ae", "HEAD", "--", path)
    return set(result.stdout.splitlines())


def review_commit(root, path):
    adds = git(root, "log", "--diff-filter=A", "--format=%H", "--", path).stdout.splitlines()
    later = git(root, "log", "--diff-filter=MRD", "--format=%H", "--", path).stdout.splitlines()
    deleted = git(root, "log", "--diff-filter=D", "--", "reviews/").stdout.splitlines()
    if len(adds) != 1 or later or deleted:
        return None, "review is not immutable"
    email = git(root, "show", "-s", "--format=%ae", adds[0]).stdout.strip()
    return (adds[0], email), None


def signed(root, commit, domain):
    keys = []
    for person in domain.get("reviewers", []):
        key = person.get("ssh_public_key", "")
        if key and person.get("revoked") is not True:
            keys.append((person.get("principal", ""), key))
    if not keys:
        return "HUMAN_REQUIRED", "no trusted reviewer keys"
    with tempfile.TemporaryDirectory(prefix="artifact-review-signers-") as td:
        signers = os.path.join(td, "allowed signers")
        with open(signers, "w", encoding="utf-8", newline="\n") as out:
            for principal, key in keys:
                out.write(f'{principal} namespaces="git" {key.strip()}\n')
        opts = ["-c", "gpg.format=ssh", "-c", f"gpg.ssh.allowedSignersFile={signers}"]
        verified = git(root, *opts, "verify-commit", commit)
        info = git(root, *opts, "log", "-1", "--format=%G? %GS", commit).stdout.strip().split(maxsplit=1)
        if verified.returncode or len(info) != 2 or info[0] != "G" or not any(info[1] == p for p, _ in keys):
            return "HUMAN_REQUIRED", "review signature untrusted or invalid"
    return "PASS", "signed"
