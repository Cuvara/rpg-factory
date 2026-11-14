"""assetgen.py style ...: authoring verbs for a game style (hooked up by assetgen.py).

  style init --id ID --extends CORE [--family FAM=STYLE]... --authoring DIR [--title T] [--json]

init writes a draft game style <authoring>/assetgen/styles/<ID>.json (extends the core style CORE, version 1, status
draft, no structured fields) and the skeleton <authoring>/assetgen/project.json (style {ID, 1}, allowed_styles, families,
an empty art_direction). Each --family FAM=STYLE maps a family to a style: STYLE equal to ID only maps; a game style
that already exists must extend ID; a core-only STYLE is refused (a core style cannot extend the project style);
any other STYLE gets a draft stub that extends ID. init never overwrites a file (exit 1, nothing written: every target is
checked before the first write) and never edits core data (templates/assetgen/).
Exit codes: 0 ok, 1 refusal or invalid result, 2 usage.
"""
import json
import os
import sys

import layers
import stylelock

STYLE_SCHEMA = layers.KINDS["style"]["schema"]
INIT_SCHEMA = "rpg-factory.assetgen-style-init/1"
DRAFT_NOTE = ("note: the style is draft: lint does not WARN for a draft style; once status is active lint WARNs until a "
              "usable structured field (palette.colors, tone, canvas, outline.edge_darkness) is set, so add those "
              "(style derive) before activating")


class Refusal(Exception):
    def __init__(self, msg, code=1):
        super().__init__(msg)
        self.code = code


def add_parsers(parser):
    """Registers the nested `style` verbs on the `style` subparser."""
    subs = parser.add_subparsers(dest="style_cmd", required=True)
    c = subs.add_parser("init", allow_abbrev=False, help="write a draft game style and a project.json skeleton")
    c.add_argument("--id", required=True, metavar="ID", help="the new game style id (lowercase id)")
    c.add_argument("--extends", required=True, metavar="CORE", help="the core style it extends")
    c.add_argument("--family", action="append", metavar="FAM=STYLE",
                   help="map a family to a style (repeatable; one style per family)")
    c.add_argument("--authoring", required=True, metavar="DIR", help="the authoring repo to write into")
    c.add_argument("--title", help="style title (default: '<ID> (draft, extends <CORE>)')")
    c.add_argument("--json", action="store_true")


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


def _write_new(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "x", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=1)
        f.write("\n")


def init(a):
    authoring, plan, fams, project = _plan(a)
    written = []
    for path, rel, obj in plan:
        try:
            _write_new(path, obj)
        except FileExistsError:
            raise Refusal("%s already exists (%s): init never overwrites" % (rel, path.replace(os.sep, "/")))
        written.append(rel)
    errors = stylelock.project_errors(project, authoring)
    if errors:
        raise Refusal("assetgen/project.json is not valid:\n" + "\n".join("  " + e for e in errors))
    if a.json:
        print(json.dumps({"schema": INIT_SCHEMA, "style": a.id, "extends": a.extends, "families": fams,
                          "files": written, "project": project}, indent=1, sort_keys=True))
    else:
        print("\n".join(["wrote " + rel for rel in written] + [DRAFT_NOTE]))
    return 0


def run(a):
    """Exit code of one `style` verb; a refusal prints `assetgen: <message>` to stderr."""
    try:
        if a.style_cmd == "init":
            return init(a)
    except Refusal as exc:
        print("assetgen: " + str(exc), file=sys.stderr)
        return exc.code
    except layers.SpecError as exc:
        print("assetgen: " + str(exc), file=sys.stderr)
        return 1
    return 2
