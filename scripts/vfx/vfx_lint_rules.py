"""Lint rules of vfx_style.py: one function per rule, each returns one row {id, state, evidence}.

A rule reads the context built by vfx_style.py: the resolved style profile (vfx-style spec body), the recipe
(cuvara.vfx-recipe/1) and its bytes, and the optional inspect result (cuvara.vfx-inspect/1), capture statistics
(cuvara.vfx-capture/1) and vfx-spec body. A rule whose only input is absent is NOT_AVAILABLE. Where the recipe holds
the same fact, a rule falls back to it when the inspect result is absent and says so in its evidence (the inspect
result is authoritative: it also sees prefab overrides and VFX Graph defaults).

Conventions (com.cuvara.vfx Documentation~/AUTHORING.md, CAPTURE.md and Schemas~):
- the effect names its element and tier in recipe meta.tags as element:<name> and tier:<name>;
- recipe colour values are linear RGB, as VFX Graph stores them; for the hue test a colour is divided by its
  largest channel when that is above 1 (HDR) and encoded to sRGB, the space of the profile's #RRGGBB palette;
  a colour with an sRGB saturation below ACHROMATIC (white, grey, black) has no hue and is not graded;
- HDR intensity is log2 of the largest of r, g, b (the inspect hdr_colors intensity, Unity's HDR picker);
- the recipe hash is the SHA-256 of the recipe file bytes (inspect recipe.sha256, capture recipe_sha256).
"""
import colorsys
import fnmatch
import hashlib
import math
import numbers
import re

RECIPE_SCHEMA = "cuvara.vfx-recipe/1"
RECIPE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PHASES = ("anticipation", "impact", "dissipation")
TIERS = ("primary", "secondary", "ambient")
ACHROMATIC = 0.1
DEFAULT_SUM_TOLERANCE = 0.01


def row(rule_id, state, evidence):
    return {"id": rule_id, "state": state, "evidence": evidence if isinstance(evidence, list) else [evidence]}


def is_num(v):
    return isinstance(v, numbers.Real) and not isinstance(v, bool) and math.isfinite(v)


def num_vec(v, sizes=(3, 4)):
    return isinstance(v, list) and len(v) in sizes and all(is_num(x) for x in v[:3])


def fmt(x):
    return ("%.4f" % x).rstrip("0").rstrip(".") if is_num(x) else str(x)


def major_minor(version):
    m = re.match(r"^\s*(\d+)\.(\d+)", str(version or ""))
    return "%s.%s" % (m.group(1), m.group(2)) if m else None


def meta(recipe):
    m = recipe.get("meta")
    return m if isinstance(m, dict) else {}


def tag_value(recipe, key):
    """The value of the first <key>:<value> tag of the recipe meta.tags, else None."""
    for tag in meta(recipe).get("tags") or []:
        if isinstance(tag, str) and tag.startswith(key + ":") and tag[len(key) + 1:]:
            return tag[len(key) + 1:]
    return None


def ops(recipe):
    return [op for op in recipe.get("ops") or [] if isinstance(op, dict)]


def colorish(name):
    n = str(name or "").lower()
    return "color" in n or "colour" in n


# ---- colour ------------------------------------------------------------------------------------------------

def hex_rgb(h):
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (1, 3, 5))


def srgb_encode(c):
    c = min(max(c, 0.0), 1.0)
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def linear_to_display(rgb):
    """Linear (possibly HDR) RGB to the LDR sRGB colour the HDR picker shows: divided by the peak above 1."""
    r, g, b = (max(float(x), 0.0) for x in rgb[:3])
    peak = max(r, g, b)
    if peak > 1:
        r, g, b = r / peak, g / peak, b / peak
    return srgb_encode(r), srgb_encode(g), srgb_encode(b)


def hue_sat(srgb):
    h, s, _v = colorsys.rgb_to_hsv(*srgb)
    return h * 360.0, s


def hue_distance(a, b):
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def peak(rgb):
    return max(float(x) for x in rgb[:3])


