#!/usr/bin/env python3
"""Read-only: is every Factory skill present everywhere the plugin lists, routes, tests or documents it?

Usage: skill-touchpoints.py [<skill>... | --all]

Checks what a new or renamed skill must update besides its own SKILL.md and registry entry (the registry
side is check-registry.sh, the SKILL.md side skills-lint.sh):
  - factory-core SKILL.md "Skills" section (a table row for a lead, the tech list for a tech skill)
  - skill-contract.md layering diagram; README architecture diagram and the skill map / tech table
  - .claude/CLAUDE.md "Skills:" paragraph and its counts; plugin.json / marketplace.json lead count
  - a routing scenario in tests/routing.test.sh (`$(lead <s>)` or `$(tech <s>)`)
  - a dogfood scenario expecting it (tests/dogfood.sh EXPECT) and an eval grader evals/*/graders/<s>-fired.md
  - tech skills: every used_by skill names `rpg-factory:<s>`
  - no `SCAFFOLD:` marker left from scripts/new-skill.py
Exit 0 = complete; 1 = something missing (one line each); 2 = usage. Writes nothing.
"""
import glob
import json
import os
import re
import sys

ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}


def read(rel):
    try:
        return open(os.path.join(ROOT, rel), encoding="utf-8").read()
    except OSError:
        return ""


def section(text, heading):
    """Text from the first line starting with `heading` to the next heading of the same or higher level."""
    m = re.search(r"^(#+) " + re.escape(heading) + r".*$", text, re.M)
    if not m:
        return ""
    level = len(m.group(1))
    end = re.search(r"^#{1,%d} " % level, text[m.end():], re.M)
    return text[m.end():m.end() + end.start()] if end else text[m.end():]


def table(text, header):
    """Rows of the markdown table whose header row starts with `header`."""
    i = text.find(header)
    if i < 0:
        return ""
    rows = []
    for line in text[i:].splitlines()[2:]:
        if not line.startswith("|"):
            break
        rows.append(line)
    return "\n".join(rows)


def block_with(text, marker):
    """The fenced code block that contains `marker`."""
    for b in re.findall(r"```[^\n]*\n(.*?)```", text, re.S):
        if marker in b:
            return b
    return ""


def has(text, name):
    return re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", text) is not None


def count_said(text, noun):
    """Number written before `noun` ("8 specialised skills", "five tech skills"), or None."""
    m = re.search(r"(\d+|" + "|".join(WORDS.values()) + r")\s+" + noun, text, re.I)
    if not m:
        return None
    v = m.group(1).lower()
    return int(v) if v.isdigit() else {w: n for n, w in WORDS.items()}[v]


def check(reg, s):
    spec = reg["skills"][s]
    kind = spec["kind"]
    if kind == "core":
        return []
    lead = kind in ("repo", "cross-repo")
    miss = []
    skill_files = [os.path.join("skills", s, "SKILL.md")] + sorted(
        os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, "skills", s, "references", "*.md")))
    if not os.path.isfile(os.path.join(ROOT, skill_files[0])):
        return [f"skills/{s}/SKILL.md does not exist"]
    for f in skill_files:
        for n, line in enumerate(read(f).splitlines(), 1):
            if "SCAFFOLD:" in line:
                miss.append(f"{f.replace(os.sep, '/')}:{n} still has a SCAFFOLD: marker - write that part")
    core = section(read("skills/factory-core/SKILL.md"), "Skills")
    if lead and not any(has(r, s) for r in core.splitlines() if r.startswith("|")):
        miss.append("factory-core SKILL.md 'Skills' table has no row for this lead")
    if not lead and not has(core, s):
        miss.append("factory-core SKILL.md 'Skills' section does not name this tech skill")
    if not has(block_with(read("skills/factory-core/references/skill-contract.md"), "factory-core  -"), s):
        miss.append("skill-contract.md layering diagram does not name it")
    readme = read("README.md")
    if not has(block_with(readme, "cross-repo drivers"), s):
        miss.append("README architecture diagram does not name it")
    t = table(readme, "| Typical task | Lead skill |") if lead else table(readme, "| Tech skill | Used by |")
    if not has(t, s):
        miss.append("README " + ("skill map table" if lead else "tech skill table") + " has no row for it")
    para = next((p for p in read(".claude/CLAUDE.md").split("\n- ") if p.startswith("**Skills:**")), "")
    if not has(para, s):
        miss.append(".claude/CLAUDE.md 'Skills:' paragraph does not name it")
    routing = read("tests/routing.test.sh")
    if not re.search(r"\$\((?:lead|tech) " + re.escape(s) + r"\)", routing):
        miss.append(f"tests/routing.test.sh has no scenario asserting $({'lead' if lead else 'tech'} {s})")
    expects = " ".join(re.findall(r'EXPECT\[[^]]+\]="([^"]*)"', read("tests/dogfood.sh")))
    if not has(expects.replace("|", " "), s):
        miss.append("tests/dogfood.sh has no scenario that EXPECTs it")
    if not glob.glob(os.path.join(ROOT, "evals", "*", "graders", f"{s}-fired.md")):
        miss.append(f"no eval grader evals/*/graders/{s}-fired.md")
    if not lead:
        for u in spec.get("used_by") or []:
            if f"rpg-factory:{s}" not in read(f"skills/{u}/SKILL.md"):
                miss.append(f"used_by skill {u} never names rpg-factory:{s}")
    return miss


def global_counts(reg):
    leads = sum(1 for v in reg["skills"].values() if v["kind"] in ("repo", "cross-repo"))
    techs = sum(1 for v in reg["skills"].values() if v["kind"] == "tech")
    out = []
    para = next((p for p in read(".claude/CLAUDE.md").split("\n- ") if p.startswith("**Skills:**")), "")
    for noun, want in (("specialised skills", leads), ("tech skills", techs)):
        got = count_said(para, noun)
        if got != want:
            out.append(f".claude/CLAUDE.md 'Skills:' says {got} {noun}, the registry has {want}")
    for f in (".claude-plugin/plugin.json", ".claude-plugin/marketplace.json"):
        got = count_said(read(f), "specialised skills")
        if got != leads:
            out.append(f"{f} description says {got} specialised skills, the registry has {leads}")
    return out


def main():
    args = sys.argv[1:]
    if not args or "-h" in args or "--help" in args:
        print(__doc__)
        return 2 if not args else 0
    reg = json.load(open(os.path.join(ROOT, "registry.json"), encoding="utf-8"))
    names = sorted(reg["skills"]) if args == ["--all"] else args
    unknown = [n for n in names if n not in reg["skills"]]
    if unknown:
        print(f"not a registry skill: {', '.join(unknown)} (add skills.<name> first: scripts/new-skill.py)")
        return 2
    problems = [f"{s}: {m}" for s in names for m in check(reg, s)] + global_counts(reg)
    for p in problems:
        print(f"MISSING  {p}")
    print(("FAILED" if problems else "OK") + f": {len(names)} skill(s) checked, {len(problems)} touchpoint(s) missing")
    return 1 if problems else 0


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252: output is UTF-8 everywhere
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
