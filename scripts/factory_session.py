#!/usr/bin/env python3
"""rpg-factory session state - the Factory execution mode and the tech-skill order, per session.

  --skill  (PreToolUse, Skill) records an explicit mode from a Factory skill's arguments ("plan only",
           "mode: validate") and denies a `kind: tech` skill until one of its `used_by` leads ran in
           this session.

As a module (git-guard.py, file-guard.py): record_mode() / current_mode() for `factory-context.sh
--mode <m>`, is_read_only() and runs_checks() to decide what a read-only or validate mode still allows.

State: per-session scratch in fstate.scratch()/<session>/ (MODE, SKILLS) - always absolute, never inside a repo.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(HERE)
sys.path.append(os.path.join(HERE, "lib"))  # appended: stdlib lookups must not stat /mnt/c first
import fstate  # noqa: E402

READ_ONLY_PROGS = {"ls", "cat", "head", "tail", "grep", "egrep", "rg", "jq", "wc", "echo", "printf", "pwd", "stat", "file",
                   "which", "type", "diff", "cmp", "sort", "uniq", "cut", "tr", "less", "more", "tree", "du", "df", "date",
                   "basename", "dirname", "realpath", "readlink", "env", "printenv", "true", "false", "test", "[", "sha256sum",
                   "md5sum", "column", "nl", "fold", "id", "whoami", "hostname", "uname", "get-childitem", "get-content",
                   "select-string", "get-location", "test-path", "get-item", "write-output", "write-host", "measure-object",
                   "select-object", "where-object", "sleep", "cd", "pushd", "popd", "set-location", "gci", "gc", "dir"}
READ_ONLY_FACTORY = {"factory-context.sh", "check-registry.sh", "pin-status.py", "pin-plan.py", "wire-parity.sh",
                     "package-ready.py", "install-status.py", "factory-status.py", "unity-package-pins.py"}
READ_ONLY_GIT = {"status", "log", "diff", "show", "rev-parse", "ls-files", "ls-remote", "ls-tree", "cat-file", "describe",
                 "blame", "grep", "shortlog", "for-each-ref", "check-ignore", "merge-base", "rev-list", "name-rev",
                 "count-objects", "help", "version", "range-diff", "diff-tree", "whatchanged", "var"}


_GUARD = None
_REGISTRY = None


def guard():
    """git-guard.py as a module - once per process (reused when git-guard.py itself is running)."""
    global _GUARD
    if _GUARD is not None:
        return _GUARD
    main = sys.modules.get("__main__")
    if main is not None and hasattr(main, "classify_gh") and hasattr(main, "find_workspace"):
        _GUARD = main
        return main
    sys.path.append(HERE)  # appended: stdlib lookups must not stat /mnt/c first
    import importlib.util
    spec = importlib.util.spec_from_file_location("git_guard", os.path.join(HERE, "git-guard.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _GUARD = mod
    return mod


def state_dir(payload):
    sid = re.sub(r"[^A-Za-z0-9_.-]", "_", str((payload or {}).get("session_id") or "default"))
    d = os.path.join(fstate.scratch(), sid)
    os.makedirs(d, exist_ok=True)
    return d


def read(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    except OSError:
        return None


def load_registry():
    global _REGISTRY
    if _REGISTRY is None:
        try:
            _REGISTRY = json.load(open(os.path.join(PLUGIN_ROOT, "registry.json"), encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
    return _REGISTRY


MODES = ("analyze", "plan", "implement", "validate", "review", "resume")
READ_ONLY_MODES = {"analyze", "plan", "review"}


def record_mode(payload):
    """`factory-context.sh --mode <m>` declares the Factory execution mode for this session (seen by the
    PreToolUse hook, which knows the session id). Returns the mode it recorded, if any."""
    command = (payload.get("tool_input") or {}).get("command") or ""
    if "--mode" not in command:
        return None
    g = guard()
    shell = "powershell" if payload.get("tool_name") == "PowerShell" else "bash"
    for argv in g.expand(command, shell=shell):
        if any(os.path.basename(a) in ("factory-context.sh", "context.py") for a in argv[:3]):
            for i, a in enumerate(argv):
                m = a.split("=", 1)[1] if a.startswith("--mode=") else (argv[i + 1] if a == "--mode" and i + 1 < len(argv) else None)
                if m in MODES:
                    open(os.path.join(state_dir(payload), "MODE"), "w", encoding="utf-8").write(m)
                    return m
    return None


MODE_PHRASES = [  # explicit phrases only - an unqualified request is not a mode declaration
    (r"\bmode\s*[:=]?\s*(analy[sz]e|plan|implement|validate|review|resume)\b", None),
    (r"\b(analy[sz]e|analysis)[- ]only\b|\bonly analy[sz]e\b", "analyze"),
    (r"\bplan(ning)?[- ]only\b|\bonly plan\b|\bjust (a )?plan\b|\bdo not implement\b|\bdon'?t implement\b", "plan"),
    (r"\bvalidat(e|ion)[- ]only\b|\bonly validate\b", "validate"),
    (r"\breview[- ]only\b|\bonly review\b", "review"),
]


def mode_from_text(text):
    t = (text or "").lower()
    for pat, mode in MODE_PHRASES:
        m = re.search(pat, t)
        if m:
            got = mode or m.group(1)
            return "analyze" if got.startswith("analy") else got
    return None


def skill_hook(payload):
    """PreToolUse(Skill): when a Factory skill is invoked with an explicit mode in its arguments ("plan only",
    "mode: validate"), record it - so the mode holds even if the model never runs the Route command.
    Also keeps tech skills (registry kind "tech") behind their leads: a tech skill invoked before one of its
    `used_by` skills ran in this session gets an advisory (it still runs - 1.0.3: hooks never block), so its
    "how it works" does not replace routing, rules and gates."""
    ti = payload.get("tool_input") or {}
    name = str(ti.get("skill", ""))
    if not name.startswith("rpg-factory:"):
        return 0
    m = mode_from_text(ti.get("args"))
    if m in MODES:
        open(os.path.join(state_dir(payload), "MODE"), "w", encoding="utf-8").write(m)
    short = name.split(":", 1)[1]
    seen_file = os.path.join(state_dir(payload), "SKILLS")
    seen = set((read(seen_file) or "").split())
    spec = ((load_registry() or {}).get("skills") or {}).get(short) or {}
    leads = [s for s in spec.get("used_by") or [] if isinstance(s, str)]
    if spec.get("kind") == "tech" and leads and not seen.intersection(leads):
        root = PLUGIN_ROOT.replace("\\", "/").rstrip("/")
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": (
                f"rpg-factory advisory (high): `{short}` is a supporting tech skill and should not run first. Route the "
                f"task (`bash \"{root}/scripts/factory-context.sh\" --mode <mode> --repo <key> --paths <files>`), invoke "
                f"the lead it prints - for {short} one of: " + ", ".join(f"rpg-factory:{s}" for s in leads)
                + f" - and use rpg-factory:{short} as supporting context.")}}))
    with open(seen_file, "a", encoding="utf-8") as fh:
        fh.write(short + "\n")
    return 0


def current_mode(payload):
    return (read(os.path.join(state_dir(payload), "MODE")) or "").strip() or None


def runs_checks(payload):
    command = (payload.get("tool_input") or {}).get("command") or ""
    g = guard()
    argvs = list(g.expand(command, shell="powershell" if payload.get("tool_name") == "PowerShell" else "bash"))
    return bool(argvs) and all(any(os.path.basename(a) in ("run-checks.py", "factory-cmd.py") for a in argv[:3]) or
                               g.prog(argv[0]) in READ_ONLY_PROGS for argv in argvs)


SED_PRINT = re.compile(r"(\d+|\$)(,(\d+|\$))?p|/[^/]*/p|\d+q")
SED_FLAGS = {"-n", "--quiet", "--silent", "-E", "-r", "--regexp-extended", "-s", "--separate", "-u", "-z", "--"}


def sed_prints_only(args):
    """`sed -n 300,340p file`: a script that only prints lines (N,Mp, /re/p, Nq). Anything else - -i, -f, a
    script file, s///w, the e and w commands, several commands - is not read-only."""
    script, i = False, 0
    while i < len(args):
        a = args[i]
        if a in SED_FLAGS:
            i += 1
            continue
        if a in ("-e", "--expression"):
            if i + 1 >= len(args) or not SED_PRINT.fullmatch(args[i + 1]):
                return False
            script, i = True, i + 2
            continue
        if a.startswith("-"):
            return False
        if not script:
            if not SED_PRINT.fullmatch(a):
                return False
            script = True
        i += 1  # after the script: input files
    return script


