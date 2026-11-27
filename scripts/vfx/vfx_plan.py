#!/usr/bin/env python3
"""Deterministic VFX production plan: the state of the five production steps of one effect, and what is missing.

Usage: vfx_plan.py [--json] [--effect ID] [--root AUTHORING] [--project DIR] [--style FILE] [--spec ID|FILE]
                   [--asset ID|FILE] [--gen-run ID ...] [--captures DIR] [--lint FILE] [<request text...>]

The five steps of an effect (rules and texts: data/plan.json):
  1 style     the project's vfx-style profile is present and approved (status approved or later and, when it carries
              binding_values, an approval record approvals/<id>/*.json for its current revision)
  2 textures  the gen-runs the effect cites (AGEN-<run id> in the sources or upstream of its vfx-spec and vfx-asset,
              plus --gen-run) are approved: run.md status approved and an approval record for its revision; a run in
              another asset-gen style than the profile's assetgen_style is FAIL
  3 recipe    <Name>.vfxrecipe.json (cuvara.vfx-recipe/1, id = the effect id) is in the project and <Name>.vfx is
              built next to it
  4 capture   a stats.json (cuvara.vfx-capture/1) under --captures (default <project>/Captures) whose recipe_sha256
              is the recipe's SHA-256, and the JSON scripts/vfx/vfx_style.py lint printed (rpg-factory.vfx-lint/1:
              --lint, else vfx-lint.json or lint.json next to stats.json) bound to the same recipe (its
              inputs.recipe.sha256) with no FAIL in its rows; a lint result of another recipe is STALE, one that
              names no recipe SHA-256 is IN_PROGRESS (lint again)
  5 record    the effect's vfx-asset record (its asset_path or delivery path names the recipe's stem or the effect id)
              is approved or later and its hash matches the asset file when that file is in the project
Step states: DONE, IN_PROGRESS, TODO, NEEDS_APPROVAL, STALE, FAIL, BLOCKED, NOT_AVAILABLE (an input to grade the
step is missing). The effect id comes from --effect, else from the request text; authoring paths come from the
registry (modules, the assetgen-to-vfx contract) with data/plan.json defaults. --root defaults to the workspace
authoring repo (an explicit RPG_FACTORY_WORKSPACE is authoritative). --project (the Unity project or package that
holds the effect folder) has no default.
Output: Markdown, or with --json the rpg-factory.vfx-plan/1 object {schema, request, status: PLAN|NEEDS_CONTEXT|
NOT_VFX, effect, context, steps, current_step, missing, lead, next}. Never guesses an effect id, root, project or
profile: a required item that is absent or ambiguous is listed in `missing` (status NEEDS_CONTEXT).
Exit 0 = PLAN or NOT_VFX, 3 = NEEDS_CONTEXT, 2 = usage. Writes nothing (no files, no state, no git call).
"""
import hashlib
import json
import os
import re
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "scripts", "lib"))
import workspace as wsl  # noqa: E402

SCHEMA = "rpg-factory.vfx-plan/1"
FRONT = re.compile(r"\A---json[ \t]*\r?\n(.*?)\r?\n---(?:[ \t]*\r?\n|\Z)", re.S)


class Usage(ValueError):
    pass


def rules():
    with open(os.path.join(HERE, "data", "plan.json"), encoding="utf-8") as f:
        return json.load(f)