def walk_colors(value, path, out, force=False):
    """Collect (path, rgb) colour values: gradients (color_keys), and 3-4 number vectors under a colour name."""
    if isinstance(value, dict):
        keys = value.get("color_keys")
        if isinstance(keys, list):
            for j, key in enumerate(keys):
                if isinstance(key, dict) and num_vec(key.get("color")):
                    out.append(("%s.color_keys.%d" % (path, j), key["color"]))
            return
        for k, sub in value.items():
            walk_colors(sub, "%s.%s" % (path, k), out, force=colorish(k))
    elif force and num_vec(value):
        out.append((path, value))


def recipe_colors(recipe):
    out = []
    for op in ops(recipe):
        kind = op.get("op")
        if kind == "add_parameter":
            ptype = str(op.get("type", "")).replace(" ", "").lower()
            force = ptype in ("color", "gradient") or (ptype in ("vector3", "vector4") and colorish(op.get("name")))
            walk_colors(op.get("value"), str(op.get("id")), out, force=force)
        elif kind in ("add_context", "add_block", "add_operator", "use_subgraph"):
            walk_colors(op.get("slots"), str(op.get("id")), out)
        elif kind == "set_slot":
            walk_colors(op.get("value"), str(op.get("slot")), out, force=colorish(op.get("slot")))
        elif kind == "set_output":
            walk_colors(op.get("gradient"), "%s.gradient" % op.get("node"), out)
    return out


# ---- recipe facts used when the inspect result is absent ------------------------------------------------------

def recipe_outputs(recipe):
    """[{id, type, blend_mode}] of the output contexts the recipe adds, blend mode after later ops (None if unset)."""
    outs = {}
    for op in ops(recipe):
        kind = op.get("op")
        if kind == "add_context" and "Output" in str(op.get("type", "")):
            settings = op.get("settings") if isinstance(op.get("settings"), dict) else {}
            outs[op.get("id")] = {"id": op.get("id"), "type": op.get("type"), "blend_mode": settings.get("blendMode")}
        elif kind == "set_output" and op.get("node") in outs and op.get("blend_mode"):
            outs[op["node"]]["blend_mode"] = op["blend_mode"]
        elif kind == "set_setting" and op.get("node") in outs and op.get("name") == "blendMode":
            outs[op["node"]]["blend_mode"] = op.get("value")
    return list(outs.values())


def recipe_systems(recipe):
    """{context id: capacity or None} of the Initialize contexts (one per particle system)."""
    caps = {}
    for op in ops(recipe):
        kind = op.get("op")
        if kind == "add_context" and "Initialize" in str(op.get("type", "")):
            settings = op.get("settings") if isinstance(op.get("settings"), dict) else {}
            caps[op.get("id")] = settings.get("capacity")
        elif kind == "set_setting" and op.get("node") in caps and op.get("name") == "capacity":
            caps[op["node"]] = op.get("value")
    return caps


def recipe_flipbooks(recipe):
    """(path, value) of every flipBookSize slot value the recipe sets."""
    found = []

    def walk(value, path):
        if isinstance(value, dict):
            for k, sub in value.items():
                if str(k).lower() == "flipbooksize":
                    found.append(("%s.%s" % (path, k), sub))
                else:
                    walk(sub, "%s.%s" % (path, k))

    for op in ops(recipe):
        kind = op.get("op")
        if kind in ("add_context", "add_block", "add_operator"):
            walk(op.get("slots"), str(op.get("id")))
        elif kind == "set_slot" and str(op.get("slot", "")).split(".")[-1].lower() == "flipbooksize":
            found.append((str(op.get("slot")), op.get("value")))
    return found


def particle_systems(inspect):
    return [s for s in inspect.get("systems") or [] if isinstance(s, dict) and s.get("capacity") is not None]


# ---- rules -------------------------------------------------------------------------------------------------

