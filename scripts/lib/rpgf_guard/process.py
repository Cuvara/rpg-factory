"""Process selectors, substitutions and host-wide termination detection."""
import re
import shlex

from .shell import expand, prog, segments, substitution_text, tokenize

PROCESS_TERMINATION_RULE = (
    "Terminating processes by image name or command-line pattern kills unrelated user and agent processes. "
    "Stop only PIDs you started (Start-Process -PassThru / $!)."
)

# Raw-text fallback: used only when the command cannot be parsed at all (never for a parsed command, so quoted
# arguments of grep / echo / git commit stay quiet).
PROCESS_KILL_FALLBACK = re.compile(
    r"(?is)(?:^|[;&|\n])\s*(?:(?:\S*[/\\])?taskkill(?:\.exe)?\b(?:(?![;&|\n]).)*?/{1,2}(?:im|fi)\b"
    r"|stop-process\b(?:(?![;&|\n]).)*?-(?:name|processname)\b|(?:pkill|killall)\b|fuser\b(?:(?![;&|\n]).)*?\s-\w*k)")
PROCESS_PREFILTER = ("kill", "terminat", "stop-process", "spps", "wmic", "remove-cim", "fuser")  # cheap: skip parsing without these
TERMINATORS = {"taskkill", "taskkill.exe", "stop-process", "spps", "kill", "pkill", "killall", "killall5", "pskill", "remove-ciminstance"}
CIM_QUERIES = {"get-ciminstance", "gcim", "get-wmiobject", "gwmi", "invoke-cimmethod", "icim"}
GREP_LIKE = {"grep", "egrep", "fgrep", "rg", "awk", "findstr", "select-string", "sls"}
START_PROCESS = {"start-process", "start", "saps"}
IMAGE_SELECTOR = re.compile(r"^(?:/{1,2}|-{1,2})(?:im|fi)(?::|$)")
PS_NAME_PARAM = re.compile(r"^-(?:n(?:a(?:m(?:e)?)?)?|processname)(?::|$)")
WMIC_PID_WHERE = re.compile(r"^(?:process)?id\s*=\s*\d+$|^handle\s*=\s*\d+$")


def _substitutions(command, shell):
    """Command substitutions the shell runs although they sit inside double quotes (`kill "$(pgrep x)"`):
    the inner texts of $(...) and, in bash, `...`. Text inside single quotes is data and is skipped."""
    out, i, n, quote = [], 0, len(command), None
    while i < n:
        ch = command[i]
        if (ch == "\\" and shell == "bash" and quote != "'") or (ch == "`" and shell == "powershell"):
            i += 2
            continue
        if quote == "'":
            quote = None if ch == "'" else quote
        elif ch == "'":
            quote = "'"
        elif ch == '"':
            quote = None if quote == '"' else '"'
        elif ch == "$" and command.startswith("$(", i):
            depth, j = 1, i + 2
            while j < n and depth:
                depth += (command[j] == "(") - (command[j] == ")")
                j += 1
            out.append(command[i + 2:j - 1])
            i = j
            continue
        elif ch == "`" and shell == "bash":
            j = command.find("`", i + 1)
            if j > 0:
                out.append(command[i + 1:j])
                i = j
        i += 1
    return out


def _process_argvs(command, shell, depth=0):
    """Every argv the command runs: expand() (nested shells, PowerShell -Command), substitutions, wsl payloads."""
    argvs = list(expand(command, shell=shell))
    for argv in list(argvs):
        if argv and prog(argv[0]) in {"wsl", "wsl.exe"}:
            i = 1
            while i < len(argv) and argv[i].startswith("-") and argv[i] != "--":
                i += 2 if argv[i] in {"-d", "-u", "--distribution", "--user", "--cd"} else 1
            if argv[i:i + 1] == ["--"]:
                i += 1
            if i < len(argv) and depth < 3:
                argvs += _process_argvs(shlex.join(argv[i:]), "bash", depth + 1)
    if depth < 3:
        for inner in _substitutions(substitution_text(command) if shell == "bash" else command, shell):
            argvs += _process_argvs(inner, shell, depth + 1)
    return argvs


