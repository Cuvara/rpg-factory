"""Style lock of asset-gen: project style config, versioned styles, anchors, rejections, reference selection, drift.

Data (all under the authoring repo, never written here; this module only reads):
  assetgen/project.json                               rpg-factory.assetgen-project/1: the game's default style
                                                      {id, version}, allowed_styles, families (asset family -> game
                                                      style that extends the base), art_direction upstream refs
  assetgen/styles/<style-id>/anchors/<id>.json + .png rpg-factory.assetgen-anchor/1: a human-approved image of a
                                                      style version (status proposed|active|retired)
  assetgen/styles/<style-id>/rejections/<id>.json     rpg-factory.assetgen-rejection/1: a rejected asset or direction
                                                      (data, not an approval; feeds the avoid list and the review)

Style reference (one shape in anchors, rejections, review bindings and spec.style_lock.style):
  {"style_id", "version": int|null, "sha256": layers.content_hash(merged style data)}

Resolution (choose): family = --family, else the purpose's default_family, else none (family_source "flag",
"purpose" or null). Style = --style (must be in allowed_styles or a families value, else refused unless an override
reason is given), else families[family], else project.style.id; without project.json the purpose's default_style
(today's behaviour, project null). project.style.version must equal that style's version. A deprecated style is
refused unless an override reason is given; the reason is recorded as style_lock.override.

Anchor validity (engine view): status active and its source gen-run (assetgen/runs/<run_id>/run.md) has status
approved. Records of older style versions stay valid; selection only uses the run's style version. The quality
plugin additionally checks the signed approval, the image hash and that approved_by is a person.

Selection (select_references) is deterministic: no clock, no recency. Candidates are the valid active anchors of
the run's style id and version, sorted by (family match first, larger dimension overlap with the purpose, strength
canonical < strong < supporting, id) and capped by max_references (purpose and template, the smaller; default 3).
An anchor of another family than the run's is a fallback: reference_warnings names each such pick, and
anchor_family_fallback: false (the purpose's value, else project.json's; default true) forbids it, so only anchors
of the run's family are selected (none when there are none). A run without a family has no fallback to judge.

Drift (drift) lists gen-runs, anchors and rejections whose recorded style ref is behind the current style
(older-version, hash-changed, style-missing) and, with project.json, those whose style id is neither the project
style nor a family style (style-id-mismatch: their anchors never feed a run of the project's styles; a new game style
id has no anchors until runs under it are approved and promoted).
"""
import hashlib
import json
import os
import re

import layers

PROJECT_SCHEMA = "rpg-factory.assetgen-project/1"
ANCHOR_SCHEMA = "rpg-factory.assetgen-anchor/1"
REJECTION_SCHEMA = "rpg-factory.assetgen-rejection/1"
DRIFT_SCHEMA = "rpg-factory.assetgen-drift/1"
STATUSES = ("draft", "active", "deprecated")
ANCHOR_STATUSES = ("proposed", "active", "retired")
DIMENSIONS = ("palette", "lighting", "shape", "texture", "composition", "line")
STRENGTHS = ("canonical", "strong", "supporting")
REJECTION_TYPES = ("asset", "direction")
REASONS = ("style_drift", "palette_off", "too_detailed", "wrong_lighting", "wrong_perspective", "text_or_logo",
           "anatomy", "other")
SEVERITIES = ("warn", "fail")
DEFAULT_MAX_REFERENCES = 3
TEXT_FIELDS = ("palette", "lighting", "outline", "shape_language")
HEX = re.compile(r"\A#[0-9a-fA-F]{6}\Z")
SHA = re.compile(r"\A[0-9a-f]{64}\Z")
DATE = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")
ASPECT = re.compile(r"\A[1-9]\d*:[1-9]\d*\Z")
ID = re.compile(r"\A[a-z0-9][a-z0-9-]*\Z")
# names that mark an agent or model, never a person who may approve (approved_by)
AGENT_NAME = re.compile(r"\A(claude.*|codex.*|gpt.*|same_model:.*)\Z", re.I)