def rule_recipe_schema(ctx):
    recipe, ev, bad = ctx["recipe"], [], False
    if recipe.get("schema") == RECIPE_SCHEMA:
        ev.append("schema %s" % RECIPE_SCHEMA)
    else:
        bad = True
        ev.append("schema is %r, expected %s" % (recipe.get("schema"), RECIPE_SCHEMA))
    rid = recipe.get("id")
    if isinstance(rid, str) and RECIPE_ID_RE.match(rid):
        ev.append("id %s" % rid)
    else:
        bad = True
        ev.append("id %r is not kebab-case (^[a-z0-9][a-z0-9-]*$)" % (rid,))
    if not isinstance(recipe.get("ops"), list):
        bad = True
        ev.append("ops is not a list")
    return row("recipe-schema", "FAIL" if bad else "PASS", ev)


def rule_vfx_graph(ctx):
    want = ctx["profile"]["vfx_graph"]
    have = recipe_ver = ctx["recipe"].get("vfx_graph")
    if have is None:
        state, ev = "WARN", ["recipe has no vfx_graph; profile targets %s" % want]
    elif major_minor(have) == major_minor(want):
        state, ev = "PASS", ["recipe vfx_graph %s matches profile %s" % (recipe_ver, want)]
    else:
        return row("vfx-graph-version", "FAIL", ["recipe vfx_graph %s, profile targets %s" % (recipe_ver, want)])
    for name, doc in (("inspect", ctx["inspect"]), ("capture", ctx["stats"])):
        if doc is None:
            continue
        ver = doc.get("vfx_graph")
        if ver is None:
            ev.append("%s has no vfx_graph" % name)
        elif major_minor(ver) == major_minor(want):
            ev.append("%s vfx_graph %s matches" % (name, ver))
        else:
            state = "WARN"
            ev.append("%s ran on vfx_graph %s, profile targets %s (re-run on the target version)" % (name, ver, want))
    return row("vfx-graph-version", state, ev)


def phase_seconds(recipe):
    """(duration, {phase name: seconds summed}, errors)."""
    m, errs = meta(recipe), []
    duration = m.get("duration_seconds")
    if not is_num(duration) or duration <= 0:
        errs.append("recipe meta.duration_seconds is missing or not positive")
        duration = None
    phases = m.get("phases")
    if not isinstance(phases, list) or not phases:
        errs.append("recipe meta.phases is missing or empty")
        return duration, {}, errs
    sums = {}
    for p in phases:
        if not isinstance(p, dict) or not isinstance(p.get("name"), str) or not is_num(p.get("seconds")):
            errs.append("phase %r needs a name and seconds" % (p,))
            continue
        sums[p["name"]] = sums.get(p["name"], 0.0) + float(p["seconds"])
    return duration, sums, errs


def sum_tolerance(profile):
    tol = profile["timing"].get("sum_tolerance_seconds")
    return float(tol) if is_num(tol) else DEFAULT_SUM_TOLERANCE


def rule_timing_sum(ctx):
    duration, sums, errs = phase_seconds(ctx["recipe"])
    if errs:
        return row("timing-sum", "FAIL", errs)
    total, tol = sum(sums.values()), sum_tolerance(ctx["profile"])
    ok = abs(total - duration) <= tol + 1e-9
    return row("timing-sum", "PASS" if ok else "FAIL",
               "phase seconds sum to %s, meta.duration_seconds %s (tolerance %s s)" % (fmt(total), fmt(duration), fmt(tol)))


def rule_timing_ratios(ctx):
    duration, sums, errs = phase_seconds(ctx["recipe"])
    if errs:
        return row("timing-ratios", "FAIL", errs)
    bands, ev, state = ctx["profile"]["timing"], [], "PASS"
    for name in PHASES:
        band, share = bands[name], sums.get(name, 0.0) / duration
        inside = band["min"] - 1e-9 <= share <= band["max"] + 1e-9
        ev.append("%s %s of %s s = %s, band %s..%s%s" % (name, fmt(sums.get(name, 0.0)), fmt(duration), fmt(share),
                                                       fmt(band["min"]), fmt(band["max"]),
                                                       "" if name in sums else " (phase absent)"))
        if not inside:
            state = "FAIL"
    extra = sorted(set(sums) - set(PHASES))
    if extra:
        ev.append("phases not in the profile, not graded: %s" % ", ".join(extra))
        state = "WARN" if state == "PASS" else state
    return row("timing-ratios", state, ev)


