"""Self-test of scripts/assetgen/imaging.py (edge fringe, defringe, composites) and of the qa.py size rules that
the e2e2 service sizes exercise (square tolerance, orientation swap).

Fixture PNGs are built in memory, written to a temp dir and decoded with png.decode (stdlib decoder unless
Pillow is present), so the checks run on the same png.Image objects qa.py sees. Prints 'ok N - <name>' or
'not ok N - <name>' per case and exits 1 when any case failed.
"""
import json
import math
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..", "..")
sys.path.insert(0, os.path.join(ROOT, "scripts", "assetgen"))

import imaging  # noqa: E402
import png  # noqa: E402
import qa  # noqa: E402

TMP = tempfile.mkdtemp(prefix="imaging-selftest-")
WOOD = (150, 90, 50)
SPECKLE = ((255, 220, 0), (255, 40, 0))  # the yellow and red of the barrel-prop-001 fringe
SIZE, CENTER, BODY_R, EDGE_R = 64, 31.5, 20.0, 23.0
failed = []
count = 0


def check(name, cond, detail=""):
    global count
    count += 1
    if cond:
        print("ok %d - %s" % (count, name))
    else:
        failed.append(name)
        print("not ok %d - %s%s" % (count, name, (": " + str(detail)) if detail else ""))


def write(name, width, height, paint, alpha=True):
    rgba = bytearray()
    for y in range(height):
        for x in range(width):
            px = paint(x, y)
            rgba += bytes(px if len(px) == 4 else px + (255,))
    path = os.path.join(TMP, name + ".png")
    with open(path, "wb") as f:
        f.write(png.encode(width, height, bytes(rgba), alpha=alpha))
    return path


def decode_bytes(name, data):
    path = os.path.join(TMP, name + ".png")
    with open(path, "wb") as f:
        f.write(data)
    return png.decode(path)


def edge_alpha(x, y):
    """Alpha 8-31 across the soft band around the disc (the body is alpha 254, the service's body alpha)."""
    return 8 + (x * 7 + y * 3) % 24


def sprite(edge_colour, name, body_alpha=254):
    def paint(x, y):
        r = math.hypot(x - CENTER, y - CENTER)
        if r <= BODY_R:
            return WOOD + (body_alpha,)
        if r <= EDGE_R:
            return edge_colour(x, y) + (edge_alpha(x, y),)
        return (0, 0, 0, 0)
    return png.decode(write(name, SIZE, SIZE, paint))


def premultiplied_round_trip(x, y):
    """The body colour stored premultiplied at the pixel's alpha and read back straight: the rounding a clean edge
    gets from a premultiplied pipeline."""
    a = edge_alpha(x, y)
    return tuple(min(255, round(round(c * a / 255) * 255 / a)) for c in WOOD)


fringe = sprite(lambda x, y: SPECKLE[(x + y) % 2], "fringe")
clean = sprite(lambda x, y: WOOD, "clean")
rounded = sprite(premultiplied_round_trip, "rounded")

state, details = imaging.edge_fringe(fringe)
check("speckled low-alpha fringe FAILs png-edge-fringe", state == "FAIL", details)
stats = imaging.edge_fringe_stats(fringe)
check("fringe stats count soft edge pixels and off-colour ones", stats["soft_edge"] > 50 and stats["share"] > 0.5, stats)
check("FAIL detail names the repair", any("defringe" in d for d in details), details)
check("clean anti-aliased edge (soft pixels carry the body colour) PASSes", imaging.edge_fringe(clean)[0] == "PASS",
      imaging.edge_fringe(clean))
check("clean edge after a premultiplied round trip PASSes", imaging.edge_fringe(rounded)[0] == "PASS",
      imaging.edge_fringe(rounded))

opaque_rgb = png.decode(write("opaque-rgb", 16, 16, lambda x, y: WOOD, alpha=False))
opaque_rgba = png.decode(write("opaque-rgba", 16, 16, lambda x, y: WOOD + (255,)))
check("opaque RGB image is NOT_AVAILABLE", imaging.edge_fringe(opaque_rgb)[0] == "NOT_AVAILABLE")
check("RGBA image with every alpha 255 is NOT_AVAILABLE", imaging.edge_fringe(opaque_rgba)[0] == "NOT_AVAILABLE")
hard = png.decode(write("hard", 16, 16, lambda x, y: WOOD + (255,) if 4 <= x < 12 else (0, 0, 0, 0)))
check("hard edge without soft pixels PASSes", imaging.edge_fringe(hard)[0] == "PASS", imaging.edge_fringe(hard))