class StyleLockError(layers.SpecError):
    pass


# -- small helpers ---------------------------------------------------------------------------------------------

def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _in(v, lo, hi):
    return _num(v) and lo <= v <= hi


def is_agent_name(name):
    return isinstance(name, str) and bool(AGENT_NAME.match(name.strip()))


def hint_text(value):
    """The hint text of a style field: a non-empty string, or the `text` of an object field; else None."""
    if isinstance(value, dict):
        value = value.get("text")
    return value if isinstance(value, str) and value else None


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f), None
    except (OSError, ValueError) as exc:
        return None, "unreadable JSON (%s)" % exc


def _file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


# -- styles ----------------------------------------------------------------------------------------------------

def style_version(data):
    v = data.get("version")
    return v if _int(v) else None


def style_status(data):
    """draft|active|deprecated; absent means active."""
    return data.get("status") or "active"


def style_ref(entry):
    """{style_id, version, sha256} of a loaded style entry (layers.load)."""
    return {"style_id": entry["id"], "version": style_version(entry["data"]), "sha256": layers.content_hash(entry["data"])}


def style_errors(data):
    """Errors of the style-lock fields of one (merged) style: version, status and the structured fields."""
    errs = []
    if "version" in data and not (_int(data["version"]) and data["version"] >= 1):
        errs.append("version must be an integer >= 1")
    if "status" in data and data["status"] not in STATUSES:
        errs.append("status must be one of %s" % ", ".join(STATUSES))
    for field in TEXT_FIELDS:
        v = data.get(field)
        if v is None or isinstance(v, str):
            continue
        if not isinstance(v, dict):
            errs.append("%s must be a string or an object with text" % field)
            continue
        if not isinstance(v.get("text"), str) or not v["text"]:
            errs.append("%s.text must be a non-empty string" % field)
        if "severity" in v and v["severity"] not in SEVERITIES:
            errs.append("%s.severity must be warn or fail" % field)
    pal = data.get("palette")
    if isinstance(pal, dict):
        colors = pal.get("colors")
        if "colors" in pal and (not isinstance(colors, list) or not colors or not all(
                isinstance(c, dict) and isinstance(c.get("hex"), str) and HEX.match(c["hex"])
                and isinstance(c.get("role", ""), str) for c in colors)):
            errs.append("palette.colors must be a non-empty list of {hex: \"#rrggbb\", role}")
        if "max_distance" in pal and not _in(pal["max_distance"], 0, 441):
            errs.append("palette.max_distance must be a number from 0 to 441")
        if "min_share" in pal and not _in(pal["min_share"], 0, 1):
            errs.append("palette.min_share must be a number from 0 to 1")
    out = data.get("outline")
    if isinstance(out, dict) and "edge_darkness" in out:
        ed = out["edge_darkness"]
        if not isinstance(ed, dict):
            errs.append("outline.edge_darkness must be an object")
        else:
            if "max_luminance" in ed and not _in(ed["max_luminance"], 0, 255):
                errs.append("outline.edge_darkness.max_luminance must be a number from 0 to 255")
            if "min_ratio" in ed and not _in(ed["min_ratio"], 0, 1):
                errs.append("outline.edge_darkness.min_ratio must be a number from 0 to 1")
            if "severity" in ed and ed["severity"] not in SEVERITIES:
                errs.append("outline.edge_darkness.severity must be warn or fail")
    if "forbidden" in data and not (isinstance(data["forbidden"], list) and all(isinstance(x, str) and x for x in data["forbidden"])):
        errs.append("forbidden must be a list of non-empty strings")
    canvas = data.get("canvas")
    if canvas is not None:
        if not isinstance(canvas, dict):
            errs.append("canvas must be an object of family -> {aspect, min_side, tolerance, severity}")
        else:
            for fam, c in sorted(canvas.items()):
                if not isinstance(c, dict):
                    errs.append("canvas.%s must be an object" % fam)
                    continue
                if not isinstance(c.get("aspect"), str) or not ASPECT.match(c["aspect"]):
                    errs.append("canvas.%s.aspect must be W:H" % fam)
                if "min_side" in c and not (_int(c["min_side"]) and c["min_side"] >= 1):
                    errs.append("canvas.%s.min_side must be an integer >= 1" % fam)
                if "tolerance" in c and not _in(c["tolerance"], 0, 1):
                    errs.append("canvas.%s.tolerance must be a number from 0 to 1" % fam)
                if "severity" in c and c["severity"] not in SEVERITIES:
                    errs.append("canvas.%s.severity must be warn or fail" % fam)
                extra = sorted(set(c) - {"aspect", "min_side", "tolerance", "severity"})
                if extra:
                    errs.append("canvas.%s: unknown keys %s (an exact pixel canvas is never set)" % (fam, ", ".join(extra)))
    tone = data.get("tone")
    if tone is not None:
        if not isinstance(tone, dict):
            errs.append("tone must be an object")
        else:
            if "tolerance" in tone and not _in(tone["tolerance"], 0, 1):
                errs.append("tone.tolerance must be a number from 0 to 1")
            if "severity" in tone and tone["severity"] not in SEVERITIES:
                errs.append("tone.severity must be warn or fail")
    return errs


