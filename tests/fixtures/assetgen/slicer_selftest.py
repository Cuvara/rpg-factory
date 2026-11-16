"""Self-test content-based slicing on deterministic gateway-sized sheets."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..", "..")
sys.path.insert(0, os.path.join(ROOT, "scripts", "assetgen"))

import png  # noqa: E402
import slicer  # noqa: E402

failed = []
count = 0


def check(name, condition, detail=""):
    global count
    count += 1
    if condition:
        print("ok %d - %s" % (count, name))
    else:
        failed.append(name)
        print("not ok %d - %s: %s" % (count, name, detail))


def sheet(w, h, opaque=False, missing=None, merged=False, row_count=3):
    background = bytes((248, 246, 244, 255) if opaque else (0, 0, 0, 0))
    data = bytearray(background * (w * h))
    bounds = []
    # The first shape crosses x = width/3; actual gutters are deliberately uneven.
    x_ranges = ((.04, .38), (.43, .65), (.72, .96))
    y_ranges = ((.05, .29), (.38, .61), (.70, .94))
    for row in range(row_count):
        for col in range(3):
            if (row, col) == missing:
                continue
            x0, x1 = (int(w * v) for v in x_ranges[col])
            y0, y1 = (int(h * v) for v in y_ranges[row])
            # Different offsets and extents while keeping each row's shapes aligned.
            x0 += row * 3
            x1 -= row * 2
            y0 += col * 3
            y1 -= col * 2
            kind = (row * 3 + col) % 5
            actual = [w, h, 0, 0]
            for y in range(y0, y1):
                for x in range(x0, x1):
                    dx = abs(2 * (x - x0) - (x1 - x0 - 1)) / (x1 - x0)
                    dy = abs(2 * (y - y0) - (y1 - y0 - 1)) / (y1 - y0)
                    radius = dx * dx + dy * dy
                    inside = (radius <= .94 if kind == 0 else
                              dx + dy <= .97 if kind == 1 else
                              True if kind == 2 else
                              .16 <= radius <= .94 if kind == 3 else
                              (x < x1 - (x1 - x0) // 5 or
                               (y0 + (y1 - y0) // 3 <= y < y0 + (y1 - y0) // 2
                                and x >= x1 - (x1 - x0) // 8)))
                    if inside:
                        # A low-alpha outer line exercises antialiased edges.
                        edge = x in (x0, x1 - 1) or y in (y0, y1 - 1)
                        color = (40 + row * 30, 50 + col * 30, 90, 160 if edge and not opaque else 255)
                        i = (y * w + x) * 4
                        data[i:i + 4] = bytes(color)
                        actual = [min(actual[0], x), min(actual[1], y), max(actual[2], x + 1),
                                  max(actual[3], y + 1)]
            bounds.append(actual)
    if merged:
        for y in range(int(h * .17), int(h * .17) + 5):
            for x in range(int(w * .37), int(w * .45)):
                i = (y * w + x) * 4
                data[i:i + 4] = bytes((40, 50, 90, 255))
    return png.Image(w, h, bytes(data), not opaque, "test"), bounds


def contains(outer, inner):
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def tiles(items, w, h):
    for row in range(3):
        boxes = [item["box"] for item in items[row * 3:row * 3 + 3]]
        if boxes[0][0] != 0 or boxes[-1][2] != w:
            return False
        if any(a[2] != b[0] or a[1] != b[1] or a[3] != b[3] for a, b in zip(boxes, boxes[1:])):
            return False
        if boxes[0][1] != (0 if row == 0 else items[(row - 1) * 3]["box"][3]):
            return False
    return items[-1]["box"][3] == h


for w, h in ((1322, 1190), (1672, 941), (2172, 724)):
    for opaque in (False, True):
        name = "%dx%d %s" % (w, h, "opaque" if opaque else "transparent")
        img, bounds = sheet(w, h, opaque)
        try:
            result, info = slicer.slice_image(img, 3, 3)
            check(name + " yields nine ordered cells", [(v["row"], v["col"]) for v in result] ==
                  [(r, c) for r in range(1, 4) for c in range(1, 4)])
            check(name + " contains known shape bounds, including detached part",
                  len(result) == 9 and all(contains(v["content"], b) and contains(v["box"], b)
                                           for v, b in zip(result, bounds)))
            check(name + " tiles the sheet", len(result) == 9 and tiles(result, w, h))
            check(name + " is deterministic", (result, info) == slicer.slice_image(img, 3, 3))
            check(name + " describes background", info["background"] ==
                  ("background #f8f6f4" if opaque else "transparent background"))
        except Exception as exc:
            check(name + " completes", False, repr(exc))


def fails(name, img, rows, cols, expected):
    try:
        slicer.cells(img, rows, cols)
    except slicer.SliceError as exc:
        check(name, expected in str(exc), str(exc))
    else:
        check(name, False, "did not raise SliceError")


img, _ = sheet(600, 450)
fails("merged cells", sheet(600, 450, merged=True)[0], 3, 3, "2 cells found, 3 expected")
fails("missing cell", sheet(600, 450, missing=(1, 1))[0], 3, 3, "2 cells found, 3 expected")
fails("wrong row count", sheet(600, 450, row_count=2)[0], 3, 3, "2 rows found, 3 expected")
fails("zero rows", img, 0, 3, "1..8")
fails("nine rows", img, 9, 3, "1..8")
text = slicer.hint(3, 3)
check("hint specifies grid and gutters", "3 rows" in text and "3 columns" in text and "gutter" in text)
print("%d passed, %d failed" % (count - len(failed), len(failed)))
sys.exit(1 if failed else 0)
