"""Core and game layers of asset-gen data: load, merge (override / extends) and resolve a generation spec.

Kinds and where they live (the id is the file name without .json; files carry no id field):
  purpose   core templates/assetgen/purposes/<id>.json   game <authoring>/assetgen/purposes/<id>.json
  style     core templates/assetgen/styles/<id>.json     game <authoring>/assetgen/styles/<id>.json
  template  core templates/assetgen/workflows/<id>.json  game <authoring>/assetgen/templates/<id>.json

A game file with a core id and no "extends" replaces the core entry (override). A game file with
"extends": "<id>" is deep-merged onto that entry (objects merge key by key, the game wins; lists and scalars are
replaced). "extends" naming its own id means the core entry of that id; any other id resolves in the game layer
first, then core. Every leaf of the merged data records the file it came from (sources: dotted path -> label).

Style hints versus purpose constraints (data/precedence.json): a field marked "purpose" there (lighting, background,
framing) is a technical constraint; a purpose's constraints.<field> replaces the style's <field>, and resolve records
spec.hints.<field> = {text, from: purpose, source, overrides: {text, source}} so the prompt writer uses one value and
sees the style hint marked overridden. A "style" field (palette) is taste only the style sets. A style field may be
prose (a string) or a structured object (stylelock.py); its hint is the object's `text`.
"""
import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(os.path.dirname(HERE))
CORE_DIR = os.path.join(PLUGIN_ROOT, "templates", "assetgen")
KINDS = {
    "purpose": {"core": "purposes", "game": "purposes", "schema": "rpg-factory.assetgen-purpose/1"},
    "style": {"core": "styles", "game": "styles", "schema": "rpg-factory.assetgen-style/1"},
    "template": {"core": "workflows", "game": "templates", "schema": "rpg-factory.comfy-template/1"},
}


PRECEDENCE = os.path.join(HERE, "data", "precedence.json")


class SpecError(Exception):
    pass


def precedence():
    """{field: "purpose"|"style"} from data/precedence.json."""
    with open(PRECEDENCE, encoding="utf-8") as f:
        return json.load(f)["hints"]


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def content_hash(obj):
    """sha256 of the canonical JSON of merged data (the hash a gen-run records for a purpose/style/template ref)."""
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def game_dir(authoring):
    return os.path.join(os.path.abspath(authoring), "assetgen") if authoring else None


def layer_files(kind, authoring=None):
    """{"core": {id: path}, "game": {id: path}} for one kind."""
    found = {"core": {}, "game": {}}
    dirs = [("core", os.path.join(CORE_DIR, KINDS[kind]["core"]))]
    if authoring:
        dirs.append(("game", os.path.join(game_dir(authoring), KINDS[kind]["game"])))
    for layer, d in dirs:
        if os.path.isdir(d):
            for name in sorted(os.listdir(d)):
                if name.endswith(".json"):
                    found[layer][name[:-5]] = os.path.join(d, name)
    return found


def label(layer, path, authoring):
    root = os.path.abspath(authoring) if layer == "game" else PLUGIN_ROOT
    return layer + ":" + os.path.relpath(path, root).replace(os.sep, "/")


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
    except (OSError, ValueError) as exc:
        raise SpecError("%s: unreadable JSON (%s)" % (path, exc))
    if not isinstance(obj, dict):
        raise SpecError("%s: top level must be an object" % path)
    return obj


def leaves(obj, src, prefix, out):
    if isinstance(obj, dict) and obj:
        for k, v in obj.items():
            leaves(v, src, prefix + "." + k if prefix else k, out)
    else:
        out[prefix] = src


def merge(base, over):
    data = dict(base)
    for k, v in over.items():
        data[k] = merge(data[k], v) if isinstance(v, dict) and isinstance(data.get(k), dict) else v
    return data


def deep_merge(base, over, base_src, over_label):
    """Merge over onto base; returns (data, sources): a leaf the game file sets is labelled with it."""
    data = merge(base, over)
    over_leaves, data_leaves = {}, {}
    leaves(over, over_label, "", over_leaves)
    leaves(data, None, "", data_leaves)
    return data, {p: over_label if p in over_leaves else base_src.get(p, over_label) for p in data_leaves}


