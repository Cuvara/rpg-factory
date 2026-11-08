"""Deterministic style-consistency signals of one output PNG against the run's style (and anchors).

Pure functions over png.Image plus merged style data (layers) and purpose data; no file or clock access. Every
check returns (state, details) with state PASS, WARN, FAIL or NOT_AVAILABLE and details a list of strings:
  style-palette  style.palette.colors: share of opaque (alpha > 8) sampled pixels within max_distance (RGB
                 euclid, 0..441, default 48) of a palette colour >= min_share (0..1, default 0.6)
  style-tone     style.tone + anchors: the output's mean luminance and mean HSV saturation (both 0..1, opaque
                 pixels) inside [min - tolerance, max + tolerance] of the anchors' means (tolerance default 0.05)
  style-edges    purpose qa.outlines + style.outline.edge_darkness: among sampled opaque pixels whose luminance
                 gradient to the right or down neighbour is > 48, the share whose darker side has luminance
                 <= max_luminance (0..255, default 80) >= min_ratio (0..1, default 0.5)
  style-canvas   style.canvas[<family>]: aspect "W:H" within tolerance (relative, default 0.02) and the short
                 side >= min_side (default 0)
A check that misses is WARN, or FAIL when its style field sets severity "fail". NOT_AVAILABLE when the style
field is absent, a prose string or an object with no setting of its check (tone {}, outline.edge_darkness {}, a
canvas entry with neither aspect nor min_side), there are no anchors (tone), the purpose has no qa.outlines
(edges), there is no canvas entry for the family, or there is nothing opaque to measure. Malformed style data is
FAIL. Pixels are sampled with the same SAMPLES grid as qa.py so a 1536x1024 output stays fast on the stdlib
decoder. The *_config helpers parse each field for its check; field_states/usable_fields (lint's WARN for an
active style that no style row can grade) are built from them, so the rule has one source.
"""

SAMPLES = 256  # rows/columns sampled per statistic, as in qa.py
OPAQUE = 8  # alpha above this counts as opaque, as in qa.py
EDGE_GRADIENT = 48  # luminance step (0..255) that counts as an edge
ROWS = ("style-palette", "style-tone", "style-edges", "style-canvas")
FIELDS = {"style-palette": "palette.colors", "style-tone": "tone", "style-edges": "outline.edge_darkness",
          "style-canvas": "canvas"}
TONE_KEYS = ("tolerance", "severity")  # a tone object needs one of them to be a check
EDGE_KEYS = ("max_luminance", "min_ratio", "severity")  # an edge_darkness object needs one of them


