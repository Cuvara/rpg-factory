#!/usr/bin/env python3
"""rpg-factory session state - the Factory execution mode and the tech-skill order, per session.

  --skill  (PreToolUse, Skill) records an explicit mode from a Factory skill's arguments ("plan only",
           "mode: validate") and keeps a `kind: tech` skill behind its leads without ever blocking: requested
           before factory-core it is auto-corrected to factory-core (updatedInput, once per session);
           after factory-core but before one of its `used_by` leads it runs with an advisory.
  --skills <session-id>      print the skills that loaded in a session, one per line, in order
  --advisories <session-id>  print the advisories the Skill hook gave a session, one per line, in order

As a module (git-guard.py, file-guard.py): record_mode() / current_mode() for `factory-context.sh
--mode <m>`, is_read_only() and runs_checks() to decide what a read-only or validate mode still allows.

State: per-session scratch in fstate.scratch()/<fstate.session_key(id)>/ - always absolute, never inside a repo:
  MODE           the declared mode (replaced atomically)
  SKILLS.d/      one file per loaded skill, ADVISORIES.d/ one file per advisory (parallel hooks lose nothing:
                 appends to one file are not atomic on Windows). Legacy SKILLS / ADVISORIES files are still read.
  CORRECTED      created exclusively by the one call that is auto-corrected to factory-core
"""
import json
import os
import re
import sys
import time

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


def session_dir(sid, create=True):
    d = os.path.join(fstate.scratch(), fstate.session_key(sid))
    if create:
        os.makedirs(d, exist_ok=True)
    return d


def state_dir(payload):
    return session_dir((payload or {}).get("session_id"))


def read(p):
    for attempt in range(8):
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                return fh.read().strip()
        except PermissionError:  # Windows: the file is being replaced (fstate.write_text) for a moment
            if os.path.isdir(p):
                return None
            time.sleep(0.01 * (attempt + 1))
        except OSError:
            return None
    return None


def write_mode(sd, mode):
    fstate.write_text(os.path.join(sd, "MODE"), mode)  # atomic: a concurrent reader never sees a torn mode


def log_event(sd, kind, text):
    """One file per event under <sd>/<kind>.d/ - lossless under parallel hooks on Windows and Linux. The name
    sorts in time order; the content is the event."""
    d = os.path.join(sd, kind + ".d")
    fstate.write_text(os.path.join(d, f"{time.time_ns():020d}-{fstate.unique_suffix()}"), text)


def read_events(sd, kind):
    """The legacy one-file log (older sessions) followed by the per-event files, in order."""
    out = (read(os.path.join(sd, kind)) or "").splitlines()
    d = os.path.join(sd, kind + ".d")
    try:
        names = sorted(f for f in os.listdir(d) if not f.endswith(".tmp"))
    except OSError:
        names = []
    for f in names:
        t = read(os.path.join(d, f))
        if t:
            out.append(t)
    return [x.strip() for x in out if x.strip()]


def seen_skills(sd):
    return set(read_events(sd, "SKILLS"))


def claim_correction(sd):
    """True for exactly one caller per session: the auto-correction to factory-core happens once, even when
    several Skill calls arrive in parallel. Unwritable state: no claim (warn, never loop on corrections)."""
    try:
        os.close(os.open(os.path.join(sd, "CORRECTED"), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644))
        return True
    except OSError:
        return False


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
        at = runs_context(g, argv)
        if at is None:
            continue
        args = argv[at + 1:]
        for i, a in enumerate(args):
            m = a.split("=", 1)[1] if a.startswith("--mode=") else (args[i + 1] if a == "--mode" and i + 1 < len(args) else None)
            if m in MODES:
                write_mode(state_dir(payload), m)
                return m
    return None


CONTEXT_SCRIPTS = ("factory-context.sh", "context.py")
INTERPRETERS = {"bash", "sh", "bash.exe", "sh.exe", "python", "python3", "python.exe", "python3.exe", "py", "py.exe"}


def runs_context(g, argv):
    """Index of the routing script in argv when this command runs it (`factory-context.sh ...`,
    `bash factory-context.sh ...`, `python3 -B context.py ...`), else None. `grep factory-context.sh --mode x`
    or `echo factory-context.sh --mode x` only mention it."""
    if not argv:
        return None
    if os.path.basename(argv[0].replace("\\", "/")) in CONTEXT_SCRIPTS:
        return 0
    if g.prog(argv[0]) in INTERPRETERS:
        i = 1
        while i < len(argv) and argv[i] in ("-B", "-u", "-x", "-e", "-E", "-s"):  # interpreter flags, no value
            i += 1
        if i < len(argv) and os.path.basename(argv[i].replace("\\", "/")) in CONTEXT_SCRIPTS:
            return i
    return None


