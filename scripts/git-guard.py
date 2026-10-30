#!/usr/bin/env python3
"""rpg-factory git guard (v2) - PreToolUse hook for the Bash and PowerShell tools.

Reads the hook payload on stdin. For commands that run inside the RPG MMO workspace (or in a linked worktree
outside it whose main checkout is in the workspace, e.g. an Orca worktree: that checkout's rules apply) it
expands the command into the programs that will actually run, peeling wrappers and
recursing into nested shells, then classifies every git / gh invocation. Advisory only (1.0.3): the
hook never asks the user and never blocks; a match is returned as additionalContext
"rpg-factory advisory (<level>): ..." for the agent to weigh. Internally a finding is a
("deny", reason) or ("ask", reason) tuple; "deny" is reported as advisory level high and "ask" as
level warn - neither is a permission decision:

  - high    creating, deleting or pushing tags (git tag, push --tags / tag refs, update-ref
            on tags, gh api .../git/refs|tags, gh release create) - release actions, only with explicit release authorization in the current task
  - warn    destructive or high-impact git (reset --hard, clean -f, checkout -- / -B,
            restore, stash, branch -D/-f, update-ref, gc --prune, reflog expire, rebase,
            filter-branch, any push, add -A, commit -a/--amend, commit/merge/cherry-pick/
            revert/am/pull --rebase/reset <commit> on a protected branch, submodule update,
            git -c alias.*), commands whose git use cannot be seen (interpreters with inline
            code or a heredoc, $VAR / $(...) as the program, encoded PowerShell), and registry
            human_gates[].match
Wrappers peeled: VAR=x, env, command, builtin, exec, sudo, doas, timeout, nohup, nice, time,
stdbuf, ionice, setsid, xargs, find -exec/-execdir, and leading shell reserved words ({ ! if then
else elif do while until, `name()` / `function name` headers; PowerShell script-block braces).
Nested: bash|sh|zsh|dash -c, a heredoc fed to a shell (`bash <<EOF`, `cat <<EOF | sh`), eval,
cmd(.exe) /c|/k, powershell|pwsh -c|-Command, PowerShell `&` call operator. On Windows, git-bash
paths (/c/..., /mnt/c/...) are mapped to drive paths before they are resolved.

Git run by a script file or a program is invisible to text analysis (documented limitation).
A declared Factory execution mode (scripts/factory_session.py) flags state changes in analyze/plan/review.

Never approves or denies: no output + exit 0 = "no opinion", advisory output = still no decision. Any
internal error = no opinion; each
part (git analysis, human gates, mode) fails independently. RPG_FACTORY_GUARD=off disables it.
"""
import io
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
MAX_COMMAND = 200_000  # characters; longer commands are not analysed (shlex on them takes minutes)
# git subcommands whose classification never depends on the branch or the repo: no git calls needed for them
STATELESS_READ_GIT = {"status", "log", "diff", "show", "rev-parse", "ls-files", "ls-remote", "ls-tree", "cat-file",
                      "describe", "blame", "grep", "shortlog", "for-each-ref", "check-ignore", "merge-base", "rev-list",
                      "name-rev", "count-objects", "help", "version", "range-diff", "diff-tree", "whatchanged", "var"}
# shell reserved words that can start a segment in front of the command that really runs
RESERVED_LEAD = {"{", "}", "!", "if", "then", "else", "elif", "do", "while", "until", "elseif", "try", "finally"}


def native_path(p, nt=None):
    """A git-bash path as the OS resolves it. Python on Windows reads `/c/ws` as `C:\\c\\ws` (rooted on the
    current drive) and `/mnt/c/ws` as `C:\\mnt\\c\\ws`; git-bash and WSL mean `C:/ws`. Elsewhere unchanged."""
    if not p or not (os.name == "nt" if nt is None else nt):
        return p
    m = re.match(r"^/mnt/([A-Za-z])(/|$)", p) or re.match(r"^/([A-Za-z])(/|$)", p)
    return f"{m.group(1).upper()}:/{p[m.end():]}" if m else p

PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_registry():
    try:
        with open(os.path.join(PLUGIN_ROOT, "registry.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def find_workspace(start, registry):
    """The workspace containing `start` (nearest ancestor with every root marker), else the env root.
    The cwd wins: an env root exported for one workspace must never hide another workspace the command
    actually runs in (the guard would see "outside the workspace" and let a tag through)."""
    markers = registry["workspace"]["root_markers"]
    candidates = []
    d = os.path.abspath(start)
    while True:
        candidates.append(d)
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    env_root = os.environ.get(registry["workspace"].get("root_env", ""), "")
    if env_root:
        candidates.append(env_root)
    for c in candidates:
        if all(os.path.exists(os.path.join(c, m)) for m in markers):
            return os.path.abspath(c)
    return None


def within(path, root):
    """True when `path` is `root` or below it. Compares normalised paths (Windows: forward vs back slashes,
    case), not strings: a payload cwd of `C:/ws/x` must match a workspace found with backslashes."""
    a, b = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(root))
    return a == b or a.startswith(b.rstrip("/\\") + os.sep)


def git_out(cwd, *args):
    try:
        r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def main_checkout(top):
    """The main checkout for a worktree (or the repo itself): parent of the common .git dir."""
    common = git_out(top, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common and os.path.basename(common.rstrip("/")) == ".git":
        return os.path.dirname(common.rstrip("/"))
    return top


def linked_worktree(d):
    """(toplevel, main checkout) when directory d is inside a linked worktree, read from its `.git` file
    (`gitdir: <main>/.git/worktrees/<name>`) without running git; else None. A `.git` directory (a main checkout),
    a submodule's `.git` file (`.git/modules/`) or no `.git` at all is None. Any error is None."""
    try:
        while d and not os.path.isdir(d):
            d = os.path.dirname(d) if os.path.dirname(d) != d else ""
        while d:
            dot = os.path.join(d, ".git")
            if os.path.isdir(dot):
                return None
            if os.path.isfile(dot):
                with open(dot, encoding="utf-8", errors="replace") as f:
                    line = f.readline().strip()
                if not line.startswith("gitdir:"):
                    return None
                gd = os.path.normpath(os.path.join(d, line[7:].strip()))
                parts = gd.replace("\\", "/").rsplit("/.git/worktrees/", 1)
                return (os.path.abspath(d), os.path.abspath(parts[0])) if len(parts) == 2 else None
            parent = os.path.dirname(d)
            d = "" if parent == d else parent
    except (OSError, ValueError):
        return None
    return None


def outside_workspace(eff, registry, cache):
    """(workspace, main checkout) for a directory outside every workspace that is a linked worktree whose main
    checkout lies in a workspace (an Orca worktree of a workspace repo): git there gets that checkout's rules.
    No git call (the worktree's `.git` file names its main checkout), memoised per hook call; any error or a main
    checkout outside the workspace = None (no opinion)."""
    if eff not in cache:
        cache[eff] = None
        lw = linked_worktree(eff)
        if lw:
            main = lw[1]
            ws = find_workspace(main, registry)
            if ws and within(main, ws) and os.path.normcase(main) != os.path.normcase(os.path.abspath(ws)):
                cache[eff] = (ws, main)
    return cache[eff]


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
    out, stack = [], []  # stack of [delimiter, reader, body lines]
    for line in lines:
        if stack and line.strip() == stack[-1][0]:
            _, reader, body = stack.pop()
            if reader and reader != "shell" and re.search(r"\b(git|gh)\b", "\n".join(body)):
                out.append(f"__opaque__ '`{reader}` code from a heredoc invokes git/gh'")
            continue
        if stack and stack[-1][1] != "shell":
            stack[-1][2].append(line)  # data (or interpreter code): not shell commands
            continue
        out.append(line)  # a command line - also the body of a heredoc that a shell executes
        m = HEREDOC.search(line)
        if m:
            stack.append([m.group(2), heredoc_reader(line), []])
    return out


def _stdin_reader(argv):
    """'shell' when argv is a shell that executes its stdin, the interpreter's name when it is an interpreter
    reading its program from stdin, else None."""
    argv = peel(argv)
    if not argv:
        return None
    p = prog(argv[0])
    opts = [a for a in argv[1:] if a.startswith("-") and a != "-"]
    rest = [a for a in argv[1:] if not a.startswith("-") or a == "-"]
    if p in SHELLS:
        if any("c" in o.lstrip("-") for o in opts if not o.startswith("--")):
            return None  # `bash -c '...' <<EOF`: the script is the argument, the heredoc is its data
        return "shell" if "-s" in opts or not rest or rest[0] == "-" else None
    if p in INTERPRETERS:
        if any(o in {"-c", "-e", "--eval", "-p", "-m", "-r"} for o in opts):
            return None
        return p if not rest or rest[0] == "-" else None
    return None


def heredoc_reader(line):
    """Who reads the heredoc started on `line`: the command carrying `<<`, or - when that is a passthrough like
    cat - the next command of its pipeline (`cat <<EOF | sh`). Returns 'shell', an interpreter name or None."""
    try:
        lex = shlex.shlex(line, posix=True, punctuation_chars=";&|()")
        lex.whitespace_split = True
        toks = list(lex)
    except ValueError:
        return None
    pipeline, cur, found = [], [], None
    for t in toks + [";"]:
        if t == "|":
            pipeline.append(cur)
            cur = []
        elif t in SEPARATORS or (t and set(t) <= set(";&|()")):
            pipeline.append(cur)
            if found is not None:
                break
            pipeline, cur = [], []
        else:
            if t.startswith("<<") and found is None:
                found = len(pipeline)
            cur.append(t)
    if found is None:
        return None
    first, skip, to_file = [], False, False
    for t in pipeline[found]:  # the command without its heredoc / redirection words
        if skip:
            skip = False
            continue
        if t in {"<<", "<<-", ">", ">>", "<"}:
            skip = True
            to_file = to_file or t.startswith(">")
            continue
        if t.startswith(("<<", ">", "<")) or re.match(r"^\d*>", t):
            to_file = to_file or (t.startswith(">") or re.match(r"^1?>", t) is not None)
            continue
        first.append(t)
    reader = _stdin_reader(first)
    if reader is None and not to_file and first and prog(first[0]) in {"cat", "tee"} and len(first) == 1 \
            and found + 1 < len(pipeline):
        reader = _stdin_reader(pipeline[found + 1])
    return reader


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


def segments(tokens, shell="bash"):
    """Simple commands of a token stream. PowerShell script-block braces end a command too
    (`if ($x) { git tag v1 }` has no `;` before the `}`)."""
    seg = []
    for t in tokens:
        if t in SEPARATORS or (t and set(t) <= set(";&|()")) or (shell == "powershell" and t in {"{", "}"}):
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
    a placeholder argument is appended to keep `git tag` from looking like a tag listing.
    Leading reserved words (`{ git tag v1; }`, `! git tag`, `then git tag`, `do git tag`) and function
    headers (`function f { ...`) are not programs: the command after them is what runs."""
    i = 0
    via_xargs = False
    while i < len(seg):
        t = seg[i]
        p = prog(t)
        if t in RESERVED_LEAD:
            i += 1
        elif t == "function" and i + 1 < len(seg):
            i += 2  # `function name` (its `()` is a separator token)
        elif re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t):
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
    for seg in segments(tokenize(command, shell), shell):
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
                d = native_path(argv[i + 1])
                cdir = d if cdir is None else os.path.join(cdir, d)
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


TAG_LIST_MODES = ("-l", "--list", "-v", "--verify", "--contains", "--no-contains", "--merged", "--no-merged", "--points-at")
TAG_RO = {"-i", "--ignore-case", "--column", "--no-column", "--color", "--no-color", "--omit-empty"}
# `--sort <key>` as a separate word only for a full, unabbreviated key: `-v:refname` (abbreviated, starts
# like the -v option) stays ambiguous, so a separate word after --sort is never mistaken for a listing
SORT_KEY = re.compile(r"-?(version:)?(refname|creatordate|taggerdate|committerdate|authordate|objectname|"
                      r"objecttype|objectsize|taggername|taggeremail|subject|body|contents|tag|type|object|"
                      r"creator|tagger|committer|author)(:[a-z]+)?")


def tag_listing(args):
    """True when `git tag <args>` only lists. --contains/--no-contains/--merged/--no-merged/--points-at imply
    --list (git: any further word is a pattern or the commit they take); otherwise only listing options and
    their values may follow, so no separate word can be a tag name."""
    if not args or any(x in TAG_LIST_MODES or x.startswith(tuple(m + "=" for m in TAG_LIST_MODES[4:])) for x in args):
        return True
    i = 0
    while i < len(args):
        x = args[i]
        if x.startswith("-n") or x in TAG_RO or x.startswith(("--sort=", "--format=", "--color=", "--column=")):
            i += 1
        elif x == "--sort" and i + 1 < len(args) and SORT_KEY.fullmatch(args[i + 1]):
            i += 2
        elif x == "--format" and i + 1 < len(args) and "%(" in args[i + 1]:
            i += 2
        else:
            return False
    return True


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
        names = [x for x in args if not x.startswith("-")]
        if has_short_flag(args, "m") or has_short_flag(args, "M") or "--move" in a:
            if any(is_protected(n, patterns) for n in names) or (len(names) < 2 and protected):
                ask("`git branch -m` renames a protected branch")
        if (has_short_flag(args, "d") or "--delete" in a) and any(is_protected(n, patterns) for n in names):
            ask("`git branch -d` deletes a protected branch")
        if has_short_flag(args, "D") or ("--delete" in a and ("--force" in a or has_short_flag(args, "f"))):
            ask("`git branch -D` force-deletes a branch (unmerged work is lost)")
        elif has_short_flag(args, "f") or "--force" in a or has_short_flag(args, "M"):
            ask("`git branch -f/-M` moves or overwrites an existing branch")
    elif sub == "push":
        if "--tags" in a or "--follow-tags" in a or "--mirror" in a or any(re.match(TAG_REF, d) for d in refspec_dsts(args)):
            deny("pushing tags is a release action (only with explicit release authorization in the current task)")
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
        if protected and not a & {"--abort", "--quit", "--skip"} and not (sub == "merge" and "--ff-only" in a):
            ask(f"`git {sub}` creates commits on protected branch `{branch}`")
    elif sub == "pull":
        if protected and (a & {"--rebase", "-r", "--no-ff", "--squash"} or any(x.startswith("--rebase=") and x[9:].lower() not in {"false", "no", "off", "0"} for x in args)):
            ask(f"`git pull --rebase/--no-ff/--squash` rewrites or merges into protected branch `{branch}`")
        elif protected and "--ff-only" not in a:
            ask(f"`git pull` may create a merge commit on protected branch `{branch}` - use `git pull --ff-only`")
    elif sub == "fetch":
        dsts = [x.split(":", 1)[1] for x in args if not x.startswith("-") and ":" in x]
        if "--update-head-ok" in a or any(d and not d.lstrip("+").startswith("refs/remotes/") for d in dsts) \
                or any(x.startswith("+") and ":" in x and not x.split(":", 1)[1].startswith("refs/remotes/") for x in args):
            if any(re.match(TAG_REF, d.lstrip("+")) for d in dsts):
                deny("`git fetch` into a tag ref - a release action (only with explicit release authorization in the current task)")
            else:
                ask("`git fetch <src>:<dst>` writes a local branch directly (can force-move it)")
    elif sub == "remote" and args and args[0] in {"add", "set-url", "remove", "rm", "rename", "set-branches", "set-head"}:
        ask(f"`git remote {args[0]}` changes where this repo fetches from / pushes to")
    elif sub == "config":
        reading = a & {"--get", "--get-all", "--get-regexp", "-l", "--list", "--get-urlmatch", "--show-origin", "--show-scope"} \
            or (args and args[0] in {"get", "list"})
        keys = [x for x in args if not x.startswith("-")]
        risky = r"^(alias\.|remote\..*\.(url|pushurl)$|url\..*\.(insteadof|pushinsteadof)$|core\.hookspath$|core\.sshcommand$|credential\.)"
        if not reading and keys and re.match(risky, keys[1 if keys[0] in {"set", "unset"} and len(keys) > 1 else 0].lower()):
            ask("`git config` changes an alias, remote URL, URL rewrite, hooks path or credential helper")
    elif sub == "symbolic-ref" and len([x for x in args if not x.startswith("-")]) >= 2:
        ask("`git symbolic-ref` repoints a ref (HEAD) directly")
    elif sub == "tag":
        if not tag_listing(args):
            deny("creating/deleting tags is a release action (only with explicit release authorization in the current task)")
    elif sub == "update-ref":
        if any(re.match(TAG_REF, x) for x in args if not x.startswith("-")):
            deny("`git update-ref` on a tag ref - a release action (only with explicit release authorization in the current task)")
        else:
            ask("`git update-ref` rewrites a ref directly")
    elif sub == "gc" and any(x.startswith("--prune") for x in args):
        ask("`git gc --prune` permanently deletes unreachable objects (lost work becomes unrecoverable)")
    elif sub == "reflog" and args and args[0] in {"expire", "delete"}:
        ask(f"`git reflog {args[0]}` removes the recovery history")
    elif sub == "prune":
        ask("`git prune` permanently deletes unreachable objects")
    elif sub == "submodule" and args and args[0] in {"update", "deinit", "sync", "foreach", "add", "set-url", "set-branch", "absorbgitdirs"}:
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


GH_READ = {  # gh <group> <verb> that only read
    "pr": {"list", "view", "diff", "checks", "status"}, "run": {"list", "view", "watch", "download"},
    "workflow": {"list", "view"}, "release": {"list", "view", "download"}, "repo": {"view", "list", "clone"},
    "issue": {"list", "view", "status"}, "label": {"list"}, "cache": {"list"}, "secret": {"list"},
    "variable": {"list", "get"}, "ruleset": {"list", "view", "check"}, "gist": {"list", "view"},
    "extension": {"list"}, "config": {"get", "list"}, "auth": {"status", "token"}, "org": {"list"},
    "project": {"list", "view", "field-list", "item-list"},
}
GH_READ_GROUPS = {"status", "search", "browse", "help", "version", "completion", "alias"}
GH_FIELD_FLAGS = {"-f", "-F", "--field", "--raw-field", "--input"}
TAGGISH = r"refs/tags|/git/tags\b|\bcreateTag\b|\bcreateRelease\b|\bupdateRelease\b|/releases\b"


def gh_api_request(argv):
    """(method, endpoint, text) of `gh api ...` as gh itself decides it: -X/--method wins, otherwise any
    field / --input makes it POST, otherwise GET. `graphql` is a POST whose query says what it does."""
    method, endpoint, fields = None, None, []
    i = 2
    while i < len(argv):
        x = argv[i]
        if x in {"-X", "--method"} and i + 1 < len(argv):
            method = argv[i + 1].upper(); i += 2; continue
        if x.startswith("--method="):
            method = x.split("=", 1)[1].upper(); i += 1; continue
        if x.startswith("-X") and len(x) > 2:
            method = x[2:].upper(); i += 1; continue
        if x in GH_FIELD_FLAGS and i + 1 < len(argv):
            fields.append(argv[i + 1]); i += 2; continue
        if x in {"-H", "--header", "-q", "--jq", "-t", "--template", "--hostname", "--cache", "-p", "--preview"} and i + 1 < len(argv):
            i += 2; continue
        if not x.startswith("-") and endpoint is None:
            endpoint = x
        i += 1
    if method is None:
        method = "POST" if fields or "--input" in argv else "GET"
    return method, endpoint or "", " ".join(fields)


GH_GLOBAL_VALUE = {"-R", "--repo", "--hostname"}


def gh_normalise(argv):
    """`gh --repo o/r release create v1` -> `gh release create v1`: the repository / host selectors in front of the
    group or the verb are dropped, so they never hide what runs. Later words (arguments) stay."""
    out, i, words = [argv[0]], 1, 0
    while i < len(argv):
        x = argv[i]
        if words < 2 and x in GH_GLOBAL_VALUE:
            i += 2
            continue
        if words < 2 and x.startswith(tuple(f + "=" for f in GH_GLOBAL_VALUE)):
            i += 1
            continue
        if words < 2 and re.match(r"^-R\S", x):
            i += 1
            continue
        if not x.startswith("-"):
            words += 1
        out.append(x)
        i += 1
    return out


def classify_gh(argv):
    """GitHub CLI: reads pass; tag/release creation and repository deletion get advisory level high (release
    actions only with explicit release authorization in the current task, never delete repos); every other remote
    mutation gets advisory level warn. Remote-only effects never show in a local checkout, so this is the only
    line of defence for them."""
    R = []
    argv = gh_normalise(argv)
    if len(argv) < 2:
        return R
    group = argv[1]
    verb = argv[2] if len(argv) > 2 else ""
    if group == "api":
        method, endpoint, fields = gh_api_request(argv)
        text = endpoint + " " + fields
        if endpoint == "graphql":
            if "--input" in argv or re.search(r"(^|\s)query=@", fields):
                R.append(("ask", "`gh api graphql` query comes from a file - cannot be checked"))
                return R
            if not re.search(r"\bmutation\b", fields):
                return R  # a graphql query reads
            if re.search(TAGGISH, text) or re.search(r"\b(createRef|updateRef|updateRefs)\b", fields) and "refs/tags" in text:
                R.append(("deny", "`gh api graphql` mutation creates/changes a tag or release - a release action (only with explicit release authorization in the current task)"))
            elif re.search(r"\b(deleteRepository|archiveRepository)\b", fields):
                R.append(("deny", "`gh api graphql` deletes/archives a repository"))
            else:
                R.append(("ask", "`gh api graphql` mutation changes GitHub state (refs, branch protection, PRs, settings)"))
            return R
        if method in {"GET", "HEAD"}:
            return R
        path = re.sub(r"^/+", "", endpoint)
        if re.search(TAGGISH, text):
            R.append(("deny", f"`gh api -X {method} {path}` creates/changes a tag or release - a release action (only with explicit release authorization in the current task)"))
        elif method == "DELETE" and re.match(r"^repos/[^/]+/[^/]+/?$", path):
            R.append(("deny", f"`gh api -X DELETE {path}` deletes a repository"))
        elif "/protection" in path or "/rulesets" in path:
            R.append(("ask", f"`gh api -X {method} {path}` changes branch protection / rulesets"))
        elif "/git/refs" in path:
            R.append(("ask", f"`gh api -X {method} {path}` writes a git ref on the remote"))
        else:
            R.append(("ask", f"`gh api -X {method} {path}` changes GitHub state"))
        return R
    if group == "release" and verb in {"create", "upload", "edit"}:
        R.append(("deny", f"`gh release {verb}` creates or changes a tag/release - a release action (only with explicit release authorization in the current task)"))
    elif group == "release" and verb == "delete-asset":
        R.append(("ask", "`gh release delete-asset` changes a published release"))
    elif group == "release" and verb == "delete":
        R.append(("ask", "`gh release delete` removes a published release"))
    elif group == "repo" and verb in {"delete", "archive"}:
        R.append(("deny", f"`gh repo {verb}` deletes/archives a repository"))
    elif group in GH_READ_GROUPS or verb in GH_READ.get(group, set()) or (group == "auth" and verb in {"login", "refresh", "setup-git", "logout", "switch"}):
        return R
    elif group == "repo" and verb in {"set-default"}:
        return R
    else:
        R.append(("ask", f"`gh {group} {verb}`".strip() + " changes GitHub state"))
    return R


def names_registry_repo(argv, registry):
    slugs = set()
    for r in registry.get("repos", {}).values():
        m = re.search(r"github\.com[:/]([^/]+/[^/.]+)", (r.get("remote") or ""))
        if m:
            slugs.add(m.group(1).lower())
    text = " ".join(argv).lower()
    return any(sl in text for sl in slugs)


def stateless(sub, cfg):
    """A read whose classification never depends on the branch or the repo (and no alias can redefine it)."""
    return sub in STATELESS_READ_GIT and not any(c.lower().startswith("alias.") for c in cfg)


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
    cwd = os.path.abspath(payload.get("cwd") or os.getcwd())
    workspace = find_workspace(cwd, registry)
    reasons = []
    predicted_branch, repo_state, pattern_cache, linked = {}, {}, {}, {}
    # a command substitution used as the program: $(which git) reset / `which git` push
    verbs = "|".join(sorted(MUTATING_GIT_WORDS, key=len, reverse=True))
    if workspace and re.search(r"(^|[;&|(]\s*)(\$\([^)]*\)|`[^`]*`)\s+(" + verbs + r")\b", command):
        reasons.append(("ask", "the program is a command substitution followed by a git verb - cannot be checked"))
    for argv in expand(command, shell=shell):
        p = prog(argv[0])
        if p in CD_WORDS:
            target = next((x for x in argv[1:] if not x.startswith("-")), None)
            if target:
                cwd = os.path.normpath(os.path.join(cwd, native_path(os.path.expanduser(target.replace("\\", "/")))))
            continue
        ws = find_workspace(cwd, registry) or workspace  # after a `cd` into another workspace, that one applies
        if p in {"gh", "gh.exe"} and (ws or names_registry_repo(argv, registry)):
            for d, t in classify_gh(argv):
                reasons.append((d, t))
            continue
        if not ws:
            # outside the workspace: not our business - unless `git -C <dir>` points git into one
            # or git works in a linked worktree (cwd or `-C`) whose main checkout lies in a workspace
            pre = parse_git(argv)
            eff = os.path.normpath(os.path.join(cwd, pre[0])) if pre and pre[0] else cwd
            ws = find_workspace(eff, registry) if pre and pre[0] else None
            if not ws and pre and not stateless(pre[1], pre[3]):
                ws = (outside_workspace(eff, registry, linked) or (None,))[0]
            if not ws:
                continue
        here = os.path.relpath(cwd, ws) if within(cwd, ws) else cwd
        if argv[0] == "__opaque__":
            reasons.append(("ask", f"[{here}] {argv[1]} - its contents cannot be checked"))
            continue
        if argv[0] == "__too_deep__":
            reasons.append(("ask", f"[{here}] shells nested deeper than {MAX_DEPTH} levels - cannot be checked"))
            continue
        if p in INTERPRETERS and any(x in {"-c", "-e", "--eval", "-p"} for x in argv[1:]) and re.search(r"\b(git|gh)\b", " ".join(argv[1:])):
            reasons.append(("ask", f"[{here}] `{p}` inline code invokes git/gh - cannot be checked; run git/gh directly"))
            continue
        if argv[0].startswith("$") or argv[0].startswith("`"):
            if any(x.lower() in MUTATING_GIT_WORDS for x in argv[1:3]):
                reasons.append(("ask", f"[{here}] the program is a variable/substitution (`{argv[0]}`) followed by a git verb - cannot be checked"))
            continue
        parsed = parse_git(argv)
        if not parsed:
            continue
        cdir, sub, args, cfg = parsed
        if stateless(sub, cfg):
            continue  # nothing to classify: skip the per-repo git calls (30 x `git status` stay fast)
        eff = os.path.normpath(os.path.join(cwd, cdir)) if cdir else cwd
        ws = find_workspace(eff, registry) or ws  # the directory git works in decides (`git -C` into another workspace)
        main = None
        if not within(eff, ws):  # a linked worktree outside the workspace: its main checkout's rules, else silent
            ws, main = outside_workspace(eff, registry, linked) or (None, None)
            if not ws:
                continue
        if eff not in repo_state:  # memoised per directory within this one hook call
            t = git_out(eff, "rev-parse", "--show-toplevel")
            t = os.path.abspath(t) if t else None
            repo_state[eff] = (t, git_out(eff, "branch", "--show-current") if t else "")
        top, current = repo_state[eff]
        branch = predicted_branch.get(top) or current
        if (top, ws) not in pattern_cache:
            pattern_cache[(top, ws)] = protected_patterns(top, ws, registry) if top else DEFAULT_PROTECTED
        patterns = pattern_cache[(top, ws)]
        if main:  # the worktree may sit on another drive (relpath would raise): name it by its main checkout
            where = f"{os.path.relpath(main, ws)} worktree {top or eff}"
        else:
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
    if not find_workspace(cwd, registry) and not any(find_workspace(native_path(os.path.expanduser(t)), registry)
                                                     for t in re.findall(r"((?:\b[A-Za-z]:[/\\]|/)[^\s'\"]+)", command)):
        return []
    shell = "powershell" if tool == "PowerShell" else "bash"
    texts = {" ".join(seg) for seg in segments(tokenize(command))}
    for argv in expand(command, shell=shell):
        texts.add(" ".join(argv))
        if prog(argv[0]) in {"gh", "gh.exe"}:  # `gh --repo o/r pr merge 1` is seen as `gh pr merge 1`
            texts.add(" ".join(["gh"] + gh_normalise(argv)[1:]))
    hits = []
    read_only = []  # computed once, only when a read_only_exempt gate matched
    for text in texts:
        for g in registry.get("human_gates", []):
            m = g.get("match")
            if not m or tool not in g.get("tools", ["Bash", "PowerShell"]):
                continue
            try:
                matched = re.search(m, text)
            except re.error:  # one bad registry regex must not disable the rest of the guard
                continue
            if matched and g.get("read_only_exempt"):
                if not read_only:
                    try:
                        sys.path.append(os.path.dirname(os.path.abspath(__file__)))  # appended: stdlib first
                        import factory_session as session  # noqa: E402
                        session._REGISTRY = session._REGISTRY or registry
                        read_only.append(session.is_read_only(payload))
                    except Exception:
                        read_only.append(False)  # cannot tell: the gate applies
                if read_only[0]:
                    continue  # `sed -n 1,40p run-clients.sh`: inspecting the script does not run it
            if matched:
                hits.append((g.get("decision", "ask"), f"human gate '{g['id']}': {g['rule']}"))
    return hits


def _needs_mode(payload):
    """Cheap file check first - factory_session.py is only imported when a mode exists or the command declares one
    (read-only hook calls stay fast on /mnt/c)."""
    sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
    import fstate  # noqa: E402
    sid = fstate.session_key(payload.get("session_id"))  # the same directory factory_session writes MODE to
    command = (payload.get("tool_input") or {}).get("command") or ""
    return os.path.exists(os.path.join(fstate.scratch(), sid, "MODE")) or "--mode" in command


MODE_SCRIPTS = {"factory-context.sh", "context.py"}


def mode_runner(payload):
    """The first expanded argv that executes factory-context.sh (or lib/context.py) with --mode: the script
    itself as the program, or a shell / interpreter whose first non-option argument is the script."""
    command = (payload.get("tool_input") or {}).get("command") or ""
    if "--mode" not in command:
        return None
    shell = "powershell" if payload.get("tool_name") == "PowerShell" else "bash"
    for argv in expand(command, shell=shell):
        p = prog(argv[0])
        if p in MODE_SCRIPTS:
            script = 0
        elif p in SHELLS or p in INTERPRETERS:
            script = next((k for k, a in enumerate(argv[1:], 1) if not a.startswith("-")), None)
            if script is None or prog(argv[script]) not in MODE_SCRIPTS:
                continue
        else:
            continue
        if any(a == "--mode" or a.startswith("--mode=") for a in argv[script + 1:]):
            return [prog(argv[script])] + argv[script + 1:]
    return None


def mode_hits(payload, registry):
    """Factory execution mode (declared with `factory-context.sh --mode <m>`): analyze/plan/review are
    read-only; validate may additionally run run-checks.py. implement/resume (or no mode) = normal rules."""
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))  # appended: stdlib lookups must not stat /mnt/c first
    import factory_session as session  # noqa: E402
    session._REGISTRY = session._REGISTRY or registry
    # a mode switch counts wherever it runs (a stale read-only mode must not outlive `--mode implement` run from
    # outside the workspace), but only when the command really runs the script - `grep factory-context.sh --mode
    # review README.md` or `echo ... --mode plan` only mention it
    runner = mode_runner(payload)
    declared = session.record_mode(dict(payload, tool_name="Bash", tool_input={"command": shlex.join(runner)})) if runner else None
    ws = find_workspace(payload.get("cwd") or os.getcwd(), registry)
    if not ws:
        return []
    mode = declared or session.current_mode(payload)
    if not mode or declared or session.is_read_only(payload):
        return []
    how = ("switch only when the user asked for it: `bash \"" + PLUGIN_ROOT.replace("\\", "/").rstrip("/")
           + "/scripts/factory-context.sh\""  # forward slashes: the command is pasted into bash
           + " --mode implement` (or validate)")
    if mode in session.READ_ONLY_MODES:
        return [("deny", f"Factory mode is `{mode}` (read-only): this command changes state - {how}")]
    if mode == "validate" and not session.runs_checks(payload):
        return [("deny", "Factory mode is `validate`: only read-only commands and run-checks.py - " + how)]
    return []


def main():
    if os.environ.get("RPG_FACTORY_GUARD", "").lower() in {"off", "0", "false"}:
        return 0
    try:  # UTF-8 whatever the console code page (Windows pipes default to cp1252: a non-ASCII cwd broke the match)
        stream = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace") if hasattr(sys.stdin, "buffer") else sys.stdin
        payload = json.load(stream)
    except (json.JSONDecodeError, ValueError, OSError):
        return 0
    if not isinstance(payload, dict) or payload.get("tool_name") not in (None, "Bash", "PowerShell"):
        return 0  # `[]`, `null`, `42`: not a hook payload
    if not isinstance(payload.get("tool_input") or {}, dict) or not isinstance((payload.get("tool_input") or {}).get("command") or "", str):
        return 0
    registry = load_registry()
    if not registry:
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    if len(command) > MAX_COMMAND:  # analysing it would take minutes: say so instead of guessing
        json.dump(advisory("rpg-factory guard", [("ask", f"command too large to check ({len(command) // 1024} KB); review it")]), sys.stdout)
        return 0
    reasons = []
    try:
        need_mode = _needs_mode(payload)
    except Exception:
        need_mode = True  # cannot tell cheaply: do the full checks
    parts = (mode_hits, evaluate, human_gate_hits) if need_mode else (evaluate, human_gate_hits)
    for part in parts:  # isolated: a failure in one never drops the others
        try:
            reasons += part(payload, registry)
        except Exception:  # a guard bug must never break the session
            pass
    if not reasons:
        return 0
    json.dump(advisory("rpg-factory guard", reasons), sys.stdout)
    return 0


def advisory(who, reasons):
    """Advisory only (1.0.3): never a permissionDecision, so the hook neither asks the user nor blocks the agent.
    The former deny class is level `high`, the former ask class `warn`; the text reaches the agent as context."""
    level = "high" if any(d == "deny" for d, _ in reasons) else "warn"
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": f"rpg-factory advisory ({level}): {who}: " + "; ".join(dict.fromkeys(t for _, t in reasons)),
    }}


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252: output is UTF-8 everywhere
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        rc = main()
    except Exception:  # a guard bug must never break the session: no opinion
        rc = 0
    sys.exit(rc)
