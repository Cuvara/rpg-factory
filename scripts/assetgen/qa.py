"""Deterministic image QA of a run's outputs/*.png against the purpose's qa expectations.

Per output PNG (results keyed by output path, rpg-factory.validation/1 states); the checks a purpose requires are
runfiles.required_checks(qa), which the gen-run quality plugin also requires as PASS rows:
  png-valid           decodes (Pillow when present, else the stdlib decoder; NOT_AVAILABLE when neither can)
  png-size            qa.size.mode: exact (= expect), min (width and height >= expect), aspect (ratio within
                      aspect_tolerance, default 0.02, and, with min_area, width x height >= min_area x the expected
                      pixel count), orientation (landscape, portrait or square: qa.size.orientation, or "auto" to
                      take it from expect; square when the long side is at most square_tolerance, default 0.05,
                      longer than the short side), area (no aspect at all), any.
                      qa.size.allow_swap (default false): for aspect and for a landscape or portrait orientation,
                      true also accepts the swapped size (1024x1536 for 1536x1024); false fails it. Each purpose
                      declares it: the service may return the other orientation (e2e: 1024x1536 for 1536x1024).
                      aspect, orientation and area also need the short side >= min_side (default 256) and, with
                      min_pixels, width x height >= min_pixels (absolute). expect defaults to the requested size
                      (workflow.json, else spec params); "auto" = any (orientation auto with expect auto too).
                      The 9router image service ignores the requested size (e2e: 1672x941 returned for 1536x1024
                      and 1024x1024 requests), so the core purposes grade orientation or area plus these floors.
  png-alpha           qa.alpha: required (alpha channel and some transparent pixels), forbidden (fully opaque), any
  png-corners         qa.transparent_corners: the four corner pixels have alpha <= 8
  png-tileable        qa.tileable.max_seam_error: wrap-around edge difference minus the interior
                      neighbour difference (0..1 scale) must stay at or under the limit
  png-not-blank       qa.not_blank: luminance stddev >= min_stddev (0..255) and, with alpha, the share of
                      pixels with alpha > 8 >= min_coverage
  png-edge-fringe     only for qa.alpha required: imaging.edge_fringe (soft edge pixels, alpha 1-31 next to the
                      opaque body, whose RGB is far from the body colour, the speckled fringe of e2e barrel-prop-001;
                      body alpha 251-254 is noted, never graded). A required check for qa.alpha required (the last
                      one in runfiles.required_checks), so the gen-run quality plugin rejects a qa.json without the
                      row: FAIL makes the qa state FAIL like any other row; NOT_AVAILABLE (no alpha) comes with a
                      png-alpha FAIL anyway. assetgen.py defringe repairs it.
  purpose-qa          FAIL (one row for outputs/, nothing graded) when the purpose qa block is malformed
                      (runfiles.qa_errors; the same rules lint reports)
Style consistency rows (only for a spec with style_lock; consistency.check_all over the style data spec.style.data,
the purpose data, spec.style_lock.family and the run's copies of the selected anchors, references/anchor-<id>.png
of spec.style_lock.references; a missing or undecodable copy is left out, so tone is NOT_AVAILABLE without one):
  style-palette, style-tone, style-edges, style-canvas  PASS, WARN, FAIL or NOT_AVAILABLE (consistency.py). They are
                      never required checks (runfiles.required_checks is unchanged): WARN and NOT_AVAILABLE do not
                      change the qa state, a style FAIL row (the style field sets severity fail) makes it FAIL.
A spec without style_lock (resolved before the style lock) gets no style rows: its qa.json is what it was.
"""
import hashlib
import math
import os

import consistency
import imaging
import png
import runfiles

