"""assetgen.py style ...: authoring verbs for a game style (hooked up by assetgen.py).

  style init --id ID --extends CORE [--family FAM=STYLE]... --authoring DIR [--title T] [--json]
  style bump --authoring DIR --id ID [--list-only] [--json]

init writes a draft game style <authoring>/assetgen/styles/<ID>.json (extends the core style CORE, version 1, status
draft, no structured fields) and the skeleton <authoring>/assetgen/project.json (style {ID, 1}, allowed_styles, families,
an empty art_direction). Each --family FAM=STYLE maps a family to a style: STYLE equal to ID only maps; a game style
that already exists must extend ID; a core-only STYLE is refused (a core style cannot extend the project style);
any other STYLE gets a draft stub that extends ID. init never overwrites a file (exit 1, nothing written: every target is
checked before the first write) and never edits core data (templates/assetgen/).

bump prepares version N+1 of an ACTIVE game style <authoring>/assetgen/styles/<ID>.json (version N) and lists what a
person has to re-approve under the new version. It never edits an active version in place and never activates anything:
  - draft: <authoring>/assetgen/styles/<ID>/versions/<N+1>.json, the raw game style object with version N+1 and status
    draft (every other key copied, extends kept). It is not a layer file (layers scans only styles/*.json), so it changes
    no resolve, selection, drift or active hash. A person activates it by replacing assetgen/styles/<ID>.json with it,
    setting status active and updating project.json style.version. Refused (exit 1, nothing written) when the style is
    core-only or missing, has no integer version, is not active (a draft: edit it or `style derive` into it; a
    deprecated one), when the draft file exists, or when the merged draft fails stylelock.style_errors.
  - anchors (every anchor record of the style gets one row): a valid active anchor of version N whose PNG is present and
    matches image_sha256 is 'carried': a NEW anchor <old id without a trailing -v<digits>>-v<N+1> (json + byte copy of
    the PNG, status proposed, approved_by/approved_on null, style = the draft ref) is written next to it; the old anchor
    is never edited and no anchor is ever written active. Other version-N anchors are 'reapprove' (never approved, not
    valid, PNG missing or changed, target id taken), retired anchors and anchors of other versions are 'none'.
  - runs of the style: 'reapprove' for a run of version N (it does not feed N+1: re-run or re-approve under N+1).
  - rejections: version N 'rerecord' (it no longer applies to N+1), version null 'applies', other 'none'.
  - quality: the assetgen artifact-quality check runs (read-only subprocess, no image generation) before and after the
    writes; a new FAIL, or a check that cannot run, removes the carried anchors this call wrote and limits the verb to
    listing (the draft stays), said plainly in the output. --list-only writes nothing and skips the check.
  --json prints rpg-factory.assetgen-style-bump/1 (deterministic, no clock). Test seam: the environment variable
  RPG_FACTORY_ASSETGEN_QUALITY_SCRIPT names a Python script run instead of scripts/checks/artifact-quality.py with the
  same arguments.
Exit codes: 0 ok (also when bump was limited to listing), 1 refusal or invalid result, 2 usage.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

import layers
import stylelock

STYLE_SCHEMA = layers.KINDS["style"]["schema"]
INIT_SCHEMA = "rpg-factory.assetgen-style-init/1"
BUMP_SCHEMA = "rpg-factory.assetgen-style-bump/1"
QUALITY_SCRIPT_ENV = "RPG_FACTORY_ASSETGEN_QUALITY_SCRIPT"
QUALITY_TIMEOUT = 600
VERSION_SUFFIX = re.compile(r"-v\d+\Z")
DRAFT_NOTE = ("note: the style is draft: lint does not WARN for a draft style; once status is active lint WARNs until a "
              "usable structured field (palette.colors, tone, canvas, outline.edge_darkness) is set, so add those "
              "(style derive) before activating")


class Refusal(Exception):
    def __init__(self, msg, code=1):
        super().__init__(msg)
        self.code = code


def add_parsers(parser):
    """Registers the nested `style` verbs on the `style` subparser; returns the subparsers action so that other
    modules (style_derive) can add their verbs to it."""
    subs = parser.add_subparsers(dest="style_cmd", required=True)
    c = subs.add_parser("init", allow_abbrev=False, help="write a draft game style and a project.json skeleton")
    c.add_argument("--id", required=True, metavar="ID", help="the new game style id (lowercase id)")
    c.add_argument("--extends", required=True, metavar="CORE", help="the core style it extends")
    c.add_argument("--family", action="append", metavar="FAM=STYLE",
                   help="map a family to a style (repeatable; one style per family)")
    c.add_argument("--authoring", required=True, metavar="DIR", help="the authoring repo to write into")
    c.add_argument("--title", help="style title (default: '<ID> (draft, extends <CORE>)')")
    c.add_argument("--json", action="store_true")
    c = subs.add_parser("bump", allow_abbrev=False,
                        help="prepare version N+1 of an active game style as a draft and list what needs re-approval")
    c.add_argument("--authoring", required=True, metavar="DIR", help="the authoring repo")
    c.add_argument("--id", required=True, metavar="ID", help="the game style id (assetgen/styles/<ID>.json)")
    c.add_argument("--list-only", action="store_true", help="write nothing: only report the draft and the re-approvals")
    c.add_argument("--json", action="store_true")
    return subs


def _usage(msg):
    return Refusal(msg, 2)


def _parse_families(values, style_id):
    """{family: style id} from the --family values; raises Refusal(2) on a malformed or repeated one."""
    fams = {}
    for raw in values or []:
        fam, sep, ident = raw.partition("=")
        if not sep or not stylelock.ID.match(fam) or not stylelock.ID.match(ident):
            raise _usage("--family %r must be FAM=STYLE, both lowercase ids" % raw)
        if fam in fams:
            raise _usage("--family %s is given twice" % fam)
        fams[fam] = ident
    return fams


def _draft(title, extends):
    return {"schema": STYLE_SCHEMA, "title": title, "extends": extends, "version": 1, "status": "draft"}


def _plan(a):
    """(files [(absolute path, relative path, object)], families, project) after every check; writes nothing."""
    authoring = os.path.abspath(a.authoring)
    style_id = a.id
    if not stylelock.ID.match(style_id):
        raise _usage("--id %r must be a lowercase id (a-z, 0-9 and '-')" % style_id)
    core = sorted(layers.layer_files("style")["core"])
    if a.extends not in core:
        raise _usage("--extends %r is not a core style: one of %s" % (a.extends, ", ".join(core)))
    fams = _parse_families(a.family, style_id)

    game = layers.layer_files("style", authoring)["game"]
    styles_dir = os.path.join(layers.game_dir(authoring), layers.KINDS["style"]["game"])
    plan = [(os.path.join(styles_dir, style_id + ".json"), "assetgen/styles/%s.json" % style_id,
             _draft(a.title or "%s (draft, extends %s)" % (style_id, a.extends), a.extends))]
    stubs = []
    for ident in sorted(set(fams.values()) - {style_id}):
        if ident in game:
            raw = layers.read_json(game[ident])
            if raw.get("extends") != style_id:
                raise Refusal("family style %s exists in assetgen/styles/ but extends %r, not %s: a family style must "
                              "extend the project style" % (ident, raw.get("extends"), style_id))
        elif ident in layers.layer_files("style")["core"]:
            raise Refusal("family style %s is a core style: a core style cannot extend the project style %s (use "
                          "another id, or %s itself)" % (ident, style_id, style_id))
        else:
            stubs.append(ident)
    for ident in stubs:
        plan.append((os.path.join(styles_dir, ident + ".json"), "assetgen/styles/%s.json" % ident,
                     _draft("%s (draft, extends %s)" % (ident, style_id), style_id)))
    project = {"schema": stylelock.PROJECT_SCHEMA, "style": {"id": style_id, "version": 1},
               "allowed_styles": [style_id] + sorted(set(fams.values()) - {style_id}),
               "families": dict(sorted(fams.items())), "art_direction": []}
    plan.append((stylelock.project_path(authoring), "assetgen/project.json", project))
    for path, rel, _ in plan:
        if os.path.lexists(path):
            raise Refusal("%s already exists (%s): init never overwrites" % (rel, path.replace(os.sep, "/")))
    return authoring, plan, fams, project


def _missing_dirs(path):
    """The directories above path that do not exist yet, outermost first."""
    out = []
    d = os.path.dirname(path)
    while d and not os.path.isdir(d):
        out.append(d)
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return out[::-1]


def _write_new(path, obj, created):
    """Writes a new file (never over an existing one); appends every directory and the file this call created to
    created before writing into it, so a failure can be undone."""
    for d in _missing_dirs(path):
        os.mkdir(d)
        created.append(d)
    with open(path, "x", encoding="utf-8", newline="\n") as f:
        created.append(path)
        json.dump(obj, f, indent=1)
        f.write("\n")


def _undo(created):
    """Removes what this call created (files, then now-empty directories, innermost first); best effort."""
    for path in reversed(created):
        try:
            if os.path.isdir(path):
                os.rmdir(path)
            else:
                os.remove(path)
        except OSError:
            pass


def init(a):
    authoring, plan, fams, project = _plan(a)
    created = []
    written = []
    try:
        for path, rel, obj in plan:
            try:
                _write_new(path, obj, created)
            except FileExistsError:
                raise Refusal("%s already exists (%s): init never overwrites" % (rel, path.replace(os.sep, "/")))
            written.append(rel)
        errors = stylelock.project_errors(project, authoring)
        if errors:
            raise Refusal("assetgen/project.json is not valid:\n" + "\n".join("  " + e for e in errors))
    except BaseException:
        _undo(created)
        raise
    if a.json:
        print(json.dumps({"schema": INIT_SCHEMA, "style": a.id, "extends": a.extends, "families": fams,
                          "files": written, "project": project}, indent=1, sort_keys=True))
    else:
        print("\n".join(["wrote " + rel for rel in written] + [DRAFT_NOTE]))
    return 0


# -- bump ------------------------------------------------------------------------------------------------------

def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _merged_style(raw, authoring, style_id):
    """The merged style data of raw (a raw game style object), as layers.load would produce it from a file with this
    content."""
    own = {k: v for k, v in raw.items() if k != "extends"}
    base_id = raw.get("extends")
    if not base_id:
        return own
    base = layers.load("style", base_id, authoring, [("style", style_id, None)], "core" if base_id == style_id else None)
    return layers.merge(base["data"], own)


def _rel(path, authoring):
    return os.path.relpath(path, authoring).replace(os.sep, "/")


def _record_version(data):
    ref = data.get("style")
    return ref.get("version") if isinstance(ref, dict) else None


def _anchor_rows(authoring, style_id, version, new_version, draft_ref):
    """([row], [carry]) for every anchor record of the style; a carry is (old id, new record, source png path, new json
    path, new png path). Writes nothing."""
    rows, carries, planned = [], [], {}
    for rec in stylelock.load_anchors(authoring, style_id):
        data, aid = rec["data"], rec["id"]
        row = {"id": aid, "family": data.get("family"), "status": data.get("status"), "version": _record_version(data),
               "action": "none", "new_id": None, "reason": ""}
        rows.append(row)
        if rec["errors"]:
            row["reason"] = "malformed: " + "; ".join(rec["errors"])
            if row["version"] == version:
                row["action"] = "reapprove"
            continue
        if data["status"] == "retired":
            row["reason"] = "retired"
            continue
        if row["version"] != version:
            row["reason"] = "recorded for style version %s, not %s" % (row["version"], version)
            continue
        valid, why = stylelock.anchor_validity(rec, authoring)
        row["action"] = "reapprove"
        if not valid:
            row["reason"] = "proposed and never approved" if data["status"] == "proposed" else why
            continue
        folder = os.path.dirname(rec["path"])
        png_path = os.path.join(folder, data["image"])
        if not os.path.isfile(png_path):
            row["reason"] = "image %s is missing" % data["image"]
            continue
        if _sha256(png_path) != data["image_sha256"]:
            row["reason"] = "image %s does not match image_sha256" % data["image"]
            continue
        new_id = VERSION_SUFFIX.sub("", aid) + "-v%d" % new_version
        new_json, new_png = os.path.join(folder, new_id + ".json"), os.path.join(folder, new_id + ".png")
        taken = [os.path.basename(p) for p in (new_json, new_png) if os.path.lexists(p)]
        if taken:
            row["reason"] = "%s already exists: a carried anchor never overwrites" % taken[0]
            continue
        if new_id in planned:
            row["reason"] = "the carried id %s is already planned for anchor %s" % (new_id, planned[new_id])
            continue
        new = dict(data, id=new_id, status="proposed", approved_by=None, approved_on=None, style=dict(draft_ref),
                   image=new_id + ".png")
        errs = stylelock.anchor_errors(new, style_id, new_id)
        if errs:
            row["reason"] = "the carried record would not be valid: " + "; ".join(errs)
            continue
        planned[new_id] = aid
        row["action"] = "carried"
        row["new_id"] = new_id
        row["reason"] = "carried as proposed anchor %s for version %d (a person approves it)" % (new_id, new_version)
        carries.append((aid, new, png_path, new_json, new_png))
    return rows, carries


def _run_rows(authoring, style_id, version, new_version):
    rows = []
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
        ref = stylelock._run_style(front) if isinstance(front, dict) else None
        if not ref or ref.get("style_id") != style_id:
            continue
        rv = ref.get("version")
        row = {"id": front.get("id") or name, "path": _rel(path, authoring), "status": front.get("status"),
               "version": rv, "action": "none", "reason": ""}
        if rv == version:
            row["action"] = "reapprove"
            row["reason"] = "a run of version %d does not feed version %d: re-run or re-approve it under %d" \
                % (version, new_version, new_version)
        else:
            row["reason"] = "recorded for style version %s, not %s" % (rv, version)
        rows.append(row)
    return sorted(rows, key=lambda r: r["id"])


def _rejection_rows(authoring, style_id, version, new_version):
    """Rows with the rejection's own reason code in `reason` and the action explanation in `note`."""
    rows = []
    for rec in stylelock.load_rejections(authoring, style_id):
        data = rec["data"]
        row = {"id": rec["id"], "type": data.get("type"), "reason": data.get("reason"),
               "version": _record_version(data), "action": "none", "note": ""}
        rows.append(row)
        if rec["errors"]:
            row["note"] = "malformed: " + "; ".join(rec["errors"])
        elif row["version"] is None:
            row["action"] = "applies"
            row["note"] = "recorded for every version: it applies to version %d" % new_version
        elif row["version"] == version:
            row["action"] = "rerecord"
            row["note"] = "it no longer applies to version %d: record it again for %d if it still holds" \
                % (new_version, new_version)
        else:
            row["note"] = "recorded for style version %s, not %s" % (row["version"], version)
    return sorted(rows, key=lambda r: r["id"])