def effect_tier(ctx):
    tier = tag_value(ctx["recipe"], "tier")
    if tier is None and ctx["spec"] is not None and isinstance(ctx["spec"].get("tier"), str):
        tier = ctx["spec"]["tier"]
    return tier


def rule_hdr(ctx):
    tier = effect_tier(ctx)
    if tier is None:
        return row("hdr-intensity", "FAIL", "the effect names no tier (recipe meta.tags tier:<%s>)" % "|".join(TIERS))
    if tier not in ctx["profile"]["hdr_intensity"]:
        return row("hdr-intensity", "FAIL", "tier %r is not one of %s" % (tier, ", ".join(TIERS)))
    band = ctx["profile"]["hdr_intensity"][tier]
    if ctx["inspect"] is not None:
        values = [(h.get("path"), h.get("intensity")) for h in ctx["inspect"].get("hdr_colors") or [] if isinstance(h, dict)]
        source = "inspect hdr_colors"
    else:
        values = [(p, round(math.log2(peak(c)), 4)) for p, c in recipe_colors(ctx["recipe"]) if peak(c) > 1]
        source = "recipe colour values (no inspect)"
    ev, state = ["tier %s band %s..%s, from %s" % (tier, fmt(band["min"]), fmt(band["max"]), source)], "PASS"
    if not values:
        ok = band["min"] <= 0
        ev.append("no HDR colour value (intensity 0)%s" % ("" if ok else ": tier %s needs at least %s" % (tier, fmt(band["min"]))))
        return row("hdr-intensity", "PASS" if ok else "FAIL", ev)
    for path, intensity in values:
        if not is_num(intensity):
            state = "FAIL"
            ev.append("%s: intensity %r is not a number" % (path, intensity))
        elif not band["min"] - 1e-9 <= intensity <= band["max"] + 1e-9:
            state = "FAIL"
            ev.append("%s: intensity %s outside %s..%s" % (path, fmt(intensity), fmt(band["min"]), fmt(band["max"])))
        else:
            ev.append("%s: intensity %s" % (path, fmt(intensity)))
    return row("hdr-intensity", state, ev)


def rule_palette(ctx):
    pal = ctx["profile"]["palette"]
    element = tag_value(ctx["recipe"], "element")
    if element is None:
        return row("palette", "FAIL", "the effect names no element (recipe meta.tags element:<name>)")
    if element not in pal["elements"]:
        return row("palette", "FAIL", "element %r is not in the profile (%s)" % (element, ", ".join(sorted(pal["elements"]))))
    tol = float(pal["hue_tolerance_degrees"])
    refs = []
    for name, hx in pal["elements"][element]["colors"].items():
        h, s = hue_sat(hex_rgb(hx))
        if s >= ACHROMATIC:
            refs.append((name, h))
    colors = recipe_colors(ctx["recipe"])
    ev, state = ["element %s, hue tolerance %s deg" % (element, fmt(tol))], "PASS"
    if not colors:
        ev.append("the recipe sets no colour value")
        return row("palette", "WARN", ev)
    for path, rgb in colors:
        h, s = hue_sat(linear_to_display(rgb))
        if s < ACHROMATIC:
            ev.append("%s: achromatic (saturation %s), not graded" % (path, fmt(s)))
            continue
        if not refs:
            state = "FAIL"
            ev.append("%s: hue %s deg, element %s has no chromatic colour" % (path, fmt(h), element))
            continue
        name, dist = min(((n, hue_distance(h, rh)) for n, rh in refs), key=lambda x: x[1])
        if dist > tol + 1e-9:
            state = "FAIL"
            ev.append("%s: hue %s deg is %s deg from the nearest palette colour %s" % (path, fmt(h), fmt(dist), name))
        else:
            ev.append("%s: hue %s deg, %s deg from %s" % (path, fmt(h), fmt(dist), name))
    return row("palette", state, ev)


def textures(ctx):
    return [t for t in ctx["inspect"].get("textures") or [] if isinstance(t, dict)]