def purpose_errors(data):
    """Errors of the style-lock fields of one (merged) purpose or template: default_family, dimensions, max_references."""
    errs = []
    if data.get("default_family") is not None and not (isinstance(data["default_family"], str) and ID.match(data["default_family"])):
        errs.append("default_family must be a lowercase id (characters, props, ...)")
    if "dimensions" in data:
        d = data["dimensions"]
        if not isinstance(d, list) or not all(isinstance(x, str) for x in d) or set(d) - set(DIMENSIONS) or len(set(d)) != len(d):
            errs.append("dimensions must be distinct values of %s" % ", ".join(DIMENSIONS))
    if "max_references" in data and not (_int(data["max_references"]) and data["max_references"] >= 0):
        errs.append("max_references must be an integer >= 0")
    if "anchor_family_fallback" in data and not isinstance(data["anchor_family_fallback"], bool):
        errs.append("anchor_family_fallback must be true or false")
    qa = data.get("qa")
    if isinstance(qa, dict) and "outlines" in qa and not isinstance(qa["outlines"], bool):
        errs.append("qa.outlines must be true or false")
    return errs


def max_references(purpose_data, template_data=None):
    """The smaller of purpose and template max_references; default 3."""
    caps = [d["max_references"] for d in (purpose_data or {}, template_data or {}) if _int(d.get("max_references"))]
    return min(caps) if caps else DEFAULT_MAX_REFERENCES


# -- project ---------------------------------------------------------------------------------------------------

def project_path(authoring):
    return os.path.join(layers.game_dir(authoring), "project.json") if authoring else None


