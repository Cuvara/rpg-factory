"""Process selectors, substitutions and host-wide termination detection."""
import re
import shlex

from .shell import expand, prog

PROCESS_TERMINATION_RULE = (
    "Terminating processes by image name or command-line pattern kills unrelated user and agent processes. "
    "Stop only PIDs you started (Start-Process -PassThru / $!)."
)

# Raw-text fallback: used only when the command cannot be parsed at all (never for a parsed command, so quoted
# arguments of grep / echo / git commit stay quiet).
PROCESS_KILL_FALLBACK = re.compile(
    r"(?is)(?:^|[;&|\n])\s*(?:(?:\S*[/\\])?taskkill(?:\.exe)?\b(?:(?![;&|\n]).)*?/{1,2}(?:im|fi)\b"
    r"|stop-process\b(?:(?![;&|\n]).)*?-(?:name|processname)\b|(?:pkill|killall)\b)")
PROCESS_PREFILTER = ("kill", "terminat", "stop-process", "spps", "wmic", "remove-cim")  # cheap: skip parsing without these
TERMINATORS = {"taskkill", "taskkill.exe", "stop-process", "spps", "kill", "pkill", "killall", "pskill", "remove-ciminstance"}
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
        for inner in _substitutions(command, shell):
            argvs += _process_argvs(inner, shell, depth + 1)
    return argvs


def _clean(argv):
    """PowerShell script-block braces glued to a word (`& {Stop-Process -Name x}`) are not part of it."""
    argv = list(argv)
    if len(argv) > 2 and argv[0].startswith("$") and argv[1] in {"=", "in"}:
        argv = argv[2:]  # `$ps = Get-CimInstance ...`, `foreach ($p in Get-CimInstance ...)`
    if argv:
        argv[0] = argv[0].lstrip("{")
        argv[-1] = argv[-1].rstrip("}") if len(argv) > 1 or argv[0] else argv[-1]
    return [a for a in argv if a != ""]


def process_findings(argvs):
    """(direct, selector, terminator) over every argv. direct = a terminator that names its targets host-wide
    (image name / filter / pattern); selector = a process query by name or pattern; terminator = any kill."""
    direct = selector = terminator = False
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
        if p in START_PROCESS:
            for i, a in enumerate(argv[1:], 1):
                if prog(a) in TERMINATORS or prog(a) == "wmic":
                    work.append([a] + [x for t in argv[i + 1:] for x in t.split(",")])
                    break
            continue
        if p in TERMINATORS:
            terminator = True
        if p in {"taskkill", "taskkill.exe"}:
            direct = direct or any(IMAGE_SELECTOR.match(a) for a in args)
        elif p in {"stop-process", "spps"}:
            direct = direct or any(PS_NAME_PARAM.match(a) for a in args)
        elif p == "kill":
            direct = direct or any(re.match(r"^-na(?:m(?:e)?)?$", a) for a in args) or "-1" in args[1:]
        elif p in {"pkill", "killall", "pskill"}:
            direct = True
        elif p.endswith((".kill", ".terminate")):
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
    return direct, selector, terminator


def process_kill_hits(payload, registry):
    """Flag host-wide process termination: a terminator that selects by image / pattern, or a process query by
    name / pattern together with any terminator (`taskkill //PID $(powershell ... Win32_Process ...)`). It is
    host safety, not repo policy: it runs outside the workspace too. Works on parsed argv (quoted arguments of
    grep / echo / git commit are data); raw text only when the command cannot be parsed. Never executes it."""
    command = (payload.get("tool_input") or {}).get("command") or ""
    low = command.lower()
    if not any(w in low for w in PROCESS_PREFILTER):
        return []
    shell = "powershell" if payload.get("tool_name") == "PowerShell" else "bash"
    try:
        direct, selector, terminator = process_findings(_process_argvs(command, shell))
        hit = direct or (selector and terminator)
    except Exception:
        hit = bool(PROCESS_KILL_FALLBACK.search(command))
    return [("deny", PROCESS_TERMINATION_RULE)] if hit else []


