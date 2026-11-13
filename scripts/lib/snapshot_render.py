"""Factory snapshot presentation: text, domain views and routing explanations.

The context engine collects workspace state; this module formats its snapshots and
prepares domain views without importing the engine.
"""
import json
import os
import sys

MODES = {  # the Factory execution-mode contract (the hooks add advisories once declared; they never block)
    "analyze":   "read-only. Explain what exists and what a change would touch. Invoke the lead skill for its domain rules; change nothing.",
    "plan":      "read-only. Invoke the lead skill, then produce the plan from its workflow: files, legs, obligations, checks (tier + command), gates. Change nothing.",
    "implement": "full workflow: branch, implement, obligations, validate with run-checks.py, verify, report.",
    "validate":  "run and grade checks only (run-checks.py; --status first). No file changes.",
    "review":    "read-only review of existing changes against the lead skill's review checklist and registry rules.",
    "resume":    "factory-status.py first, then continue the interrupted task at its first incomplete step (implement rules).",
}


def die(msg, code=2):
    print(f"factory-context: {msg}", file=sys.stderr)
    sys.exit(code)


def domain_result(reg, domain_id, ws, lead_override=None):
    domains = reg.get("domains", {})
    if domain_id not in domains:
        die(f"unknown domain {domain_id}; known: {', '.join(domains) or 'none'}")
    d = dict(domains[domain_id])
    lead = d.get("lead")
    if lead_override:
        if lead_override not in reg.get("skills", {}):
            die(f"unknown lead {lead_override}; known: {', '.join(reg.get('skills', {}))}")
        if reg["skills"][lead_override].get("domain", "engineering") != domain_id:
            die(f"lead {lead_override} does not belong to domain {domain_id}")
        lead = lead_override
    repos = []
    for key in d.get("repos", []):
        rep = reg["repos"][key]
        path = os.path.join(ws, rep["path"]) if ws else rep["path"]
        present = os.path.isdir(path)
        if not present and not rep.get("optional", False):
            present = True
        repos.append({"id": key, "path": path, "status": "present" if present else "absent"})
    return {"id": domain_id, "status": d.get("status"), "summary": d.get("summary"), "lead": lead,
            "repos": repos, "artifact_kinds": d.get("artifact_kinds", []), "quality_gates": d.get("quality_gates", []),
            "human_gates": d.get("human_gates", []), "handoffs": d.get("handoffs", [])}


def intent_domain(reg, args, ws):
    domains = reg.get("domains", {})
    if args["domain"]:
        result = domain_result(reg, args["domain"], ws, args["lead"])
        if args["kind"] and args["kind"] not in result["artifact_kinds"]:
            die(f"kind {args['kind']} is not claimed by domain {args['domain']}")
        return result
    if not args["kind"]:
        return None
    kinds = {}
    for did, d in domains.items():
        for kind in d.get("artifact_kinds", []):
            kinds.setdefault(kind, []).append(did)
    candidates = kinds.get(args["kind"], [])
    if not candidates:
        die("unknown artifact kind; known: " + (", ".join(sorted(kinds)) if kinds else "no artifact kinds registered"))
    if args["lead"]:
        skill = reg.get("skills", {}).get(args["lead"])
        if not skill:
            die(f"unknown lead {args['lead']}; known: {', '.join(reg.get('skills', {}))}")
        did = skill.get("domain", "engineering")
        if did not in candidates:
            die(f"lead {args['lead']} does not belong to a domain claiming kind {args['kind']}")
        return domain_result(reg, did, ws, args["lead"])
    if len(candidates) > 1:
        if args["json"]:
            print(json.dumps({"ambiguous": True, "domains": candidates}))
        else:
            print(f"AMBIGUOUS: kind {args['kind']} is claimed by domains {', '.join(candidates)}")
        sys.exit(3)
    return domain_result(reg, candidates[0], ws)