def _quality_results(authoring):
    """(results, None) of one run of the assetgen artifact-quality check, or (None, why) when it cannot run."""
    script = os.environ.get(QUALITY_SCRIPT_ENV) or os.path.join(layers.PLUGIN_ROOT, "scripts", "checks", "artifact-quality.py")
    cmd = [sys.executable, "-B", script, authoring, "--registry", os.path.join(layers.PLUGIN_ROOT, "registry.json"),
           "--domain", "assetgen", "--json"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=QUALITY_TIMEOUT)
    except subprocess.TimeoutExpired:
        return None, "the artifact-quality check timed out after %d s" % QUALITY_TIMEOUT
    except (OSError, subprocess.SubprocessError) as exc:
        return None, "the artifact-quality check could not start (%s)" % exc
    try:
        results = json.loads(proc.stdout)["results"]
        if not isinstance(results, list) or not all(isinstance(r, dict) for r in results):
            raise ValueError("results is not a list of objects")
    except (ValueError, KeyError, TypeError) as exc:
        return None, "the artifact-quality check printed no usable JSON results (%s)" % exc
    return results, None


def _new_fails(before, after):
    """The FAIL rows of after whose (artifact, check) was not FAIL before, sorted."""
    old = {(r.get("artifact"), r.get("check")) for r in before if r.get("state") == "FAIL"}
    out, seen = [], set()
    for r in after:
        key = (r.get("artifact"), r.get("check"))
        if r.get("state") == "FAIL" and key not in old and key not in seen:
            seen.add(key)
            out.append({"artifact": key[0], "check": key[1], "reasons": list(r.get("reasons") or [])})
    return sorted(out, key=lambda f: (str(f["artifact"]), str(f["check"])))