def _clean(argv):
    """PowerShell script-block braces glued to a word (`& {Stop-Process -Name x}`) are not part of it."""
    argv = list(argv)
    if len(argv) > 2 and argv[0].startswith("$") and argv[1] in {"=", "in"}:
        argv = argv[2:]  # `$ps = Get-CimInstance ...`, `foreach ($p in Get-CimInstance ...)`
    if argv:
        argv[0] = argv[0].lstrip("{")
        if (len(argv) > 1 or argv[0]) and not re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}", argv[-1]):
            argv[-1] = argv[-1].rstrip("}")
    return [a for a in argv if a != ""]


def _own_pid_targets(command, shell):
    """Recognize unambiguously assigned own PIDs and direct PowerShell variable pipelines."""
    # Reassignments inside a nested bash -c are not tracked in the outer command.
    tokens = tokenize(command, shell)
    assignments = {}
    for seg in segments(tokens, shell):
        if shell == "bash" and seg and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", seg[0]):
            name, value = seg[0].split("=", 1)
            assignments.setdefault(name, []).append(len(seg) == 1 and value == "$!")
        elif shell == "bash" and seg and seg[0] in {"export", "declare", "local", "typeset", "readonly"}:
            for word in seg[1:]:
                if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", word):
                    name, value = word.split("=", 1)
                    assignments.setdefault(name, []).append(value == "$!")
        elif shell == "powershell" and len(seg) >= 3 and seg[0].startswith("$") and seg[1] == "=":
            name = seg[0][1:].lower()
            assignments.setdefault(name, []).append(prog(seg[2]) in START_PROCESS and
                                                   any(a.lower() == "-passthru" for a in seg[3:]))
        if shell == "bash":
            for i, token in enumerate(seg):
                if token in {"for", "select"} and i + 2 < len(seg) and seg[i + 2] == "in":
                    assignments.setdefault(seg[i + 1], []).append(False)
                elif token == "read":
                    for name in seg[i + 1:]:
                        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                            assignments.setdefault(name, []).append(False)
        elif len(seg) >= 3 and seg[0].startswith("$") and seg[1].lower() == "in":
            assignments.setdefault(seg[0][1:].lower(), []).append(False)
    own = {name for name, values in assignments.items() if values == [True]}
    # A bare Stop-Process is safe only if every such occurrence is directly piped from an own variable.
    bare_stops = [i for i, t in enumerate(tokens) if prog(t) in {"stop-process", "spps"}
                  and (i + 1 == len(tokens) or tokens[i + 1] in {";", "|", "&", "\n"})]
    safe_pipe = bool(bare_stops) and all(i >= 2 and tokens[i - 1] == "|" and
                                         tokens[i - 2].lower().lstrip("$") in own and
                                         tokens[i - 2].startswith("$") for i in bare_stops)
    return own, safe_pipe


def _own_terminator(p, args, own, safe_pipe):
    if p == "kill":
        targets = []
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "--":
                targets.extend(args[i + 1:])
                break
            if arg in {"-s", "-n"}:
                if i + 1 >= len(args):
                    return False
                i += 2
                continue
            if re.fullmatch(r"-(?:[0-9]+|(?:SIG)?(?:HUP|INT|QUIT|KILL|TERM|STOP|CONT|USR1|USR2))", arg):
                i += 1
                continue
            targets.append(arg)
            i += 1
    elif p in {"stop-process", "spps"}:
        if not args:
            return safe_pipe
        args = [a for a in args if a not in {"-force", "-passthru", "-confirm:$false", "-whatif"}]
        targets = args[1:] if args and args[0] in {"-id", "-pid"} else args
    else:
        return False
    pattern = (r"\$([a-z_][a-z0-9_]*)(?:\.id)?" if p in {"stop-process", "spps"} else
               r"\$(?:([A-Za-z_][A-Za-z0-9_]*)|\{([A-Za-z_][A-Za-z0-9_]*)\})")
    matches = [re.fullmatch(pattern, a) for a in targets]
    return bool(matches) and all(m and next(g for g in m.groups() if g is not None) in own for m in matches)