def project_errors(data, authoring=None):
    """Errors of one project.json (structure; with authoring also the styles it names and the version match)."""
    if not isinstance(data, dict):
        return ["project.json must be an object"]
    errs = []
    if data.get("schema") != PROJECT_SCHEMA:
        errs.append("schema must be %s" % PROJECT_SCHEMA)
    style = data.get("style")
    if not isinstance(style, dict) or not isinstance(style.get("id"), str) or not style.get("id") \
            or not (_int(style.get("version")) and style["version"] >= 1):
        errs.append("style must be {id, version} with an integer version >= 1")
        style = None
    allowed = data.get("allowed_styles", [])
    if not isinstance(allowed, list) or not all(isinstance(x, str) and x for x in allowed):
        errs.append("allowed_styles must be a list of style ids")
        allowed = []
    fams = data.get("families", {})
    if not isinstance(fams, dict) or not all(isinstance(k, str) and ID.match(k) and isinstance(v, str) and v for k, v in fams.items()):
        errs.append("families must map a family id to a style id")
        fams = {}
    if "anchor_family_fallback" in data and not isinstance(data["anchor_family_fallback"], bool):
        errs.append("anchor_family_fallback must be true or false")
    arts = data.get("art_direction", [])
    if not isinstance(arts, list) or not all(isinstance(a, dict) and isinstance(a.get("artifact"), str) and a["artifact"]
                                             and "rev" in a for a in arts):
        errs.append("art_direction must be a list of {artifact, rev}")
    if authoring is None:
        return errs
    if style:
        try:
            entry = layers.load("style", style["id"], authoring)
            if style_version(entry["data"]) != style["version"]:
                errs.append("style %s: project version %s is not the style's version %s"
                            % (style["id"], style["version"], style_version(entry["data"])))
        except layers.SpecError as exc:
            errs.append("style: %s" % exc)
    for ident in allowed:
        try:
            layers.load("style", ident, authoring)
        except layers.SpecError as exc:
            errs.append("allowed_styles: %s" % exc)
    for fam, ident in sorted(fams.items()):
        try:
            entry = layers.load("style", ident, authoring)
        except layers.SpecError as exc:
            errs.append("families.%s: %s" % (fam, exc))
            continue
        if style and ident != style["id"] and entry.get("extends") != style["id"]:
            errs.append("families.%s: style %s must extend the project style %s" % (fam, ident, style["id"]))
    return errs


def load_project(authoring):
    """None without project.json, else {"path": "assetgen/project.json", "sha256", "data"}; raises on a bad file."""
    path = project_path(authoring)
    if not path or not os.path.isfile(path):
        return None
    data, err = _read(path)
    if err:
        raise StyleLockError("assetgen/project.json: " + err)
    errs = project_errors(data)
    if errs:
        raise StyleLockError("assetgen/project.json: " + "; ".join(errs))
    return {"path": "assetgen/project.json", "sha256": _file_sha256(path), "data": data}


def choose(purpose, authoring=None, family=None, style=None, override=None):
    """Family and style for a run. purpose: a loaded purpose entry. Returns {"project": null|{path, sha256},
    "family", "family_source", "style_id", "override"}; raises StyleLockError on a refusal."""
    override = override.strip() if isinstance(override, str) and override.strip() else None
    project = load_project(authoring)
    if family:
        fam, fam_src = family, "flag"
    elif isinstance(purpose["data"].get("default_family"), str) and purpose["data"]["default_family"]:
        fam, fam_src = purpose["data"]["default_family"], "purpose"
    else:
        fam, fam_src = None, None
    used_override = None
    if project is None:
        style_id = style or purpose["data"].get("default_style")
        if not style_id:
            raise StyleLockError("purpose %r has no default_style and there is no assetgen/project.json; pass --style" % purpose["id"])
    else:
        pdata = project["data"]
        fams = pdata.get("families", {})
        if style:
            allowed = set(pdata.get("allowed_styles", [])) | set(fams.values()) | {pdata["style"]["id"]}
            if style not in allowed:
                if not override:
                    raise StyleLockError("style %r is not allowed by assetgen/project.json (allowed: %s); pass --style-override REASON"
                                         % (style, ", ".join(sorted(allowed))))
                used_override = override
            style_id = style
        elif fam and fam in fams:
            style_id = fams[fam]
        else:
            style_id = pdata["style"]["id"]
    entry = layers.load("style", style_id, authoring)
    if project is not None and style_id == project["data"]["style"]["id"] \
            and style_version(entry["data"]) != project["data"]["style"]["version"]:
        raise StyleLockError("assetgen/project.json pins style %s version %s, the style file is version %s"
                             % (style_id, project["data"]["style"]["version"], style_version(entry["data"])))
    if style_status(entry["data"]) == "deprecated":
        if not override:
            raise StyleLockError("style %r is deprecated; pass --style-override REASON" % style_id)
        used_override = override
    return {"project": {"path": project["path"], "sha256": project["sha256"]} if project else None,
            "family": fam, "family_source": fam_src, "style_id": style_id, "override": used_override}