def _copy_new(src, dst, created):
    """Byte copy of src to a new file dst (never over an existing one); dst joins created before it is written."""
    with open(dst, "xb") as out:
        created.append(dst)
        with open(src, "rb") as f:
            shutil.copyfileobj(f, out)


def _bump_plan(a):
    """(authoring, report, draft path, draft raw object, carries) after every check; writes nothing."""
    authoring = os.path.abspath(a.authoring)
    style_id = a.id
    if not stylelock.ID.match(style_id):
        raise _usage("--id %r must be a lowercase id (a-z, 0-9 and '-')" % style_id)
    path = layers.layer_files("style", authoring)["game"].get(style_id)
    if path is None:
        raise Refusal("style %s has no game file assetgen/styles/%s.json in %s: bump works on a game style "
                      "(style init creates one)" % (style_id, style_id, authoring.replace(os.sep, "/")))
    raw = layers.read_json(path)
    entry = layers.load("style", style_id, authoring)
    version = stylelock.style_version(entry["data"])
    status = stylelock.style_status(entry["data"])
    if version is None:
        raise Refusal("style %s has no integer version: set version in assetgen/styles/%s.json before bumping"
                      % (style_id, style_id))
    if status != "active":
        raise Refusal("style %s has status %s: bump only works on an active style (edit the draft, or style derive "
                      "into it)" % (style_id, status))
    new_version = version + 1
    draft_raw = dict(raw, version=new_version, status="draft")
    merged = _merged_style(draft_raw, authoring, style_id)
    errors = stylelock.style_errors(merged)
    if errors:
        raise Refusal("the draft style is not valid, nothing written:\n" + "\n".join("  " + e for e in errors))
    draft_ref = {"style_id": style_id, "version": new_version, "sha256": layers.content_hash(merged)}
    draft_path = os.path.join(stylelock.style_dir(authoring, style_id), "versions", "%d.json" % new_version)
    if os.path.lexists(draft_path):
        raise Refusal("%s already exists: bump never overwrites a draft version" % _rel(draft_path, authoring))
    anchors, carries = _anchor_rows(authoring, style_id, version, new_version, draft_ref)
    report = {"schema": BUMP_SCHEMA,
              "style": {"style_id": style_id, "version": version, "status": status},
              "draft": {"path": _rel(draft_path, authoring), "style": draft_ref, "written": False},
              "anchors": anchors,
              "runs": _run_rows(authoring, style_id, version, new_version),
              "rejections": _rejection_rows(authoring, style_id, version, new_version),
              "quality": {"state": "SKIPPED", "new_fails": [], "note": ""},
              "list_only": bool(a.list_only), "needs_reapproval": {}}
    return authoring, report, draft_path, draft_raw, carries


