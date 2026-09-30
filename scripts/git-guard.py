#!/usr/bin/env python3
"""rpg-factory git guard (v2) - PreToolUse hook for the Bash and PowerShell tools.

Reads the hook payload on stdin. For commands that run inside the RPG MMO workspace it
expands the command into the programs that will actually run, peeling wrappers and
recursing into nested shells, then classifies every git / gh invocation:

  - "deny"  creating, deleting or pushing tags (git tag, push --tags / tag refs, update-ref
            on tags, gh api .../git/refs|tags, gh release create) - agents never tag
  - "ask"   destructive or high-impact git (reset --hard, clean -f, checkout -- / -B,
            restore, stash, branch -D/-f, update-ref, gc --prune, reflog expire, rebase,
            filter-branch, any push, add -A, commit -a/--amend, commit/merge/cherry-pick/
            revert/am/pull --rebase/reset <commit> on a protected branch, submodule update,
            git -c alias.*), commands whose git use cannot be seen (interpreters with inline
            code, $VAR / $(...) as the program, encoded PowerShell), and registry
            human_gates[].match
Wrappers peeled: VAR=x, env, command, builtin, exec, sudo, doas, timeout, nohup, nice, time,
stdbuf, ionice, setsid, xargs, find -exec/-execdir. Nested: bash|sh|zsh|dash -c, eval,
cmd(.exe) /c|/k, powershell|pwsh -c|-Command, PowerShell `&` call operator.

Git run by a script file or a program is invisible to text analysis; scripts/tripwire.py
(PostToolUse) catches its effect and latches: afterwards this guard denies every
non-read-only command until the user acknowledges.

Never approves: no output + exit 0 = "no opinion". Any internal error = no opinion; each
part (git analysis, human gates, latch) fails independently. RPG_FACTORY_GUARD=off disables it.
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
GLOBAL_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "bash.exe", "sh.exe", "wsl", "wsl.exe"}
POWERSHELLS = {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}
CMDS = {"cmd", "cmd.exe"}
INTERPRETERS = {"python", "python3", "python.exe", "py", "node", "node.exe", "perl", "ruby", "php", "deno", "bun"}
CD_WORDS = {"cd", "pushd", "set-location", "sl", "push-location", "chdir"}
MUTATING_GIT_WORDS = {"reset", "clean", "checkout", "restore", "stash", "branch", "push", "add", "commit", "tag",
                      "submodule", "rebase", "merge", "cherry-pick", "revert", "am", "update-ref", "gc", "reflog",
                      "switch", "worktree", "filter-branch", "filter-repo", "pull", "rm", "mv", "apply", "prune"}
GIT_BUILTINS = MUTATING_GIT_WORDS | {"status", "log", "diff", "show", "fetch", "remote", "config", "rev-parse",
                                     "ls-files", "ls-remote", "ls-tree", "cat-file", "describe", "blame", "grep",
                                     "shortlog", "for-each-ref", "symbolic-ref", "check-ignore", "archive", "bisect",
                                     "clone", "init", "notes", "count-objects", "fsck", "help", "version", "diff-tree",
                                     "name-rev", "merge-base", "rev-list", "var", "whatchanged", "range-diff",
                                     "sparse-checkout", "maintenance", "repack", "replace", "format-patch",
                                     "request-pull", "bundle", "filter-repo"}
MAX_DEPTH = 4

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


def main_checkout(top):
    """The main checkout for a worktree (or the repo itself): parent of the common .git dir."""
    common = git_out(top, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common and os.path.basename(common.rstrip("/")) == ".git":
        return os.path.dirname(common.rstrip("/"))
    return top


def protected_patterns(repo_top, workspace, registry):
    main = os.path.abspath(main_checkout(repo_top)) if repo_top else None
    for repo in registry.get("repos", {}).values():
        if os.path.abspath(os.path.join(workspace, repo["path"])) in (repo_top, main):
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


def tokenize(command, shell="bash"):
    tokens = []
    for line in logical_lines(command):
        try:
            lex = shlex.shlex(line.replace("\\\n", " "), posix=True, punctuation_chars=";&|()")
            lex.whitespace_split = True
            if shell == "powershell":
                lex.escape = "`"  # PowerShell: backslash is a path separator, backtick escapes
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


def prog(tok):
    return os.path.basename(tok.replace("\\", "/")).lower()


def peel(seg):
    """Strip env assignments and wrapper programs; return the argv that really runs.

    xargs appends its stdin items to the command, so `echo v9 | xargs git tag` runs `git tag v9`:
    a placeholder argument is appended to keep `git tag` from looking like a tag listing."""
    i = 0
    via_xargs = False
    while i < len(seg):
        t = seg[i]
        p = prog(t)
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t):
            i += 1
        elif p == "env":
            i += 1
            while i < len(seg) and (seg[i].startswith("-") or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", seg[i])):
                i += 2 if seg[i] in {"-u", "--unset", "-C", "--chdir", "-S"} else 1
        elif p in {"command", "builtin", "exec", "nohup", "time", "setsid", "doas"}:
            i += 1
            while i < len(seg) and seg[i].startswith("-"):
                i += 1
        elif p == "sudo":
            i += 1
            while i < len(seg) and seg[i].startswith("-"):
                i += 2 if seg[i] in {"-u", "-g", "-h", "-p", "-C", "-D", "-R", "-T"} else 1
        elif p == "timeout":
            i += 1
            while i < len(seg) and seg[i].startswith("-"):
                i += 2 if seg[i] in {"-s", "--signal", "-k", "--kill-after"} else 1
            i += 1  # the duration
        elif p in {"nice", "ionice", "stdbuf", "chrt", "taskset"}:
            i += 1
            while i < len(seg) and (seg[i].startswith("-") or re.match(r"^\d+$", seg[i])):
                i += 1
        elif p == "xargs":
            via_xargs = True
            i += 1
            while i < len(seg) and seg[i].startswith("-"):
                i += 2 if seg[i] in {"-I", "-n", "-P", "-L", "-s", "-d", "-E", "-a"} else 1
        else:
            break
    return seg[i:] + (["__xargs_input__"] if via_xargs and seg[i:] else [])


def expand(command, depth=0, shell="bash"):
    """Yield the argv lists a command line will execute, recursing into nested shells."""
    if depth > MAX_DEPTH:
        yield ["__too_deep__"]
        return
    for seg in segments(tokenize(command, shell)):
        if seg and seg[0] == "&":  # PowerShell call operator: & 'git.exe' tag x
            seg = seg[1:]
        argv = peel(seg)
        if not argv:
            continue
        p = prog(argv[0])
        if p == "find":
            for k, t in enumerate(argv):
                if t in {"-exec", "-execdir", "-ok", "-okdir"}:
                    rest = []
                    for u in argv[k + 1:]:
                        if u in {";", "+", "\\;"}:
                            break
                        rest.append(u)
                    if rest:
                        yield from expand(shlex.join(rest), depth + 1)
            yield argv
            continue
        if p in SHELLS and len(argv) > 1:
            flags = [a for a in argv[1:] if a.startswith("-") and not a.startswith("--")]
            if any("c" in f.lstrip("-") for f in flags):
                idx = next((k for k, a in enumerate(argv[1:], 1) if not a.startswith("-")), None)
                if idx is not None:
                    yield from expand(argv[idx], depth + 1)
                    continue
            yield argv
            continue
        if p == "eval":
            yield from expand(" ".join(argv[1:]), depth + 1)
            continue
        if p in CMDS:
            for k, a in enumerate(argv[1:], 1):
                if a.lower() in {"/c", "/k"}:
                    yield from expand(" ".join(argv[k + 1:]), depth + 1)
                    break
            else:
                yield argv
            continue
        if p in POWERSHELLS:
            for k, a in enumerate(argv[1:], 1):
                al = a.lower()
                if al in {"-encodedcommand", "-enc", "-e", "-ec"}:
                    yield ["__opaque__", "encoded PowerShell command"]
                    break
                if al in {"-c", "-command", "-com"}:
                    yield from expand(" ".join(argv[k + 1:]), depth + 1, shell="powershell")
                    break
            else:
                yield argv
            continue
        yield argv


def parse_git(argv):
    """(cdir, subcommand, args, config_opts) or None if argv is not a git call."""
    if not argv or prog(argv[0]) not in ("git", "git.exe"):
        return None
    i, cdir, cfg = 1, None, []
    while i < len(argv) and argv[i].startswith("-"):
        if argv[i] in GLOBAL_OPTS_WITH_VALUE and i + 1 < len(argv):
            if argv[i] == "-C":
                cdir = argv[i + 1] if cdir is None else os.path.join(cdir, argv[i + 1])
            if argv[i] == "-c":
                cfg.append(argv[i + 1])
            i += 2
        else:
            i += 1
    if i >= len(argv):
        return None
    return cdir, argv[i], argv[i + 1:], cfg


def has_short_flag(args, letter):
    return any(re.match(r"^-[A-Za-z]*" + letter + r"[A-Za-z]*$", a) for a in args)


def refspec_dsts(args):
    out = []
    for x in args:
        if x.startswith("-"):
            continue
        out.append(x.split(":", 1)[1] if ":" in x else x)
    return [d.lstrip("+") for d in out]


def classify(sub, args, branch, patterns, cfg):
    """List of (decision, reason) for one git invocation."""
    R = []

    def ask(m):
        R.append(("ask", m))

    def deny(m):
        R.append(("deny", m))

    a = set(args)
    protected = bool(branch) and is_protected(branch, patterns)
    if any(c.lower().startswith("alias.") for c in cfg):
        ask("`git -c alias.*` defines an ad-hoc alias - the real operation cannot be checked")
    if sub == "reset":
        if a & {"--hard", "--merge", "--keep"}:
            ask("`git reset --hard/--merge/--keep` discards working-tree changes")
        elif protected and any(not x.startswith("-") for x in args):
            ask(f"`git reset <commit>` moves protected branch `{branch}`")
    elif sub == "clean" and (has_short_flag(args, "f") or "--force" in a):
        ask("`git clean -f` permanently deletes untracked files (user work, imported Unity samples)")
    elif sub == "checkout":
        if "--" in a or "." in a or has_short_flag(args, "f") or "--force" in a:
            ask("`git checkout -- <path>` / `checkout .` / `checkout -f` overwrites working-tree changes")
        if "-B" in a:
            ask("`git checkout -B` resets an existing branch to another commit")
    elif sub == "restore" and not (a & {"--staged", "-S"} and not a & {"--worktree", "-W"}):
        ask("`git restore` overwrites working-tree changes")
    elif sub == "stash" and (not args or args[0] in {"push", "save", "drop", "clear", "pop"} or args[0].startswith("-")):
        ask("`git stash` moves or drops uncommitted changes that may belong to the user")
    elif sub == "branch":
        if has_short_flag(args, "D") or ("--delete" in a and ("--force" in a or has_short_flag(args, "f"))):
            ask("`git branch -D` force-deletes a branch (unmerged work is lost)")
        elif has_short_flag(args, "f") or "--force" in a or has_short_flag(args, "M"):
            ask("`git branch -f/-M` moves or overwrites an existing branch")
    elif sub == "push":
        if "--tags" in a or "--follow-tags" in a or "--mirror" in a or any(re.match(TAG_REF, d) for d in refspec_dsts(args)):
            deny("pushing tags is a release action reserved for the lead (agents never tag)")
        if any(x == "--force" or x.startswith("--force-with-lease") or x.startswith("--force-if-includes") for x in args) \
                or has_short_flag(args, "f") or any(x.startswith("+") for x in args):
            ask("force push rewrites remote history")
        if "--delete" in a or has_short_flag(args, "d") or any(x.startswith(":") and len(x) > 1 for x in args):
            ask("push deletes a remote ref")
        if not R:
            ask("push publishes commits to the remote - only when the user asked for it")
    elif sub == "add" and (a & {"-A", "--all", ".", ":/", "*"} or has_short_flag(args, "A")):
        ask("`git add -A` / `add .` can stage pre-existing user changes; stage explicit paths")
    elif sub == "commit":
        if protected:
            ask(f"commit on protected branch `{branch}` - work on a feature branch (type/module/topic)")
        if "--amend" in a:
            ask("`git commit --amend` rewrites the previous commit")
        if "-a" in a or "--all" in a or has_short_flag([x for x in args if not x.startswith("--")], "a"):
            ask("`git commit -a` stages every modified tracked file, including the user's")
    elif sub in {"merge", "cherry-pick", "revert", "am"}:
        if protected and not a & {"--abort", "--quit", "--skip"}:
            ask(f"`git {sub}` creates commits on protected branch `{branch}`")
    elif sub == "pull":
        if protected and (a & {"--rebase", "-r", "--no-ff", "--squash"} or any(x.startswith("--rebase=") for x in args)):
            ask(f"`git pull --rebase/--no-ff/--squash` rewrites or merges into protected branch `{branch}`")
    elif sub == "tag":
        listing = (not args) or a & {"-l", "--list", "-v", "--verify", "--contains", "--points-at"} or all(x.startswith("-n") for x in args)
        if not listing:
            deny("creating/deleting tags is a release action reserved for the lead (agents never tag)")
    elif sub == "update-ref":
        if any(re.match(TAG_REF, x) for x in args if not x.startswith("-")):
            deny("`git update-ref` on a tag ref - agents never tag")
        else:
            ask("`git update-ref` rewrites a ref directly")
    elif sub == "gc" and any(x.startswith("--prune") for x in args):
        ask("`git gc --prune` permanently deletes unreachable objects (lost work becomes unrecoverable)")
    elif sub == "reflog" and args and args[0] in {"expire", "delete"}:
        ask(f"`git reflog {args[0]}` removes the recovery history")
    elif sub == "prune":
        ask("`git prune` permanently deletes unreachable objects")
    elif sub == "submodule" and args and args[0] in {"update", "deinit", "sync", "foreach"}:
        ask(f"`git submodule {args[0]}` changes submodule checkouts (the client's com.gdk.* state belongs to the user)")
    elif sub == "rebase" and not a & {"--abort", "--continue", "--skip", "--quit"}:
        ask("`git rebase` rewrites branch history")
    elif sub in {"filter-branch", "filter-repo", "replace"}:
        ask(f"`git {sub}` rewrites history")
    elif sub == "worktree" and args and args[0] in {"remove", "prune"} and ("--force" in a or has_short_flag(args, "f")):
        ask("`git worktree remove --force` deletes a worktree with its uncommitted changes")
    elif sub == "switch":
        if a & {"--discard-changes", "--force"} or has_short_flag(args, "f"):
            ask("`git switch --discard-changes/-f` discards working-tree changes")
        if "-C" in a or "--force-create" in a:
            ask("`git switch -C` resets an existing branch to another commit")
    return R


def classify_gh(argv):
    """Tag / release creation through the GitHub CLI or its REST API."""
    R = []
    if len(argv) < 2:
        return R
    sub = argv[1]
    text = " ".join(argv[2:])
    if sub == "release" and len(argv) > 2 and argv[2] in {"create", "upload", "edit"}:
        R.append(("deny", f"`gh release {argv[2]}` creates or changes a tag/release - agents never tag"))
    elif sub == "release" and len(argv) > 2 and argv[2] == "delete":
        R.append(("ask", "`gh release delete` removes a published release"))
    elif sub == "api":
        method = "GET"
        for k, x in enumerate(argv):
            if x in {"-X", "--method"} and k + 1 < len(argv):
                method = argv[k + 1].upper()
            elif x.startswith("--method=") or x.startswith("-X") and len(x) > 2:
                method = x.split("=", 1)[-1].replace("-X", "").upper()
        writes = method != "GET" or any(x in {"-f", "-F", "--field", "--raw-field", "--input"} for x in argv)
        if writes:
            if re.search(r"/git/tags\b", text) or (re.search(r"/git/refs\b", text) and re.search(r"refs/tags|/git/refs/tags", text)):
                R.append(("deny", "`gh api` tag creation/deletion - agents never tag"))
            elif re.search(r"/releases\b", text):
                R.append(("deny", "`gh api` release write - agents never tag/release"))
            elif re.search(r"/git/refs\b", text):
                R.append(("ask", "`gh api` writes a git ref on the remote"))
    return R


def new_branch_from(sub, args):
    flags = {"checkout": {"-b", "-B"}, "switch": {"-c", "-C", "--create", "--force-create"}}.get(sub)
    if not flags:
        return None
    for i, x in enumerate(args):
        if x in flags and i + 1 < len(args):
            return args[i + 1]
    return None


def evaluate(payload, registry):
    command = (payload.get("tool_input") or {}).get("command") or ""
    if not re.search(r"git|\bgh\b|\$|`|eval|python|node|perl|ruby|php|powershell|pwsh|cmd", command, re.I):
        return []
    shell = "powershell" if payload.get("tool_name") == "PowerShell" else "bash"
    cwd = payload.get("cwd") or os.getcwd()
    workspace = find_workspace(cwd, registry)
    reasons = []
    predicted_branch = {}
    # a command substitution used as the program: $(which git) reset / `which git` push
    verbs = "|".join(sorted(MUTATING_GIT_WORDS, key=len, reverse=True))
    if workspace and re.search(r"(^|[;&|(]\s*)(\$\([^)]*\)|`[^`]*`)\s+(" + verbs + r")\b", command):
        reasons.append(("ask", "the program is a command substitution followed by a git verb - cannot be checked"))
    for argv in expand(command, shell=shell):
        p = prog(argv[0])
        if p in CD_WORDS:
            target = next((x for x in argv[1:] if not x.startswith("-")), None)
            if target:
                cwd = os.path.normpath(os.path.join(cwd, os.path.expanduser(target.replace("\\", "/"))))
            continue
        ws = workspace or find_workspace(cwd, registry)
        if not ws:
            continue  # outside the workspace: not our business
        here = os.path.relpath(cwd, ws) if cwd.startswith(ws) else cwd
        if argv[0] == "__opaque__":
            reasons.append(("ask", f"[{here}] {argv[1]} - its contents cannot be checked"))
            continue
        if argv[0] == "__too_deep__":
            reasons.append(("ask", f"[{here}] shells nested deeper than {MAX_DEPTH} levels - cannot be checked"))
            continue
        if p in INTERPRETERS and any(x in {"-c", "-e", "--eval", "-p"} for x in argv[1:]) and re.search(r"\bgit\b", " ".join(argv[1:])):
            reasons.append(("ask", f"[{here}] `{p}` inline code invokes git - cannot be checked; run git directly"))
            continue
        if argv[0].startswith("$") or argv[0].startswith("`"):
            if any(x.lower() in MUTATING_GIT_WORDS for x in argv[1:3]):
                reasons.append(("ask", f"[{here}] the program is a variable/substitution (`{argv[0]}`) followed by a git verb - cannot be checked"))
            continue
        if p in {"gh", "gh.exe"}:
            for d, t in classify_gh(argv):
                reasons.append((d, f"[{here}] {t}"))
            continue
        parsed = parse_git(argv)
        if not parsed:
            continue
        cdir, sub, args, cfg = parsed
        eff = os.path.normpath(os.path.join(cwd, cdir)) if cdir else cwd
        if not os.path.abspath(eff).startswith(ws):
            continue
        top = git_out(eff, "rev-parse", "--show-toplevel")
        top = os.path.abspath(top) if top else None
        branch = predicted_branch.get(top) or (git_out(eff, "branch", "--show-current") if top else "")
        patterns = protected_patterns(top, ws, registry) if top else DEFAULT_PROTECTED
        where = os.path.relpath(top, ws) if top else os.path.relpath(eff, ws)
        if sub not in GIT_BUILTINS and top:
            alias = git_out(eff, "config", "--get", f"alias.{sub}")
            if alias:
                if alias.startswith("!"):
                    reasons.append(("ask", f"[{where}] git alias `{sub}` runs a shell command - cannot be checked"))
                    continue
                parts = shlex.split(alias)
                sub, args = parts[0], parts[1:] + args
        created = new_branch_from(sub, args)
        for d, t in classify(sub, args, branch, patterns, cfg):
            reasons.append((d, f"[{where}] {t}"))
        if created and top:
            predicted_branch[top] = created
    return reasons


def human_gate_hits(payload, registry):
    """Registry human_gates with a `match` regex, applied to every expanded command inside the workspace."""
    command = (payload.get("tool_input") or {}).get("command") or ""
    tool = payload.get("tool_name") or "Bash"
    cwd = payload.get("cwd") or os.getcwd()
    if not find_workspace(cwd, registry) and not any(find_workspace(os.path.expanduser(t), registry)
                                                     for t in re.findall(r"(/[^\s'\"]+)", command)):
        return []
    shell = "powershell" if tool == "PowerShell" else "bash"
    texts = {" ".join(seg) for seg in segments(tokenize(command))}
    texts |= {" ".join(argv) for argv in expand(command, shell=shell)}
    hits = []
    for text in texts:
        for g in registry.get("human_gates", []):
            m = g.get("match")
            if not m or tool not in g.get("tools", ["Bash", "PowerShell"]):
                continue
            try:
                matched = re.search(m, text)
            except re.error:  # one bad registry regex must not disable the rest of the guard
                continue
            if matched:
                hits.append((g.get("decision", "ask"), f"human gate '{g['id']}': {g['rule']}"))
    return hits


def latch_hits(payload, registry):
    """After the tripwire detected an unauthorized mutation, only read-only commands may run."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import tripwire  # noqa: E402
    latch = tripwire.latched(payload)
    if latch and not tripwire.is_read_only(payload):
        return [("deny", f"tripwire latched - {latch}. Stop and report it to the user; they clear it with "
                         f"`python3 {os.path.join(PLUGIN_ROOT, 'scripts', 'tripwire.py')} --ack`")]
    return []


def main():
    if os.environ.get("RPG_FACTORY_GUARD", "").lower() in {"off", "0", "false"}:
        return 0
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if payload.get("tool_name") not in (None, "Bash", "PowerShell"):
        return 0
    registry = load_registry()
    if not registry:
        return 0
    reasons = []
    for part in (latch_hits, evaluate, human_gate_hits):  # isolated: a failure in one never drops the others
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