def rule_texture_size(ctx):
    if ctx["inspect"] is None:
        return row("texture-size", "NOT_AVAILABLE", "needs --inspect (inspect textures)")
    limit, ev, state = ctx["profile"]["textures"]["max_size"], [], "PASS"
    for t in textures(ctx):
        w, h = t.get("width"), t.get("height")
        ok = is_num(w) and is_num(h) and max(w, h) <= limit
        state = state if ok else "FAIL"
        ev.append("%s: %sx%s%s" % (t.get("path"), w, h, "" if ok else ", above max_size %s" % limit))
    return row("texture-size", state, ev or "the effect references no texture")


def rule_flipbook_grid(ctx):
    allowed, ev, state = ctx["profile"]["textures"]["flipbook_grids"], [], "PASS"
    for path, value in recipe_flipbooks(ctx["recipe"]):
        if not (isinstance(value, list) and len(value) == 2 and all(is_num(x) and float(x).is_integer() and x >= 1 for x in value)):
            state = "FAIL"
            ev.append("%s: %r is not a <columns, rows> pair of whole numbers" % (path, value))
            continue
        grid = "%dx%d" % (int(value[0]), int(value[1]))
        ok = grid in allowed
        state = state if ok else "FAIL"
        ev.append("%s: %s%s" % (path, grid, "" if ok else ", not one of %s" % ", ".join(allowed)))
    return row("texture-flipbook-grid", state, ev or "the recipe sets no flipBookSize")


def rule_color_space(ctx):
    if ctx["inspect"] is None:
        return row("texture-color-space", "NOT_AVAILABLE", "needs --inspect (inspect textures srgb)")
    conv = ctx["profile"]["textures"]
    linear_globs = conv.get("linear_textures") or []
    ev, state = [], "PASS"
    for t in textures(ctx):
        path = str(t.get("path"))
        data = any(fnmatch.fnmatchcase(path, g) or fnmatch.fnmatchcase(path.rsplit("/", 1)[-1], g) for g in linear_globs)
        want_srgb = False if data else conv["color_space"] == "srgb"
        ok = t.get("srgb") is want_srgb
        state = state if ok else "FAIL"
        ev.append("%s: srgb %s, expected %s%s" % (path, t.get("srgb"), want_srgb, " (linear_textures)" if data else ""))
    return row("texture-color-space", state, ev or "the effect references no texture")


def effect_outputs(ctx):
    if ctx["inspect"] is not None:
        return [o for o in ctx["inspect"].get("outputs") or [] if isinstance(o, dict)], "inspect outputs"
    return recipe_outputs(ctx["recipe"]), "recipe output contexts (no inspect)"


def rule_output_type(ctx):
    allowed = ctx["profile"]["outputs"]["types"]
    outs, source = effect_outputs(ctx)
    ev, state = ["from %s" % source], "PASS"
    if not outs:
        return row("output-type", "WARN", ev + ["the effect has no output context"])
    for o in outs:
        ok = o.get("type") in allowed
        state = state if ok else "FAIL"
        ev.append("%s: %s%s" % (o.get("id"), o.get("type"), "" if ok else ", not one of %s" % ", ".join(allowed)))
    return row("output-type", state, ev)


def rule_blend_mode(ctx):
    allowed = ctx["profile"]["outputs"]["blend_modes"]
    outs, source = effect_outputs(ctx)
    ev, state = ["from %s" % source], "PASS"
    if not outs:
        return row("blend-mode", "WARN", ev + ["the effect has no output context"])
    for o in outs:
        mode = o.get("blend_mode")
        if mode is None:
            if ctx["inspect"] is None:
                state = "WARN" if state == "PASS" else state
                ev.append("%s: blend mode not set in the recipe (VFX Graph default; --inspect shows the effective one)" % o.get("id"))
            else:
                ev.append("%s: no blend mode (%s), not graded" % (o.get("id"), o.get("type")))
            continue
        ok = mode in allowed
        state = "FAIL" if not ok else state
        ev.append("%s: %s%s" % (o.get("id"), mode, "" if ok else ", not one of %s" % ", ".join(allowed)))
    return row("blend-mode", state, ev)