def is_read_only(payload):
    command = (payload.get("tool_input") or {}).get("command") or ""
    if not command.strip():
        return True
    command = re.sub(r"\d*>{1,2}\s*/dev/null|\d*>&\d", " ", command)  # discarding output is not a write
    if re.search(r"(^|[^>])>{1,2}[^>&]|\btee\b|\bsed\b[^|;]*\s-i|\bmv\b|\brm\b|\bcp\b|\btouch\b|\bmkdir\b", command):
        return False
    g = guard()
    shell = "powershell" if payload.get("tool_name") == "PowerShell" else "bash"
    try:
        argvs = list(g.expand(command, shell=shell))
    except Exception:
        return False
    for argv in argvs:
        p = g.prog(argv[0])
        if p in ("git", "git.exe"):
            parsed = g.parse_git(argv)
            if not parsed:
                continue
            _, sub, args, _ = parsed
            if sub in READ_ONLY_GIT:
                continue
            branch_flags = {"-a", "-r", "-v", "-vv", "--list", "-l", "--show-current", "--all"}
            if sub == "branch" and all(a in branch_flags for a in args):
                continue
            if sub == "branch" and {"--list", "-l"} & set(args) and all(a in branch_flags or not a.startswith("-") for a in args):
                continue  # `git branch --list 'backup/*'`: a pattern after --list only filters
            if sub == "stash" and args[:1] in (["list"], ["show"]):
                continue
            if sub == "reflog" and not {"expire", "delete", "drop", "write"} & set(args):
                continue  # show / list / exists / <ref>; expire, delete, drop and write rewrite reflogs
            if sub == "tag" and (not args or set(args) & {"-l", "--list"}):
                continue
            if sub in {"remote", "config", "worktree"} and args[:1] in (["-v"], ["--get"], ["list"], ["get-url"], ["--list"], ["show"]):
                continue
            return False
        if p == "find" and not any(a in {"-exec", "-execdir", "-delete", "-ok", "-okdir"} for a in argv):
            continue
        if p == "sed" and sed_prints_only(argv[1:]):
            continue
        script = next((a for a in argv[:3] if "/" in a or a.endswith((".py", ".sh"))), "")
        if os.path.basename(script) in READ_ONLY_FACTORY:
            continue
        if os.path.basename(script) == "factory-cmd.py" and not ("check" in argv and "--status" not in argv):
            continue
        if p not in READ_ONLY_PROGS:
            return False
    return True


def main():
    if sys.argv[1:] != ["--skill"]:
        print("usage: factory_session.py --skill  (PreToolUse hook on the Skill tool; reads the payload on stdin)")
        return 2
    try:
        return skill_hook(json.load(sys.stdin))
    except Exception:
        return 0  # never break the session


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252: output is UTF-8 everywhere
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
