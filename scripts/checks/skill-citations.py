#!/usr/bin/env python3
"""Read-only check that the file:line citations in the Factory skills still point at what they name.

Usage: skill-citations.py [--workspace DIR] [--skill NAME]... [--ref REPO=REF]... [--suggest] [--offline]

A line citation is a backticked `path/File.cs:N`, `File.cs:N-M`, `File.cs:N,M-K` or a bare `:N` that
continues the last file named earlier in the same section (a heading resets it). Paths resolve through the registry:
`skills.<s>.cite_roots` maps a prefix ("" = default, "dots:", "client:", "backend/", ...) to
"<repo key>:<subpath>"; every repo directory name ("Netcode/", "UnityDots/", ...) is a prefix as well.
A path that does not exist there is looked up by suffix in the skill's repos (unique match only).

Every line citation needs an anchor: a backticked identifier written after the previous citation and
before this one (`TickOnce` (`Server/TickLoop.cs:510`)); its last segment must occur within the cited
lines +/- 3. Files are read at the integration branch (`origin/<default_branch>` from the last fetch,
`--ref server=HEAD` to override), never from the working tree.

--offline checks only what needs no repos (every line citation backticked and anchored) - skills-lint.
Exit 0 = no problem; 1 = problems; 2 = usage. Writes nothing.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(os.path.dirname(HERE))
EXT = r"(?:cs|go|py|sh|yml|yaml|json|asmdef|asset|md|proto|sql|csproj|uxml|uss|mod|toml|txt|jq)"
LINES = r"\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*"
FULL = re.compile(r"^(?P<path>(?:[a-z]+:)?[A-Za-z0-9_.~/\-]+\." + EXT + r"):(?P<lines>" + LINES + r")$", re.IGNORECASE)
CONT = re.compile(r"^:(?P<lines>" + LINES + r")$")
FILE = re.compile(r"^(?P<path>(?:[a-z]+:)?[A-Za-z0-9_.~/\-]+\." + EXT + r")$", re.IGNORECASE)
IDENT = re.compile(r"^[\[@]?(?P<id>[A-Za-z_][\w.]*?)(?:<[^`]*>)?(?:\([^`]*\))?[\]]?(?:\s.*)?$")
BARE_LINE_CITE = re.compile(r"(?<![`\w/])[A-Za-z0-9_.~/\-]+\." + EXT + r":\d+", re.IGNORECASE)
SPAN = re.compile(r"`([^`\n]+)`")
SLACK = 3


def blocks(text):
    """Paragraphs, list items and table rows: the scope a bare `:N` continuation inherits from."""
    out, cur = [], []
    for line in text.splitlines():
        starts = re.match(r"^\s*(?:[-*]|\d+\.|\|)\s", line) or not line.strip()
        if starts and cur:
            out.append("\n".join(cur))
            cur = []
        if line.strip():
            cur.append(line)
    if cur:
        out.append("\n".join(cur))
    return out


def anchor_of(span):
    """The identifier a backticked span names, or None (file names, numbers, prose, flags)."""
    s = span.strip()
    if FILE.match(s) or FULL.match(s) or CONT.match(s) or s.startswith(("-", "$", "/", ".")):
        return None
    m = IDENT.match(s)
    if not m:
        return None
    ident = m.group("id").rstrip(".")
    last = ident.split(".")[-1]
    if not last or not (re.search(r"[A-Z_]", ident) or "." in ident or "(" in s):
        return None  # lowercase words in backticks are values or keywords, not symbols
    return last


def parse(text):
    """[(path, lines, anchor or None, context)] in document order, plus unbackticked line citations."""
    cites, loose = [], []
    last_file = None  # carries across the paragraphs and list items of one section; a heading resets it
    for b in blocks(text):
        pending = None
        if b.lstrip().startswith("#"):
            last_file = None
        for m in SPAN.finditer(b):
            s = m.group(1).strip()
            full, cont, fmatch = FULL.match(s), CONT.match(s), FILE.match(s)
            if full:
                last_file = full.group("path")
                cites.append((last_file, full.group("lines"), pending, b))
                pending = None
            elif cont and last_file:
                cites.append((last_file, cont.group("lines"), pending, b))
                pending = None
            elif cont:
                loose.append(f":{cont.group('lines')} (continues no file named earlier in its section)")
            elif fmatch:
                last_file = fmatch.group("path")
            else:
                a = anchor_of(s)
                if a:
                    pending = a
        loose += BARE_LINE_CITE.findall(SPAN.sub("", b))
    return cites, loose


def ranges(spec):
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out.append((int(a), int(b or a)))
    return out


class Repos:
    def __init__(self, ws, reg, overrides):
        self.ws, self.reg, self.over = ws, reg, overrides
        self._ref, self._tree, self._file = {}, {}, {}

    def dir(self, key):
        return os.path.join(self.ws, self.reg["repos"][key]["path"])

    def git(self, key, *args):
        try:
            r = subprocess.run(["git", "-C", self.dir(key), *args], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=60)
        except (OSError, subprocess.SubprocessError):
            return None
        return r.stdout if r.returncode == 0 else None

    def present(self, key):
        return os.path.isdir(os.path.join(self.dir(key), ".git")) or os.path.isfile(os.path.join(self.dir(key), ".git"))

    def ref(self, key):
        if key not in self._ref:
            want = self.over.get(key)
            if not want:
                b = self.reg["repos"][key].get("default_branch") or "HEAD"
                want = next((r for r in (f"origin/{b}", b, "HEAD") if self.git(key, "rev-parse", "-q", "--verify", r + "^{commit}")), "HEAD")
            self._ref[key] = want
        return self._ref[key]

    def tree(self, key):
        if key not in self._tree:
            self._tree[key] = (self.git(key, "ls-tree", "-r", "--name-only", self.ref(key)) or "").splitlines()
        return self._tree[key]

    def read(self, key, path):
        k = (key, path)
        if k not in self._file:
            out = self.git(key, "show", f"{self.ref(key)}:{path}")
            self._file[k] = None if out is None else out.splitlines()
        return self._file[k]


def roots_for(reg, skill):
    spec = reg["skills"][skill]
    roots = {r["path"].rstrip("/") + "/": f"{k}:" for k, r in reg["repos"].items()}
    roots.setdefault("", f"{spec['repos'][0]}:")
    roots.update(spec.get("cite_roots") or {})
    return roots


def resolve(repos, reg, skill, path):
    """(repo key, repo-relative path, candidates) - candidates set when the path is ambiguous."""
    roots = roots_for(reg, skill)
    prefix = max((p for p in roots if path.startswith(p)), key=len)
    key, _, sub = roots[prefix].partition(":")
    rest = path[len(prefix):]
    full = f"{sub.strip('/')}/{rest}".lstrip("/") if sub else rest
    if repos.read(key, full) is not None:
        return key, full, None
    keys = [key] + [k for k in reg["skills"][skill]["repos"] if k != key and k in reg["repos"]]
    hits = [(k, p) for k in keys if repos.present(k) for p in repos.tree(k) if ("/" + p).endswith("/" + rest)]
    if len(hits) > 1:
        inside = [h for h in hits if h[0] == key and h[1].startswith(sub.strip("/") + "/")] if sub else []
        hits = inside if len(inside) == 1 else hits
    if len(hits) == 1:
        return hits[0][0], hits[0][1], None
    return key, full, hits


def main():
    args = sys.argv[1:]
    if "-h" in args or "--help" in args:
        print(__doc__)
        return 0
    reg = json.load(open(os.path.join(PLUGIN_ROOT, "registry.json"), encoding="utf-8"))
    ws = os.environ.get(reg["workspace"].get("root_env", ""), "") or reg["workspace"]["root_default"]
    skills, overrides = [], {}
    suggest, offline = "--suggest" in args, "--offline" in args
    it = iter(args)
    for a in it:
        if a == "--workspace":
            ws = next(it, "")
        elif a == "--skill":
            skills.append(next(it, ""))
        elif a == "--ref":
            k, _, v = next(it, "").partition("=")
            overrides[k] = v
        elif a not in ("--suggest", "--offline"):
            print(f"unknown argument {a}\n{__doc__}")
            return 2
    skills = skills or sorted(reg["skills"])
    unknown = [s for s in skills if s not in reg["skills"]]
    if unknown:
        print(f"unknown skill(s): {', '.join(unknown)}")
        return 2
    repos = Repos(ws, reg, overrides)
    problems, checked, skipped = [], 0, set()
    for skill in skills:
        sdir = os.path.join(PLUGIN_ROOT, "skills", skill)
        files = [os.path.join(sdir, "SKILL.md")] + sorted(
            os.path.join(sdir, "references", f) for f in os.listdir(os.path.join(sdir, "references"))
            if f.endswith(".md")) if os.path.isdir(os.path.join(sdir, "references")) else [os.path.join(sdir, "SKILL.md")]
        for f in files:
            if not os.path.isfile(f):
                continue
            rel = os.path.relpath(f, PLUGIN_ROOT).replace("\\", "/")
            cites, loose = parse(open(f, encoding="utf-8").read())
            for c in loose:
                if c.startswith(":"):
                    problems.append(f"{rel}: `{c.split(' ')[0]}` - orphan continuation: it {c.split(' (')[1].rstrip(')')}; name the file")
                else:
                    problems.append(f"{rel}: `{c}` - line citation outside backticks (write it as `path:N`)")
            for path, spec, anchor, _ in cites:
                where = f"{rel}: `{path}:{spec}`"
                if path.lower().endswith(".md"):
                    problems.append(f"{where} - doc line citation: cite `{path}` by section, not line (skill-contract)")
                    continue
                if not anchor:
                    problems.append(f"{where} - unanchored: name the symbol it shows in backticks right before it")
                    continue
                if offline:
                    checked += 1
                    continue
                key, rpath, cands = resolve(repos, reg, skill, path)
                if not repos.present(key):
                    skipped.add(key)
                    continue
                checked += 1
                if cands:
                    problems.append(f"{where} - ambiguous file: " + ", ".join(f"{k}:{p}" for k, p in cands[:4]))
                    continue
                text = repos.read(key, rpath)
                if text is None:
                    problems.append(f"{where} - no such file at {key} {repos.ref(key)}")
                    continue
                rs = ranges(spec)
                if max(b for _, b in rs) > len(text):
                    problems.append(f"{where} - line past the end ({key}:{rpath} has {len(text)} lines at {repos.ref(key)})")
                    continue
                word = re.compile(r"(?<![\w])" + re.escape(anchor) + r"(?![\w])")
                near = any(word.search(text[i]) for a, b in rs for i in range(max(0, a - 1 - SLACK), min(len(text), b + SLACK)))
                if near:
                    continue
                found = [i + 1 for i, line in enumerate(text) if word.search(line)]
                msg = f"{where} - drift: `{anchor}` is not at the cited lines ({key}:{rpath} @ {repos.ref(key)})"
                if found:
                    first = rs[0][0]
                    to = min(found, key=lambda n: abs(n - first))
                    d = to - first
                    new = ",".join(f"{a + d}" if a == b else f"{a + d}-{b + d}" for a, b in rs)
                    msg += f"; `{anchor}` is at line {', '.join(map(str, found[:5]))}"
                    if suggest:
                        msg += f" -> suggest `{path}:{new}`"
                else:
                    msg += f"; `{anchor}` no longer occurs in the file"
                problems.append(msg)
    for p in problems:
        print(f"FAIL  {p}")
    for k in sorted(skipped):
        print(f"SKIP  repo {k} not present in {ws}: its citations are not checked")
    mode = "offline (anchors only)" if offline else "against " + ", ".join(
        f"{k}@{repos.ref(k)}" for k in sorted({k for k in reg["repos"] if repos.present(k)}))
    if problems:
        print(f"FAILED: {checked} line citation(s) checked {mode}, {len(problems)} problem(s)")
        return 1
    print(f"OK: {checked} line citation(s) checked {mode}, 0 problem(s)")
    return 0


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252: output is UTF-8 everywhere
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
