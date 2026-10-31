#!/usr/bin/env python3
"""Deterministic UI plan: classify a UI request, pick ONLY the UI skills it needs, list what is missing.

Usage: ui_plan.py [--verb ui|ui-figma|ui-components|ui-screen|ui-review] [--json] [--project DIR]
                  [--uitoolkit-ref REF] <request text...>

The verb `ui` classifies the intent from the text; the other verbs force their intent family and the
text refines it. Rules (signals, intent order, intent -> skills, screen archetypes, Figma URL patterns)
are data in data/intents.json. Output: Markdown, or with --json the rpg-factory.ui-plan/1 object
{schema, request, verb, status: PLAN|NEEDS_CONTEXT|NOT_UI, intent, skills, not_loaded, lead, context,
missing, components, next}. Never guesses a Figma file key, node id or project: a required item that is
absent is listed in `missing` (status NEEDS_CONTEXT). An explicit import verb with a Figma URL is figma-import
even when the text also asks to validate. The lead is client-integration for work that consumes
com.cuvara.uitoolkit, unity-package only when the request changes the package; a --project (or path) outside
the workspace client repo keeps client-integration and `next` says the routed paths are advisory there.
Component/control phrasing next to a UI noun counts as a UI signal (not next to ECS, Go or server terms); adding or
bumping a package dependency with no UI work is NOT_UI (factory-core routes pins to pin-bump).
Exit 0 = PLAN or NOT_UI, 3 = NEEDS_CONTEXT, 2 = usage. Writes nothing.
"""
import json
import os
import re
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ui_catalog  # noqa: E402
import ui_select  # noqa: E402

SCHEMA = "rpg-factory.ui-plan/1"
VERBS = ("ui", "ui-figma", "ui-components", "ui-screen", "ui-review")
PATH_RE = re.compile(r"(?<![\w/.:-])((?:[A-Za-z]:[\\/]|/)[^\s\"'<>|]+)")


def rules():
    return json.load(open(os.path.join(HERE, "data", "intents.json"), encoding="utf-8"))


def any_match(patterns, text):
    return any(re.search(p, text, re.I) for p in patterns)


def figma_context(text, r):
    m = re.search(r["figma_url"], text)
    if not m:
        return None
    url = m.group(0).rstrip(".,;:)]}>'\"")
    node = re.search(r["figma_node_id"], url)
    node_id = urllib.parse.unquote(node.group("id")).replace("-", ":") if node else None
    return {"url": url, "file_key": m.group("key"), "node_id": node_id}


def ui_skill_names(reg):
    return [s for s, v in sorted(reg["skills"].items(), key=lambda kv: kv[1].get("order", 0))
            if v.get("kind") == "tech" and v.get("domain") == "ui" and s != "ui-orchestrator"]


def ui_signal(words, r):
    """A UI signal, or component/control phrasing next to a UI noun that is not about ECS, Go or server parts."""
    return any_match(r["ui_signals"], words) or (
        any_match(r["component_signals"], words) and not any_match(r["component_guard"], words))


def dependency_only(words, r):
    """A package dependency change with no UI work left once the package names are removed."""
    if not any_match(r["dependency_signals"], words):
        return False
    rest = words
    for pat in r["dependency_names"]:
        rest = re.sub(pat, " ", rest, flags=re.I)
    return not ui_signal(rest, r)


def classify(verb, words, figma, r):
    family = r["verbs"][verb]
    has_figma = bool(figma) or any_match(r["figma_terms"], words) or verb == "ui-figma"
    for it in r["intents"]:
        if family is not None and it["id"] not in family:
            continue
        if it["figma"] and not has_figma:
            continue
        if it.get("url") and not figma:  # an explicit import verb counts only with a Figma URL
            continue
        if not it["patterns"] or any_match(it["patterns"], words):
            return it["id"], has_figma
    return (family or ["screen"])[-1], has_figma


