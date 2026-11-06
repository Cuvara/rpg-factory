"""Git and GitHub classification and workspace-aware evaluation."""
import os
import re
import shlex

from .common import (CD_WORDS, DEFAULT_PROTECTED, GIT_BUILTINS, GLOBAL_OPTS_WITH_VALUE,
                     INTERPRETERS, MAX_DEPTH, MUTATING_GIT_WORDS, STATELESS_READ_GIT,
                     TAG_REF, find_workspace, git_out, native_path, outside_workspace,
                     protected_patterns, is_protected, within)
from .shell import expand, prog

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


