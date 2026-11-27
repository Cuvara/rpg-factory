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
                      For qa.size.fit pad, grades the file finalize fitted; fit is not a QA row and QA never pads.
  png-alpha           qa.alpha: required (alpha channel and some transparent pixels), forbidden (fully opaque), any
  png-corners         qa.transparent_corners: the four corner pixels have alpha <= 8
  png-tileable        qa.tileable.max_seam_error: wrap-around edge difference minus the interior
                      neighbour difference (0..1 scale) must stay at or under the limit. qa.tileable.axis: both
                      (default; the left/right and the top/bottom seam), x (only the left/right seam, pixel(0,y) against
                      pixel(w-1,y), interior at x = w//2; a trail that scrolls along x) or y (only top/bottom). The
                      detail names the axis for x and y; the detail for both is unchanged.
  png-flipbook-grid   qa.flipbook_grid {columns, rows, max_gutter_luminance 32, min_cell_stddev 2.0}: the image is split
                      into columns x rows cells by float boundaries (the image service ignores the requested size, so
                      no divisibility is needed). The gutter is a band of max(1, round(2% of the cell side)) px around
                      every internal cell boundary. PASS when the mean luminance of the gutter pixels is at most
                      max_gutter_luminance and every cell interior (gutter excluded) has a luminance stddev of at least
                      min_cell_stddev; the detail names a bright gutter and the blank cells as (column,row), 1-based.
  png-black-background  qa.black_background {max_luminance 16, border 0.03, edges all four}: each listed edge is graded
                      on its own: the mean luminance of its border band (border x the short side, at least 1 px) must
                      be at most max_luminance, so one bright edge fails even when the pooled mean is low. The detail
                      gives the mean per edge and, on FAIL, names the edges over the limit. A pure-black opaque
                      background.
  png-not-blank       qa.not_blank: luminance stddev >= min_stddev (0..255) and, with alpha, the share of
                      pixels with alpha > 8 >= min_coverage
  png-edge-fringe     only for qa.alpha required: imaging.edge_fringe (soft edge pixels, alpha 1-31 next to the
                      opaque body, whose RGB is far from the body colour, the speckled fringe of e2e barrel-prop-001;
                      body alpha 251-254 is noted, never graded). A required check for qa.alpha required (the last
                      one in runfiles.required_checks), so the gen-run quality plugin rejects a qa.json without the
                      row: FAIL makes the qa state FAIL like any other row; NOT_AVAILABLE (no alpha) comes with a
                      png-alpha FAIL anyway. assetgen.py defringe repairs it.
  png-pixel-grid      when pixelgrid.json exists: grades recorded pixels and palette limit
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
import json
import math
import os

import consistency
import imaging
import png
import pixelgrid
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


def check_tileable(img, limit, axis="both"):
    w, h = img.width, img.height
    if w < 4 or h < 4:
        return "FAIL", ["image too small for a seam check"]
    ys, xs = list(steps(h)), list(steps(w))
    edge, inner = [], []
    if axis in ("both", "x"):  # the left/right wrap-around seam
        edge += [diff(img.pixel(0, y), img.pixel(w - 1, y)) for y in ys]
        inner += [diff(img.pixel(w // 2, y), img.pixel(w // 2 - 1, y)) for y in ys]
    if axis in ("both", "y"):  # the top/bottom wrap-around seam
        edge += [diff(img.pixel(x, 0), img.pixel(x, h - 1)) for x in xs]
        inner += [diff(img.pixel(x, h // 2), img.pixel(x, h // 2 - 1)) for x in xs]
    e, i = sum(edge) / len(edge), sum(inner) / len(inner)
    seam = max(0.0, e - i)
    where = "" if axis == "both" else " on the %s axis" % axis
    return ("PASS" if seam <= limit else "FAIL"), ["seam error %.3f%s (edge %.3f, interior %.3f; limit %.3f)" % (seam, where, e, i, limit)]


def luminance(px):
    return 0.299 * px[0] + 0.587 * px[1] + 0.114 * px[2]


def grid_bounds(n, size):
    """The n + 1 float cell boundaries of an axis of `size` px, 0 and size included."""
    return [i * size / n for i in range(n + 1)]


def gutter_bands(bounds, side):
    """[lo, hi) pixel bands, max(1, round(2% of the cell side)) px wide, centred on each internal boundary."""
    width = max(1, round(0.02 * side))
    bands = []
    for b in bounds[1:-1]:
        lo = int(round(b - width / 2.0))
        bands.append((lo, lo + width))
    return bands


def in_bands(v, bands):
    return any(lo <= v < hi for lo, hi in bands)


def check_flipbook_grid(img, cfg):
    cols, rows = cfg["columns"], cfg["rows"]
    max_gutter = cfg.get("max_gutter_luminance", 32)
    min_std = cfg.get("min_cell_stddev", 2.0)
    w, h = img.width, img.height
    if w < cols * 4 or h < rows * 4:
        return "FAIL", ["%dx%d is too small for a %dx%d grid" % (w, h, cols, rows)]
    xb, yb = grid_bounds(cols, w), grid_bounds(rows, h)
    xbands, ybands = gutter_bands(xb, w / cols), gutter_bands(yb, h / rows)
    ys, xs = list(steps(h)), list(steps(w))
    gutter, cells = [], {}
    for lo, hi in xbands:  # every gutter column (a band is only a few px wide) at the sampled rows
        for x in range(max(0, lo), min(w, hi)):
            gutter += [luminance(img.pixel(x, y)) for y in ys]
    for lo, hi in ybands:  # every gutter row at the sampled columns outside the vertical bands
        for y in range(max(0, lo), min(h, hi)):
            gutter += [luminance(img.pixel(x, y)) for x in xs if not in_bands(x, xbands)]
    for y in ys:
        if in_bands(y, ybands):
            continue
        row = sum(1 for b in yb[1:-1] if b <= y)
        for x in xs:
            if in_bands(x, xbands):
                continue
            col = sum(1 for b in xb[1:-1] if b <= x)
            cells.setdefault((col, row), []).append(luminance(img.pixel(x, y)))
    gutter_mean = sum(gutter) / len(gutter) if gutter else 0.0
    blank = []
    for row in range(rows):
        for col in range(cols):
            lum = cells.get((col, row), [])
            mean = sum(lum) / len(lum) if lum else 0.0
            std = math.sqrt(sum((v - mean) ** 2 for v in lum) / len(lum)) if lum else 0.0
            if std < min_std:
                blank.append("(%d,%d)" % (col + 1, row + 1))
    ok = gutter_mean <= max_gutter and not blank
    detail = ["%dx%d grid, gutter luminance mean %.1f (max %.1f)" % (cols, rows, gutter_mean, max_gutter)]
    detail.append("blank cells (column,row) %s (stddev below %.2f)" % (" ".join(blank), min_std) if blank
                  else "no blank cell (stddev at least %.2f)" % min_std)
    return ("PASS" if ok else "FAIL"), ["; ".join(detail)]


def check_black_background(img, cfg):
    max_lum = cfg.get("max_luminance", 16)
    border = cfg.get("border", 0.03)
    edges = cfg.get("edges", ["top", "bottom", "left", "right"])
    w, h = img.width, img.height
    band = max(1, round(border * min(w, h)))
    ys, xs = list(steps(h)), list(steps(w))
    sampled = {"top": [(x, y) for y in range(min(band, h)) for x in xs],
               "bottom": [(x, y) for y in range(max(0, h - band), h) for x in xs],
               "left": [(x, y) for x in range(min(band, w)) for y in ys],
               "right": [(x, y) for x in range(max(0, w - band), w) for y in ys]}
    parts, over = [], []
    for edge in edges:
        lum = [luminance(img.pixel(x, y)) for x, y in sampled[edge]]
        mean = sum(lum) / len(lum) if lum else 0.0
        parts.append("%s %.1f" % (edge, mean))
        if mean > max_lum:
            over.append(edge)
    detail = "border luminance mean per edge (max %.1f) over a %d px band: %s" % (max_lum, band, ", ".join(parts))
    if over:
        detail += "; edges over the limit: %s" % ", ".join(over)
    return ("FAIL" if over else "PASS"), [detail]


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
    pixel_path = os.path.join(run_dir, "pixelgrid.json")
    pixel_present = os.path.exists(pixel_path)
    pixel_record = None
    pixel_rows = {}
    if pixel_present:
        try:
            with open(pixel_path, encoding="utf-8") as f:
                pixel_record = json.load(f)
            if not isinstance(pixel_record, dict):
                raise ValueError("record is not an object")
            rows = pixel_record.get("outputs", [])
            if isinstance(rows, list):
                pixel_rows = {row.get("output"): row for row in rows if isinstance(row, dict)}
        except (OSError, ValueError, UnicodeError) as exc:
            results.append({"output": "pixelgrid.json", "check": "png-pixel-grid", "state": "FAIL",
                            "reasons": ["cannot read pixelgrid.json: %s" % exc]})
    if not files:
        return results + [{"output": "outputs/", "check": "png-present", "state": "FAIL", "reasons": ["no outputs/*.png in the run"]}], []
    malformed = runfiles.qa_errors(qa) if isinstance(data, dict) else ["spec.json purpose data must be an object"]
    if malformed:  # grade nothing against a qa block that cannot be read; the outputs are still hashed
        outputs = [{"path": "outputs/" + n, "sha256": sha256(os.path.join(out_dir, n))} for n in files]
        return results + [{"output": "outputs/", "check": "purpose-qa", "state": "FAIL",
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
        pixel_row = pixel_rows.get(rel, {})
        pixels_hash = hashlib.sha256(b"%dx%d:" % (img.width, img.height) + img.rgba).hexdigest()
        matching = (pixel_row.get("state") == "pixelated" and pixel_row.get("after_pixels_sha256") == pixels_hash)
        source_size = parse_size(pixel_row.get("source_size")) if matching else None
        def size_check():
            if source_size is None:
                return check_size(img, qa.get("size", {"mode": "any"}), requested_size)
            size_img = type("SourceSize", (), {"width": source_size[0], "height": source_size[1]})()
            state, reasons = check_size(size_img, qa.get("size", {"mode": "any"}), requested_size)
            suffix = " (pixel grid %dx%d, graded at source size %dx%d from pixelgrid.json)" % (
                img.width, img.height, source_size[0], source_size[1])
            return state, [reason + suffix for reason in reasons]
        checks = {"png-size": size_check,
                  "png-alpha": lambda: check_alpha(img, qa.get("alpha", "any")),
                  "png-corners": lambda: check_corners(img),
                  "png-tileable": lambda: check_tileable(img, qa["tileable"].get("max_seam_error", 0.06),
                                                         qa["tileable"].get("axis", "both")),
                  "png-flipbook-grid": lambda: check_flipbook_grid(img, qa["flipbook_grid"]),
                  "png-black-background": lambda: check_black_background(img, qa["black_background"]),
                  "png-not-blank": lambda: check_not_blank(img, qa["not_blank"]),
                  "png-edge-fringe": lambda: imaging.edge_fringe(img)}
        for name_ in runfiles.required_checks(qa)[1:]:  # png-valid is the first required check, added above
            add(rel, name_, checks[name_]())
        if pixel_present and pixel_record is not None:
            if pixel_row.get("state") == "skipped":
                verdict = ("WARN", ["pixel grid skipped: %s" % pixel_row.get("reason", "no reason recorded")])
            elif not pixel_row:
                verdict = ("FAIL", ["output missing from pixelgrid.json"])
            elif not matching:
                verdict = ("FAIL", ["pixels do not match pixelgrid.json"])
            else:
                params = pixel_record.get("params") if isinstance(pixel_record.get("params"), dict) else {}
                colors = pixelgrid.count_colors(img.rgba)
                palette = params.get("palette_colors")
                limit = len(palette) if isinstance(palette, list) else params.get("max_colors")
                valid_limit = isinstance(limit, int) and not isinstance(limit, bool) and limit > 0
                verdict = ("PASS" if valid_limit and colors <= limit else "FAIL", [
                    "scale %s, grid %s, source %s, %d colors (limit %s)" % (
                        pixel_row.get("scale"), pixel_row.get("size"), pixel_row.get("source_size"), colors, limit)])
            add(rel, "png-pixel-grid", verdict)
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