def process_findings(argvs, own=None, safe_pipe=False, shell="bash"):
    """(direct, selector, terminator) over every argv. direct = a terminator that names its targets host-wide
    (image name / filter / pattern); selector = a process query by name or pattern; terminator = any kill."""
    direct = selector = terminator = False
    own = own or set()
    greps = any(a and prog(a[0]) in GREP_LIKE for a in argvs)
    work = []
    for argv in argvs:  # a script block glued to the previous word (`ForEach-Object {$_.Kill`) starts a command
        work.append(_clean(argv))
        work.extend(_clean(argv[i:]) for i in range(1, len(argv)) if argv[i].startswith("{") and len(argv[i]) > 1)
    k = 0
    while k < len(work):
        argv = work[k]
        k += 1
        if not argv:
            continue
        p = prog(argv[0])
        args = [a.lower() for a in argv[1:]]
        if p in {"busybox", "busybox.exe"} and args and prog(args[0]) in {"pkill", "killall"}:
            work.append(argv[1:])
            continue
        if p in {"pkill.exe", "killall.exe"}:
            p = p[:-4]
        if p in START_PROCESS:
            for i, a in enumerate(argv[1:], 1):
                if prog(a) in TERMINATORS or prog(a) == "wmic":
                    work.append([a] + [x for t in argv[i + 1:] for x in t.split(",")])
                    break
            continue
        target_args = args if shell == "powershell" else argv[1:]
        if p in TERMINATORS and not _own_terminator(p, target_args, own, safe_pipe):
            terminator = True
        if p in {"taskkill", "taskkill.exe"}:
            direct = direct or any(IMAGE_SELECTOR.match(a) for a in args)
        elif p in {"stop-process", "spps"}:
            direct = direct or any(PS_NAME_PARAM.match(a) for a in args)
        elif p == "kill":
            direct = direct or any(re.match(r"^-na(?:m(?:e)?)?$", a) for a in args) or "-1" in args[1:]
        elif p in {"pkill", "killall", "killall5", "pskill"}:
            direct = True
        elif p in {"fuser", "fuser.exe"} and any(re.match(r"^-[^-]*k", a) or a == "--kill" for a in args):
            direct = True
        elif p in {"%", "foreach-object", "foreach"} and (args == ["kill"] or args == ["-membername", "kill"]):
            terminator = True
        elif p.endswith((".kill", ".terminate")):
            match = re.fullmatch(r"\$([a-z_][a-z0-9_]*)\.(?:kill|terminate)", p)
            if shell != "powershell" or not match or match.group(1) not in own:
                terminator = True
        elif p == "wmic" and "process" in args:
            rest = args[args.index("process") + 1:]
            where = " ".join(rest[rest.index("where") + 1:]) if "where" in rest else ""
            scoped = bool(where) and bool(WMIC_PID_WHERE.match(re.split(r"\b(?:delete|call|get)\b", where)[0].strip()))
            if "delete" in rest or ("call" in rest and "terminate" in rest):
                terminator = True
                direct = direct or not scoped
            elif not scoped:
                selector = True
        elif p in CIM_QUERIES:
            if "win32_process" in " ".join(args):
                selector = True
            if p in {"invoke-cimmethod", "icim"} and "terminate" in args:
                terminator = True
        elif p in {"get-process", "gps"}:
            selector = selector or not any(re.match(r"^-(?:id|pid)$", a) for a in args)
        elif p == "ps":
            selector = selector or greps or any(not a.startswith("-") and not re.match(r"^[aeuxfwol]+$|^\d+$", a) for a in args)
        elif p in {"pgrep", "pidof", "tasklist"} or "getprocessesbyname" in p:
            selector = True
        elif p in {"lsof", "lsof.exe"} and any(re.match(r"^-[^-]*t", a) for a in args):
            selector = True
    return direct, selector, terminator


def process_kill_hits(payload, registry):
    """Flag host-wide process termination: a terminator that selects by image / pattern, or a process query by
    name / pattern together with any terminator (`taskkill //PID $(powershell ... Win32_Process ...)`). It is
    host safety, not repo policy: it runs outside the workspace too. Works on parsed argv (quoted arguments of
    grep / echo / git commit are data); raw text only when the command cannot be parsed. EncodedCommand is
    opaque and cannot be inspected. Never executes the command."""
    command = (payload.get("tool_input") or {}).get("command") or ""
    low = command.lower()
    if not any(w in low for w in PROCESS_PREFILTER):
        return []
    shell = "powershell" if payload.get("tool_name") == "PowerShell" else "bash"
    try:
        own, safe_pipe = _own_pid_targets(command, shell)
        direct, selector, terminator = process_findings(_process_argvs(command, shell), own, safe_pipe, shell)
        hit = direct or (selector and terminator)
    except Exception:
        hit = bool(PROCESS_KILL_FALLBACK.search(substitution_text(command) if shell == "bash" else command))
    return [("deny", PROCESS_TERMINATION_RULE)] if hit else []