def steps(n):
    return range(0, n, max(1, n // SAMPLES))


def luminance(r, g, b):
    return 0.299 * r + 0.587 * g + 0.114 * b


def saturation(r, g, b):
    hi = max(r, g, b)
    return (hi - min(r, g, b)) / hi if hi else 0.0


def miss_state(cfg):
    return "FAIL" if isinstance(cfg, dict) and cfg.get("severity") == "fail" else "WARN"


def number(cfg, key, default, lo, hi):
    """cfg[key] as a float in [lo, hi], default when absent; None when malformed."""
    value = cfg.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not lo <= value <= hi:
        return None
    return float(value)


def parse_hex(text):
    if not isinstance(text, str) or len(text) != 7 or text[0] != "#":
        return None
    try:
        return tuple(int(text[i:i + 2], 16) for i in (1, 3, 5))
    except ValueError:
        return None


def opaque_samples(img):
    for y in steps(img.height):
        for x in steps(img.width):
            px = img.pixel(x, y)
            if px[3] > OPAQUE:
                yield px


def not_graded(state, reason):
    """(state, details) of a config that cannot grade: absent is NOT_AVAILABLE, malformed is FAIL."""
    return ("NOT_AVAILABLE" if state == "absent" else "FAIL"), [reason]


def palette_config(style):
    """("ok", (cfg, rgb, max_distance, min_share)), ("absent", reason) or ("malformed", reason)."""
    cfg = (style or {}).get("palette")
    if not isinstance(cfg, dict) or "colors" not in cfg:
        return "absent", "style has no structured palette colours"
    colors = cfg["colors"]
    rgb = [parse_hex(c.get("hex")) if isinstance(c, dict) else None for c in colors] if isinstance(colors, list) else []
    max_distance, min_share = number(cfg, "max_distance", 48, 0, 441), number(cfg, "min_share", 0.6, 0, 1)
    if not rgb or None in rgb or max_distance is None or min_share is None:
        return "malformed", "malformed style palette (colors [{hex: #rrggbb}], max_distance 0..441, min_share 0..1)"
    return "ok", (cfg, rgb, max_distance, min_share)


def check_palette(img, style):
    state, got = palette_config(style)
    if state != "ok":
        return not_graded(state, got)
    cfg, rgb, max_distance, min_share = got
    limit = max_distance * max_distance
    total = near = 0
    for r, g, b, _ in opaque_samples(img):
        total += 1
        if any((r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2 <= limit for pr, pg, pb in rgb):
            near += 1
    if not total:
        return "NOT_AVAILABLE", ["no opaque pixels to compare with the palette"]
    share = near / total
    detail = ["%.1f%% of opaque pixels within %d of %d palette colours (min %.1f%%)"
              % (share * 100, max_distance, len(rgb), min_share * 100)]
    return ("PASS" if share >= min_share else miss_state(cfg)), detail


def tone_stats(img):
    """(mean luminance 0..1, mean HSV saturation 0..1) over sampled opaque pixels; None when none is opaque."""
    n = lum = sat = 0
    for r, g, b, _ in opaque_samples(img):
        n += 1
        lum += luminance(r, g, b) / 255.0
        sat += saturation(r, g, b)
    return (lum / n, sat / n) if n else None


def tone_config(style):
    """("ok", (cfg, tolerance)), ("absent", reason) or ("malformed", reason); anchors are a run-time input."""
    cfg = (style or {}).get("tone")
    if not isinstance(cfg, dict) or not any(k in cfg for k in TONE_KEYS):
        return "absent", "style has no tone settings (%s)" % ", ".join(TONE_KEYS)
    tol = number(cfg, "tolerance", 0.05, 0, 1)
    if tol is None:
        return "malformed", "malformed style tone (tolerance 0..1)"
    return "ok", (cfg, tol)


def check_tone(img, style, anchors):
    """anchors: png.Image objects or precomputed tone_stats tuples of the selected anchors."""
    state, got = tone_config(style)
    if state != "ok":
        return not_graded(state, got)
    cfg, tol = got
    stats = [a if isinstance(a, tuple) else tone_stats(a) for a in anchors or ()]
    stats = [s for s in stats if s is not None]
    if not stats:
        return "NOT_AVAILABLE", ["no anchors to compare tone with"]
    own = tone_stats(img)
    if own is None:
        return "NOT_AVAILABLE", ["no opaque pixels to measure tone"]
    ok, detail = True, []
    for i, name in enumerate(("luminance", "saturation")):
        lo, hi = min(s[i] for s in stats) - tol, max(s[i] for s in stats) + tol
        inside = lo <= own[i] <= hi
        ok = ok and inside
        detail.append("mean %s %.3f %s [%.3f, %.3f] of %d anchor(s) +/- %.2f"
                      % (name, own[i], "inside" if inside else "outside", lo + tol, hi - tol, len(stats), tol))
    return ("PASS" if ok else miss_state(cfg)), detail


def edges_config(style):
    """("ok", (cfg, max_luminance, min_ratio)), ("absent", reason) or ("malformed", reason); the purpose's
    qa.outlines is a run-time input."""
    outline = (style or {}).get("outline")
    cfg = outline.get("edge_darkness") if isinstance(outline, dict) else None
    if not isinstance(cfg, dict) or not any(k in cfg for k in EDGE_KEYS):
        return "absent", "style outline has no edge_darkness settings (%s)" % ", ".join(EDGE_KEYS)
    max_lum, min_ratio = number(cfg, "max_luminance", 80, 0, 255), number(cfg, "min_ratio", 0.5, 0, 1)
    if max_lum is None or min_ratio is None:
        return "malformed", "malformed style outline.edge_darkness (max_luminance 0..255, min_ratio 0..1)"
    return "ok", (cfg, max_lum, min_ratio)


def check_edges(img, style, purpose):
    qa = (purpose or {}).get("qa")
    if not (isinstance(qa, dict) and qa.get("outlines") is True):
        return "NOT_AVAILABLE", ["purpose does not expect outlines (qa.outlines)"]
    state, got = edges_config(style)
    if state != "ok":
        return not_graded(state, got)
    cfg, max_lum, min_ratio = got
    w, h = img.width, img.height
    edges = dark = 0
    for y in steps(h):
        for x in steps(w):
            px = img.pixel(x, y)
            if px[3] <= OPAQUE:
                continue
            own = luminance(*px[:3])
            darkest = None
            for nx, ny in ((x + 1, y), (x, y + 1)):
                if nx >= w or ny >= h:
                    continue
                nb = img.pixel(nx, ny)
                if nb[3] <= OPAQUE:
                    continue
                other = luminance(*nb[:3])
                if abs(own - other) > EDGE_GRADIENT:
                    side = min(own, other)
                    darkest = side if darkest is None else min(darkest, side)
            if darkest is not None:
                edges += 1
                dark += darkest <= max_lum
    if not edges:
        return miss_state(cfg), ["no edges found (luminance step > %d) where outlines are expected" % EDGE_GRADIENT]
    ratio = dark / edges
    detail = ["%.1f%% of %d sampled edges have a dark side <= %d luminance (min %.1f%%)"
              % (ratio * 100, edges, max_lum, min_ratio * 100)]
    return ("PASS" if ratio >= min_ratio else miss_state(cfg)), detail


def parse_aspect(text):
    try:
        w, h = (float(v) for v in str(text).split(":"))
    except ValueError:
        return None
    return w / h if w > 0 and h > 0 else None


def canvas_config(style, family):
    """("ok", (cfg, aspect or None, tolerance, min_side)), ("absent", reason) or ("malformed", reason) of one
    family's canvas entry; an entry with neither aspect nor min_side measures nothing (absent)."""
    canvas = (style or {}).get("canvas")
    cfg = canvas.get(family) if isinstance(canvas, dict) and family else None
    if cfg is None:
        return "absent", "style has no canvas entry for family %s" % (family or "(none)")
    if not isinstance(cfg, dict):
        return "malformed", "malformed style canvas.%s (object with aspect, min_side, tolerance)" % family
    if "aspect" not in cfg and "min_side" not in cfg:
        return "absent", "style canvas.%s has neither aspect nor min_side" % family
    want = parse_aspect(cfg["aspect"]) if "aspect" in cfg else None
    tol, min_side = number(cfg, "tolerance", 0.02, 0, 1), number(cfg, "min_side", 0, 0, 1 << 20)
    if ("aspect" in cfg and want is None) or tol is None or min_side is None:
        return "malformed", "malformed style canvas.%s (aspect W:H, min_side >= 0, tolerance 0..1)" % family
    return "ok", (cfg, want, tol, min_side)


def check_canvas(img, style, family):
    state, got = canvas_config(style, family)
    if state != "ok":
        return not_graded(state, got)
    cfg, want, tol, min_side = got
    got, short = img.width / img.height, min(img.width, img.height)
    ok = short >= min_side
    detail = ["%dx%d, short side %d (min %d)" % (img.width, img.height, short, min_side)]
    if want is not None:
        ok = ok and abs(got - want) <= tol * want
        detail.append("aspect %.3f (expected %s = %.3f +/- %d%%)" % (got, cfg["aspect"], want, round(tol * 100)))
    return ("PASS" if ok else miss_state(cfg)), ["family %s: %s" % (family, ", ".join(detail))]


def check_all(img, style, purpose=None, family=None, anchors=()):
    """[(row, state, details)] for every style row, in ROWS order."""
    return [
        ("style-palette",) + check_palette(img, style),
        ("style-tone",) + check_tone(img, style, anchors),
        ("style-edges",) + check_edges(img, style, purpose),
        ("style-canvas",) + check_canvas(img, style, family),
    ]


def field_states(style):
    """{row: (state, reason)} of every style row from the style alone, through the *_config helpers the checks
    use: "ok" (reason "") when the row's check can grade an output with this config, run-time inputs aside
    (anchors, qa.outlines, the run's family), else "absent" or "malformed". canvas is ok when any family is."""
    states = {"style-palette": palette_config(style), "style-tone": tone_config(style),
              "style-edges": edges_config(style)}
    canvas = (style or {}).get("canvas")
    fams = [canvas_config(style, f) for f in sorted(canvas)] if isinstance(canvas, dict) else []
    states["style-canvas"] = (next((s for s in fams if s[0] == "ok"), None)
                              or next((s for s in fams if s[0] == "malformed"), None)
                              or ("absent", "style has no canvas entry with aspect or min_side"))
    return {row: (state, "" if state == "ok" else why) for row, (state, why) in states.items()}


def usable_fields(style):
    """Set of style rows (ROWS) whose check can grade an output with this style's config (field_states ok)."""
    return {row for row, (state, _) in field_states(style).items() if state == "ok"}


def overall(rows):
    """A style FAIL row fails the qa state; WARN and NOT_AVAILABLE never change it."""
    return "FAIL" if any(state == "FAIL" for _, state, _ in rows) else "PASS"
