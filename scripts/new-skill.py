#!/usr/bin/env python3
"""Scaffold a new Factory skill: skills/<name>/SKILL.md and its registry entry.

Usage:
  new-skill.py --name NAME --kind tech|repo|cross-repo --repos KEY[,KEY] --summary TEXT
               [--used-by SKILL,...]            tech: the repo/cross-repo skills that load it (required)
               [--owns-modules MODULE,...]      lead: become the primary owner of these modules
               [--drives-contract CONTRACT,...] lead: become the driver of these contracts (must have none)
               [--tools TOOL,...]               registry dev_tools the skill uses (its ## Tools section)
               [--domain ID]                 assign the skill to a registered domain
               [--cite-root PREFIX=REPO:SUB]... where its path:line citations resolve (registry cite_roots)
               [--dry-run]

A lead must own a module or drive a contract. The SKILL.md has every section skills-lint.sh requires,
with `SCAFFOLD:` markers where content must be written; skills-lint fails while any marker is left, and
`scripts/skill-touchpoints.py NAME` lists the other places to update (factory-core, README, CLAUDE.md,
routing/dogfood/eval scenarios, the leads that load a tech skill). The registry is only rewritten when
a JSON round trip reproduces the current file byte for byte, so the diff is exactly the new entry.
Exit 0 = written (or --dry-run printed); 2 = refused (nothing written).
"""
import json
import os
import re
import sys

ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(ROOT, "registry.json")
PREREQ = ("> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, "
          "invoke it first. Honour the declared Factory mode: in `analyze`, `plan` and `review` apply this skill's "
          "workflow, rules and checklist to produce the analysis, plan or findings - change nothing; in `validate` "
          "only run and grade checks.")
FRONT = """---
name: {name}
description: SCAFFOLD: {what}. Use when SCAFFOLD: <the developer situation this skill applies to>. Not for SCAFFOLD: <what the neighbouring skills own>.
argument-hint: "[task]"
allowed-tools: Bash(bash ${{CLAUDE_PLUGIN_ROOT}}/scripts/factory-context.sh:*)
---
"""


def tools_section(tools):
    lines = ["## Tools", ""]
    lines += [f"- `{t}`: SCAFFOLD: the step that uses it and the fallback when it is not OK." for t in tools] or [
        "- SCAFFOLD: no registry dev tool yet; name the ones this skill uses (registry `dev_tools[].used_by`)."]
    return "\n".join(lines) + "\n"


def tech_body(name, spec, tools):
    leads = ", ".join(f"`{u}`" for u in spec["used_by"])
    return f"""# SCAFFOLD: {name} - title

{PREREQ}

> **Supporting skill, never the owner:** invoke the lead (and co-leads) from the snapshot's routing line
> first - here {leads}. If you have not, stop and invoke it now: rules, gates, validation and the
> report come only from it. This skill adds how the technology works; it decides nothing.

Task: $ARGUMENTS

SCAFFOLD: which repo root the paths below are relative to (registry `cite_roots` if not the first repo's root).

## Applies when / Not when

- **Applies:** SCAFFOLD: the code you are writing, debugging or reviewing.
- **Not when:** SCAFFOLD: deciding scope, rules, checks or gates ({leads} own those).

## Scope

Repos {", ".join(f"`{r}`" for r in spec["repos"])}. Owns no module, contract or check.

## Architecture

- SCAFFOLD: how it is wired, each claim with `Symbol` (`path/File.cs:N`) checked by `skill-citations.py`.

## Idioms

- SCAFFOLD: the patterns the code uses, cited.

## Pitfalls

- SCAFFOLD: a verified failure and the file or issue that proves it (`path/File.cs`).

## Testing

- SCAFFOLD: how to run one test and what a skip means.

""" + tools_section(tools)


def lead_body(name, spec, tools):
    return f"""# SCAFFOLD: {name} - title

{PREREQ}

Task: $ARGUMENTS

## Applies when / Not when

- **Applies:** SCAFFOLD: the paths and tasks this skill owns.
- **Not when:** SCAFFOLD: the neighbouring skill for each excluded area.

## Scope

Repo(s) {", ".join(f"`{r}`" for r in spec["repos"])}. SCAFFOLD: modules and contracts (from the registry), hand-offs.

## Workflow delta

1. SCAFFOLD: the steps this skill adds to factory-core's workflow.

## Rules

- SCAFFOLD: each rule with its source doc (rules that are registry module rules stay in the registry).

## Generated & protected paths

- SCAFFOLD: generator-owned or protected paths, or "none".

## Validation delta

- SCAFFOLD: the registry checks that matter and their evidence; external checks.

## Human gates

- SCAFFOLD: the registry human gates this work reaches.

## Review checklist

- [ ] SCAFFOLD: what a reviewer verifies.

## Report additions

- SCAFFOLD: what the report adds to factory-core's template.

""" + tools_section(tools)


def refuse(msg):
    print(f"REFUSED: {msg} - nothing written")
    return 2


def csv(v):
    return [x for x in (v or "").split(",") if x]


