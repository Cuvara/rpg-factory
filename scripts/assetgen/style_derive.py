"""assetgen.py style derive: propose the structured fields of a game style from its anchors (hooked up by assetgen.py).

  style derive --authoring DIR --style ID [--family FAM] [--apply] [--json]

The anchors are the valid active anchors of the style (stylelock.valid_anchors) recorded for the style's current
version, optionally only those of --family. An anchor whose PNG is missing or no longer matches its image_sha256 is
skipped and reported. The proposal is deterministic (no clock, no randomness; inputs sorted by anchor id, fixed
rounding), so the same anchors always print byte-identical output:
  palette  the most common colours of the sampled opaque pixels (each channel quantized to 16 levels), kept greedily
           when more than the default palette.max_distance away from every kept colour, at most 8; text is the style's
           existing palette prose, else a one-line "Derived from ..." note
  tone     tolerance 0.05 with two or more anchors, 0.1 with one
  canvas   per family of the used anchors: the most common aspect W:H (reduced), tolerance = the widest relative
           deviation of the family's anchors, rounded up to 2 decimals, at least 0.02 (min_side is never proposed)
Without --apply nothing is written. --apply merges the proposal into the raw game style file
<authoring>/assetgen/styles/<ID>.json, only when its status is exactly "draft" (an active style, or a style without
status, is refused, as is a style without a usable anchor), validates the merged style (stylelock.style_errors) and
writes it atomically; keys the proposal does not set (palette.text, tone.severity, canvas min_side/severity, other
families) stay. Core data (templates/assetgen/) is never written.
Exit codes: 0 ok, 1 refusal or invalid result, 2 usage.
"""
import hashlib
import json
import math
import os
import sys
import tempfile
from fractions import Fraction

import consistency
import layers
import png
import style_cmd
import stylelock

DERIVE_SCHEMA = "rpg-factory.assetgen-style-derive/1"
MAX_COLORS = 8
QUANT_SHIFT = 4  # 16 levels per channel
MAX_DISTANCE = consistency.palette_config({"palette": {"colors": [{"hex": "#000000"}]}})[1][2]  # the default (48)
TONE_TOLERANCE_MANY, TONE_TOLERANCE_ONE = 0.05, 0.1
MIN_CANVAS_TOLERANCE = 0.02
Refusal = style_cmd.Refusal


def add_parser(subs):
    """Registers `derive` on the nested `style` subparsers (assetgen.py passes the style parser's subparsers action)."""
    c = subs.add_parser("derive", allow_abbrev=False,
                        help="propose palette, tone and canvas of a game style from its anchors (--apply: merge into a draft)")
    c.add_argument("--authoring", required=True, metavar="DIR", help="the authoring repo")
    c.add_argument("--style", required=True, metavar="ID", help="the game style id (assetgen/styles/<ID>.json)")
    c.add_argument("--family", metavar="FAM", help="use only the anchors of this family")
    c.add_argument("--apply", action="store_true", help="merge the proposal into the style file (draft styles only)")
    c.add_argument("--json", action="store_true")


# -- anchors ---------------------------------------------------------------------------------------------------

def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_anchors(authoring, style_id, version, family):
    """([(anchor data, png.Image)] sorted by id, [{id, reason}] skipped sorted by id)."""
    used, skipped = [], []
    for rec in stylelock.valid_anchors(authoring, style_id):  # sorted by id
        data = rec["data"]
        if family and data["family"] != family:
            continue
        if data["style"].get("version") != version:
            skipped.append({"id": data["id"], "reason": "recorded for style version %s, the style is version %s"
                            % (data["style"].get("version"), version)})
            continue
        path = os.path.join(os.path.dirname(rec["path"]), data["image"])
        if not os.path.isfile(path):
            skipped.append({"id": data["id"], "reason": "image %s is missing" % data["image"]})
            continue
        if _sha256(path) != data["image_sha256"]:
            skipped.append({"id": data["id"], "reason": "image %s does not match image_sha256" % data["image"]})
            continue
        try:
            img = png.decode(path)
        except (png.Invalid, png.Unsupported, OSError) as exc:
            skipped.append({"id": data["id"], "reason": "image %s is not readable (%s)" % (data["image"], exc)})
            continue
        used.append((data, img))
    return used, skipped


# -- derivation ------------------------------------------------------------------------------------------------