def _needs_reapproval(report):
    return {"anchors": [r["id"] for r in report["anchors"] if r["action"] in ("carried", "reapprove")],
            "runs": [r["id"] for r in report["runs"] if r["action"] == "reapprove"],
            "rejections": [r["id"] for r in report["rejections"] if r["action"] == "rerecord"]}


def _limit_to_listing(report, why):
    """Every carried anchor row becomes a plain reapprove row (its files were not written or are removed)."""
    for row in report["anchors"]:
        if row["action"] == "carried":
            row["action"] = "reapprove"
            row["new_id"] = None
            row["reason"] = "listed only: " + why


def _bump_text(report):
    sid = report["style"]["style_id"]
    new = report["draft"]["style"]["version"]
    lines = ["style %s version %s status %s" % (sid, report["style"]["version"], report["style"]["status"])]
    if report["draft"]["written"]:
        lines.append("wrote %s (draft version %d)" % (report["draft"]["path"], new))
    elif report["list_only"]:
        lines.append("draft version %d would be written to %s (--list-only: nothing written)" % (new, report["draft"]["path"]))
    for row in report["anchors"]:
        if row["action"] == "carried" and report["draft"]["written"]:
            lines.append("wrote assetgen/styles/%s/anchors/%s.json and .png (proposed anchor)" % (sid, row["new_id"]))
    for row in report["anchors"]:
        lines.append("anchor %s (%s, version %s): %s: %s" % (row["id"], row["status"], row["version"], row["action"],
                                                              row["reason"]))
    for row in report["runs"]:
        lines.append("run %s (%s, version %s): %s: %s" % (row["id"], row["status"], row["version"], row["action"],
                                                          row["reason"]))
    for row in report["rejections"]:
        lines.append("rejection %s (%s, %s, version %s): %s: %s" % (row["id"], row["type"], row["reason"], row["version"],
                                                                     row["action"], row["note"]))
    q = report["quality"]
    lines.append("quality: %s%s" % (q["state"], " (" + q["note"] + ")" if q["note"] else ""))
    for f in q["new_fails"]:
        lines.append("  new FAIL %s %s: %s" % (f["artifact"], f["check"], (f["reasons"] or ["(no reason)"])[0]))
    if q["state"] in ("REJECTED", "NOT_RUN"):
        lines.append("the verb was limited to listing: no carried anchor was kept; the draft stays (it is not active and "
                     "not a layer file)")
    lines.append("only a person activates the draft (replace assetgen/styles/%s.json with it, set status active, update "
                 "project.json style.version) and the proposed anchors; nothing active was edited" % sid)
    return "\n".join(lines)