def build(request, verb="ui", project=None, uitoolkit_ref=None):
    r = rules()
    reg = ui_catalog.registry()
    figma = figma_context(request, r)
    words = re.sub(r["figma_url"], " ", request)
    words = re.sub(r"https?://\S+", " ", words)
    plan = {"schema": SCHEMA, "request": request, "verb": verb, "status": "PLAN", "intent": None, "skills": [],
            "not_loaded": [], "lead": None,
            "context": {"figma": figma, "project": None, "uitoolkit": None, "screen": None},
            "missing": [], "components": None, "next": []}
    if verb == "ui" and not figma and not ui_signal(words, r):
        plan["status"] = "NOT_UI"
        plan["not_loaded"] = ui_skill_names(reg)
        plan["next"] = ["not a UI request: use rpg-factory:factory-core directly"]
        return plan
    if verb == "ui" and not figma and dependency_only(words, r):
        plan["status"] = "NOT_UI"
        plan["not_loaded"] = ui_skill_names(reg)
        plan["next"] = ["not a UI request: use rpg-factory:factory-core directly",
                        "a package dependency change (add, install or bump com.cuvara.* in Packages/manifest.json): "
                        "factory-core routes it to pin-bump (client.packages); ask for UI work separately"]
        return plan
    intent, has_figma = classify(verb, words, figma, r)
    plan["intent"] = intent
    screen = next((s for s in r["screens"] if any_match(s["patterns"], words)), None)
    plan["context"]["screen"] = screen["id"] if screen else None

    skills = list(r["intent_skills"][intent])
    if intent == "design" and any_match(r["components_signals"], words):
        skills.append("ui-component-selection")
    if intent == "review" and has_figma:
        skills.insert(0, "ui-figma-import")
    if intent == "troubleshoot" and has_figma:
        skills = ["ui-figma-import"]
    plan["skills"] = [{"name": s, "why": r["skill_why"][s]} for s in skills]
    plan["not_loaded"] = [s for s in ui_skill_names(reg) if s not in skills]

    # target project: --project, else an absolute path in the text, else the workspace client repo
    proj_src = None
    if project:
        proj_src = "arg"
    else:
        m = PATH_RE.search(words)
        if m:
            project, proj_src = m.group(1).rstrip(".,;:)"), "text"
    cat_repo, ws_client, _ = ui_catalog.locate(None, project if proj_src else None)
    if not project and ws_client:
        project, proj_src = ws_client, "workspace"
    plan["context"]["project"] = project
    client_repo = ui_catalog.locate()[1]
    same = lambda a, b: os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
    outside = bool(project) and proj_src in ("arg", "text") and not (
        client_repo and (same(project, client_repo) or os.path.normcase(os.path.abspath(project)).startswith(
            os.path.normcase(os.path.abspath(client_repo)) + os.sep)))
    if cat_repo:
        try:
            u = ui_catalog.resolve_ref(cat_repo, uitoolkit_ref, project)
            plan["context"]["uitoolkit"] = {"ref": u["ref"], "source": u["source"], "client_pin": u["client_pin"],
                                            "warnings": u["warnings"]}
        except ui_catalog.Unavailable as e:
            plan["context"]["uitoolkit"] = {"ref": uitoolkit_ref, "source": "arg" if uitoolkit_ref else None,
                                            "error": str(e)}

    # missing context: never guess a file key, node id or project
    if intent in ("figma-import", "figma-analyze"):
        if not figma:
            plan["missing"].append({"item": "figma-frame-url", "why": f"{intent} needs the Figma frame to read",
                                    "how": "pass a figma.com/design/<key>/...?node-id=<id> URL (in Figma: Copy link to selection)"})
        elif intent == "figma-import" and not figma["node_id"]:
            plan["missing"].append({"item": "figma-node-id", "why": "the connector imports one frame, named by node-id",
                                    "how": "in Figma select the frame and use Copy link to selection (the URL then has ?node-id=)"})
    if intent == "figma-import":
        if not project:
            plan["missing"].append({"item": "target-project", "why": "no client repo in the workspace and no project given",
                                    "how": "pass --project <Unity project folder> or open the RPG MMO workspace"})
        elif proj_src in ("arg", "text") and not os.path.isdir(project):
            plan["missing"].append({"item": "target-project", "why": f"{project} is not a directory",
                                    "how": "pass --project <existing Unity project folder>"})

    # lead and its route (factory-core routes it; the UI skills are tech skills behind the lead)
    name = screen["name"] if screen else None
    if intent == "design":
        plan["lead"] = {"skill": "ui-ux", "route": ["--domain", "ui"]}
    elif any_match(r["package_signals"], words):
        plan["lead"] = {"skill": "unity-package", "route": ["--repo", "uitoolkit", "--paths", "Runtime/"]}
    else:
        paths = (["Assets/Figma/"] if intent.startswith("figma-") else []) + [f"Assets/Scripts/UI/{name}/" if name else "Assets/Scripts/UI/"]
        plan["lead"] = {"skill": "client-integration", "route": ["--repo", "client", "--paths", *paths]}

    if "ui-component-selection" in skills:
        cat = ui_catalog.build(None, uitoolkit_ref, project if proj_src else None)
        sel_screen = screen["id"] if screen and screen["id"] in ui_select.recipes()["screens"] else None
        plan["components"] = ui_select.select(screen=sel_screen, cat=cat, text=words)

    if plan["missing"]:
        plan["status"] = "NEEDS_CONTEXT"
        plan["next"] = ["ask the user for exactly: " + "; ".join(f"{m['item']} ({m['how']})" for m in plan["missing"]),
                        "stop: do not import, route or guess a Figma file key, node id or project until they answer"]
        return plan
    mode = r["intent_mode"][intent]
    route = " ".join(f'"{x}"' if " " in x else x for x in plan["lead"]["route"])
    plan["next"] = [f"invoke rpg-factory:factory-core (mode {mode}) and Route with: factory-context.sh {route}",
                    f"then invoke the lead rpg-factory:{plan['lead']['skill']}"
                    + (", then, in order: " + ", ".join(f"rpg-factory:{s}" for s in skills) if skills else "")
                    + (" (load no other UI skill: " + ", ".join(plan["not_loaded"]) + ")" if plan["not_loaded"] else ""),
                    "report only what has evidence (PASS, FAIL, BLOCKED, NOT_AVAILABLE, HUMAN_REQUIRED, SKIPPED, NOT_RUN, STALE)"]
    if outside:
        plan["next"].insert(1, f"the target project {project} is outside the registry (not the workspace client repo "
                               f"{client_repo or '- none found'}): the routed paths, checks and gates are advisory there; "
                               "write only inside that project")
    return plan