def rule_shader(ctx):
    if ctx["inspect"] is None:
        return row("shader", "NOT_AVAILABLE", "needs --inspect (inspect outputs shader and shader_graph)")
    globs = ctx["profile"]["outputs"]["shaders"]
    ev, state = [], "PASS"
    for o in effect_outputs(ctx)[0]:
        names = []
        for key, field in (("shader", "name"), ("shader_graph", "path")):
            v = o.get(key)
            if isinstance(v, dict) and v.get(field):
                names.append(str(v[field]))
        if not names:
            state = "WARN" if state == "PASS" else state
            ev.append("%s: no shader found (graph not compiled?)" % o.get("id"))
            continue
        ok = any(fnmatch.fnmatchcase(n, g) for n in names for g in globs)
        state = state if ok else "FAIL"
        ev.append("%s: %s%s" % (o.get("id"), " | ".join(names), "" if ok else ", matches none of %s" % ", ".join(globs)))
    return row("shader", state, ev or "the effect has no output context")


def per_platform(ctx, rule_id, key, label, value, source):
    """One row comparing value with budgets.<platform>.<key> of every platform of the profile."""
    ev, state = ["%s %s from %s" % (label, value, source)], "PASS"
    for platform, budget in sorted(ctx["profile"]["budgets"].items()):
        limit = budget[key]
        ok = value <= limit
        state = state if ok else "FAIL"
        ev.append("%s: %s %s %s" % (platform, value, "<=" if ok else ">", limit))
    return row(rule_id, state, ev)


def rule_budget_capacity(ctx):
    if ctx["inspect"] is not None:
        systems = particle_systems(ctx["inspect"])
        total = ctx["inspect"].get("totals", {}).get("capacity")
        if not is_num(total):
            total = sum(s["capacity"] for s in systems)
        source = "inspect totals.capacity"
    elif ctx["stats"] is not None:
        total, source = sum(s.get("capacity", 0) for s in ctx["stats"].get("systems") or []), "capture systems"
    else:
        caps = recipe_systems(ctx["recipe"])
        unset = [k for k, v in caps.items() if not is_num(v)]
        if unset:
            return row("budget-capacity", "WARN", "recipe Initialize contexts without a capacity setting: %s (--inspect reads the built one)" % ", ".join(map(str, unset)))
        total, source = sum(caps.values()), "recipe Initialize capacity settings (no inspect)"
    return per_platform(ctx, "budget-capacity", "max_alive_particles", "capacity", total, source)


def rule_budget_systems(ctx):
    if ctx["inspect"] is not None:
        count, source = len(particle_systems(ctx["inspect"])), "inspect systems with a capacity"
    elif ctx["stats"] is not None:
        count, source = len(ctx["stats"].get("systems") or []), "capture systems"
    else:
        count, source = len(recipe_systems(ctx["recipe"])), "recipe Initialize contexts (no inspect)"
    return per_platform(ctx, "budget-systems", "max_systems", "particle systems", count, source)


def rule_budget_texture_memory(ctx):
    if ctx["inspect"] is None:
        return row("budget-texture-memory", "NOT_AVAILABLE", "needs --inspect (inspect totals.texture_bytes)")
    total = ctx["inspect"].get("totals", {}).get("texture_bytes")
    if not is_num(total):
        total = sum(t.get("estimated_bytes") or 0 for t in textures(ctx))
    return per_platform(ctx, "budget-texture-memory", "max_texture_memory_bytes", "texture bytes", total, "inspect totals.texture_bytes")


def rule_budget_alive(ctx):
    if ctx["stats"] is None:
        return row("budget-alive", "NOT_AVAILABLE", "needs --stats (capture alive.peak)")
    return per_platform(ctx, "budget-alive", "max_alive_particles", "alive peak", ctx["stats"]["alive"]["peak"], "capture alive.peak")