def print_domain(result, as_json):
    if as_json:
        print(json.dumps({"domain": result}))
        return
    print("Domain")
    for key in ("id", "status", "summary"):
        print(f"{key}: {result.get(key) or ''}")
    print("lead: " + (result["lead"] if result["lead"] else "routes by --repo/--paths (module ownership)"))
    for key in ("repos", "artifact_kinds", "quality_gates", "human_gates", "handoffs"):
        values = result[key]
        if key == "repos":
            values = [f"{r['id']} ({r['status']}: {r['path']})" for r in values]
        print(f"{key}: {', '.join(values) if values else 'none'}")


def handoff_graph(reg, domain_id):
    """Return all domains in stable topological order or a concrete cycle."""
    domains = reg.get("domains", {})
    if domain_id not in domains:
        die(f"unknown domain {domain_id}; known: {', '.join(domains)}", 3)
    edges = {name: set() for name in domains}
    for c in reg.get("contracts", []):
        if c.get("kind") != "handoff":
            continue
        src = c.get("domain") or next((m.get("domain", "engineering") for m in reg.get("modules", [])
                                        if m["repo"] == c.get("source", {}).get("repo") and
                                        any(c["source"].get("path", "").startswith(p.rstrip("/") + "/") or
                                            c["source"].get("path", "") == p.rstrip("/") for p in m.get("paths", []))), "engineering")
        for end in c.get("copies", []):
            dst = next((m.get("domain", "engineering") for m in reg.get("modules", []) if m["repo"] == end.get("repo") and
                        any(end.get("path", "").startswith(p.rstrip("/") + "/") or end.get("path", "") == p.rstrip("/")
                            for p in m.get("paths", []))), "engineering")
            if src in edges and dst in edges and src != dst:
                edges[src].add(dst)
    indegree = {n: 0 for n in edges}
    for targets in edges.values():
        for target in targets:
            indegree[target] += 1
    ready = sorted(n for n, d in indegree.items() if d == 0)
    order = []
    while ready:
        node = ready.pop(0)
        order.append(node)
        for target in sorted(edges[node]):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
                ready.sort()
    if len(order) != len(edges):
        remaining = {n for n, d in indegree.items() if d}
        visited, stack, positions = set(), [], {}

        def find_cycle(node):
            if node in positions:
                return stack[positions[node]:] + [node]
            if node in visited:
                return None
            visited.add(node)
            positions[node] = len(stack)
            stack.append(node)
            for target in sorted(edges[node] & remaining):
                found = find_cycle(target)
                if found:
                    return found
            stack.pop()
            positions.pop(node)
            return None

        for start in sorted(remaining):
            cycle = find_cycle(start)
            if cycle:
                return None, cycle
        return None, sorted(remaining)
    return order, None


def explain(state, reg):
    sel = {s["skill"]: s for s in state["suggested_skills"]}
    rows = []
    for name, sk in sorted(reg["skills"].items(), key=lambda kv: kv[1].get("order", 999)):
        if name == "factory-core":
            continue
        if name in sel:
            s = sel[name]
            role = "lead" if state["routing"]["lead"] == name else ("co-lead" if name in state["routing"]["co_leads"] else s["role"])
            rows.append({"skill": name, "selected": role, "class": s.get("class"), "order": s.get("order"), "why": s["reasons"]})
        elif sk.get("kind") == "tech":
            users = [u for u in sk.get("used_by", []) if u in sel and sel[u]["role"] != "follow-up"]
            rows.append({"skill": name, "selected": "tech (supporting)" if name in state["routing"].get("tech", []) else "not selected",
                         "why": [f"tech skill: never lead/leg/follow-up; listed when a working skill uses it ({', '.join(users)})" if users
                                 else f"tech skill: none of its users ({', '.join(sk.get('used_by', []))}) works on this change"]})
        else:
            owns = [m["id"] for m in reg["modules"] if name in (m.get("skills") or [])]
            drives = [c["id"] for c in reg["contracts"] if c.get("driver") == name]
            rows.append({"skill": name, "selected": "not selected",
                         "why": [f"no touched path maps to its modules ({', '.join(owns[:4])}{'...' if len(owns) > 4 else ''})"
                                 + (f" and no touched end of its contracts ({', '.join(drives)})" if drives else "")]})
    return rows


