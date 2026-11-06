"""Deterministic image QA of a run's outputs/*.png against the purpose's qa expectations.

Per output PNG (results keyed by output path, rpg-factory.validation/1 states):
  png-valid           decodes (Pillow when present, else the stdlib decoder; NOT_AVAILABLE when neither can)
  png-size            qa.size.mode: exact (= expect), min (width and height >= expect), aspect (ratio within
                      aspect_tolerance, default 0.02, and the short side >= min_side, default 256), any.
                      expect defaults to the requested size (workflow.json, else spec params); "auto" = any.
                      The 9router gateway may return another size than requested, so exact is opt-in.
  png-alpha           qa.alpha: required (alpha channel and some transparent pixels), forbidden (fully opaque), any
  png-corners         qa.transparent_corners: the four corner pixels have alpha <= 8
  png-tileable        qa.tileable.max_seam_error: wrap-around edge difference minus the interior
                      neighbour difference (0..1 scale) must stay at or under the limit
  png-not-blank       qa.not_blank: luminance stddev >= min_stddev (0..255) and, with alpha, the share of
                      pixels with alpha > 8 >= min_coverage
"""
import hashlib
import math
import os

import png

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
        w, h = str(text).lower().split("x")
        return int(w), int(h)
    except ValueError:
        return None


def check_size(img, cfg, requested):
    mode = cfg.get("mode", "any")
    expect = parse_size(cfg.get("expect", requested))
    got = "%dx%d" % (img.width, img.height)
    if mode == "any" or expect is None:
        return "PASS", ["%s (size mode any%s)" % (got, "" if mode == "any" else ", expected size auto")]
    ew, eh = expect
    if mode == "exact":
        ok = (img.width, img.height) == expect
    elif mode == "min":
        ok = img.width >= ew and img.height >= eh
    else:
        tol, min_side = cfg.get("aspect_tolerance", 0.02), cfg.get("min_side", 256)
        ok = abs(img.width / img.height - ew / eh) <= tol * (ew / eh) and min(img.width, img.height) >= min_side
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


def run_qa(run_dir, spec, requested_size):
    """(results, outputs) for every outputs/*.png of the run."""
    qa = spec["purpose"]["data"].get("qa", {})
    out_dir = os.path.join(run_dir, "outputs")
    files = sorted(n for n in os.listdir(out_dir) if n.lower().endswith(".png")) if os.path.isdir(out_dir) else []
    results, outputs = [], []
    if not files:
        return [{"output": "outputs/", "check": "png-present", "state": "FAIL", "reasons": ["no outputs/*.png in the run"]}], []

    def add(rel, check, verdict):
        results.append({"output": rel, "check": check, "state": verdict[0], "reasons": verdict[1]})
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
        add(rel, "png-size", check_size(img, qa.get("size", {"mode": "any"}), requested_size))
        add(rel, "png-alpha", check_alpha(img, qa.get("alpha", "any")))
        if qa.get("transparent_corners"):
            add(rel, "png-corners", check_corners(img))
        if qa.get("tileable"):
            add(rel, "png-tileable", check_tileable(img, qa["tileable"].get("max_seam_error", 0.06)))
        if qa.get("not_blank") is not None:
            add(rel, "png-not-blank", check_not_blank(img, qa["not_blank"]))
    return results, outputs


def overall(results):
    states = {r["state"] for r in results}
    return "FAIL" if "FAIL" in states else ("NOT_AVAILABLE" if "NOT_AVAILABLE" in states else "PASS")
