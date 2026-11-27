#!/usr/bin/env python3
"""VFX style profile: print the resolved profile, or lint one effect against it.

Usage: vfx_style.py show --style <profile>
       vfx_style.py lint --style <profile> --recipe <file> [--inspect <file>] [--stats <file>] [--spec <file>]

<profile> is a vfx-style artifact (docs/schemas/kinds/vfx-style.schema.json): a .md file with a ---json front
matter, a .json artifact (its spec is the profile) or a .json spec body. show prints rpg-factory.vfx-style/1
{schema, source, artifact, profile}: the profile with its defaults filled in (timing.sum_tolerance_seconds 0.01,
textures.linear_textures [], textures.channel_packing {}). lint reads the com.cuvara.vfx recipe
(<Name>.vfxrecipe.json, cuvara.vfx-recipe/1) and optionally the inspect result (cuvara.vfx-inspect/1), the capture
statistics (stats.json, cuvara.vfx-capture/1, or the final capture verb result) and the effect's vfx-spec
artifact, and prints rpg-factory.vfx-lint/1 {schema, effect, style, inputs, element, tier, status, counts, rows}
with one row {id, state: PASS|FAIL|WARN|NOT_AVAILABLE, evidence} per rule (scripts/vfx/vfx_lint_rules.py):
recipe-schema, vfx-graph-version, timing-sum, timing-ratios, hdr-intensity, palette, texture-size,
texture-flipbook-grid, texture-color-space, output-type, blend-mode, shader, budget-capacity, budget-systems,
budget-texture-memory, budget-alive, capture-conditions, recipe-hash, spec-match. A rule is NOT_AVAILABLE when
its optional input is absent. The effect names its element and tier in recipe meta.tags (element:<name>,
tier:primary|secondary|ambient).
Exit 0 = no FAIL, 1 = a FAIL, 3 = the style or recipe (or another named input) missing, unreadable or not of its
format, 2 = usage. Reads only the files it is given; writes nothing; no network; needs no Unity.
"""
import copy
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vfx_lint_rules as rules  # noqa: E402

LINT_SCHEMA = "rpg-factory.vfx-lint/1"
SHOW_SCHEMA = "rpg-factory.vfx-style/1"
INSPECT_SCHEMA = "cuvara.vfx-inspect/1"
CAPTURE_SCHEMA = "cuvara.vfx-capture/1"
FRONT_RE = re.compile(r"\A---json\s*\n(.*?)\n---\s*(\n|\Z)", re.S)
PROFILE_REQUIRED = ("purpose", "assetgen_style", "vfx_graph", "palette", "hdr_intensity", "timing", "textures",
                    "outputs", "budgets", "capture")
OBJECT_FIELDS = {"palette": ("hue_tolerance_degrees", "elements"), "hdr_intensity": rules.TIERS,
                 "timing": rules.PHASES, "textures": ("max_size", "flipbook_grids", "color_space"),
                 "outputs": ("types", "blend_modes", "shaders"), "capture": ("camera", "lighting", "seed")}
BUDGET_FIELDS = ("max_alive_particles", "max_systems", "max_texture_memory_bytes")
COMMANDS = {"show": ("--style",), "lint": ("--style", "--recipe", "--inspect", "--stats", "--spec")}
REQUIRED = {"show": ("--style",), "lint": ("--style", "--recipe")}


class InputError(Exception):
    """A named input is missing, unreadable or not of its format (exit 3)."""


def read_bytes(path, what):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError as e:
        raise InputError("%s %s: cannot read (%s)" % (what, path, e.strerror or e))


def parse_doc(path, data, what):
    """A JSON object from a .json file or the ---json front matter of an artifact."""
    try:
        text = data.decode("utf-8-sig")
        m = FRONT_RE.match(text)
        obj = json.loads(m.group(1) if m else text)
    except (UnicodeDecodeError, ValueError) as e:
        raise InputError("%s %s: not JSON or a ---json artifact (%s)" % (what, path, e))
    if not isinstance(obj, dict):
        raise InputError("%s %s: not a JSON object" % (what, path))
    return obj


def artifact_body(obj, kind, path, what):
    """(spec body, artifact summary or None); an artifact of another kind is an InputError."""
    if isinstance(obj.get("spec"), dict) and "kind" in obj:
        if obj.get("kind") != kind:
            raise InputError("%s %s: artifact kind is %r, expected %s" % (what, path, obj.get("kind"), kind))
        info = {k: obj.get(k) for k in ("id", "kind", "status", "title")}
        if kind == "vfx-style":
            info["binding_values"] = obj.get("binding_values")
        return obj["spec"], info
    return obj, None


