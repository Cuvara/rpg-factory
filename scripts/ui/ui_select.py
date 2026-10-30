#!/usr/bin/env python3
"""Read-only component selection: map UI needs to the real catalog - reuse > configure > compose > missing.

Usage: ui_select.py (--screen ARCHETYPE | --need NEED...) [--uitoolkit DIR] [--ref REF] [--project DIR] [--json]

Needs and screen archetypes (settings, inventory, popup, hud, quest-panel, shop, confirm) are data in
data/screen-recipes.json. A --need is a recipe id or natural language ("confirmation popup"), resolved by
id, then exact alias, then the longest whole-word alias/keyword match. Each selection: {need, recipe, status:
reuse|configure|compose|missing, choice: [catalog ids], evidence: [catalog sources], notes, owner_if_missing:
unity-package|client-integration}. A required choice is kept only if the catalog (ui_catalog.py at the
resolved ref) has it: a required choice absent at that ref, or a need the recipes do not know, is `missing` -
nothing is invented; absent optional ids are a note only. Without a UIToolkit repo the result status is
NOT_AVAILABLE and every need that relies on the package is listed under `not_available` (no status, no
choice); built-in-only needs still resolve.
Exit 0 = selection made, 1 = catalog NOT_AVAILABLE, 2 = usage. Writes nothing.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ui_catalog  # noqa: E402

SCHEMA = "rpg-factory.ui-select/1"
STATUS_ORDER = ["reuse", "configure", "compose", "missing"]


def recipes():
    return json.load(open(os.path.join(HERE, "data", "screen-recipes.json"), encoding="utf-8"))


def norm(text):
    """Lower case, every run of non-alphanumerics one blank: 'Confirm-Popup!' -> 'confirm popup'."""
    return " ".join(re.findall(r"[a-z0-9]+", (text or "").lower()))


def has_words(text, phrase):
    return re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", text) is not None


def needs_in_text(text, rec=None):
    """Known need ids whose keywords or aliases appear (whole words) in free text, in recipe order."""
    rec = rec or recipes()
    low = norm(text)
    return [n for n, r in rec["needs"].items()
            if any(has_words(low, norm(k)) for k in r["keywords"] + r.get("aliases", []))]


def resolve_need(need, rec):
    """(recipe id | None, how): the id itself, then an exact alias, then the single best whole-word match."""
    if need in rec["needs"]:
        return need, "id"
    n = norm(need)
    for nid, r in rec["needs"].items():
        if n == norm(nid) or n in (norm(a) for a in r.get("aliases", [])):
            return nid, "alias"
    best, score = None, 0
    for nid, r in rec["needs"].items():  # longest matching phrase wins; recipe order breaks ties
        for k in r.get("aliases", []) + r["keywords"]:
            k = norm(k)
            if k and has_words(n, k) and len(k) > score:
                best, score = nid, len(k)
    return (best, "keyword") if best else (None, None)


def select_one(need, cat, rec):
    nid, how = resolve_need(need, rec)
    rule = rec["needs"].get(nid) if nid else None
    ref = (cat.get("uitoolkit") or {}).get("ref")
    if rule is None:
        return {"need": need, "recipe": None, "status": "missing", "choice": [], "evidence": [],
                "notes": "not a known need and not in the catalog: nothing to reuse. Decide whether it is a reusable "
                         "package control (unity-package) or game-specific (client-integration) and stop for that "
                         "decision before creating anything.",
                "owner_if_missing": "client-integration"}
    out = {"need": need, "recipe": nid, "status": rule["status"], "choice": [], "evidence": [], "notes": rule["notes"],
           "owner_if_missing": rule["owner_if_missing"]}
    if how != "id":
        out["notes"] = f"matched recipe '{nid}' by {how}. " + out["notes"]
    if rule["status"] == "missing":
        return out
    absent = []
    for cid in rule["choice"]:
        hits = ui_catalog.find(cat, cid)
        if hits:
            out["choice"].append(hits[0]["id"])
            out["evidence"].append(hits[0]["source"])
        else:
            absent.append(cid)
    if absent:
        if cat["status"] != "PASS" and all(not c.startswith("unity:") for c in absent):
            # the catalog is unreadable: no status at all (select() lists it under not_available)
            return {"need": need, "recipe": nid, "requires": absent, "reason": cat["reason"]}
        out["status"] = "missing"
        out["notes"] = (f"{', '.join(absent)} not in the catalog at {ref or 'any ref'}"
                        + ("; check a newer com.cuvara.uitoolkit tag (pin-bump) before creating anything" if ref else "")
                        + f". Recipe: {rule['notes']}")
        if out["choice"]:  # a need that is not fully available selects nothing; say what does exist
            out["notes"] += " Present at this ref: " + ", ".join(out["choice"]) + "."
            out["choice"], out["evidence"] = [], []
        return out
    gone = []
    for cid in rule.get("optional", []):  # optional ids add value when present, never make a need missing
        hits = ui_catalog.find(cat, cid)
        if hits:
            out["choice"].append(hits[0]["id"])
            out["evidence"].append(hits[0]["source"])
        else:
            gone.append(cid)
    if gone:
        tokens = all(c.startswith(("token:", "uss:")) for c in gone)
        out["notes"] += (f" Optional {', '.join(gone)} not in the catalog at {ref or 'any ref'}"
                         + (": style with game USS until a com.cuvara.uitoolkit tag with the theme tokens is pinned (pin-bump)."
                            if tokens else "; do without it or pin a tag that has it (pin-bump)."))
    return out


def select(needs=(), screen=None, cat=None, uitoolkit=None, ref=None, project=None, text=None):
    rec = recipes()
    if screen and screen not in rec["screens"]:
        raise ValueError(f"unknown screen archetype '{screen}'; known: {', '.join(rec['screens'])}")
    cat = cat or ui_catalog.build(uitoolkit, ref, project)
    order = list(rec["screens"].get(screen, [])) + list(needs) + (needs_in_text(text, rec) if text else [])
    order = list(dict.fromkeys(order))
    results = [select_one(n, cat, rec) for n in order]
    sel = [r for r in results if "status" in r]
    unavailable = [r for r in results if "status" not in r]
    u = cat.get("uitoolkit") or {}
    return {"schema": SCHEMA, "status": cat["status"], "reason": cat["reason"], "screen": screen,
            "uitoolkit": {k: u.get(k) for k in ("repo", "ref", "source", "client_pin", "warnings")} if u else None,
            "summary": {s: sum(1 for x in sel if x["status"] == s) for s in STATUS_ORDER},
            "selections": sel,
            "not_available": unavailable,
            "rule": "reuse > configure > compose (Unity built-ins styled with --cuvara-* tokens) > missing; "
                    "missing means stop for a decision on the owner before creating anything"}


def markdown(res):
    u = res.get("uitoolkit") or {}
    out = ["## UI component selection" + (f" - {res['screen']}" if res.get("screen") else ""), ""]
    if res["status"] != "PASS":
        out.append(f"Catalog **NOT_AVAILABLE**: {res['reason']}.")
    else:
        out.append(f"Catalog: com.cuvara.uitoolkit `{u.get('ref')}` ({u.get('source')}); client pin {u.get('client_pin') or 'none'}.")
        out += [f"- warning: {w}" for w in u.get("warnings") or []]
    out += ["", "Rule: " + res["rule"] + ".", "", "| need | status | choice | evidence | notes |", "|---|---|---|---|---|"]
    for s in res["selections"]:
        owner = f" Owner if created: {s['owner_if_missing']}." if s["status"] == "missing" else ""
        out.append(f"| {s['need']} | **{s['status']}** | {', '.join('`' + c + '`' for c in s['choice']) or '-'} | "
                   f"{'<br>'.join(s['evidence']) or '-'} | {s['notes'].replace('|', '/')}{owner} |")
    for r in res.get("not_available") or []:
        out.append(f"| {r['need']} | **NOT_AVAILABLE** | - | - | needs {', '.join(r['requires'])}; {r['reason']} |")
    if not res["selections"] and not res.get("not_available"):
        out.append("| - | - | - | - | no screen archetype or known need: pass --screen or --need |")
    return "\n".join(out)


def main(argv):
    try:
        a, rest = ui_catalog.parse(argv, extra=(("--screen", "screen"), ("--need", "need")))
        if rest:
            raise ValueError(f"unexpected argument '{rest[0]}'")
        needs = a["need"]
        screen = a.get("screen")
        if not screen and not needs:
            raise ValueError("pass --screen <archetype> or at least one --need <need>")
        res = select(needs, screen, uitoolkit=a["uitoolkit"], ref=a["ref"], project=a["project"])
    except ValueError as e:
        print(f"ui_select: {e}\n{__doc__}", file=sys.stderr)
        return 2
    print(json.dumps(res, indent=1) if a["json"] else markdown(res))
    return 0 if res["status"] == "PASS" else 1


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252: output is UTF-8 everywhere
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