body = [d for d in imaging.edge_fringe(fringe)[1] if d.startswith("body:")]
n_body = sum(1 for a in fringe.rgba[3::4] if a == 254)
check("body alpha 251-254 counted and noted (never a FAIL by itself)",
      body and body[0].startswith("body: %d of %d" % (n_body, n_body)) and imaging.edge_fringe(clean)[0] == "PASS", body)

data, dstats = imaging.defringe(fringe)
fixed = decode_bytes("fringe-defringed", data)
check("defringe output PASSes png-edge-fringe", imaging.edge_fringe(fixed)[0] == "PASS", imaging.edge_fringe(fixed))
check("defringe keeps every alpha", fixed.rgba[3::4] == fringe.rgba[3::4])
same = all(fixed.rgba[i:i + 4] == fringe.rgba[i:i + 4]
           for i in range(0, len(fringe.rgba), 4) if fringe.rgba[i + 3] >= imaging.OPAQUE)
check("defringe keeps opaque pixels byte-identical", same)
check("defringe recolours every soft pixel next to the body", dstats["recoloured"] == dstats["soft"]
      and dstats["unreached"] == 0 and dstats["floored"] == 0, dstats)
soft = [fixed.rgba[i:i + 3] for i in range(0, len(fixed.rgba), 4) if 0 < fixed.rgba[i + 3] < imaging.OPAQUE]
check("defringed soft pixels take the body colour", soft and all(tuple(px) == WOOD for px in soft), soft[:3])
check("defringe is deterministic", imaging.defringe(fringe) == (data, dstats))

data16, fstats = imaging.defringe(fringe, alpha_floor=16)
floored = decode_bytes("fringe-floor16", data16)
expect_alpha = bytes(0 if a < 16 else a for a in fringe.rgba[3::4])
check("alpha_floor 16 sets alpha below 16 to 0 and keeps the rest", floored.rgba[3::4] == expect_alpha
      and fstats["floored"] == sum(1 for a in fringe.rgba[3::4] if 0 < a < 16) > 0, fstats)
for bad in (-1, imaging.OPAQUE + 1, 1.5, True):
    try:
        imaging.defringe(fringe, alpha_floor=bad)
        check("alpha_floor %r is refused" % (bad,), False)
    except ValueError:
        check("alpha_floor %r is refused" % (bad,), True)

for bg in imaging.BACKGROUNDS:
    comp = decode_bytes("composite-" + bg, imaging.composite(fringe, bg))
    top_left = imaging.CHECKER[0] if bg == "checker" else imaging.SOLID[bg]
    check("composite %s: same size, opaque, transparent corner equals the background" % bg,
          (comp.width, comp.height) == (SIZE, SIZE) and min(comp.rgba[3::4]) == 255
          and tuple(comp.pixel(0, 0)[:3]) == top_left, (comp.width, comp.height, tuple(comp.pixel(0, 0))))
comp = decode_bytes("composite-checker-2", imaging.composite(fringe, "checker"))
check("checker composite alternates every %d px" % imaging.CHECKER_SIZE,
      tuple(comp.pixel(imaging.CHECKER_SIZE, 0)[:3]) == imaging.CHECKER[1]
      and tuple(comp.pixel(0, imaging.CHECKER_SIZE)[:3]) == imaging.CHECKER[1]
      and tuple(comp.pixel(2 * imaging.CHECKER_SIZE, 0)[:3]) == imaging.CHECKER[0])
