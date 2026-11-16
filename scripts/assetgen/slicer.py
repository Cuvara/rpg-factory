"""Slice sheets at content gutters rather than at assumed grid coordinates.

Threshold alpha or distance from the median border colour to find foreground.
Project it onto each axis, discard thin noise bands, and merge only gaps much
smaller than the remaining gutters. Midpoints of gutters define tiling crops;
foreground bounds within each crop describe its content.
"""


class SliceError(Exception):
    """The sheet cannot be divided into the requested cells."""


def hint(rows, cols):
    return ("Create exactly %d rows and %d columns of separate items in a regular grid, "
            "each fully inside its own cell and centred. Separate items with wide empty "
            "gutters of plain background (transparent when possible); no grid lines, "
            "borders, labels, numbers or text, nothing crossing a gutter, and items not touching."
            % (rows, cols))


def foreground(img):
    w, h, data = img.width, img.height, img.rgba
    alpha = data[3::4]
    if sum(a < 128 for a in alpha) * 100 >= len(alpha):
        table = bytes(1 if a >= 128 else 0 for a in range(256))
        return bytearray(alpha.translate(table)), "transparent background"
    border = []
    for x in range(w):
        border.append(x * 4)
        if h > 1:
            border.append(((h - 1) * w + x) * 4)
    for y in range(1, h - 1):
        border.append(y * w * 4)
        if w > 1:
            border.append((y * w + w - 1) * 4)
    color = [sorted(data[i + c] for i in border)[(len(border) - 1) // 2] for c in range(3)]
    tables = [bytes(int(abs(v - c) > 40) for v in range(256)) for c in color]
    red, green, blue = (data[c::4].translate(tables[c]) for c in range(3))
    mask = bytearray(a | b | c for a, b, c in zip(red, green, blue))
    return mask, "background #%02x%02x%02x" % tuple(color)


def _bands(profile, threshold, minimum, expected, label):
    bands = []
    start = None
    for i, count in enumerate(profile):
        if count > threshold:
            if start is None:
                start = i
        elif start is not None:
            if i - start >= minimum:
                bands.append([start, i])
            start = None
    if start is not None and len(profile) - start >= minimum:
        bands.append([start, len(profile)])
    while len(bands) > expected:
        gaps = [bands[i + 1][0] - bands[i][1] for i in range(len(bands) - 1)]
        smallest = min(range(len(gaps)), key=gaps.__getitem__)
        remaining = gaps[:smallest] + gaps[smallest + 1:]
        if not remaining or gaps[smallest] * 2 >= min(remaining):
            break
        bands[smallest:smallest + 2] = [[bands[smallest][0], bands[smallest + 1][1]]]
    if len(bands) != expected:
        raise SliceError("%s%d %s found, %d expected (merged or missing cells)" %
                         (label, len(bands), "rows" if not label else "cells", expected))
    return bands


def _edges(bands, length):
    return [0] + [(a[1] + b[0]) // 2 for a, b in zip(bands, bands[1:])] + [length]


def _cells(mask, w, h, rows, cols):
    row_profile = [mask[y * w:(y + 1) * w].count(1) for y in range(h)]
    row_bands = _bands(row_profile, max(1, w // 500), max(2, h // 200), rows, "")
    y_edges = _edges(row_bands, h)
    result = []
    for row, (ya, yb) in enumerate(row_bands):
        profile = [0] * w
        for y in range(ya, yb):
            line = mask[y * w:(y + 1) * w]
            for x, value in enumerate(line):
                profile[x] += value
        bands = _bands(profile, max(1, h // 500), max(2, w // 200), cols, "row %d: " % (row + 1))
        x_edges = _edges(bands, w)
        for col in range(cols):
            x0, x1, y0, y1 = x_edges[col], x_edges[col + 1], y_edges[row], y_edges[row + 1]
            left, right, top, bottom = x1, x0, y1, y0
            for y in range(y0, y1):
                line = mask[y * w + x0:y * w + x1]
                first = line.find(1)
                if first >= 0:
                    left, right = min(left, x0 + first), max(right, x0 + line.rfind(1) + 1)
                    top, bottom = min(top, y), y + 1
            if top == y1:
                raise SliceError("row %d: cell %d is missing foreground" % (row + 1, col + 1))
            result.append({"row": row + 1, "col": col + 1, "box": [x0, y0, x1, y1],
                           "content": [left, top, right, bottom]})
    return result


def cells(img, rows, cols):
    return slice_image(img, rows, cols)[0]


def crop(img, box):
    x0, y0, x1, y1 = box
    stride = img.width * 4
    return x1 - x0, y1 - y0, b"".join(img.rgba[y * stride + x0 * 4:y * stride + x1 * 4]
                                      for y in range(y0, y1))


def slice_image(img, rows, cols):
    if (not isinstance(rows, int) or isinstance(rows, bool) or not isinstance(cols, int)
            or isinstance(cols, bool) or not 1 <= rows <= 8 or not 1 <= cols <= 8 or rows * cols < 2):
        raise SliceError("rows and columns must be in 1..8 and contain at least two cells")
    mask, background = foreground(img)
    result = _cells(mask, img.width, img.height, rows, cols)
    return result, {"rows": rows, "cols": cols, "size": "%dx%d" % (img.width, img.height),
                    "background": background}