def _palette_colors(images):
    """[(r, g, b)] of at most MAX_COLORS colours over the sampled opaque pixels of every image; [] when none is opaque."""
    buckets = {}
    for img in images:
        for px in consistency.opaque_samples(img):
            key = (px[0] >> QUANT_SHIFT, px[1] >> QUANT_SHIFT, px[2] >> QUANT_SHIFT)
            b = buckets.setdefault(key, [0, 0, 0, 0])
            b[0] += 1
            b[1] += px[0]
            b[2] += px[1]
            b[3] += px[2]
    limit = MAX_DISTANCE * MAX_DISTANCE
    kept = []
    for key in sorted(buckets, key=lambda k: (-buckets[k][0], k)):
        n, r, g, b = buckets[key]
        rgb = (r // n, g // n, b // n)
        if all(sum((x - y) ** 2 for x, y in zip(rgb, other)) > limit for other in kept):
            kept.append(rgb)
            if len(kept) == MAX_COLORS:
                break
    return kept


def _aspect(img):
    g = math.gcd(img.width, img.height)
    return img.width // g, img.height // g


def _canvas(used):
    """{family: {aspect "W:H", tolerance}} of the used anchors, families sorted."""
    by_family = {}
    for data, img in used:
        by_family.setdefault(data["family"], []).append(_aspect(img))
    out = {}
    for fam in sorted(by_family):
        aspects = by_family[fam]
        # most common reduced aspect; a tie goes to the smaller W/H value, then the smaller string
        best = min(set(aspects), key=lambda a: (-aspects.count(a), Fraction(a[0], a[1]), "%d:%d" % a))
        want = Fraction(best[0], best[1])
        dev = max(abs(Fraction(w, h) - want) / want for w, h in aspects)
        tol = max(MIN_CANVAS_TOLERANCE, min(1.0, math.ceil(dev * 100) / 100))
        out[fam] = {"aspect": "%d:%d" % best, "tolerance": tol}
    return out


def derive(used, merged):
    """The proposal {palette: {text, colors}, tone: {tolerance}, canvas: {family: {aspect, tolerance}}}, or None when
    no used image has an opaque sampled pixel."""
    colors = _palette_colors([img for _, img in used])
    if not colors:
        return None
    hexes = ["#%02x%02x%02x" % c for c in colors]
    text = stylelock.hint_text(merged.get("palette")) or "Derived from %d anchor(s): %s" % (len(used), ", ".join(hexes))
    return {"palette": {"text": text, "colors": [{"hex": h, "role": "derived-%d" % (i + 1)} for i, h in enumerate(hexes)]},
            "tone": {"tolerance": TONE_TOLERANCE_MANY if len(used) >= 2 else TONE_TOLERANCE_ONE},
            "canvas": _canvas(used)}


# -- apply -----------------------------------------------------------------------------------------------------

def _merged_raw(raw, authoring, style_id, proposal):
    """The raw game style object with the proposal merged in; raises Refusal on a field of the wrong shape."""
    out = dict(raw)
    pal = raw.get("palette")
    if pal is None or isinstance(pal, str):
        pal = {"text": pal} if pal else {}
    elif not isinstance(pal, dict):
        raise Refusal("palette is not a string or an object: fix it before deriving")
    pal = dict(pal)
    if not (isinstance(pal.get("text"), str) and pal["text"]):
        pal["text"] = proposal["palette"]["text"]  # an inherited prose is the proposal's text already
    pal["colors"] = proposal["palette"]["colors"]
    out["palette"] = pal
    tone = raw.get("tone")
    if tone is not None and not isinstance(tone, dict):
        raise Refusal("tone is not an object: fix it before deriving")
    out["tone"] = dict(tone or {}, tolerance=proposal["tone"]["tolerance"])
    canvas = raw.get("canvas")
    if canvas is not None and not isinstance(canvas, dict):
        raise Refusal("canvas is not an object: fix it before deriving")
    canvas = dict(canvas or {})
    for fam, entry in proposal["canvas"].items():
        if fam in canvas and not isinstance(canvas[fam], dict):
            raise Refusal("canvas.%s is not an object: fix it before deriving" % fam)
        canvas[fam] = dict(canvas.get(fam) or {}, **entry)
    out["canvas"] = canvas
    return out


def _merged_style(new_raw, authoring, style_id):
    """The merged style data of new_raw, as layers.load would produce it from a file with this content."""
    own = {k: v for k, v in new_raw.items() if k != "extends"}
    base_id = new_raw.get("extends")
    if not base_id:
        return own
    base = layers.load("style", base_id, authoring, [("style", style_id, None)], "core" if base_id == style_id else None)
    return layers.merge(base["data"], own)


def _write_atomic(path, obj):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".derive-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(obj, f, indent=1, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _apply(path, raw, authoring, style_id, proposal):
    core = os.path.normcase(os.path.realpath(layers.CORE_DIR))
    if os.path.normcase(os.path.realpath(path)).startswith(core + os.sep):
        raise Refusal("%s is core data (templates/assetgen/): derive never writes it" % path)
    new_raw = _merged_raw(raw, authoring, style_id, proposal)
    merged = _merged_style(new_raw, authoring, style_id)
    errors = stylelock.style_errors(merged)
    if errors:
        raise Refusal("the merged style is not valid, nothing written:\n" + "\n".join("  " + e for e in errors))
    states = consistency.field_states(merged)
    bad = ["%s: %s" % (row, states[row][1]) for row in ("style-palette", "style-tone", "style-canvas")
           if states[row][0] != "ok"]
    if bad:
        raise Refusal("the merged style would not grade, nothing written:\n" + "\n".join("  " + b for b in bad))
    _write_atomic(path, new_raw)


# -- output ----------------------------------------------------------------------------------------------------

def _text(report, rel):
    prop = report["proposal"]
    st = report["style"]
    lines = ["style %s version %s status %s%s" % (st["style_id"], st["version"], st["status"],
                                                  " family " + report["family"] if report["family"] else "")]
    lines.append("anchors used (%d): %s" % (len(report["anchors"]), ", ".join(
        "%s (%s)" % (a["id"], a["family"]) for a in report["anchors"])))
    lines += ["anchor skipped: %s: %s" % (s["id"], s["reason"]) for s in report["skipped"]]
    lines.append("proposal:")
    lines.append("  palette.text: " + prop["palette"]["text"])
    lines.append("  palette.colors: " + ", ".join("%s (%s)" % (c["hex"], c["role"]) for c in prop["palette"]["colors"]))
    lines.append("  tone.tolerance: %s" % prop["tone"]["tolerance"])
    lines += ["  canvas.%s: aspect %s, tolerance %s" % (fam, c["aspect"], c["tolerance"])
              for fam, c in prop["canvas"].items()]
    lines.append("wrote %s (merged into the draft style)" % rel if report["applied"]
                 else "not applied: a proposal only (--apply merges it into a draft style)")
    return "\n".join(lines)


def run(a):
    """Exit code of `style derive`; a refusal prints `assetgen: <message>` to stderr."""
    try:
        return _run(a)
    except Refusal as exc:
        print("assetgen: " + str(exc), file=sys.stderr)
        return exc.code
    except layers.SpecError as exc:
        print("assetgen: " + str(exc), file=sys.stderr)
        return 1


def _run(a):
    authoring = os.path.abspath(a.authoring)
    if not stylelock.ID.match(a.style):
        raise Refusal("--style %r must be a lowercase id (a-z, 0-9 and '-')" % a.style, 2)
    if a.family is not None and not stylelock.ID.match(a.family):
        raise Refusal("--family %r must be a lowercase id" % a.family, 2)
    path = layers.layer_files("style", authoring)["game"].get(a.style)
    if path is None:
        raise Refusal("style %s has no game file assetgen/styles/%s.json in %s: derive works on a game style "
                      "(style init creates one)" % (a.style, a.style, authoring.replace(os.sep, "/")))
    raw = layers.read_json(path)
    status = raw.get("status")
    if a.apply and status != "draft":
        raise Refusal("style %s has status %s: --apply only merges into a draft style (never an active one)"
                      % (a.style, status if status is not None else "(none, i.e. active)"))
    entry = layers.load("style", a.style, authoring)
    version = stylelock.style_version(entry["data"])
    used, skipped = _load_anchors(authoring, a.style, version, a.family)
    proposal = derive(used, entry["data"]) if used else None
    if proposal is None:
        why = "; ".join("%s: %s" % (s["id"], s["reason"]) for s in skipped)
        raise Refusal("style %s version %s has no usable anchor%s (a valid active anchor of this style version "
                      "with its PNG next to it)%s" % (a.style, version, " in family " + a.family if a.family else "",
                                                       " [skipped: " + why + "]" if why else ""))
    rel = "assetgen/styles/%s.json" % a.style
    applied = False
    if a.apply:
        _apply(path, raw, authoring, a.style, proposal)
        applied = True
    report = {"schema": DERIVE_SCHEMA,
              "style": {"style_id": a.style, "version": version, "status": stylelock.style_status(entry["data"])},
              "family": a.family,
              "anchors": [{"id": d["id"], "family": d["family"], "image_sha256": d["image_sha256"]} for d, _ in used],
              "skipped": skipped, "proposal": proposal, "applied": applied}
    if a.json:
        print(json.dumps(report, indent=1, sort_keys=True))
    else:
        print(_text(report, rel))
    return 0