def render(snap, reg, args, views):
    out = []
    add = out.append
    code = lambda s: f"`{s}`"
    inst = snap["install"]
    add(f"# Factory context ({snap['generated_at']}, {snap['elapsed_ms']} ms)")
    add(f"rpg-factory runtime {inst.get('runtime_version') or '-'} ({inst.get('runtime_kind') or 'not in a session'}), "
        f"installed {inst.get('installed_version')}, source {inst.get('source_version')} - install state **{inst.get('state')}**")
    if inst.get("state") not in ("CURRENT", None):
        for r in inst.get("reasons", [])[:3]:
            add(f"- {r}")
    add(f"Workspace `{snap['workspace']}`. Live snapshot: recompute per task; changed paths listed at task start are the user's baseline.")
    if snap.get("mode"):
        add(f"**Mode: {snap['mode']}** - {MODES[snap['mode']]} (advisory: the hooks warn on state-changing commands and file writes in read-only modes, they do not block - keep to the mode; switch with `--mode implement` only when the user asked)")
    cl = snap.get("cwd_clone")
    if cl:
        add(f"**The current directory is an embedded clone** `{cl['in']}/{cl['path']}` (of `{cl['of']}`): gitignored user state inside "
            f"the {cl['in']} repo, NOT the canonical {cl['of']} checkout `{cl['canonical']}`. Factory snapshots, routes and validates "
            f"the canonical repos below. Do not edit, commit, reset or clean the clone unless the user explicitly asks.")
    add("")
    add("**Rules:** " + "; ".join(f"**{g['id']}** {g['rule']}" if args["full"] else f"**{g['id']}**" for g in reg["global_rules"])
        + ("" if args["full"] else " (full text: `--full` or registry `global_rules`)"))
    lang = (reg.get("workspace") or {}).get("report_language")
    add("**Language:** write everything in English (files, plans, briefs, messages, commits, PR text); report to the owner in "
        + (lang.strip() if isinstance(lang, str) and lang.strip() else "the user's language") + ".")
    add("**Human gates:** " + ", ".join(g["id"] + (" (high)" if g.get("decision") == "deny" else "") for g in reg["human_gates"])
        + " - no tag or release without explicit release authorization in this task; otherwise stop at READY_TO_TAG.")
    if snap.get("services"):
        add("**Services:** " + ", ".join(f"`{sid}` {'reachable' if s['reachable'] else 'not reachable'} ({s['probe']})"
                                         for sid, s in snap["services"].items()))
    for r in snap["repos"]:
        add("")
        if r.get("error"):
            add(f"## {r['repo']}: ERROR {r['error']}")
            continue
        wt = f" worktree of {code(r['main_checkout'])}" if r.get("worktree") else ""
        if (r.get("resolution") or {}).get("note"):
            add(f"> **{r['repo']}: canonical checkout used.** {r['resolution']['note']}")
        up = r.get("upstream")
        upt = f", {up['ref']} +{up['ahead']}/-{up['behind']} (last fetch)" if up else ""
        prot = " **PROTECTED** (branch before committing)" if r["protected"] else ""
        if not r["files"]:
            add(f"## {r['repo']}: {r['branch']}{prot} @{r['head']}{upt}{wt} - clean"
                + (f" (submodules {', '.join(r['submodules'])} not scanned)" if r.get("submodules") and not r.get("submodules_scanned") else ""))
            continue
        add(f"## {r['repo']}: {r['branch']}{prot} @{r['head']}{upt}{wt}  `{r['path']}`")
        given = any(f["source"] == "given" for f in r["files"])
        add(f"Changed paths ({len(r['files'])}" + (", from --paths" if given else ", pre-existing at task start = user baseline: never stage/clean/reset them") + "):")
        for f in r["files"][:25]:
            add(f"- {code(f['status'])} {code(f['path'])} -> {f['module'] or '**unmapped**'}" + (" (committed on branch)" if f["source"] == "branch" else ""))
        if len(r["files"]) > 25:
            add(f"- ... {len(r['files']) - 25} more (use --json)")
        if not r.get("submodules_scanned") and r.get("submodules"):
            add(f"- submodules {', '.join(map(code, r['submodules']))}: pointer moves shown above; uncommitted work inside them "
                "is NOT scanned (`--submodules`, ~9 s) - treat their contents as user state")
        for x in r.get("rejected_paths", []):
            add(f"**Warning: not routed** {code(x['path'])} - {x['reason']} (not a {r['repo']} file; never treated as repo-level)")
        route_cmd = f"`factory-context.sh --repo {r['repo']} --paths <files the task will write>`"
        v = views.get(r["repo"])
        if v is None:  # uncommitted changes only: the user's baseline, not the task
            add(f"**Baseline only - not routed:** the paths above are the user's pre-existing changes, not the task: no lead, "
                f"checks or gates are derived from them. Route the task with {route_cmd}.")
            issues = [k for k in reg.get("known_issues", []) if r["repo"] in k["scope"].split(",") or k["scope"] == "workspace"]
            if issues:
                add("Known issues here: " + "; ".join(f"**{k['id']}**" + (f" {k['summary']}" if args["full"] else "") for k in issues))
            continue
        if v is not r and any(f["source"] == "worktree" for f in r["files"]):
            add(f"Routing below covers only the {len(v['files'])} path(s) committed on this branch; the uncommitted paths are the "
                f"user's baseline. Route the task with {route_cmd}.")
        r = v
        rt = r["routing"]
        if not (rt["lead"] or rt["legs"] or rt["follow_ups"]):
            mods = {m["id"]: m for m in reg["modules"]}
            docs = list(dict.fromkeys(f"{reg['repos'][r['repo']]['path']}/{mods[t]['claude_md']}" for t in r["touched"]
                                      if t in mods and mods[t].get("claude_md")))
            add(f"**Routing** no specialised lead - factory-core only; follow "
                + (", ".join(map(code, docs)) if docs else code(reg["repos"][r["repo"]]["path"] + "/CLAUDE.md")))
        else:
            add("**Routing** " + (f"lead {code('rpg-factory:' + rt['lead'])}" if rt["lead"] else "no specialised lead (factory-core only)")
                + (f" · co-leads {', '.join(rt['co_leads'])}" if rt["co_leads"] else "")
                + (f" · legs {', '.join(rt['legs'])}" if rt["legs"] else "")
                + (f" · follow-ups {', '.join(rt['follow_ups'])}" if rt["follow_ups"] else "")
                + (f" · tech {', '.join(rt['tech'])}" if rt.get("tech") else "")
                + (" · **AMBIGUOUS** (same precedence class and order) - ask the user or pass --lead" if rt["ambiguous"] else "")
                + (" · (override)" if rt.get("override") else ""))
            # UI tech skills load progressively: the orchestrator's plan picks the subset (docs/architecture/ui-skills.md).
            ui_tech = [s for s in rt.get("tech") or [] if (reg["skills"].get(s) or {}).get("domain") == "ui"]
            other_tech = [s for s in rt.get("tech") or [] if s not in ui_tech]
            if rt["lead"] and not rt["ambiguous"]:
                add(f"  **Next:** invoke the Skill tool with {code('rpg-factory:' + rt['lead'])} now - also for plan-only or "
                    "read-only requests; it owns this change's workflow, validation and gates"
                    + (f", then {', '.join(code('rpg-factory:' + c) for c in rt['co_leads'])}" if rt["co_leads"] else "") + "."
                    + (f" Then invoke the tech skill(s) {', '.join(code('rpg-factory:' + t) for t in other_tech)} (supporting context, "
                       "not a follow-up) before implementing, debugging, reviewing, or answering how the code works or how to "
                       "run a test - in every mode." if other_tech else "")
                    + (f" UI skills ({', '.join(ui_tech)}): invoke {code('rpg-factory:ui-orchestrator')} first; its UI plan "
                       "names the subset to load - invoke only those, never all of them." if ui_tech else ""))
            regc = {c["id"]: c for c in reg.get("contracts", [])}
            for c in r["contracts"]:
                src_repo = (regc.get(c["id"], {}).get("source") or {}).get("repo")
                if (src_repo and src_repo != r["repo"] and c["driver"] != rt["lead"]
                        and all(h["role"] != "source" for h in c["hits"])):
                    add(f"  **Cross-repo:** this repo is a downstream end of contract {code(c['id'])} (source in `{src_repo}`, "
                        f"driver {code('rpg-factory:' + c['driver'])}). If the task also changes the `{src_repo}` side, the task's "
                        f"lead is {code('rpg-factory:' + c['driver'])} - invoke it first; {code('rpg-factory:' + rt['lead'])} "
                        "is its follow-up here.")
            if rt.get("lead_basis"):
                add(f"  lead because: {'; '.join(rt['lead_basis']['reasons'][:3])} (class {rt['lead_basis']['class']}, order {rt['lead_basis']['order']})")
        if r.get("dev_tools"):
            add("Tools for this change: " + "; ".join(
                f"{t['id']} {t['state']}" + (f" (fallback: {t['fallback']})" if not t["ok"] and t.get("fallback") else "")
                for t in r["dev_tools"]))
        add(f"Modules: {', '.join(r['touched']) or 'none'}" + (f"; dependents {', '.join(r['dependents'])}" if r["dependents"] else "")
            + (f"; cross-repo (advisory) {', '.join(x['id'] for x in r['cross_repo_dependents'])}" if r["cross_repo_dependents"] else ""))
        if r.get("repo_level"):
            add(f"Repo-level files (no module; review with the repo owner): {', '.join(map(code, r['repo_level']))}")
        if r["unmapped"]:
            add(f"**Unmapped**: {', '.join(map(code, r['unmapped']))}")
        if r["generated_hits"]:
            add("Generated paths touched (change only via their generator): " + ", ".join(f"{code(g['path'])} ({g['generated_by']})" for g in r["generated_hits"]))
        for c in r["contracts"]:
            add(f"Contract {code(c['id'])} ({'/'.join(sorted({h['role'] for h in c['hits']}))} touched, driver {c['driver']}): "
                + "; ".join(f"{e['repo']}:{e['path']}" for e in c["other_ends"][:6]))
        if r["gates"]:
            add("Gates for this change: " + ", ".join(f"**{g['gate']}**" for g in r["gates"]))
        if r["checks"]:
            add("Validation (run with `scripts/run-checks.py --repo " + r["repo"] + " --paths ...`):")
            for tier in ("fast", "extended", "external"):
                cs = [c for c in r["checks"] if c["tier"] == tier]
                if cs:
                    add(f"- {tier}: " + "; ".join(f"{c['module']}/{c['id']}" + (" MISSING " + ",".join(c["missing_tools"]) if c["missing_tools"] else "") for c in cs))
        for o in r["obligations"]:
            if o.get("changelog") or o.get("docs"):
                add(f"Obligations {o['module']}: CHANGELOG {o.get('changelog') or '-'}" + (f"; docs {', '.join(o['docs'][:3])}" if o.get("docs") else ""))
        issues = [k for k in reg.get("known_issues", []) if r["repo"] in k["scope"].split(",") or k["scope"] == "workspace"]
        if issues:
            add("Known issues here: " + "; ".join(f"**{k['id']}**" + (f" {k['summary']}" if args["full"] else "") for k in issues))
        if r.get("explain"):
            add("Explain:")
            for e in r["explain"]:
                add(f"- {e['skill']}: {e['selected']} - {'; '.join(e['why'][:2])}")
    tc = snap["toolchain"]
    if tc:
        add("")
        add("**Toolchain:** " + ", ".join(f"{t['tool']} " + ((t.get("version") or os.path.basename(t["resolved"])) if t["resolved"] else "**MISSING**")
                                          + (f" (CI pins {t['expected']})" if t.get("expected") and t.get("version") and t["expected"] not in t["version"] else "")
                                          for t in tc))
    return "\n".join(out)
