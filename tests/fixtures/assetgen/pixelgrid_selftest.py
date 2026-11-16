"""Self-test pixel-grid detection, reduction and deterministic palette limiting.

Prints ok/not ok per case and exits nonzero if any case fails.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..", "..")
sys.path.insert(0, os.path.join(ROOT, "scripts", "assetgen"))

import pixelgrid  # noqa: E402
import png  # noqa: E402

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


COLORS = ((10, 20, 30, 255), (220, 30, 50, 255), (30, 210, 70, 255),
          (40, 50, 230, 255), (240, 210, 20, 255), (0, 0, 0, 0))
source = bytes(v for y in range(14) for x in range(20)
               for v in COLORS[(x * 11 + y * 7 + x * y * 3) % 6])


def upscale(scale, crop):
    w, h = 20 * scale - crop, 14 * scale - crop
    data = bytearray()
    for y in range(h):
        for x in range(w):
            i = (((y + crop) // scale) * 20 + (x + crop) // scale) * 4
            data.extend(source[i:i + 4])
    return png.Image(w, h, bytes(data), True, "test")


for scale in (4, 7):
    for crop in (0, 2):
        img = upscale(scale, crop)
        name = "scale %d crop %d" % (scale, crop)
        try:
            found = pixelgrid.detect(img)
            check(name + " detects scale and offset", found == (scale, (-crop) % scale, (-crop) % scale), found)
            w, h, reduced = pixelgrid.downsample(img, *found)
            check(name + " reproduces source", (w, h, reduced) == (20, 14, source), (w, h))
            result = pixelgrid.process(img, max_colors=4)
            check(name + " limits colors", pixelgrid.count_colors(result[2]) <= 4, result[3])
            check(name + " is deterministic", result == pixelgrid.process(img, max_colors=4))
            palette = [(0, 0, 0), (255, 0, 0), (0, 255, 255)]
            styled = pixelgrid.process(img, palette=palette)
            used = {tuple(styled[2][i:i + 3]) for i in range(0, len(styled[2]), 4) if styled[2][i + 3]}
            check(name + " maps to style palette", used <= set(palette), used)
        except Exception as exc:
            check(name + " completes", False, repr(exc))


def no_grid(img):
    try:
        pixelgrid.detect(img)
    except pixelgrid.NoGrid:
        return True
    return False


flat = png.Image(80, 56, bytes((20, 30, 40, 255)) * (80 * 56), True, "test")
gradient = png.Image(80, 56, bytes(v for y in range(56) for x in range(80)
                                   for v in (x * 3, y * 4, x + y, 255)), True, "test")
check("flat image has no grid", no_grid(flat))
check("smooth gradient has no grid", no_grid(gradient))
print("%d passed, %d failed" % (count - len(failed), len(failed)))
sys.exit(1 if failed else 0)