def registry():
    try:
        with open(os.path.join(PLUGIN_ROOT, "registry.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def any_match(patterns, text):
    return any(re.search(p, text, re.I) for p in patterns)


def posix(p):
    return p.replace(os.sep, "/")


def rel(path, base):
    try:
        r = os.path.relpath(path, base)
    except ValueError:  # another drive
        return posix(path)
    return posix(path) if r.startswith("..") else posix(r)


def read_bytes(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def read_json(path):
    data = read_bytes(path)
    if data is None:
        return None
    try:
        obj = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def read_artifact(path):
    """The front-matter object of a ---json Markdown artifact or a JSON artifact, and the file's bytes."""
    data = read_bytes(path)
    if data is None:
        return None, None
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None, data
    try:
        if path.lower().endswith(".json"):
            obj = json.loads(text)
        else:
            m = FRONT.match(text)
            obj = json.loads(m.group(1)) if m else None
    except ValueError:
        return None, data
    return (obj if isinstance(obj, dict) else None), data


def git_blob(data):
    return hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()


def revs(data):
    """The blob ids an approval of these bytes may name: as they are, and with LF line endings (core.autocrlf)."""
    out = [git_blob(data)]
    lf = data.replace(b"\r\n", b"\n")
    if lf != data:
        out.append(git_blob(lf))
    return out


def kebab(name):
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", name)
    s = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "-", s)
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def walk(top, skip):
    if not top or not os.path.isdir(top):
        return
    for d, dirs, files in os.walk(top):
        dirs[:] = sorted(x for x in dirs if x not in skip and not x.endswith("~"))
        for name in sorted(files):
            yield os.path.join(d, name)


# ---------------------------------------------------------------- context


def authoring_dirs(reg, r):
    """Authoring directories per artifact family: {key: (relative dir, source)} from the registry, else the data."""
    rk, d = r["registry"], r["defaults"]
    mods = {m.get("id"): m for m in reg.get("modules", []) if isinstance(m, dict)}

    def module(mid, default):
        paths = (mods.get(mid) or {}).get("paths") or []
        return (paths[0], "registry " + mid) if paths else (default, "data default")

    out = {"style": module(rk["style_module"], d["style_dir"]), "spec": module(rk["spec_module"], d["spec_dir"]),
           "asset": module(rk["asset_module"], d["asset_dir"])}
    contract = next((c for c in reg.get("contracts", []) if isinstance(c, dict) and c.get("id") == rk["gen_run_contract"]), None)
    src = (contract or {}).get("source") or {}
    out["gen_run"] = (src["path"], "registry contract " + rk["gen_run_contract"]) if src.get("path") else (d["gen_run_dir"], "data default")
    out["approvals"] = (d["approvals_dir"], "data default")
    return out


def workspace_root(reg):
    ws = reg.get("workspace") or {}
    markers = ws.get("root_markers") or []
    if not markers:
        return None
    env = os.environ.get(ws.get("root_env", ""), "")
    if env:  # an explicit workspace is authoritative: no fallback that could pick up a real workspace on the host
        env = wsl.native_abs(env)
        return os.path.abspath(env) if all(os.path.exists(os.path.join(env, m)) for m in markers) else None
    found = wsl.find_workspace(os.getcwd(), reg)
    if found:
        return found
    default = wsl.native_abs(ws.get("root_default") or "")
    return default if default and all(os.path.exists(os.path.join(default, m)) for m in markers) else None


def default_root(reg, r):
    repo = (reg.get("repos") or {}).get(r["registry"]["authoring_repo"]) or {}
    ws = workspace_root(reg)
    if not ws or not repo.get("path"):
        return None, ws
    p = os.path.join(ws, repo["path"])
    return (p if os.path.isdir(p) else None), ws


def effect_from_text(text, r):
    for pat in r["effect_id_patterns"]:
        m = re.search(pat, text)
        if m:
            return m.group("id")
    return None


# ---------------------------------------------------------------- approvals and lifecycle


def approval_state(root, adir, aid, data):
    """('ok', record, gate) | ('stale', record, gate) | ('missing', None, None) for the artifact's current bytes."""
    d = os.path.join(root, adir, aid) if root else None
    if not d or not os.path.isdir(d):
        return "missing", None, None
    want = revs(data)
    stale = None
    for path in walk(d, ()):
        if not path.lower().endswith(".json"):
            continue
        rec = read_json(path)
        if not rec or rec.get("artifact") != aid:
            continue
        if rec.get("rev") in want:
            return "ok", rel(path, root), rec.get("gate")
        stale = stale or (rel(path, root), rec.get("gate"))
    return ("stale", stale[0], stale[1]) if stale else ("missing", None, None)


def lifecycle_state(obj, data, root, adir, r, needs_record, evidence):
    """Step state of an artifact from its status and (when needs_record) its approval record."""
    status = obj.get("status")
    aid = obj.get("id")
    if status in r["blocked_states"]:
        evidence.append(f"{aid} is {status}")
        return "BLOCKED"
    if status in r["open_states"] or status not in r["approved_states"]:
        evidence.append(f"{aid} status {status}: not approved yet")
        return "NEEDS_APPROVAL" if status in ("proposed", "review", "reviewed") else "IN_PROGRESS"
    if not needs_record:
        evidence.append(f"{aid} status {status}")
        return "DONE"
    state, record, gate = approval_state(root, adir, aid, data)
    if state == "ok":
        evidence.append(f"{aid} status {status}, approval record {record} (gate {gate}) names its current revision; "
                        "artifact-trace verifies the signed commit")
        return "DONE"
    if state == "stale":
        evidence.append(f"{aid} status {status}, but approval record {record} names another revision")
        return "STALE"
    evidence.append(f"{aid} status {status}, but no approval record under {adir}{aid}/ for its current revision")
    return "NEEDS_APPROVAL"


def scan_kind(root, rdir, kind, skip):
    out = []
    for path in walk(os.path.join(root, rdir) if root else None, skip):
        if not path.lower().endswith((".md", ".json")):
            continue
        obj, data = read_artifact(path)
        if obj and obj.get("kind") == kind and obj.get("id"):
            out.append((path, obj, data))
    return out


def find_artifact(ref, root, rdir, kind, skip):
    """An artifact named by a path (absolute or relative to the cwd) or by its id under root/rdir."""
    if not ref:
        return None, None
    for cand in (ref, os.path.join(root, ref) if root else None):
        if cand and os.path.isfile(cand):
            obj, data = read_artifact(cand)
            if obj and obj.get("kind") == kind:
                return (cand, obj, data), None
            return None, f"{posix(ref)} is not a {kind} artifact"
    for item in scan_kind(root, rdir, kind, skip):
        if item[1].get("id") == ref:
            return item, None
    return None, f"no {kind} artifact {ref} under {rdir}"


def cited(obj):
    if not obj:
        return []
    ids = [x for x in obj.get("sources") or [] if isinstance(x, str)]
    ids += [x.get("id") for x in obj.get("upstream") or [] if isinstance(x, dict) and isinstance(x.get("id"), str)]
    return ids


# ---------------------------------------------------------------- the plan


def build(request, effect=None, root=None, project=None, style=None, spec=None, asset=None, gen_runs=(),
          captures=None, lint=None):
    r = rules()
    reg = registry()
    words = re.sub(r"https?://\S+", " ", request or "")
    dirs = authoring_dirs(reg, r)
    skip = set(r["skip_dirs"])
    vfx_domain = (reg.get("domains") or {}).get(r["registry"]["domain"]) or {}
    lead_skill = vfx_domain.get("lead") or "vfx"
    plan = {"schema": SCHEMA, "request": request, "status": "PLAN", "effect": None,
            "context": {"root": None, "root_source": None, "project": None, "paths": {k: v[0] for k, v in dirs.items()},
                        "path_sources": {k: v[1] for k, v in dirs.items()}, "style": None, "spec": None, "asset": None,
                        "recipe": None, "built_asset": None, "capture": None, "lint": None, "gen_runs": []},
            "steps": [], "current_step": None, "missing": [],
            "lead": {"skill": lead_skill, "route": ["--domain", r["registry"]["domain"]]}, "next": []}
    if not effect and not any_match(r["vfx_signals"], words):
        plan["status"] = "NOT_VFX"
        plan["lead"] = None
        plan["next"] = ["not a VFX request: use rpg-factory:factory-core directly"]
        return plan
    ctx = plan["context"]
    missing = plan["missing"]

    effect = effect or effect_from_text(words, r)
    if effect and not re.fullmatch(r["effect_id"], effect):
        raise Usage(f"effect id {effect!r} is not a kebab-case recipe id")
    plan["effect"] = effect
    if not effect:
        missing.append({"item": "effect-id", "why": "the plan grades one effect, named by its recipe id",
                        "how": "pass --effect <kebab-case id> (the id of <Name>.vfxrecipe.json)"})

    if root:
        ctx["root_source"] = "arg"
        if not os.path.isdir(root):
            missing.append({"item": "authoring-root", "why": f"{posix(root)} is not a directory",
                            "how": "pass --root <the authoring repo that holds vfx/ and assetgen/>"})
            root = None
    else:
        root, ws = default_root(reg, r)
        ctx["root_source"] = "workspace" if root else None
        if not root:
            missing.append({"item": "authoring-root",
                            "why": "no --root and no authoring repo in the workspace"
                                   + (f" ({posix(ws)})" if ws else " (no workspace found)"),
                            "how": "pass --root <the authoring repo that holds vfx/ and assetgen/>"})
    ctx["root"] = posix(os.path.abspath(root)) if root else None

    if project and not os.path.isdir(project):
        missing.append({"item": "project", "why": f"{posix(project)} is not a directory",
                        "how": "pass --project <the Unity project or com.cuvara.vfx package that holds the effect folder>"})
        project = None
    elif not project:
        missing.append({"item": "project", "why": "the recipe, the built .vfx and the captures live in a Unity project or package",
                        "how": "pass --project <the Unity project or com.cuvara.vfx package that holds the effect folder>"})
    ctx["project"] = posix(os.path.abspath(project)) if project else None
    adir = dirs["approvals"][0]
    steps = {s["id"]: {"n": i, "id": s["id"], "title": s["title"], "state": None, "evidence": [],
                       "lead": (reg.get("domains") or {}).get(s["lead_domain"], {}).get("lead") or s["lead_skill"],
                       "action": s["action"]} for i, s in enumerate(r["steps"], 1)}

    # 1 style profile
    st = steps["style"]
    style_obj = None
    if style:
        item, err = find_artifact(style, root, dirs["style"][0], r["kinds"]["style"], skip)
        if err:
            missing.append({"item": "style-profile", "why": err, "how": "pass --style <the project's vfx-style artifact>"})
            st["state"] = "NOT_AVAILABLE"
            st["evidence"].append(err)
    elif root:
        found = scan_kind(root, dirs["style"][0], r["kinds"]["style"], skip)
        if len(found) > 1:
            names = ", ".join(f"{o['id']} ({rel(p, root)})" for p, o, _ in found)
            missing.append({"item": "style-profile", "why": f"several vfx-style profiles: {names}",
                            "how": "pass --style <the profile of this project and binding>"})
            st["state"] = "NOT_AVAILABLE"
            st["evidence"].append(f"several vfx-style profiles under {dirs['style'][0]}")
            item = None
        else:
            item = found[0] if found else None
    else:
        item = None
        st["state"] = "NOT_AVAILABLE"
        st["evidence"].append("no authoring root")
    if item:
        path, style_obj, data = item
        ctx["style"] = {"id": style_obj["id"], "path": rel(path, root) if root else posix(path),
                        "status": style_obj.get("status"),
                        "assetgen_style": (style_obj.get("spec") or {}).get("assetgen_style")}
        st["state"] = lifecycle_state(style_obj, data, root, adir, r, style_obj.get("binding_values") is True, st["evidence"])
    elif st["state"] is None:
        st["state"] = "TODO"
        st["evidence"].append(f"no vfx-style artifact under {dirs['style'][0]}")

    # 3 recipe and built asset (found first: the other steps are matched by its file stem)
    sr = steps["recipe"]
    recipe = recipe_data = None
    stem = None
    if project and effect:
        found = []
        for path in walk(project, skip):
            if path.endswith(r["recipe_suffix"]):
                obj = read_json(path)
                if obj and obj.get("id") == effect:
                    found.append((path, obj))
        if len(found) > 1:
            names = ", ".join(rel(p, project) for p, _ in found)
            missing.append({"item": "recipe", "why": f"several recipes with id {effect}: {names}",
                            "how": "keep one recipe per effect id, or pass --project <the folder of one of them>"})
            sr["state"] = "NOT_AVAILABLE"
            sr["evidence"].append(f"several recipes with id {effect}")
        elif found:
            path, obj = found[0]
            recipe, recipe_data = path, read_bytes(path)
            stem = os.path.basename(path)[: -len(r["recipe_suffix"])]
            sha = hashlib.sha256(recipe_data).hexdigest()
            built = os.path.join(os.path.dirname(path), stem + r["asset_suffix"])
            ctx["recipe"] = {"path": rel(path, project), "sha256": sha, "schema": obj.get("schema"),
                             "vfx_graph": obj.get("vfx_graph")}
            if obj.get("schema") != r["schemas"]["recipe"]:
                sr["state"] = "FAIL"
                sr["evidence"].append(f"{rel(path, project)} schema {obj.get('schema')!r}, expected {r['schemas']['recipe']}")
            elif os.path.isfile(built):
                ctx["built_asset"] = {"path": rel(built, project), "meta": os.path.isfile(built + ".meta")}
                sr["state"] = "DONE"
                sr["evidence"].append(f"recipe {rel(path, project)} (sha256 {sha[:12]}), built {rel(built, project)}"
                                      + ("" if os.path.isfile(built + ".meta") else " (no .meta: not imported by Unity yet)"))
            else:
                sr["state"] = "IN_PROGRESS"
                sr["evidence"].append(f"recipe {rel(path, project)} present, {stem}{r['asset_suffix']} not built")
        else:
            sr["state"] = "TODO"
            sr["evidence"].append(f"no *{r['recipe_suffix']} with id {effect} under the project")
    else:
        sr["state"] = "NOT_AVAILABLE"
        sr["evidence"].append("no project" if not project else "no effect id")

    names = {n for n in (effect, kebab(stem) if stem else None) if n}

    # 5 vfx-asset record (matched by the asset path's stem)
    sa = steps["record"]
    asset_item = None
    if asset:
        asset_item, err = find_artifact(asset, root, dirs["asset"][0], r["kinds"]["asset"], skip)
        if err:
            missing.append({"item": "vfx-asset", "why": err, "how": "pass --asset <the effect's vfx-asset id or file>"})
            sa["state"] = "NOT_AVAILABLE"
            sa["evidence"].append(err)
    elif root and names:
        found = []
        for item in scan_kind(root, dirs["asset"][0], r["kinds"]["asset"], skip):
            obj = item[1]
            paths = [(obj.get("spec") or {}).get("asset_path"), (obj.get("delivery") or {}).get("path")]
            stems = {kebab(os.path.basename(p).split(".", 1)[0]) for p in paths if isinstance(p, str) and p}
            if stems & names or (stem and stems & {stem.lower()}):
                found.append(item)
        if len(found) > 1:
            ids = ", ".join(o["id"] for _, o, _ in found)
            missing.append({"item": "vfx-asset", "why": f"several vfx-asset records name this effect: {ids}",
                            "how": "pass --asset <the effect's vfx-asset id>"})
            sa["state"] = "NOT_AVAILABLE"
            sa["evidence"].append("several vfx-asset records")
        else:
            asset_item = found[0] if found else None
    asset_obj = asset_item[1] if asset_item else None

    # vfx-spec: --spec, else cited by the record, else the spec whose title names the effect
    spec_obj = None
    if spec:
        item, err = find_artifact(spec, root, dirs["spec"][0], r["kinds"]["spec"], skip)
        if err:
            missing.append({"item": "vfx-spec", "why": err, "how": "pass --spec <the effect's vfx-spec id or file>"})
        spec_obj = item[1] if item else None
        spec_item = item
    elif root:
        specs = scan_kind(root, dirs["spec"][0], r["kinds"]["spec"], skip)
        ids = set(cited(asset_obj))
        found = [i for i in specs if i[1]["id"] in ids] or [
            i for i in specs if names & {kebab(str(i[1].get("title") or "")), kebab(os.path.basename(i[0]).split(".", 1)[0])}]
        if len(found) > 1:
            missing.append({"item": "vfx-spec", "why": "several vfx-specs match this effect: "
                                                       + ", ".join(o["id"] for _, o, _ in found),
                            "how": "pass --spec <the effect's vfx-spec id>"})
        spec_item = found[0] if len(found) == 1 else None
        spec_obj = spec_item[1] if spec_item else None
    else:
        spec_item = None
    if spec_obj:
        ctx["spec"] = {"id": spec_obj["id"], "path": rel(spec_item[0], root) if root else posix(spec_item[0]),
                       "status": spec_obj.get("status")}

    # 2 texture gen-runs
    sg = steps["textures"]
    run_ids = list(dict.fromkeys([g if g.startswith("AGEN-") else "AGEN-" + g for g in gen_runs]
                                 + [x for x in cited(spec_obj) + cited(asset_obj) if x.startswith("AGEN-")]))
    profile_style = (ctx["style"] or {}).get("assetgen_style")
    if not root:
        sg["state"] = "NOT_AVAILABLE"
        sg["evidence"].append("no authoring root")
    elif not run_ids:
        sg["state"] = "TODO"
        sg["evidence"].append("no gen-run cited (AGEN-<run id> in the vfx-spec or vfx-asset sources, or --gen-run)"
                              + ("" if spec_obj else "; no vfx-spec found for this effect"))
    else:
        states = []
        for aid in run_ids:
            path = os.path.join(root, dirs["gen_run"][0], aid[len("AGEN-"):], "run.md")
            obj, data = read_artifact(path)
            entry = {"id": aid, "path": rel(path, root), "status": None, "style": None, "state": None}
            ev = []
            if not obj or obj.get("kind") != r["kinds"]["gen_run"] or obj.get("id") != aid:
                entry["state"] = "TODO"
                ev.append(f"{aid} is cited but {rel(path, root)} is not its gen-run")
            else:
                spec_g = obj.get("spec") or {}
                entry["status"] = obj.get("status")
                entry["style"] = (spec_g.get("style") or {}).get("id")
                entry["state"] = lifecycle_state(obj, data, root, adir, r, True, ev)
                if spec_g.get("handoff_domain") not in (None, r["registry"]["domain"]):
                    ev.append(f"{aid} hands off to {spec_g.get('handoff_domain')}, not {r['registry']['domain']}")
                    entry["state"] = "FAIL"
                if profile_style and entry["style"] and entry["style"] != profile_style:
                    ev.append(f"{aid} style {entry['style']} is not the profile's assetgen_style {profile_style}")
                    entry["state"] = "FAIL"
            ctx["gen_runs"].append(entry)
            sg["evidence"] += ev
            states.append(entry["state"])
        order = ("FAIL", "BLOCKED", "STALE", "TODO", "IN_PROGRESS", "NEEDS_APPROVAL", "DONE")
        sg["state"] = next(s for s in order if s in states)

    # 4 capture and lint
    sc = steps["capture"]
    cap_dir = captures or (os.path.join(project, r["defaults"]["captures_dir"]) if project else None)
    if captures and not os.path.isdir(captures):
        missing.append({"item": "captures", "why": f"{posix(captures)} is not a directory",
                        "how": "pass --captures <the folder capture wrote stats.json under>"})
        cap_dir = None
    if not recipe:
        sc["state"] = "NOT_AVAILABLE" if sr["state"] == "NOT_AVAILABLE" else "TODO"
        sc["evidence"].append("no recipe: nothing to capture yet")
    else:
        sha = ctx["recipe"]["sha256"]
        current, stale = [], []
        for path in walk(cap_dir, skip):
            if os.path.basename(path) != r["capture_file"]:
                continue
            obj = read_json(path)
            if not obj or obj.get("schema") != r["schemas"]["capture"]:
                continue
            eff = obj.get("effect") or ""
            eff_stem = os.path.basename(eff).split(".", 1)[0] if isinstance(eff, str) else ""
            if obj.get("recipe_sha256") == sha:
                current.append((path, obj))
            elif eff_stem and (eff_stem == stem or kebab(eff_stem) in names):
                stale.append((path, obj))
        want = (style_obj.get("spec") or {}).get("capture") if style_obj else None
        want = want if isinstance(want, dict) else None
        cond = lambda o: {k: o.get(k) for k in ("camera", "lighting", "seed")}
        if want:
            current.sort(key=lambda x: cond(x[1]) != {k: want.get(k) for k in ("camera", "lighting", "seed")})
        if not current:
            if stale:
                sc["state"] = "STALE"
                sc["evidence"].append(f"{len(stale)} capture(s) of this effect name another recipe_sha256 "
                                      f"(first: {rel(stale[0][0], cap_dir)}); capture the current recipe again")
            else:
                sc["state"] = "TODO"
                sc["evidence"].append(f"no {r['capture_file']} with recipe_sha256 {sha[:12]} under "
                                      + (posix(cap_dir) if cap_dir else "the captures folder"))
        else:
            path, obj = current[0]
            ctx["capture"] = {"path": rel(path, cap_dir), "conditions": cond(obj),
                              "alive_peak": (obj.get("alive") or {}).get("peak")}
            sc["evidence"].append(f"capture {rel(path, cap_dir)} binds the recipe; conditions {cond(obj)}")
            if want and cond(obj) != {k: want.get(k) for k in ("camera", "lighting", "seed")}:
                sc["evidence"].append(f"its viewing conditions differ from the profile's {want}: lint grades it FAIL")
            lint_path = lint or next((os.path.join(os.path.dirname(path), n) for n in r["lint_files"]
                                      if os.path.isfile(os.path.join(os.path.dirname(path), n))), None)
            res = read_json(lint_path) if lint_path else None
            if lint and res is None:
                missing.append({"item": "lint", "why": f"{posix(lint)} is not a JSON lint result",
                                "how": "pass --lint <the JSON vfx_style.py lint printed>"})
            if not res or res.get("schema") != r["schemas"]["lint"]:
                sc["state"] = "IN_PROGRESS"
                sc["evidence"].append("no lint result (" + r["schemas"]["lint"] + ") next to the capture"
                                      + (f": {posix(lint_path)} has schema {res.get('schema')!r}" if res else ""))
            else:
                rows = res["rows"] if isinstance(res.get("rows"), list) else []
                fails = [x.get("id") for x in rows if isinstance(x, dict) and x.get("state") == "FAIL"]
                bound = lint_recipe_sha(res)
                ctx["lint"] = {"path": posix(lint_path) if lint else rel(lint_path, cap_dir), "rows": len(rows),
                               "fail": len(fails), "recipe_sha256": bound}
                if not bound:
                    sc["state"] = "IN_PROGRESS"
                    sc["evidence"].append("lint result names no recipe SHA-256 (inputs.recipe.sha256): run "
                                          "vfx_style.py lint on the current recipe again")
                elif bound != sha:
                    sc["state"] = "STALE"
                    sc["evidence"].append(f"lint result is bound to recipe sha256 {bound[:12]}, not the current "
                                          f"recipe {sha[:12]}: lint again")
                elif fails:
                    sc["state"] = "FAIL"
                    sc["evidence"].append(f"lint: {len(fails)} FAIL row(s): {', '.join(str(x) for x in fails)}")
                elif not rows:
                    sc["state"] = "IN_PROGRESS"
                    sc["evidence"].append("lint result has no rows")
                else:
                    sc["state"] = "DONE"
                    sc["evidence"].append(f"lint bound to recipe sha256 {sha[:12]}: {len(rows)} row(s), no FAIL; "
                                          "the contact sheet review is HUMAN_REQUIRED")

    # 5 vfx-asset record state
    if sa["state"] is None:
        if not root:
            sa["state"] = "NOT_AVAILABLE"
            sa["evidence"].append("no authoring root")
        elif not asset_obj:
            sa["state"] = "TODO"
            sa["evidence"].append(f"no vfx-asset record under {dirs['asset'][0]} names this effect")
        else:
            path, obj, data = asset_item
            aspec = obj.get("spec") or {}
            ctx["asset"] = {"id": obj["id"], "path": rel(path, root), "status": obj.get("status"),
                            "asset_path": aspec.get("asset_path")}
            sa["state"] = lifecycle_state(obj, data, root, adir, r, obj.get("binding_values") is True, sa["evidence"])
            target = asset_file(project, aspec.get("asset_path"))
            if target:
                body = read_bytes(target)
                hashes = {hashlib.sha1(body).hexdigest(), hashlib.sha256(body).hexdigest(), git_blob(body)}
                if str(aspec.get("hash", "")).lower() not in hashes:
                    sa["evidence"].append(f"hash {str(aspec.get('hash'))[:12]} does not match {rel(target, project)}")
                    if sa["state"] in ("DONE", "NEEDS_APPROVAL"):
                        sa["state"] = "STALE"
                else:
                    sa["evidence"].append(f"hash matches {rel(target, project)}")
            elif aspec.get("asset_path"):
                sa["evidence"].append(f"{aspec.get('asset_path')} is not in the project: hash not verified")

    plan["steps"] = [steps[s["id"]] for s in r["steps"]]
    cur = next((s for s in plan["steps"] if s["state"] != "DONE"), None)
    plan["current_step"] = cur["id"] if cur else None
    if missing:
        plan["status"] = "NEEDS_CONTEXT"
        plan["next"] = ["ask the user for exactly: " + "; ".join(f"{m['item']} ({m['how']})" for m in missing),
                        "stop: do not author, build, capture or route until they answer"]
        return plan
    route = " ".join(plan["lead"]["route"])
    plan["next"] = [f"invoke rpg-factory:factory-core and Route with: factory-context.sh {route}",
                    f"then invoke the lead rpg-factory:{lead_skill}"]
    if cur:
        plan["next"].append(f"step {cur['n']} {cur['id']} ({cur['state']}): {cur['action']}"
                            + (f" (lead rpg-factory:{cur['lead']})" if cur["lead"] != lead_skill else ""))
        if cur["state"] == "NEEDS_APPROVAL":
            plan["next"].append("only a person approves: ask for the approval and never write an approval record")
    else:
        plan["next"].append("all five steps are DONE: run artifact-trace (signed approvals) and hand the effect to "
                            "Engineering through vfx-spec-to-impl")
    plan["next"].append("report only what has evidence (PASS, FAIL, BLOCKED, NOT_AVAILABLE, HUMAN_REQUIRED, SKIPPED, NOT_RUN, STALE)")
    return plan


def lint_recipe_sha(res):
    """The recipe SHA-256 a vfx_style.py lint result is bound to (its inputs.recipe.sha256, the only place lint
    writes it), else None."""
    inputs = res.get("inputs") if isinstance(res.get("inputs"), dict) else {}
    recipe = inputs.get("recipe") if isinstance(inputs.get("recipe"), dict) else {}
    sha = recipe.get("sha256")
    return sha.lower() if isinstance(sha, str) and re.fullmatch(r"[0-9A-Fa-f]{64}", sha) else None


def asset_file(project, asset_path):
    """The file a vfx-asset asset_path names inside the project: <project>/<path>, or for Packages/<name>/<rest> the
    package itself when the project is that package (package.json name)."""
    if not project or not isinstance(asset_path, str) or not asset_path:
        return None
    p = asset_path.replace("\\", "/")
    cands = [os.path.join(project, p)]
    m = re.match(r"^Packages/([^/]+)/(.+)$", p)
    if m:
        pkg = read_json(os.path.join(project, "package.json")) or {}
        if pkg.get("name") == m.group(1):
            cands.append(os.path.join(project, m.group(2)))
    return next((c for c in cands if os.path.isfile(c)), None)


def markdown(plan):
    out = ["## rpg-factory VFX plan", "", f"Request: {plan['request'] or '-'}", "",
           f"**Status: {plan['status']}**" + (f" - effect `{plan['effect']}`" if plan["effect"] else "")]
    if plan["status"] == "NOT_VFX":
        out += ["", "Not a VFX request: use rpg-factory:factory-core directly."]
        return "\n".join(out)
    c = plan["context"]
    out += ["", "### Context", f"- authoring root: {c['root'] or 'none'}", f"- project: {c['project'] or 'none'}",
            f"- style profile: {c['style']['id'] + ' (' + c['style']['path'] + ')' if c['style'] else 'none'}",
            f"- vfx-spec: {c['spec']['id'] if c['spec'] else 'none'}",
            f"- recipe: {c['recipe']['path'] if c['recipe'] else 'none'}",
            f"- vfx-asset: {c['asset']['id'] if c['asset'] else 'none'}"]
    out += ["", "### Steps"]
    for s in plan["steps"]:
        out.append(f"{s['n']}. **{s['title']}** - {s['state']} (lead `rpg-factory:{s['lead']}`)")
        out += [f"   - {e}" for e in s["evidence"]]
    if plan["missing"]:
        out += ["", "### Missing (ask the user, then stop)"]
        out += [f"- **{m['item']}**: {m['why']} - {m['how']}" for m in plan["missing"]]
    if plan["lead"]:
        out += ["", f"Lead: `rpg-factory:{plan['lead']['skill']}` - route `{' '.join(plan['lead']['route'])}`"]
    out += ["", "### Next steps"]
    out += [f"{i}. {n}" for i, n in enumerate(plan["next"], 1)]
    return "\n".join(out)


def parse(argv):
    a = {"json": False, "effect": None, "root": None, "project": None, "style": None, "spec": None, "asset": None,
         "gen_runs": [], "captures": None, "lint": None}
    flags = {"--effect": "effect", "--root": "root", "--project": "project", "--style": "style", "--spec": "spec",
             "--asset": "asset", "--captures": "captures", "--lint": "lint"}
    words, i = [], 0
    while i < len(argv):
        x = argv[i]
        if x == "--json":
            a["json"] = True
        elif x in flags or x == "--gen-run":
            if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                raise Usage(f"{x} needs a value")
            if x == "--gen-run":
                a["gen_runs"].append(argv[i + 1])
            else:
                a[flags[x]] = wsl.native_abs(argv[i + 1]) if flags[x] not in ("effect", "spec", "asset") else argv[i + 1]
            i += 1
        elif x.startswith("--"):
            raise Usage(f"unknown option {x}")
        else:
            words.append(x)
        i += 1
    a["request"] = " ".join(words).strip()
    if not a["request"] and not a["effect"]:
        raise Usage("give the request text or --effect ID")
    return a


def main(argv):
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    try:
        a = parse(argv)
        plan = build(a["request"], a["effect"], a["root"], a["project"], a["style"], a["spec"], a["asset"],
                     a["gen_runs"], a["captures"], a["lint"])
    except Usage as e:
        print(f"vfx_plan: {e}\n{__doc__}", file=sys.stderr)
        return 2
    print(json.dumps(plan, indent=1) if a["json"] else markdown(plan))
    return 3 if plan["status"] == "NEEDS_CONTEXT" else 0


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252: output is UTF-8 everywhere
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