# -- anchors and rejections ------------------------------------------------------------------------------------

def style_dir(authoring, style_id):
    return os.path.join(layers.game_dir(authoring), "styles", style_id)


def ref_errors(ref, key="style"):
    if not isinstance(ref, dict) or not isinstance(ref.get("style_id"), str) or not ref["style_id"]:
        return ["%s must be {style_id, version, sha256}" % key]
    errs = []
    if ref.get("version") is not None and not (_int(ref["version"]) and ref["version"] >= 1):
        errs.append("%s.version must be null or an integer >= 1" % key)
    if not isinstance(ref.get("sha256"), str) or not SHA.match(ref["sha256"]):
        errs.append("%s.sha256 must be a sha256 hex digest" % key)
    return errs


def run_ref_errors(run, key):
    if not isinstance(run, dict) or not isinstance(run.get("run_id"), str) or not run["run_id"] \
            or not isinstance(run.get("output"), str) or not run["output"].startswith("outputs/") \
            or not isinstance(run.get("sha256"), str) or not SHA.match(run["sha256"]):
        return ["%s must be {run_id, output: outputs/<name>, sha256}" % key]
    return []


def anchor_errors(data, style_id=None, anchor_id=None):
    """Structure errors of one anchor (style_id / anchor_id: the directory and file stem it lives in)."""
    if not isinstance(data, dict):
        return ["anchor must be an object"]
    errs = []
    if data.get("schema") != ANCHOR_SCHEMA:
        errs.append("schema must be %s" % ANCHOR_SCHEMA)
    if not isinstance(data.get("id"), str) or not ID.match(data["id"]):
        errs.append("id must be a lowercase id")
    elif anchor_id is not None and data["id"] != anchor_id:
        errs.append("id %s is not the file name %s" % (data["id"], anchor_id))
    if data.get("status") not in ANCHOR_STATUSES:
        errs.append("status must be one of %s" % ", ".join(ANCHOR_STATUSES))
    errs += ref_errors(data.get("style"))
    if style_id is not None and isinstance(data.get("style"), dict) and data["style"].get("style_id") not in (None, style_id):
        errs.append("style.style_id %s is not the style directory %s" % (data["style"].get("style_id"), style_id))
    if not isinstance(data.get("family"), str) or not ID.match(data["family"]):
        errs.append("family must be a lowercase id")
    dims = data.get("dimensions")
    if not isinstance(dims, list) or not dims or not all(isinstance(x, str) for x in dims) or set(dims) - set(DIMENSIONS):
        errs.append("dimensions must be a non-empty list of %s" % ", ".join(DIMENSIONS))
    if data.get("strength") not in STRENGTHS:
        errs.append("strength must be one of %s" % ", ".join(STRENGTHS))
    if not isinstance(data.get("image"), str) or os.path.basename(data["image"]) != data["image"] or not data["image"].endswith(".png"):
        errs.append("image must be a .png file name next to the anchor")
    if not isinstance(data.get("image_sha256"), str) or not SHA.match(data["image_sha256"]):
        errs.append("image_sha256 must be a sha256 hex digest")
    errs += run_ref_errors(data.get("source_run"), "source_run")
    by, on = data.get("approved_by"), data.get("approved_on")
    if data.get("status") == "active":
        if not isinstance(by, str) or not by.strip():
            errs.append("an active anchor needs approved_by (a person)")
        elif is_agent_name(by):
            errs.append("approved_by %r is an agent or model; only a person approves an anchor" % by)
        if not isinstance(on, str) or not DATE.match(on):
            errs.append("an active anchor needs approved_on YYYY-MM-DD")
    else:
        if by is not None and not isinstance(by, str):
            errs.append("approved_by must be null or a name")
        if on is not None and not (isinstance(on, str) and DATE.match(on)):
            errs.append("approved_on must be null or YYYY-MM-DD")
    return errs


