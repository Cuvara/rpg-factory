"""Shell tokenization, wrapper peeling and nested command expansion."""
import os
import re
import shlex

from .common import CMDS, INTERPRETERS, MAX_DEPTH, POWERSHELLS, RESERVED_LEAD, SEPARATORS, SHELLS

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


