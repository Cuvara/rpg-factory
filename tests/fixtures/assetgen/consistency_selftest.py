"""Self-test of scripts/assetgen/consistency.py: every state of every style check on fixture PNGs.

Fixture PNGs are built in memory, written to a temp dir and decoded with png.decode (stdlib decoder unless
Pillow is present), so the checks run on the same png.Image objects qa.py sees. Prints 'ok N - <name>' per
case and exits 1 on the first failure summary.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "scripts", "assetgen"))

import consistency  # noqa: E402
import png  # noqa: E402

TMP = tempfile.mkdtemp(prefix="consistency-selftest-")
RED, GREEN, BLUE, BLACK, WHITE = (200, 40, 40), (40, 160, 60), (40, 60, 200), (10, 10, 10), (250, 250, 250)
MAGENTA, GREY = (230, 0, 230), (128, 128, 128)
CLEAR = (0, 0, 0, 0)


def image(width, height, paint, name):
    """paint(x, y) -> (r, g, b) or (r, g, b, a); encoded to PNG, written and decoded back."""
    rgba = bytearray()
    for y in range(height):
        for x in range(width):
            px = paint(x, y)
            rgba += bytes(px if len(px) == 4 else px + (255,))
    path = os.path.join(TMP, name + ".png")
    with open(path, "wb") as f:
        f.write(png.encode(width, height, bytes(rgba)))
    return png.decode(path)


def solid(color, width=32, height=32, name=None):
    return image(width, height, lambda x, y: color, name or "solid-%d-%d-%d-%dx%d" % (color + (width, height)))


def stripes(colors, width=32, height=32, name="stripes"):
    return image(width, height, lambda x, y: colors[(x * len(colors)) // width], name)


def outlined(fill, line, name):
    """A filled square with a 2 px line around it on a transparent background."""
    def paint(x, y):
        if x < 4 or y < 4 or x >= 28 or y >= 28:
            return CLEAR
        if x < 6 or y < 6 or x >= 26 or y >= 26:
            return line
        return fill
    return image(32, 32, paint, name)


PALETTE = {"text": "warm red, green and blue", "colors": [{"hex": "#c82828", "role": "primary"},
                                                          {"hex": "#28a03c", "role": "accent"},
                                                          {"hex": "#283cc8", "role": "shadow"}]}
OUTLINES = {"qa": {"outlines": True}}
EDGES = {"outline": {"text": "dark outlines", "edge_darkness": {"max_luminance": 80, "min_ratio": 0.6}}}
CANVAS = {"canvas": {"characters": {"aspect": "1:2", "min_side": 32}, "props": {"aspect": "1:1", "severity": "fail"}}}

CASES = []


def case(name):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


def expect(result, state, contains=None):
    got, details = result
    assert got == state, "state %s, expected %s: %s" % (got, state, details)
    assert isinstance(details, list) and details and all(isinstance(d, str) for d in details), details
    if contains:
        assert any(contains in d for d in details), "%r not in %s" % (contains, details)


# palette
@case("palette PASS on-palette image")
def _():
    expect(consistency.check_palette(stripes([RED, GREEN, BLUE]), {"palette": PALETTE}), "PASS", "100.0%")


@case("palette WARN off-palette image (default severity)")
def _():
    expect(consistency.check_palette(solid(MAGENTA), {"palette": PALETTE}), "WARN", "0.0%")


@case("palette FAIL off-palette image with severity fail")
def _():
    cfg = dict(PALETTE, severity="fail")
    expect(consistency.check_palette(stripes([RED, MAGENTA, MAGENTA]), {"palette": cfg}), "FAIL")


@case("palette min_share and max_distance thresholds")
def _():
    img = stripes([RED, RED, MAGENTA, MAGENTA])
    expect(consistency.check_palette(img, {"palette": dict(PALETTE, min_share=0.5)}), "PASS", "50.0%")
    expect(consistency.check_palette(img, {"palette": dict(PALETTE, min_share=0.51)}), "WARN")
    near = solid((215, 40, 40))  # 15 away from the red
    expect(consistency.check_palette(near, {"palette": dict(PALETTE, max_distance=20)}), "PASS")
    expect(consistency.check_palette(near, {"palette": dict(PALETTE, max_distance=10)}), "WARN")


@case("palette ignores transparent pixels")
def _():
    img = image(32, 32, lambda x, y: RED + (255,) if x < 8 else MAGENTA + (0,), "palette-alpha")
    expect(consistency.check_palette(img, {"palette": PALETTE}), "PASS", "100.0%")


@case("palette NOT_AVAILABLE without structured colours")
def _():
    img = solid(RED)
    expect(consistency.check_palette(img, {}), "NOT_AVAILABLE")
    expect(consistency.check_palette(img, None), "NOT_AVAILABLE")
    expect(consistency.check_palette(img, {"palette": "warm reds"}), "NOT_AVAILABLE")
    expect(consistency.check_palette(img, {"palette": {"text": "warm reds"}}), "NOT_AVAILABLE")


@case("palette NOT_AVAILABLE on a fully transparent image")
def _():
    expect(consistency.check_palette(solid(CLEAR, name="clear"), {"palette": PALETTE}), "NOT_AVAILABLE")


@case("palette FAIL on malformed data")
def _():
    img = solid(RED)
    for bad in ({"colors": []}, {"colors": [{"hex": "red"}]}, {"colors": "#c82828"},
                dict(PALETTE, max_distance=500), dict(PALETTE, min_share=2), dict(PALETTE, min_share=True)):
        expect(consistency.check_palette(img, {"palette": bad}), "FAIL", "malformed")


# tone
DARK, MID, BRIGHT = solid((60, 60, 60)), solid((120, 100, 90)), solid((240, 240, 240))
TONE = {"tone": {"tolerance": 0.05}}


@case("tone stats: luminance and HSV saturation in 0..1")
def _():
    lum, sat = consistency.tone_stats(solid((200, 100, 0)))
    assert abs(lum - (0.299 * 200 + 0.587 * 100) / 255) < 1e-9, lum
    assert abs(sat - 1.0) < 1e-9, sat
    lum, sat = consistency.tone_stats(solid(BLACK))
    assert abs(lum - 10 / 255) < 1e-9 and sat == 0.0, (lum, sat)
    assert consistency.tone_stats(solid(CLEAR, name="clear")) is None


@case("tone PASS inside the anchors' range")
def _():
    expect(consistency.check_tone(solid((90, 80, 75)), TONE, [DARK, MID]), "PASS", "inside")


@case("tone PASS with precomputed anchor stats")
def _():
    stats = [consistency.tone_stats(DARK), consistency.tone_stats(MID)]
    expect(consistency.check_tone(solid((90, 80, 75)), TONE, stats), "PASS")


@case("tone WARN outside the range (default severity)")
def _():
    expect(consistency.check_tone(BRIGHT, TONE, [DARK, MID]), "WARN", "outside")


@case("tone WARN on saturation alone")
def _():
    vivid = solid((120, 40, 0))  # luminance inside, saturation 1.0 far above the anchors
    status, details = consistency.check_tone(vivid, TONE, [DARK, MID])
    assert status == "WARN" and "inside" in details[0] and "outside" in details[1], details


@case("tone FAIL outside the range with severity fail")
def _():
    expect(consistency.check_tone(BRIGHT, {"tone": {"severity": "fail"}}, [DARK]), "FAIL")


@case("tone tolerance widens the range")
def _():
    expect(consistency.check_tone(solid((75, 75, 75)), {"tone": {"tolerance": 0.1}}, [DARK]), "PASS")
    expect(consistency.check_tone(solid((75, 75, 75)), {"tone": {"tolerance": 0.0}}, [DARK]), "WARN")


@case("tone NOT_AVAILABLE without tone settings, anchors or opaque pixels")
def _():
    expect(consistency.check_tone(MID, {}, [DARK]), "NOT_AVAILABLE", "no tone")
    expect(consistency.check_tone(MID, TONE, []), "NOT_AVAILABLE", "no anchors")
    expect(consistency.check_tone(MID, TONE, None), "NOT_AVAILABLE", "no anchors")
    expect(consistency.check_tone(MID, TONE, [solid(CLEAR, name="clear")]), "NOT_AVAILABLE", "no anchors")
    expect(consistency.check_tone(solid(CLEAR, name="clear"), TONE, [DARK]), "NOT_AVAILABLE", "no opaque")


@case("tone FAIL on malformed data")
def _():
    expect(consistency.check_tone(MID, {"tone": {"tolerance": -1}}, [DARK]), "FAIL", "malformed")


# edges
LINED = outlined(RED, BLACK, "outlined")
UNLINED = outlined(RED, WHITE, "outline-bright")  # strong edges, but the dark side is the red fill (lum ~84)
FLAT = solid(RED, name="flat-red")


@case("edges PASS on an outlined image")
def _():
    expect(consistency.check_edges(LINED, EDGES, OUTLINES), "PASS", "100.0%")


@case("edges WARN when edges are not dark (default severity)")
def _():
    expect(consistency.check_edges(UNLINED, EDGES, OUTLINES), "WARN", "0.0%")


@case("edges WARN when an outlined purpose has no edges at all")
def _():
    expect(consistency.check_edges(FLAT, EDGES, OUTLINES), "WARN", "no edges")


@case("edges FAIL with severity fail")
def _():
    style = {"outline": {"edge_darkness": {"min_ratio": 0.6, "severity": "fail"}}}
    expect(consistency.check_edges(UNLINED, style, OUTLINES), "FAIL")


@case("edges max_luminance threshold")
def _():
    style = {"outline": {"edge_darkness": {"max_luminance": 90}}}
    expect(consistency.check_edges(UNLINED, style, OUTLINES), "PASS")


@case("edges NOT_AVAILABLE without qa.outlines or edge_darkness")
def _():
    expect(consistency.check_edges(LINED, EDGES, {}), "NOT_AVAILABLE", "qa.outlines")
    expect(consistency.check_edges(LINED, EDGES, None), "NOT_AVAILABLE", "qa.outlines")
    expect(consistency.check_edges(LINED, EDGES, {"qa": {"outlines": False}}), "NOT_AVAILABLE", "qa.outlines")
    expect(consistency.check_edges(LINED, {}, OUTLINES), "NOT_AVAILABLE", "edge_darkness")
    expect(consistency.check_edges(LINED, {"outline": "thin dark lines"}, OUTLINES), "NOT_AVAILABLE")
    expect(consistency.check_edges(LINED, {"outline": {"text": "thin"}}, OUTLINES), "NOT_AVAILABLE")


@case("edges FAIL on malformed data")
def _():
    style = {"outline": {"edge_darkness": {"max_luminance": 300}}}
    expect(consistency.check_edges(LINED, style, OUTLINES), "FAIL", "malformed")


# canvas
@case("canvas PASS on the family's aspect and min side")
def _():
    expect(consistency.check_canvas(solid(RED, 32, 64), CANVAS, "characters"), "PASS", "family characters")
    expect(consistency.check_canvas(solid(RED, 40, 40), CANVAS, "props"), "PASS")


@case("canvas WARN on wrong aspect or too small (default severity)")
def _():
    expect(consistency.check_canvas(solid(RED, 64, 32), CANVAS, "characters"), "WARN", "aspect 2.000")
    expect(consistency.check_canvas(solid(RED, 16, 32), CANVAS, "characters"), "WARN", "short side 16")


@case("canvas FAIL on wrong aspect with severity fail")
def _():
    expect(consistency.check_canvas(solid(RED, 64, 32), CANVAS, "props"), "FAIL")


@case("canvas tolerance")
def _():
    style = {"canvas": {"props": {"aspect": "1:1", "tolerance": 0.1}}}
    expect(consistency.check_canvas(solid(RED, 34, 32), style, "props"), "PASS")
    expect(consistency.check_canvas(solid(RED, 34, 32), CANVAS, "props"), "FAIL")


@case("canvas NOT_AVAILABLE without an entry for the family")
def _():
    img = solid(RED)
    expect(consistency.check_canvas(img, CANVAS, "ui"), "NOT_AVAILABLE", "family ui")
    expect(consistency.check_canvas(img, CANVAS, None), "NOT_AVAILABLE", "(none)")
    expect(consistency.check_canvas(img, {}, "props"), "NOT_AVAILABLE")


@case("canvas FAIL on malformed data")
def _():
    img = solid(RED)
    for bad in ("1:1", {"aspect": "square"}, {"aspect": "0:1"}, {"aspect": "1:1", "tolerance": 3},
                {"min_side": -1}):
        expect(consistency.check_canvas(img, {"canvas": {"props": bad}}, "props"), "FAIL", "malformed")


# sampling and aggregation
@case("large images are sampled on the SAMPLES grid")
def _():
    w = h = consistency.SAMPLES * 2
    big = png.Image(w, h, bytes(RED + (255,)) * (w * h), True, "test")
    status, details = consistency.check_palette(big, {"palette": PALETTE})
    assert status == "PASS", details
    assert len(list(consistency.steps(w))) == consistency.SAMPLES


@case("check_all returns every row in order; overall fails only on FAIL")
def _():
    style = dict(EDGES, palette=PALETTE, tone=TONE["tone"], canvas=CANVAS["canvas"])
    rows = consistency.check_all(LINED, style, OUTLINES, "props", [LINED])
    assert [r[0] for r in rows] == list(consistency.ROWS), rows
    assert all(r[1] == "PASS" for r in rows), rows
    assert consistency.overall(rows) == "PASS"
    rows = consistency.check_all(solid(MAGENTA, 64, 32), {"palette": PALETTE}, {}, "ui", [])
    assert [r[1] for r in rows] == ["WARN", "NOT_AVAILABLE", "NOT_AVAILABLE", "NOT_AVAILABLE"], rows
    assert consistency.overall(rows) == "PASS"
    rows = consistency.check_all(solid(MAGENTA, 64, 32), CANVAS, {}, "props", [])
    assert consistency.overall(rows) == "FAIL", rows


def main():
    failed = 0
    for n, (name, fn) in enumerate(CASES, 1):
        try:
            fn()
            print("ok %d - %s" % (n, name))
        except Exception as exc:  # report every case, then fail
            failed += 1
            print("not ok %d - %s: %s: %s" % (n, name, type(exc).__name__, exc))
    print("%d passed, %d failed" % (len(CASES) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