def resolve_profile(path):
    obj = parse_doc(path, read_bytes(path, "style"), "style")
    body, info = artifact_body(obj, "vfx-style", path, "style")
    missing = [k for k in PROFILE_REQUIRED if k not in body]
    for key, fields in OBJECT_FIELDS.items():
        if key in body:
            if not isinstance(body[key], dict):
                missing.append("%s (not an object)" % key)
            else:
                missing += ["%s.%s" % (key, f) for f in fields if f not in body[key]]
    if isinstance(body.get("palette"), dict) and isinstance(body["palette"].get("elements"), dict):
        for name, el in body["palette"]["elements"].items():
            if not isinstance(el, dict) or not isinstance(el.get("colors"), dict) or \
                    not all(isinstance(v, str) and re.match(r"^#[0-9A-Fa-f]{6}$", v) for v in el["colors"].values()):
                missing.append("palette.elements.%s.colors (#RRGGBB values)" % name)
    budgets = body.get("budgets")
    if "budgets" in body and (not isinstance(budgets, dict) or not budgets):
        missing.append("budgets (one platform at least)")
    elif isinstance(budgets, dict):
        for platform, b in budgets.items():
            missing += ["budgets.%s.%s" % (platform, f) for f in BUDGET_FIELDS if not isinstance(b, dict) or f not in b]
    if missing:
        raise InputError("style %s: not a vfx-style profile, missing or malformed: %s" % (path, ", ".join(missing)))
    profile = copy.deepcopy(body)
    profile["timing"].setdefault("sum_tolerance_seconds", rules.DEFAULT_SUM_TOLERANCE)
    profile["textures"].setdefault("linear_textures", [])
    profile["textures"].setdefault("channel_packing", {})
    return profile, info


def load_input(path, what, schema=None):
    obj = parse_doc(path, read_bytes(path, what), what)
    if schema is not None and obj.get("schema") != schema:
        raise InputError("%s %s: schema is %r, expected %s" % (what, path, obj.get("schema"), schema))
    return obj


def parse(argv):
    if not argv or argv[0] not in COMMANDS:
        raise ValueError("first argument must be a command: %s" % ", ".join(COMMANDS))
    cmd, opts, i = argv[0], {}, 1
    while i < len(argv):
        x = argv[i]
        if x not in COMMANDS[cmd]:
            raise ValueError("%s: unknown argument %r" % (cmd, x))
        if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
            raise ValueError("%s needs a value" % x)
        if x in opts:
            raise ValueError("%s given twice" % x)
        opts[x] = argv[i + 1]
        i += 2
    absent = [x for x in REQUIRED[cmd] if x not in opts]
    if absent:
        raise ValueError("%s needs %s" % (cmd, ", ".join(absent)))
    return cmd, opts


def lint(opts):
    profile, info = resolve_profile(opts["--style"])
    recipe_bytes = read_bytes(opts["--recipe"], "recipe")
    recipe = parse_doc(opts["--recipe"], recipe_bytes, "recipe")
    inspect = load_input(opts["--inspect"], "inspect", INSPECT_SCHEMA) if "--inspect" in opts else None
    stats = load_input(opts["--stats"], "stats", CAPTURE_SCHEMA) if "--stats" in opts else None
    spec = None
    if "--spec" in opts:
        spec, _ = artifact_body(load_input(opts["--spec"], "spec"), "vfx-spec", opts["--spec"], "spec")
    ctx = {"profile": profile, "recipe": recipe, "recipe_bytes": recipe_bytes, "inspect": inspect, "stats": stats,
           "spec": spec}
    rows = rules.run(ctx)
    counts = {s: sum(1 for r in rows if r["state"] == s) for s in ("PASS", "FAIL", "WARN", "NOT_AVAILABLE")}
    status = "FAIL" if counts["FAIL"] else "WARN" if counts["WARN"] else "PASS"
    return {
        "schema": LINT_SCHEMA,
        "effect": recipe.get("id"),
        "style": {"path": opts["--style"], "artifact": info},
        "inputs": {k: opts.get("--" + k) for k in ("recipe", "inspect", "stats", "spec")},
        "element": rules.tag_value(recipe, "element"),
        "tier": rules.effect_tier(ctx),
        "status": status,
        "counts": counts,
        "rows": rows,
    }


def main(argv):
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    try:
        cmd, opts = parse(argv)
    except ValueError as e:
        print("vfx_style: %s\n%s" % (e, __doc__), file=sys.stderr)
        return 2
    try:
        if cmd == "show":
            profile, info = resolve_profile(opts["--style"])
            print(json.dumps({"schema": SHOW_SCHEMA, "source": opts["--style"], "artifact": info, "profile": profile}, indent=1))
            return 0
        result = lint(opts)
    except InputError as e:
        print("vfx_style: %s" % e, file=sys.stderr)
        return 3
    print(json.dumps(result, indent=1))
    return 1 if result["status"] == "FAIL" else 0


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252: output is UTF-8 everywhere
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