def rejection_errors(data, style_id=None, rejection_id=None):
    if not isinstance(data, dict):
        return ["rejection must be an object"]
    errs = []
    if data.get("schema") != REJECTION_SCHEMA:
        errs.append("schema must be %s" % REJECTION_SCHEMA)
    if not isinstance(data.get("id"), str) or not ID.match(data["id"]):
        errs.append("id must be a lowercase id")
    elif rejection_id is not None and data["id"] != rejection_id:
        errs.append("id %s is not the file name %s" % (data["id"], rejection_id))
    if data.get("type") not in REJECTION_TYPES:
        errs.append("type must be asset or direction")
    errs += ref_errors(data.get("style"))
    if style_id is not None and isinstance(data.get("style"), dict) and data["style"].get("style_id") not in (None, style_id):
        errs.append("style.style_id %s is not the style directory %s" % (data["style"].get("style_id"), style_id))
    if data.get("family") is not None and not (isinstance(data["family"], str) and ID.match(data["family"])):
        errs.append("family must be null or a lowercase id")
    if data.get("reason") not in REASONS:
        errs.append("reason must be one of %s" % ", ".join(REASONS))
    text = data.get("text")
    if text is not None and not isinstance(text, str):
        errs.append("text must be a string")
    if (data.get("type") == "direction" or data.get("reason") == "other") and not (isinstance(text, str) and text.strip()):
        errs.append("text is required for a direction rejection and for reason other")
    if data.get("type") == "asset":
        errs += run_ref_errors(data.get("run"), "run")
    return errs