dark = decode_bytes("composite-dark-2", imaging.composite(fringe, "dark"))
cx = int(CENTER)
check("composite blends the body: alpha 254 over dark", tuple(dark.pixel(cx, cx)[:3])
      == tuple((c * 254 + 0x20 + 127) // 255 for c in WOOD), tuple(dark.pixel(cx, cx)))
custom = decode_bytes("composite-custom", imaging.composite(fringe, (0, 255, 0)))
check("composite over an (r, g, b) background", tuple(custom.pixel(0, 0)[:3]) == (0, 255, 0))
try:
    imaging.composite(fringe, "purple")
    check("unknown background is refused", False)
except ValueError:
    check("unknown background is refused", True)


class Size:
    def __init__(self, w, h):
        self.width, self.height = w, h


def purpose_size(name):
    with open(os.path.join(ROOT, "templates", "assetgen", "purposes", name + ".json"), encoding="utf-8") as f:
        return json.load(f)["qa"]["size"]


def size_case(name, purpose_or_cfg, w, h, requested, want):
    cfg = purpose_size(purpose_or_cfg) if isinstance(purpose_or_cfg, str) else purpose_or_cfg
    state, detail = qa.check_size(Size(w, h), cfg, requested)
    check(name, state == want, detail)


size_case("sprite-2d: real 1322x1190 (11% off square) PASSes", "sprite-2d", 1322, 1190, "1024x1024", "PASS")
size_case("icon: real 1322x1190 PASSes", "icon", 1322, 1190, "1024x1024", "PASS")
size_case("icon: real 1254x1254 still PASSes", "icon", 1254, 1254, "1024x1024", "PASS")
size_case("sprite-2d: 1672x941 still FAILs square", "sprite-2d", 1672, 941, "1024x1024", "FAIL")
size_case("icon: 384x256 still FAILs square", "icon", 384, 256, "1024x1024", "FAIL")
size_case("ref-3d-turnaround: 1672x941 still PASSes landscape", "ref-3d-turnaround", 1672, 941, "1536x1024", "PASS")
size_case("ref-3d-turnaround (allow_swap false): 1024x1536 FAILs", "ref-3d-turnaround", 1024, 1536, "1536x1024", "FAIL")
swap = {"mode": "orientation", "expect": "1536x1024", "min_side": 512}
size_case("orientation from 1536x1024, allow_swap absent: 1024x1536 FAILs", dict(swap), 1024, 1536, "auto", "FAIL")
size_case("orientation from 1536x1024, allow_swap false: 1024x1536 FAILs", dict(swap, allow_swap=False), 1024, 1536,
          "auto", "FAIL")
size_case("orientation from 1536x1024, allow_swap true: 1024x1536 PASSes", dict(swap, allow_swap=True), 1024, 1536,
          "auto", "PASS")
size_case("orientation from 1536x1024, allow_swap true: 1672x941 PASSes", dict(swap, allow_swap=True), 1672, 941,
          "auto", "PASS")
state, detail = qa.check_size(Size(1024, 1536), dict(swap, allow_swap=True), "auto")
check("swap detail names qa.size.allow_swap", "swap accepted (qa.size.allow_swap)" in detail[0], detail)
aspect = {"mode": "aspect", "expect": "1536x1024", "min_side": 512}
size_case("aspect 1536x1024, allow_swap false: 1024x1536 FAILs", dict(aspect), 1024, 1536, "auto", "FAIL")
size_case("aspect 1536x1024, allow_swap true: 1024x1536 PASSes", dict(aspect, allow_swap=True), 1024, 1536, "auto",
          "PASS")
size_case("allow_swap is ignored for square", dict(purpose_size("sprite-2d"), allow_swap=True), 1672, 941,
          "1024x1024", "FAIL")


def qa_run(name, purpose, src):
    run = os.path.join(TMP, "run-" + name)
    os.makedirs(os.path.join(run, "outputs"))
    shutil.copy(src, os.path.join(run, "outputs", "out.png"))
    with open(os.path.join(ROOT, "templates", "assetgen", "purposes", purpose + ".json"), encoding="utf-8") as f:
        spec = {"purpose": {"id": purpose, "data": json.load(f)}}
    results, _ = qa.run_qa(run, spec, "1024x1024")
    return {r["check"]: r["state"] for r in results}, qa.overall(results)


rows, state = qa_run("fringe", "sprite-2d", os.path.join(TMP, "fringe.png"))
check("qa: sprite-2d grades png-edge-fringe FAIL and the qa state FAIL", rows.get("png-edge-fringe") == "FAIL"
      and state == "FAIL", rows)
rows, _ = qa_run("clean", "icon", os.path.join(TMP, "clean.png"))
check("qa: icon grades a clean edge png-edge-fringe PASS", rows.get("png-edge-fringe") == "PASS", rows)
rows, _ = qa_run("concept", "concept-2d", os.path.join(TMP, "fringe.png"))
check("qa: concept-2d (alpha any) has no png-edge-fringe row", "png-edge-fringe" not in rows, rows)

shutil.rmtree(TMP, ignore_errors=True)
print("%d passed, %d failed" % (count - len(failed), len(failed)))
sys.exit(1 if failed else 0)