def load(kind, ident, authoring=None, _seen=None, _layer=None):
    """Merged entry: {"id", "kind", "layer", "files": [labels], "data", "sources"}; raises SpecError."""
    if kind not in KINDS:
        raise SpecError("unknown kind %r (purpose, style, template)" % kind)
    seen = _seen or []
    if (kind, ident, _layer) in seen:
        raise SpecError("extends cycle: " + " -> ".join(i for _, i, _ in seen + [(kind, ident, _layer)]))
    files = layer_files(kind, authoring)
    layer = _layer or ("game" if ident in files["game"] else "core")
    if ident not in files[layer]:
        raise SpecError("%s %r not found in the %s layer" % (kind, ident, "core or game" if _layer is None else layer))
    path = files[layer][ident]
    raw = read_json(path)
    src = label(layer, path, authoring)
    base_id = raw.get("extends")
    own = {k: v for k, v in raw.items() if k != "extends"}
    if layer == "game" and base_id:
        base_layer = "core" if base_id == ident else None
        base = load(kind, base_id, authoring, seen + [(kind, ident, _layer)], base_layer)
        data, sources = deep_merge(base["data"], own, base["sources"], src)
        return {"id": ident, "kind": kind, "layer": "game-extends", "extends": base_id,
                "files": base["files"] + [src], "data": data, "sources": sources}
    if base_id:
        raise SpecError("%s: extends is only allowed in the game layer" % src)
    sources = {}
    leaves(own, src, "", sources)
    overrides = layer == "game" and ident in files["core"]
    return {"id": ident, "kind": kind, "layer": "game-override" if overrides else layer,
            "files": [src], "data": own, "sources": sources}


def entries(kind=None, authoring=None):
    """Every visible id per kind (game shadows core), merged; errors are reported per entry."""
    out = []
    for k in ([kind] if kind else list(KINDS)):
        files = layer_files(k, authoring)
        for ident in sorted(set(files["core"]) | set(files["game"])):
            try:
                e = load(k, ident, authoring)
                out.append({"kind": k, "id": ident, "layer": e["layer"], "title": e["data"].get("title", ""),
                            "files": e["files"]})
            except SpecError as exc:
                out.append({"kind": k, "id": ident, "layer": "error", "title": "", "files": [], "error": str(exc)})
    return out


def find(ident, kind=None, authoring=None):
    kinds = [kind] if kind else [k for k in KINDS if ident in set().union(*layer_files(k, authoring).values())]
    if not kinds:
        raise SpecError("no purpose, style or template named %r" % ident)
    if len(kinds) > 1:
        raise SpecError("%r is ambiguous (%s); pass --kind" % (ident, ", ".join(kinds)))
    return load(kinds[0], ident, authoring)


def resolve(purpose, style=None, template=None, authoring=None):
    """The resolved generation spec. Param precedence (low -> high): template default < style.params <
    purpose.params (purpose requirements beat style taste); --param on render beats all."""
    p = load("purpose", purpose, authoring)
    style = style or p["data"].get("default_style")
    if not style:
        raise SpecError("purpose %r has no default_style; pass --style" % purpose)
    s = load("style", style, authoring)
    template = template or p["data"].get("default_template")
    if not template:
        raise SpecError("purpose %r has no default_template; pass --template" % purpose)
    t = load("template", template, authoring)
    declared = t["data"].get("params", {})
    params, param_sources = {}, {}
    for name, decl in declared.items():
        if "default" in decl:
            params[name], param_sources[name] = decl["default"], t["sources"].get("params.%s.default" % name, "template")
    for layer, entry in (("style", s), ("purpose", p)):
        for name, value in (entry["data"].get("params") or {}).items():
            if name not in declared:
                raise SpecError("%s %r sets param %r that template %r does not declare" % (layer, entry["id"], name, template))
            params[name], param_sources[name] = value, entry["sources"].get("params." + name, layer)
    sources = {}
    for prefix, entry in (("purpose", p), ("style", s), ("template", t)):
        for path, src in entry["sources"].items():
            sources[prefix + "." + path] = src
    hints = resolve_hints(p, s)

    def ref(e):
        return {"id": e["id"], "layer": e["layer"], "files": e["files"], "sha256": content_hash(e["data"]), "data": e["data"]}
    return {"schema": "rpg-factory.assetgen-spec/1", "authoring": os.path.abspath(authoring) if authoring else None,
            "purpose": ref(p), "style": ref(s), "template": ref(t),
            "params": params, "param_sources": param_sources, "hints": hints, "sources": sources}


def resolve_hints(p, s):
    """spec.hints: the one text per hint field the prompt writer uses (see the module docstring)."""
    constraints = p["data"].get("constraints")
    constraints = constraints if isinstance(constraints, dict) else {}
    hints = {}
    for field, winner in sorted(precedence().items()):
        style_value, purpose_text = s["data"].get(field), constraints.get(field)
        # a structured style field (palette, lighting, ...) is an object whose hint is its text
        style_text = style_value.get("text") if isinstance(style_value, dict) else style_value
        style_src = s["sources"].get(field + ".text" if isinstance(style_value, dict) else field, "style")
        purpose_src = p["sources"].get("constraints." + field, "purpose")
        if winner == "purpose" and isinstance(purpose_text, str) and purpose_text:
            hints[field] = {"text": purpose_text, "from": "purpose", "source": purpose_src}
            if isinstance(style_text, str) and style_text:
                hints[field]["overrides"] = {"text": style_text, "source": style_src}
        elif isinstance(style_text, str) and style_text:
            hints[field] = {"text": style_text, "from": "style", "source": style_src}
    return hints
