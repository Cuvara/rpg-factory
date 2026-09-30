#!/usr/bin/env python3
"""rpg-factory git guard - PreToolUse(Bash) hook.

Reads the hook payload on stdin. For git commands that run inside the RPG MMO
workspace and are destructive or high-impact, prints a PreToolUse decision of
"ask" with the reasons, so the user confirms even when an allow rule or a
permissive permission mode would otherwise run the command silently.

Decisions:
  - "deny" for creating/deleting tags and pushing tags (global rule: agents never tag).
  - "ask" for every other guarded git operation and for Bash commands matching a
    registry human_gates[].match regex (kubectl/helm/ssh, workflow dispatch, secrets,
    toggle-packages.sh, local stack) - human_gates[].decision may raise it to "deny".
Never approves: no output + exit 0 means "no opinion" and the normal permission flow
applies. Any internal error also means no opinion.

Disable for one session with RPG_FACTORY_GUARD=off.
"""
import json
import os
import re
import shlex
import subprocess
import sys

DEFAULT_PROTECTED = ["develop", "staging", "main", "master", "release-*"]
TAG_REF = r"^(refs/tags/|v\d|sgl-v\d|core-baseline)"
SEPARATORS = {";", "&&", "||", "|", "&", "(", ")", "\n"}
# git global options that take a separate value argument
GLOBAL_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}

PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_registry():
    try:
        with open(os.path.join(PLUGIN_ROOT, "registry.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def find_workspace(start, registry):
    markers = registry["workspace"]["root_markers"]
    candidates = []
    env_root = os.environ.get(registry["workspace"].get("root_env", ""), "")
    if env_root:
        candidates.append(env_root)
    d = os.path.abspath(start)
    while True:
        candidates.append(d)
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    for c in candidates:
        if all(os.path.exists(os.path.join(c, m)) for m in markers):
            return os.path.abspath(c)
    return None


def git_out(cwd, *args):
    try:
        r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def protected_patterns(repo_top, workspace, registry):
    for repo in registry.get("repos", {}).values():
        if os.path.abspath(os.path.join(workspace, repo["path"])) == repo_top:
            return repo.get("protected_branches", DEFAULT_PROTECTED)
    return DEFAULT_PROTECTED


def is_protected(branch, patterns):
    for p in patterns:
        if p.endswith("*") and branch.startswith(p[:-1]):
            return True
        if branch == p:
            return True
    return False


HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def logical_lines(command):
    """Split on newlines outside quotes; drop heredoc bodies (they are data, not commands)."""
    lines, buf, quote, escape = [], [], None, False
    for ch in command:
        if escape:
            buf.append(ch)
            escape = False
            continue
        if ch == "\\" and quote != "'":
            escape = True
            buf.append(ch)
            continue
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "\n":
            lines.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    lines.append("".join(buf))
    out, delimiter = [], None
    for line in lines:
        if delimiter is not None:
            if line.strip() == delimiter:
                delimiter = None
            continue
        out.append(line)
        m = HEREDOC.search(line)
        if m:
            delimiter = m.group(2)
    return out


def tokenize(command):
    tokens = []
    for line in logical_lines(command):
        try:
            lex = shlex.shlex(line.replace("\\\n", " "), posix=True, punctuation_chars=";&|()")
            lex.whitespace_split = True
            tokens.extend(list(lex))
        except ValueError:
            tokens.extend(line.split())
        tokens.append("\n")
    return tokens


def segments(tokens):
    seg = []
    for t in tokens:
        if t in SEPARATORS or (t and set(t) <= set(";&|()")):
            if seg:
                yield seg
            seg = []
        else:
            seg.append(t)
    if seg:
        yield seg


def parse_git(seg):
    """Return (git_dir_override, subcommand, args) or None if seg is not a git call."""
    i = 0
    while i < len(seg) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", seg[i]):  # VAR=x git ...
        i += 1
    if i >= len(seg) or os.path.basename(seg[i]) not in ("git", "git.exe"):
        return None
    i += 1
    cdir = None
    while i < len(seg) and seg[i].startswith("-"):
        if seg[i] in GLOBAL_OPTS_WITH_VALUE and i + 1 < len(seg):
            if seg[i] == "-C":
                cdir = seg[i + 1] if cdir is None else os.path.join(cdir, seg[i + 1])
            i += 2
        else:
            i += 1
    if i >= len(seg):
        return None
    return cdir, seg[i], seg[i + 1:]


def has_short_flag(args, letter):
    return any(re.match(r"^-[A-Za-z]*" + letter + r"[A-Za-z]*$", a) for a in args)


def classify(sub, args, branch, patterns):
    """Return a list of reasons this git call needs confirmation."""
    reasons = []
    a = set(args)
    if sub == "reset" and a & {"--hard", "--merge", "--keep"}:
        reasons.append("`git reset --hard/--merge/--keep` discards working-tree changes")
    elif sub == "clean" and (has_short_flag(args, "f") or "--force" in a):
        reasons.append("`git clean -f` permanently deletes untracked files (user work, imported Unity samples)")
    elif sub == "checkout" and ("--" in a or "." in a or has_short_flag(args, "f") or "--force" in a):
        reasons.append("`git checkout -- <path>` / `checkout .` / `checkout -f` overwrites working-tree changes")
    elif sub == "restore" and not (a & {"--staged", "-S"} and not a & {"--worktree", "-W"}):
        reasons.append("`git restore` overwrites working-tree changes")
    elif sub == "stash" and (not args or args[0] in {"push", "save", "drop", "clear", "pop"} or args[0].startswith("-")):
        reasons.append("`git stash` moves or drops uncommitted changes that may belong to the user")
    elif sub == "branch" and (has_short_flag(args, "D") or ("--delete" in a and ("--force" in a or has_short_flag(args, "f")))):
        reasons.append("`git branch -D` force-deletes a branch (unmerged work is lost)")
    elif sub == "push":
        if "--tags" in a or "--follow-tags" in a or any(re.match(TAG_REF, x.lstrip("+:")) for x in args):
            reasons.append(("deny", "pushing tags is a release action reserved for the lead (agents never tag)"))
        if any(x == "--force" or x.startswith("--force-with-lease") or x.startswith("--force-if-includes") for x in args) or has_short_flag(args, "f") or any(x.startswith("+") for x in args):
            reasons.append("force push rewrites remote history")
        if "--delete" in a or has_short_flag(args, "d") or any(x.startswith(":") and len(x) > 1 for x in args):
            reasons.append("push deletes a remote ref")
        if not reasons:
            reasons.append("push publishes commits to the remote - only when the user asked for it")
    elif sub == "add" and (a & {"-A", "--all", ".", ":/", "*"} or has_short_flag(args, "A")):
        reasons.append("`git add -A` / `add .` can stage pre-existing user changes; stage explicit paths")
    elif sub == "commit":
        if branch and is_protected(branch, patterns):
            reasons.append(f"commit on protected branch `{branch}` - work on a feature branch (type/module/topic)")
        if "--amend" in a:
            reasons.append("`git commit --amend` rewrites the previous commit")
        if "-a" in a or "--all" in a or has_short_flag([x for x in args if not x.startswith("--")], "a"):
            reasons.append("`git commit -a` stages every modified tracked file, including the user's")
    elif sub == "tag":
        listing = (not args) or a & {"-l", "--list", "-v", "--verify", "--contains", "--points-at"} or all(x.startswith("-n") for x in args)
        if not listing:
            reasons.append(("deny", "creating/deleting tags is a release action reserved for the lead (agents never tag)"))
    elif sub == "submodule" and args and args[0] in {"update", "deinit", "sync", "foreach"}:
        reasons.append(f"`git submodule {args[0]}` changes submodule checkouts (the client's com.gdk.* state belongs to the user)")
    elif sub == "rebase" and not a & {"--abort", "--continue", "--skip", "--quit"}:
        reasons.append("`git rebase` rewrites branch history")
    elif sub in {"filter-branch", "filter-repo"}:
        reasons.append(f"`git {sub}` rewrites history")
    elif sub == "worktree" and args and args[0] in {"remove", "prune"} and ("--force" in a or has_short_flag(args, "f")):
        reasons.append("`git worktree remove --force` deletes a worktree with its uncommitted changes")
    elif sub == "switch" and (a & {"--discard-changes", "--force"} or has_short_flag(args, "f")):
        reasons.append("`git switch --discard-changes/-f` discards working-tree changes")
    return reasons


def new_branch_from(sub, args):
    """Branch name created and checked out by `checkout -b X` / `switch -c X`, else None."""
    flags = {"checkout": {"-b", "-B"}, "switch": {"-c", "-C", "--create", "--force-create"}}.get(sub)
    if not flags:
        return None
    for i, x in enumerate(args):
        if x in flags and i + 1 < len(args):
            return args[i + 1]
    return None


def evaluate(payload, registry):
    command = (payload.get("tool_input") or {}).get("command") or ""
    if "git" not in command:
        return []
    cwd = payload.get("cwd") or os.getcwd()
    workspace = find_workspace(cwd, registry)
    reasons = []
    predicted_branch = {}  # repo top -> branch after a same-command checkout -b
    for seg in segments(tokenize(command)):
        if seg[0] == "cd" and len(seg) > 1:
            cwd = os.path.normpath(os.path.join(cwd, os.path.expanduser(seg[1])))
            continue
        parsed = parse_git(seg)
        if not parsed:
            continue
        cdir, sub, args = parsed
        eff = os.path.normpath(os.path.join(cwd, cdir)) if cdir else cwd
        ws = workspace or find_workspace(eff, registry)
        if not ws or not os.path.abspath(eff).startswith(ws):
            continue  # outside the workspace: not our business
        top = git_out(eff, "rev-parse", "--show-toplevel")
        top = os.path.abspath(top) if top else None
        branch = predicted_branch.get(top) or (git_out(eff, "branch", "--show-current") if top else "")
        patterns = protected_patterns(top, ws, registry) if top else DEFAULT_PROTECTED
        created = new_branch_from(sub, args)
        if created and top:
            predicted_branch[top] = created
        where = os.path.relpath(top, ws) if top else os.path.relpath(eff, ws)
        for r in classify(sub, args, branch, patterns):
            decision, text = r if isinstance(r, tuple) else ("ask", r)
            reasons.append((decision, f"[{where}] {text}"))
    return reasons


def human_gate_hits(payload, registry):
    """Registry human_gates with a `match` regex, applied to each command segment inside the workspace."""
    command = (payload.get("tool_input") or {}).get("command") or ""
    cwd = payload.get("cwd") or os.getcwd()
    if not find_workspace(cwd, registry) and not any(find_workspace(os.path.expanduser(t), registry)
                                                     for t in re.findall(r"(/[^\s'\"]+)", command)):
        return []
    hits = []
    for seg in segments(tokenize(command)):
        text = " ".join(seg)
        for g in registry.get("human_gates", []):
            m = g.get("match")
            if not m:
                continue
            try:
                matched = re.search(m, text)
            except re.error:  # one bad registry regex must not disable the rest of the guard
                continue
            if matched:
                hits.append((g.get("decision", "ask"), f"human gate '{g['id']}': {g['rule']}"))
    return hits


def main():
    if os.environ.get("RPG_FACTORY_GUARD", "").lower() in {"off", "0", "false"}:
        return 0
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if payload.get("tool_name") not in (None, "Bash"):
        return 0
    registry = load_registry()
    if not registry:
        return 0
    reasons = []
    for part in (evaluate, human_gate_hits):  # isolated: a failure in one never drops the other
        try:
            reasons += part(payload, registry)
        except Exception:  # a guard bug must never break the session
            pass
    if not reasons:
        return 0
    decision = "deny" if any(d == "deny" for d, _ in reasons) else "ask"
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": "rpg-factory guard: " + "; ".join(dict.fromkeys(t for _, t in reasons)),
        }
    }, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