def _records(authoring, style_id, sub, check):
    d = os.path.join(style_dir(authoring, style_id), sub)
    out = []
    if not authoring or not os.path.isdir(d):
        return out
    for name in sorted(os.listdir(d)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(d, name)
        data, err = _read(path)
        errs = [err] if err else check(data, style_id, name[:-5])
        out.append({"id": name[:-5], "path": path, "data": data if isinstance(data, dict) else {}, "errors": errs})
    return out


def load_anchors(authoring, style_id):
    """Every anchor record of a style: [{"id", "path", "data", "errors"}], sorted by id."""
    return _records(authoring, style_id, "anchors", anchor_errors)


def load_rejections(authoring, style_id):
    return _records(authoring, style_id, "rejections", rejection_errors)


def run_status(authoring, run_id):
    """The status in the front matter of assetgen/runs/<run_id>/run.md, or None."""
    if not isinstance(run_id, str) or not ID.match(run_id):
        return None
    path = os.path.join(layers.game_dir(authoring), "runs", run_id, "run.md")
    try:
        with open(path, encoding="utf-8") as f:
            m = re.match(r"\A---json\s*\n(.*?)\n---", f.read(), re.S)
        front = json.loads(m.group(1)) if m else None
    except (OSError, ValueError):
        return None
    return front.get("status") if isinstance(front, dict) else None


def anchor_validity(record, authoring):
    """(valid, reason) in the engine view: well formed, status active, source gen-run approved."""
    if record["errors"]:
        return False, "malformed: " + "; ".join(record["errors"])
    data = record["data"]
    if data["status"] != "active":
        return False, "status %s" % data["status"]
    status = run_status(authoring, data["source_run"]["run_id"])
    if status != "approved":
        return False, "source gen-run %s is %s, not approved" % (data["source_run"]["run_id"], status or "missing")
    return True, "active, source gen-run approved"


def valid_anchors(authoring, style_id):
    return [r for r in load_anchors(authoring, style_id) if anchor_validity(r, authoring)[0]]


def family_fallback(purpose_data, authoring=None):
    """anchor_family_fallback of a run: the purpose's value, else project.json's, else true (other-family anchors
    may be selected, with a warning). A malformed project.json counts as unset here (choose refuses it)."""
    if isinstance((purpose_data or {}).get("anchor_family_fallback"), bool):
        return purpose_data["anchor_family_fallback"]
    try:
        project = load_project(authoring)
    except StyleLockError:
        project = None
    value = project["data"].get("anchor_family_fallback") if project else None
    return value if isinstance(value, bool) else True


def select_references(anchors, style, family, dimensions, cap, fallback=True):
    """Deterministic picks among anchor records (valid ones) for a run of style ref `style` and family. fallback
    False keeps only anchors of the run's family (a run without a family is not filtered)."""
    want = set(dimensions or [])
    rank = {s: i for i, s in enumerate(STRENGTHS)}
    cands = [a["data"] for a in anchors
             if a["data"]["style"]["style_id"] == style["style_id"] and a["data"]["style"].get("version") == style.get("version")
             and (fallback or not family or a["data"]["family"] == family)]

    def key(a):
        return (0 if a["family"] == family else 1, -len(set(a["dimensions"]) & want), rank[a["strength"]], a["id"])
    picks = []
    for a in sorted(cands, key=key)[:max(cap, 0)]:
        overlap = [d for d in DIMENSIONS if d in want and d in a["dimensions"]]
        reason = ["family match" if a["family"] == family else "same style"]
        if overlap:
            reason.append("dimensions: " + ", ".join(overlap))
        reason.append("strength " + a["strength"])
        picks.append({"anchor_id": a["id"], "family": a["family"], "strength": a["strength"], "dimensions": a["dimensions"],
                      "image": "references/anchor-%s.png" % a["id"], "sha256": a["image_sha256"], "reason": reason})
    return picks


def reference_warnings(picks, family, fallback=True, skipped=0):
    """Warnings of a selection: each pick of another family than the run's, and the anchors a false
    anchor_family_fallback left out."""
    out = []
    if family:
        out += ["reference %s is a %s anchor, the run's family is %s (cross-family fallback; set anchor_family_fallback: "
                "false in the purpose or project.json to forbid it)" % (p["anchor_id"], p["family"], family)
                for p in picks if p["family"] != family]
    if not fallback and skipped:
        out.append("anchor_family_fallback is false: %d anchor(s) of other families than %s were not selected"
                   % (skipped, family))
    return out


def select_with_warnings(anchors, style, family, dimensions, cap, fallback=True):
    """(picks, warnings): select_references plus reference_warnings."""
    picks = select_references(anchors, style, family, dimensions, cap, fallback)
    skipped = 0
    if not fallback and family:
        skipped = len(select_references(anchors, style, family, dimensions, len(anchors), True)) \
            - len(select_references(anchors, style, family, dimensions, len(anchors), False))
    return picks, reference_warnings(picks, family, fallback, skipped)


def relevant_rejections(rejections, style, family):
    """Rejection records relevant to a run: same style_id, family null or equal, style version null or equal."""
    out = []
    for r in rejections:
        if r["errors"]:
            continue
        d = r["data"]
        if d["style"]["style_id"] != style["style_id"]:
            continue
        if d.get("family") is not None and d["family"] != family:
            continue
        if d["style"].get("version") is not None and d["style"]["version"] != style.get("version"):
            continue
        item = {"id": d["id"], "type": d["type"], "reason": d["reason"]}
        if d.get("text"):
            item["text"] = d["text"]
        if d.get("run"):
            item["run"] = d["run"]
        out.append(item)
    return sorted(out, key=lambda x: x["id"])


def anchor_files(authoring):
    """[(style_id, kind "anchor"|"rejection", path)] of every anchor and rejection JSON in the game layer."""
    out = []
    root = os.path.join(layers.game_dir(authoring), "styles") if authoring else None
    if not root or not os.path.isdir(root):
        return out
    for sid in sorted(os.listdir(root)):
        for sub, kind in (("anchors", "anchor"), ("rejections", "rejection")):
            d = os.path.join(root, sid, sub)
            if os.path.isdir(d):
                out += [(sid, kind, os.path.join(d, n)) for n in sorted(os.listdir(d)) if n.endswith(".json")]
    return out


def classify(path, authoring):
    """("project"|"anchor"|"rejection", style_id, id) for a style-lock file of the authoring repo, else (None,)*3."""
    if not authoring:
        return None, None, None
    full = os.path.normcase(os.path.abspath(path))
    if full == os.path.normcase(os.path.abspath(project_path(authoring))):
        return "project", None, None
    parent = os.path.dirname(full)
    sub = os.path.basename(parent)
    styles = os.path.normcase(os.path.abspath(os.path.join(layers.game_dir(authoring), "styles")))
    if sub in ("anchors", "rejections") and os.path.dirname(os.path.dirname(parent)) == styles and full.endswith(".json"):
        return ("anchor" if sub == "anchors" else "rejection"), os.path.basename(os.path.dirname(parent)), os.path.basename(full)[:-5]
    return None, None, None


# -- drift -----------------------------------------------------------------------------------------------------

def _state(recorded, current):
    if current is None:
        return "style-missing"
    rv, cv = recorded.get("version"), current["version"]
    if _int(rv) and _int(cv) and rv < cv:
        return "older-version"
    if recorded.get("sha256") != current["sha256"]:
        return "hash-changed"
    return None


def _run_style(front):
    spec = front.get("spec") if isinstance(front.get("spec"), dict) else {}
    lock = spec.get("style_lock") if isinstance(spec.get("style_lock"), dict) else None
    if lock and isinstance(lock.get("style"), dict):
        return lock["style"]
    st = spec.get("style") if isinstance(spec.get("style"), dict) else None
    if st and isinstance(st.get("id"), str):  # a run from before the style lock: id and content hash only
        return {"style_id": st["id"], "version": None, "sha256": st.get("sha256")}
    return None


def project_styles(authoring):
    """(project style id, the style ids a run of the project may lock: the project style and the family styles),
    or (None, None) without a readable project.json."""
    try:
        project = load_project(authoring)
    except StyleLockError:
        project = None
    if not project:
        return None, None
    pdata = project["data"]
    return pdata["style"]["id"], {pdata["style"]["id"]} | set((pdata.get("families") or {}).values())


def drift(authoring):
    """Gen-runs, anchors and rejections whose recorded style ref is behind the current style, or whose style id is
    not one of project.json's styles (read-only)."""
    cache = {}
    project_style, locked = project_styles(authoring)

    def current(sid):
        if sid not in cache:
            try:
                cache[sid] = style_ref(layers.load("style", sid, authoring))
            except layers.SpecError:
                cache[sid] = None
        return cache[sid]
    items = []
    runs = os.path.join(layers.game_dir(authoring), "runs")
    for name in sorted(os.listdir(runs)) if os.path.isdir(runs) else []:
        path = os.path.join(runs, name, "run.md")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                m = re.match(r"\A---json\s*\n(.*?)\n---", f.read(), re.S)
            front = json.loads(m.group(1)) if m else None
        except (OSError, ValueError):
            front = None
        rec = _run_style(front) if isinstance(front, dict) else None
        if rec and isinstance(rec.get("style_id"), str):
            items.append(("gen-run", front.get("id") or name, path, rec))
    for sid, kind, path in anchor_files(authoring):
        data, _ = _read(path)
        rec = data.get("style") if isinstance(data, dict) else None
        if isinstance(rec, dict) and isinstance(rec.get("style_id"), str):
            items.append((kind, data.get("id") or os.path.basename(path)[:-5], path, rec))
    out = []
    for kind, ident, path, rec in items:
        cur = current(rec["style_id"])
        state = _state(rec, cur)
        extra = {}
        if locked is not None and rec["style_id"] not in locked and state != "style-missing":
            # another style id than the project's: its anchors never feed a project run (its version state kept apart)
            extra = {"project_style": project_style, "version_state": state}
            state = "style-id-mismatch"
        if state:
            out.append(dict({"kind": kind, "id": ident, "path": os.path.relpath(path, os.path.abspath(authoring)).replace(os.sep, "/"),
                             "state": state, "style": {"style_id": rec["style_id"], "version": rec.get("version"), "sha256": rec.get("sha256")},
                             "current": cur}, **extra))
    return {"schema": DRIFT_SCHEMA, "items": out}