MODE_PHRASES = [  # explicit phrases only - an unqualified request is not a mode declaration
    (r"\bmode\s*[:=]?\s*(analy[sz]e|plan|implement|validate|review|resume)\b", None),
    (r"\b(analy[sz]e|analysis)[- ]only\b|\bonly analy[sz]e\b", "analyze"),
    (r"\bplan(ning)?[- ]only\b|\bonly plan\b|\bjust (a )?plan\b", "plan"),  # "do not implement" alone is no declaration
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
    Also keeps tech skills (registry kind "tech") behind their leads, without ever blocking (1.0.3: hooks are
    advisory only): requested before factory-core, the call is auto-corrected to factory-core (updatedInput,
    once per session); after factory-core but before one of its `used_by` leads, it runs with an advisory
    naming the leads (only routing knows which one applies). Each advisory is logged to the session's
    ADVISORIES.d/ (read them with --advisories)."""
    ti = payload.get("tool_input") or {}
    name = str(ti.get("skill", ""))
    skills = (load_registry() or {}).get("skills") or {}
    if name.startswith("rpg-factory:"):
        short = name.split(":", 1)[1]
    elif ":" not in name and name in skills:
        short = name  # a bare registry skill name ("go-backend") is this plugin's skill
    else:
        return 0
    try:
        sd = state_dir(payload)
    except OSError:
        sd = None  # no state: still advise, never correct (nothing could record that it happened)
    m = mode_from_text(ti.get("args"))
    if m in MODES and sd:
        try:
            write_mode(sd, m)
        except OSError:
            pass
    seen = seen_skills(sd) if sd else set()
    spec = skills.get(short) or {}
    leads = [s for s in spec.get("used_by") or [] if isinstance(s, str)]
    loads, event = short, None
    if spec.get("kind") == "tech" and leads and not seen.intersection(leads):
        root = PLUGIN_ROOT.replace("\\", "/").rstrip("/")
        route = f"`bash \"{root}/scripts/factory-context.sh\" --mode <mode> --repo <key> --paths <files>`"
        lead_list = ", ".join(f"rpg-factory:{s}" for s in leads)
        out = {"hookEventName": "PreToolUse"}
        if "factory-core" not in seen and sd and claim_correction(sd):
            # auto-correct, never block: the one safe target is factory-core (it routes and names the real lead).
            # The Skill tool honours updatedInput (verified 2026-10-22, not documented for Skill). Once per
            # session: only the call that creates CORRECTED is corrected (parallel calls included), so this
            # branch cannot repeat and cannot loop.
            out["updatedInput"] = dict(ti, skill="rpg-factory:factory-core")
            loads = "factory-core"
            out["additionalContext"] = (
                f"rpg-factory advisory (high): `{short}` is a supporting tech skill and was requested before "
                f"factory-core, so this call loads rpg-factory:factory-core instead (auto-corrected; nothing is "
                f"blocked). Next: route the task ({route}), invoke the lead it prints - for {short} one of: "
                f"{lead_list} - then invoke rpg-factory:{short} again as supporting context.")
            event = f"{short} autocorrect factory-core"
        else:
            # factory-core ran (or the one corrected call is loading it) but no lead: several leads can own this
            # technology and only routing knows which, so warn and let the call run (1.0.3: hooks never block)
            out["additionalContext"] = (
                f"rpg-factory advisory (high): `{short}` is a supporting tech skill and no lead skill has run yet. "
                f"This call continues. Next: route the task ({route}) and invoke the lead it prints - for {short} one "
                f"of: {lead_list} - its rules, gates and validation apply; use rpg-factory:{short} as supporting context.")
            event = f"{short} warn lead-missing"
        print(json.dumps({"hookSpecificOutput": out}))  # the advisory first: logging below is best-effort
        sys.stdout.flush()
    if sd:
        try:
            if event:
                log_event(sd, "ADVISORIES", event)  # evidence for tests and dogfood: what the hook told the session
            log_event(sd, "SKILLS", loads)  # the skill that actually loads (factory-core when auto-corrected)
        except OSError:
            pass
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
    if len(sys.argv) == 3 and sys.argv[1] in ("--skills", "--advisories"):
        kind = "SKILLS" if sys.argv[1] == "--skills" else "ADVISORIES"
        for line in read_events(session_dir(sys.argv[2], create=False), kind):
            print(line)
        return 0
    if sys.argv[1:] != ["--skill"]:
        print("usage: factory_session.py --skill  (PreToolUse hook on the Skill tool; reads the payload on stdin)\n"
              "       factory_session.py --skills <session-id> | --advisories <session-id>  (one per line, in order)")
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