SAMPLES = 256  # rows/columns sampled per statistic; keeps the stdlib path fast on 1536x1024 outputs


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def steps(n):
    return range(0, n, max(1, n // SAMPLES))


def parse_size(text):
    try:
        w, h = (int(v) for v in str(text).lower().split("x"))
    except ValueError:
        return None
    return (w, h) if w > 0 and h > 0 else None


def orientation_of(w, h, tol):
    if max(w, h) <= min(w, h) * (1 + tol):
        return "square"
    return "landscape" if w > h else "portrait"


def floor_detail(img, cfg):
    """The absolute floors of aspect, orientation and area: short side >= min_side (default 256), with min_pixels
    width x height >= min_pixels. Returns (ok, detail parts)."""
    side, area = min(img.width, img.height), img.width * img.height
    min_side, min_pixels = cfg.get("min_side", 256), cfg.get("min_pixels")
    ok = side >= min_side and (min_pixels is None or area >= min_pixels)
    detail = ["short side %d (min %d)" % (side, min_side)]
    if min_pixels is not None:
        detail.append("area %d px (min %d)" % (area, min_pixels))
    return ok, detail


def check_size(img, cfg, requested):
    mode = cfg.get("mode", "any")
    got = "%dx%d" % (img.width, img.height)
    if mode == "area":
        ok, detail = floor_detail(img, cfg)
        return ("PASS" if ok else "FAIL"), ["%s, expected area (any aspect): %s" % (got, ", ".join(detail))]
    raw = cfg.get("expect", requested)
    expect = parse_size(raw)
    want_orient = cfg.get("orientation", "auto")
    if mode == "orientation" and want_orient != "auto":
        raw, expect = "%s orientation" % want_orient, (0, 0)  # the expected size plays no part
    if mode != "any" and expect is None and raw != "auto":
        return "FAIL", ["%s, expected size %r is not WIDTHxHEIGHT with positive dimensions" % (got, raw)]
    if mode == "any" or expect is None:
        return "PASS", ["%s (size mode any%s)" % (got, "" if mode == "any" else ", expected size auto")]
    ew, eh = expect
    swap = cfg.get("allow_swap") is True
    if mode == "exact":
        ok = (img.width, img.height) == expect
    elif mode == "min":
        ok = img.width >= ew and img.height >= eh
    elif mode == "orientation":
        tol = cfg.get("square_tolerance", 0.05)
        want = want_orient if want_orient != "auto" else orientation_of(ew, eh, tol)
        have = orientation_of(img.width, img.height, tol)
        ok, detail = floor_detail(img, cfg)
        swapped = {"landscape": "portrait", "portrait": "landscape"}.get(want) == have
        ok = ok and (have == want or (swapped and swap))
        source = "" if want_orient != "auto" else " (from %dx%d)" % (ew, eh)
        if swapped:
            source += ", swap %s (qa.size.allow_swap)" % ("accepted" if swap else "not accepted")
        return ("PASS" if ok else "FAIL"), ["%s is %s, expected orientation %s%s (square within %d%%): %s"
                                            % (got, have, want, source, round(tol * 100), ", ".join(detail))]
    else:
        tol, min_area = cfg.get("aspect_tolerance", 0.02), cfg.get("min_area")
        ratio, want = img.width / img.height, ew / eh
        ok, floors = floor_detail(img, cfg)
        fits = abs(ratio - want) <= tol * want or (swap and abs(1 / ratio - want) <= tol * want)
        ok = ok and fits and (min_area is None or img.width * img.height >= min_area * ew * eh)
        detail = ["aspect %.3f (expected %.3f +/- %d%%%s)" % (ratio, want, round(tol * 100), ", or swapped" if swap else "")]
        if min_area is not None:
            detail.append("area %d px (min %d%% of %d)" % (img.width * img.height, round(min_area * 100), ew * eh))
        detail += floors
        return ("PASS" if ok else "FAIL"), ["%s, expected %s %dx%d: %s" % (got, mode, ew, eh, ", ".join(detail))]
    return ("PASS" if ok else "FAIL"), ["%s, expected %s %dx%d" % (got, mode, ew, eh)]


def alpha_stats(img):
    total = transparent = 0
    for y in steps(img.height):
        for x in steps(img.width):
            total += 1
            if img.rgba[(y * img.width + x) * 4 + 3] <= 8:
                transparent += 1
    return transparent / total if total else 0.0


def check_alpha(img, mode):
    share = alpha_stats(img)
    opaque = all(b == 255 for b in img.rgba[3::4])
    if mode == "required":
        ok = img.has_alpha and share > 0
        return ("PASS" if ok else "FAIL"), ["alpha channel %s, %.1f%% transparent (alpha required)" % ("present" if img.has_alpha else "absent", share * 100)]
    if mode == "forbidden":
        return ("PASS" if opaque else "FAIL"), ["%s (alpha forbidden)" % ("fully opaque" if opaque else "has transparent pixels")]
    return "PASS", ["%.1f%% transparent (alpha any)" % (share * 100)]


def check_corners(img):
    w, h = img.width, img.height
    alphas = [img.pixel(x, y)[3] for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    ok = all(a <= 8 for a in alphas)
    return ("PASS" if ok else "FAIL"), ["corner alpha %s (must be <= 8)" % alphas]


def diff(a, b):
    return sum(abs(a[i] - b[i]) for i in range(3)) / (3 * 255.0)


def check_tileable(img, limit):
    w, h = img.width, img.height
    if w < 4 or h < 4:
        return "FAIL", ["image too small for a seam check"]
    ys, xs = list(steps(h)), list(steps(w))
    edge = [diff(img.pixel(0, y), img.pixel(w - 1, y)) for y in ys] + [diff(img.pixel(x, 0), img.pixel(x, h - 1)) for x in xs]
    inner = [diff(img.pixel(w // 2, y), img.pixel(w // 2 - 1, y)) for y in ys] + \
            [diff(img.pixel(x, h // 2), img.pixel(x, h // 2 - 1)) for x in xs]
    e, i = sum(edge) / len(edge), sum(inner) / len(inner)
    seam = max(0.0, e - i)
    return ("PASS" if seam <= limit else "FAIL"), ["seam error %.3f (edge %.3f, interior %.3f; limit %.3f)" % (seam, e, i, limit)]


def check_not_blank(img, cfg):
    lum, covered, total = [], 0, 0
    for y in steps(img.height):
        for x in steps(img.width):
            r, g, b, a = img.pixel(x, y)
            total += 1
            if a > 8:
                covered += 1
                lum.append(0.299 * r + 0.587 * g + 0.114 * b)
    mean = sum(lum) / len(lum) if lum else 0.0
    std = math.sqrt(sum((v - mean) ** 2 for v in lum) / len(lum)) if lum else 0.0
    cover = covered / total if total else 0.0
    min_std, min_cov = cfg.get("min_stddev", 2.0), cfg.get("min_coverage", 0.0)
    ok = std >= min_std and cover >= min_cov
    return ("PASS" if ok else "FAIL"), ["luminance stddev %.2f (min %.2f), coverage %.1f%% (min %.1f%%)" % (std, min_std, cover * 100, min_cov * 100)]


def style_anchors(run_dir, spec):
    """tone_stats of the decodable run copies of the selected anchors, in selection order."""
    stats = []
    for pick in runfiles.style_lock_references(spec):
        image = pick.get("image")
        path = os.path.join(run_dir, *image.split("/")) if isinstance(image, str) and image else None
        if not path or not os.path.isfile(path):
            continue
        try:
            tone = consistency.tone_stats(png.decode(path))
        except (png.Invalid, png.Unsupported, OSError):
            continue
        if tone is not None:
            stats.append(tone)
    return stats


def run_qa(run_dir, spec, requested_size):
    """(results, outputs) for every outputs/*.png of the run."""
    purpose = spec.get("purpose") if isinstance(spec, dict) else None
    data = purpose.get("data") if isinstance(purpose, dict) else None
    qa = data.get("qa", {}) if isinstance(data, dict) else None
    out_dir = os.path.join(run_dir, "outputs")
    files = sorted(n for n in os.listdir(out_dir) if n.lower().endswith(".png")) if os.path.isdir(out_dir) else []
    results, outputs = [], []
    if not files:
        return [{"output": "outputs/", "check": "png-present", "state": "FAIL", "reasons": ["no outputs/*.png in the run"]}], []
    malformed = runfiles.qa_errors(qa) if isinstance(data, dict) else ["spec.json purpose data must be an object"]
    if malformed:  # grade nothing against a qa block that cannot be read; the outputs are still hashed
        outputs = [{"path": "outputs/" + n, "sha256": sha256(os.path.join(out_dir, n))} for n in files]
        return [{"output": "outputs/", "check": "purpose-qa", "state": "FAIL",
                 "reasons": ["the purpose qa block is malformed: " + "; ".join(malformed)]}], outputs

    def add(rel, check, verdict):
        results.append({"output": rel, "check": check, "state": verdict[0], "reasons": verdict[1]})
    lock = spec.get("style_lock") if isinstance(spec.get("style_lock"), dict) else None
    style = spec.get("style") if isinstance(spec.get("style"), dict) else {}
    style_data = style.get("data") if isinstance(style.get("data"), dict) else {}
    anchors = style_anchors(run_dir, spec) if lock is not None else []
    for name in files:
        rel, path = "outputs/" + name, os.path.join(out_dir, name)
        item = {"path": rel, "sha256": sha256(path)}
        outputs.append(item)
        try:
            img = png.decode(path)
        except png.Unsupported as exc:
            add(rel, "png-valid", ("NOT_AVAILABLE", [str(exc)]))
            continue
        except png.Invalid as exc:
            add(rel, "png-valid", ("FAIL", [str(exc)]))
            continue
        item.update(width=img.width, height=img.height)
        add(rel, "png-valid", ("PASS", ["%dx%d, decoder %s" % (img.width, img.height, img.decoder)]))
        checks = {"png-size": lambda: check_size(img, qa.get("size", {"mode": "any"}), requested_size),
                  "png-alpha": lambda: check_alpha(img, qa.get("alpha", "any")),
                  "png-corners": lambda: check_corners(img),
                  "png-tileable": lambda: check_tileable(img, qa["tileable"].get("max_seam_error", 0.06)),
                  "png-not-blank": lambda: check_not_blank(img, qa["not_blank"]),
                  "png-edge-fringe": lambda: imaging.edge_fringe(img)}
        for name_ in runfiles.required_checks(qa)[1:]:  # png-valid is the first required check, added above
            add(rel, name_, checks[name_]())
        if lock is not None:
            family = lock.get("family") if isinstance(lock.get("family"), str) else None
            for row, state, details in consistency.check_all(img, style_data, data, family, anchors):
                add(rel, row, (state, details))
    return results, outputs


def is_style_row(row):
    return str(row.get("check", "")).startswith("style-")


def overall(results):
    """FAIL when any row is FAIL; NOT_AVAILABLE when a non-style row is; style WARN and NOT_AVAILABLE never count."""
    states = {r["state"] for r in results}
    if "FAIL" in states:
        return "FAIL"
    return "NOT_AVAILABLE" if any(r["state"] == "NOT_AVAILABLE" for r in results if not is_style_row(r)) else "PASS"