def markdown(plan):
    out = [f"## rpg-factory UI plan ({plan['verb']})", "", f"Request: {plan['request']}", "",
           f"**Status: {plan['status']}**" + (f" - intent `{plan['intent']}`" if plan["intent"] else "")]
    if plan["status"] == "NOT_UI":
        out += ["", "Not a UI request: use rpg-factory:factory-core directly. No UI skill is loaded."]
        out += [f"- {n}" for n in plan["next"][1:]]
        return "\n".join(out)
    c = plan["context"]
    out += ["", "### Skills to load (in order)"]
    out += [f"{i}. `rpg-factory:{s['name']}` - {s['why']}" for i, s in enumerate(plan["skills"], 1)] or ["- none beyond the lead"]
    out.append("Not loaded: " + (", ".join(f"`{s}`" for s in plan["not_loaded"]) or "-"))
    if plan["lead"]:
        out += ["", f"Lead: `rpg-factory:{plan['lead']['skill']}` - route `{' '.join(plan['lead']['route'])}`"]
    out += ["", "### Context"]
    f = c["figma"]
    out.append(f"- Figma: {f['url']} (file_key `{f['file_key']}`, node_id `{f['node_id']}`)" if f else "- Figma: none")
    out.append(f"- project: {c['project'] or 'none'}")
    u = c["uitoolkit"]
    if u:
        out.append(f"- com.cuvara.uitoolkit: `{u.get('ref')}` ({u.get('source')})" + (f" - {u['error']}" if u.get("error") else ""))
        out += [f"  - warning: {w}" for w in u.get("warnings") or []]
    else:
        out.append("- com.cuvara.uitoolkit: NOT_AVAILABLE (no UIToolkit repository found)")
    out.append(f"- screen archetype: {c['screen'] or 'none'}")
    if plan["missing"]:
        out += ["", "### Missing (ask the user, then stop)"]
        out += [f"- **{m['item']}**: {m['why']} - {m['how']}" for m in plan["missing"]]
    if plan["components"]:
        out += ["", "### Components", ui_select.markdown(plan["components"]).split("\n", 2)[2]]
    out += ["", "### Next steps"]
    out += [f"{i}. {n}" for i, n in enumerate(plan["next"], 1)]
    return "\n".join(out)


def parse(argv):
    a = {"verb": "ui", "json": False, "project": None, "uitoolkit_ref": None}
    words, i = [], 0
    flags = {"--verb": "verb", "--project": "project", "--uitoolkit-ref": "uitoolkit_ref"}
    while i < len(argv):
        x = argv[i]
        if x == "--json":
            a["json"] = True
        elif x in flags:
            if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                raise ValueError(f"{x} needs a value")
            a[flags[x]] = argv[i + 1]
            i += 1
        else:
            words.append(x)
        i += 1
    if a["verb"] not in VERBS:
        raise ValueError(f"unknown verb '{a['verb']}'; verbs: {', '.join(VERBS)}")
    a["request"] = " ".join(words).strip()
    if not a["request"]:
        raise ValueError("the request text is empty")
    return a


def main(argv):
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    try:
        a = parse(argv)
    except ValueError as e:
        print(f"ui_plan: {e}\n{__doc__}", file=sys.stderr)
        return 2
    plan = build(a["request"], a["verb"], a["project"], a["uitoolkit_ref"])
    print(json.dumps(plan, indent=1) if a["json"] else markdown(plan))
    return 3 if plan["status"] == "NEEDS_CONTEXT" else 0


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252: output is UTF-8 everywhere
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