def rule_capture_conditions(ctx):
    if ctx["stats"] is None:
        return row("capture-conditions", "NOT_AVAILABLE", "needs --stats (capture camera, lighting, seed)")
    want, ev, state = ctx["profile"]["capture"], [], "PASS"
    for key in ("camera", "lighting", "seed"):
        have = ctx["stats"].get(key)
        ok = have == want[key] and type(have) is type(want[key])
        state = state if ok else "FAIL"
        ev.append("%s %s%s" % (key, have, "" if ok else ", profile %s" % want[key]))
    return row("capture-conditions", state, ev)


def rule_recipe_hash(ctx):
    sources = []
    if ctx["stats"] is not None:
        sources.append(("capture recipe_sha256", ctx["stats"].get("recipe_sha256")))
    if ctx["inspect"] is not None:
        rec = ctx["inspect"].get("recipe")
        sources.append(("inspect recipe.sha256", rec.get("sha256") if isinstance(rec, dict) else None))
    if not sources:
        return row("recipe-hash", "NOT_AVAILABLE", "needs --stats or --inspect (recipe_sha256)")
    digest = hashlib.sha256(ctx["recipe_bytes"]).hexdigest()
    ev, state = ["recipe file sha256 %s" % digest], "PASS"
    for name, have in sources:
        ok = have == digest
        state = state if ok else "FAIL"
        ev.append("%s %s%s" % (name, have, "" if ok else ": differs, the evidence is of another recipe (rebuild and recapture)"))
    return row("recipe-hash", state, ev)


def rule_spec_match(ctx):
    spec = ctx["spec"]
    if spec is None:
        return row("spec-match", "NOT_AVAILABLE", "needs --spec (vfx-spec duration_seconds and phases)")
    m, tol, ev, state = meta(ctx["recipe"]), sum_tolerance(ctx["profile"]), [], "PASS"
    sd, rd = spec.get("duration_seconds"), m.get("duration_seconds")
    ok = is_num(sd) and is_num(rd) and abs(sd - rd) <= tol + 1e-9
    state = state if ok else "FAIL"
    ev.append("duration: recipe %s, spec %s" % (fmt(rd), fmt(sd)))
    sp = [(p.get("name"), p.get("duration_seconds")) for p in spec.get("phases") or [] if isinstance(p, dict)]
    rp = [(p.get("name"), p.get("seconds")) for p in m.get("phases") or [] if isinstance(p, dict)]
    same = len(sp) == len(rp) and all(a[0] == b[0] and is_num(a[1]) and is_num(b[1]) and abs(a[1] - b[1]) <= tol + 1e-9
                                      for a, b in zip(sp, rp))
    state = state if same else "FAIL"
    ev.append("phases: recipe %s, spec %s" % (", ".join("%s %s" % (n, fmt(s)) for n, s in rp) or "none",
                                              ", ".join("%s %s" % (n, fmt(s)) for n, s in sp) or "none"))
    return row("spec-match", state, ev)


RULES = [
    ("recipe-schema", rule_recipe_schema),
    ("vfx-graph-version", rule_vfx_graph),
    ("timing-sum", rule_timing_sum),
    ("timing-ratios", rule_timing_ratios),
    ("hdr-intensity", rule_hdr),
    ("palette", rule_palette),
    ("texture-size", rule_texture_size),
    ("texture-flipbook-grid", rule_flipbook_grid),
    ("texture-color-space", rule_color_space),
    ("output-type", rule_output_type),
    ("blend-mode", rule_blend_mode),
    ("shader", rule_shader),
    ("budget-capacity", rule_budget_capacity),
    ("budget-systems", rule_budget_systems),
    ("budget-texture-memory", rule_budget_texture_memory),
    ("budget-alive", rule_budget_alive),
    ("capture-conditions", rule_capture_conditions),
    ("recipe-hash", rule_recipe_hash),
    ("spec-match", rule_spec_match),
]


def run(ctx):
    """One row per rule, in RULES order; a rule that trips on a malformed input is a FAIL that says so."""
    rows = []
    for rule_id, fn in RULES:
        try:
            rows.append(fn(ctx))
        except (KeyError, TypeError, ValueError, AttributeError, ZeroDivisionError) as e:
            rows.append(row(rule_id, "FAIL", "could not grade: malformed input (%s: %s)" % (type(e).__name__, e)))
    return rows