def bump(a):
    authoring, report, draft_path, draft_raw, carries = _bump_plan(a)
    if a.list_only:
        report["quality"]["note"] = "--list-only: the artifact-quality check was not run"
    else:
        created = []
        try:
            before, why = _quality_results(authoring)
            _write_new(draft_path, draft_raw, created)
            report["draft"]["written"] = True
            anchor_start = len(created)
            limited = None
            if before is None:
                limited = why + " (before writing)"
                report["quality"].update(state="NOT_RUN", note=limited)
            else:
                for _, record, png_src, new_json, new_png in carries:
                    _copy_new(png_src, new_png, created)
                    _write_new(new_json, record, created)
                after, why = _quality_results(authoring)
                if after is None:
                    limited = why + " (after writing)"
                    report["quality"].update(state="NOT_RUN", note=limited)
                else:
                    fails = _new_fails(before, after)
                    if fails:
                        limited = "the artifact-quality check reports %d new FAIL: %s %s: %s" % (
                            len(fails), fails[0]["artifact"], fails[0]["check"], (fails[0]["reasons"] or ["(no reason)"])[0])
                        report["quality"].update(state="REJECTED", new_fails=fails, note=limited)
                    else:
                        report["quality"].update(state="PASS", note="no new FAIL")
            if limited:
                _undo(created[anchor_start:])
                del created[anchor_start:]
                _limit_to_listing(report, limited)
        except BaseException:
            _undo(created)
            raise
    report["needs_reapproval"] = _needs_reapproval(report)
    if a.json:
        print(json.dumps(report, indent=1, sort_keys=True))
    else:
        print(_bump_text(report))
    return 0


def run(a):
    """Exit code of one `style` verb; a refusal prints `assetgen: <message>` to stderr."""
    try:
        if a.style_cmd == "init":
            return init(a)
        if a.style_cmd == "bump":
            return bump(a)
    except Refusal as exc:
        print("assetgen: " + str(exc), file=sys.stderr)
        return exc.code
    except layers.SpecError as exc:
        print("assetgen: " + str(exc), file=sys.stderr)
        return 1
    return 2