def main():
    a = {"cite_root": []}
    it = iter(sys.argv[1:])
    for arg in it:
        if arg in ("-h", "--help"):
            print(__doc__)
            return 0
        if arg == "--dry-run":
            a["dry_run"] = True
            continue
        if not arg.startswith("--"):
            return refuse(f"unexpected argument {arg}")
        key, val = arg[2:].replace("-", "_"), next(it, None)
        if val is None:
            return refuse(f"{arg} needs a value")
        if key == "cite_root":
            a["cite_root"].append(val)
        else:
            a[key] = val
    name, kind = a.get("name", ""), a.get("kind", "")
    if not re.fullmatch(r"[a-z][a-z0-9-]*[a-z0-9]", name):
        return refuse("--name must be kebab-case (e.g. unity-physics)")
    if kind not in ("tech", "repo", "cross-repo"):
        return refuse("--kind must be tech, repo or cross-repo")
    if not a.get("summary") or not a.get("repos"):
        return refuse("--summary and --repos are required")

    raw = open(REG, encoding="utf-8").read()
    if json.dumps(json.loads(raw), indent=2, ensure_ascii=False) + "\n" != raw:
        return refuse("registry.json is not in canonical form (json.dumps indent=2), a rewrite would reformat it; "
                      "normalise it in its own commit first")
    reg = json.loads(raw)
    skills, repos = reg["skills"], reg["repos"]
    if name in skills or os.path.exists(os.path.join(ROOT, "skills", name)):
        return refuse(f"skill {name} already exists")
    rlist = csv(a["repos"])
    bad = [r for r in rlist if r not in repos]
    if bad:
        return refuse(f"unknown repo key(s) {bad} (known: {', '.join(repos)})")
    tools = csv(a.get("tools"))
    known_tools = {t["id"]: t for t in reg.get("dev_tools", [])}
    bad = [t for t in tools if t not in known_tools]
    if bad:
        return refuse(f"unknown dev tool(s) {bad} (known: {', '.join(known_tools)})")
    spec = {"kind": kind, "repos": rlist}
    domain = a.get("domain")
    if domain:
        if domain not in reg.get("domains", {}):
            return refuse(f"unknown domain {domain}")
        spec["domain"] = domain
    used_by, mods, contracts = csv(a.get("used_by")), csv(a.get("owns_modules")), csv(a.get("drives_contract"))
    if kind == "tech":
        if mods or contracts:
            return refuse("a tech skill owns no module and drives no contract")
        bad = [u for u in used_by if skills.get(u, {}).get("kind") not in ("repo", "cross-repo")]
        if not used_by or bad:
            return refuse("--used-by must name existing repo/cross-repo skills" + (f" (not: {bad})" if bad else ""))
        spec["order"] = max(int(s["order"]) for s in skills.values() if s["kind"] == "tech") + 1
        spec["used_by"] = used_by
    else:
        if used_by:
            return refuse("--used-by is for tech skills")
        if not mods and not contracts:
            return refuse("a lead must own a module (--owns-modules) or drive a contract (--drives-contract)")
        known_mods = {m["id"]: m for m in reg["modules"]}
        bad = [m for m in mods if m not in known_mods]
        if bad:
            return refuse(f"unknown module(s) {bad}")
        known_c = {c["id"]: c for c in reg.get("contracts", [])}
        bad = [c for c in contracts if c not in known_c or known_c[c].get("driver")]
        if bad:
            return refuse(f"contract(s) {bad} unknown or already driven by another skill")
        # after every existing lead: a lower order wins routing ties, so a new skill never outranks an old one
        # silently (move it later on purpose if it should); stays below the tech skills (90+)
        used = {int(s["order"]) for s in skills.values()}
        top = max(int(s["order"]) for s in skills.values() if s["kind"] in ("repo", "cross-repo"))
        spec["order"] = next(o for o in list(range(top + 5, 90, 5)) + list(range(top + 1, 90)) if o not in used)
    spec["summary"] = a["summary"]
    roots = {}
    for cr in a["cite_root"]:
        prefix, _, target = cr.partition("=")
        if target.split(":")[0] not in repos or ":" not in target:
            return refuse(f"--cite-root {cr}: target must be <repo key>:<subpath>")
        roots[prefix] = target
    if roots:
        spec["cite_roots"] = roots

    skills[name] = spec
    for m in reg["modules"]:
        if m["id"] in mods:
            m["skills"] = [name] + [s for s in m.get("skills", []) if s != name]
    for c in reg.get("contracts", []):
        if c["id"] in contracts:
            c["driver"] = name
    for t in tools:
        known_tools[t]["used_by"] = list(known_tools[t].get("used_by", [])) + [name]
    what = a["summary"].rstrip(".")
    body = FRONT.format(name=name, what=what) + "\n" + (tech_body(name, spec, tools) if kind == "tech" else lead_body(name, spec, tools))
    out = json.dumps(reg, indent=2, ensure_ascii=False) + "\n"
    path = os.path.join(ROOT, "skills", name, "SKILL.md")
    if a.get("dry_run"):
        print(f"--- would write skills/{name}/SKILL.md ({body.count(chr(10))} lines) and registry skills.{name}:")
        print(json.dumps(spec, indent=2, ensure_ascii=False))
        return 0
    os.makedirs(os.path.dirname(path))
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)
    with open(REG, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(out)
    print(f"wrote skills/{name}/SKILL.md and registry skills.{name} (order {spec['order']})")
    if mods or contracts or tools:
        print(f"  registry also: {'primary owner of ' + ', '.join(mods) + '; ' if mods else ''}"
              f"{'driver of ' + ', '.join(contracts) + '; ' if contracts else ''}{'dev_tools used_by ' + ', '.join(tools) if tools else ''}")
    print(f"next: write every SCAFFOLD: part, then `python3 -B scripts/skill-touchpoints.py {name}` lists the rest"
          + (f" (each of {', '.join(used_by)} must name rpg-factory:{name} at the step that needs it)" if used_by else ""))
    return 0


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252: output is UTF-8 everywhere
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
