"""Deterministic pixel-grid detection, reduction and palette limiting for RGBA8 images.

Boundary energy is the sum of absolute RGBA differences between adjacent pixels.
For each candidate cell size, find the strongest boundary residue on each axis;
choose the largest size within 90% of the best combined energy fraction, provided
it exceeds the gridless threshold. Cells begin at offset + n * scale; clipped
border cells are included. Their channel medians use the cell interior, excluding
one pixel at each full cell boundary for scale >= 4 when pixels remain.
Palette reduction uses weighted median cut and deterministic nearest RGB mapping.
"""


class NoGrid(Exception):
    """No convincing pixel grid was found."""


def detect(img):
    w, h, data = img.width, img.height, img.rgba
    xs, ys = [0] * w, [0] * h
    for y in range(h):
        for x in range(w):
            i = (y * w + x) * 4
            if x:
                xs[x] += sum(abs(data[i + c] - data[i - 4 + c]) for c in range(4))
            if y:
                ys[y] += sum(abs(data[i + c] - data[i - w * 4 + c]) for c in range(4))
    total = sum(xs) + sum(ys)
    if not total:
        raise NoGrid("image has no edge energy")
    candidates = []
    for k in range(2, min(64, min(w, h) // 4) + 1):
        xbins, ybins = [0] * k, [0] * k
        for x in range(1, w):
            xbins[x % k] += xs[x]
        for y in range(1, h):
            ybins[y % k] += ys[y]
        ox, oy = xbins.index(max(xbins)), ybins.index(max(ybins))
        candidates.append((k, ox, oy, (xbins[ox] + ybins[oy]) / total))
    if not candidates:
        raise NoGrid("image is too small to detect a grid")
    best = max(c[3] for c in candidates)
    k, ox, oy, score = next(c for c in reversed(candidates) if c[3] >= 0.9 * best)
    if score < max(0.5, 3 / k):
        raise NoGrid("edge energy does not show a clear pixel grid")
    return k, ox, oy


def _cells(length, scale, offset):
    start = offset - scale if offset else 0
    while start < length:
        yield max(0, start), min(length, start + scale), start
        start += scale


def downsample(img, scale, ox, oy):
    if scale < 2 or not (0 <= ox < scale and 0 <= oy < scale):
        raise ValueError("invalid scale or offset")
    cols, rows = list(_cells(img.width, scale, ox)), list(_cells(img.height, scale, oy))
    out = bytearray()
    for y0, y1, sy in rows:
        for x0, x1, sx in cols:
            # Trim only actual cell boundaries, retaining pixels at clipped image edges.
            xa, xb, ya, yb = x0, x1, y0, y1
            if scale >= 4:
                xa, xb = max(x0, sx + 1), min(x1, sx + scale - 1)
                ya, yb = max(y0, sy + 1), min(y1, sy + scale - 1)
                if xa >= xb:
                    xa, xb = x0, x1
                if ya >= yb:
                    ya, yb = y0, y1
            channels = [[], [], [], []]
            for y in range(ya, yb):
                for x in range(xa, xb):
                    i = (y * img.width + x) * 4
                    for c in range(4):
                        channels[c].append(img.rgba[i + c])
            median = [sorted(c)[(len(c) - 1) // 2] for c in channels]
            out.extend(median[:3] + [255] if median[3] >= 128 else (0, 0, 0, 0))
    return len(cols), len(rows), bytes(out)


def count_colors(rgba):
    return len({tuple(rgba[i:i + 3]) for i in range(0, len(rgba), 4) if rgba[i + 3] > 0})


def _median_palette(counts, limit):
    boxes = [sorted(counts)] if counts else []
    while len(boxes) < limit:
        choices = []
        for index, box in enumerate(boxes):
            if len(box) < 2:
                continue
            ranges = [max(c[ch] for c in box) - min(c[ch] for c in box) for ch in range(3)]
            channel = ranges.index(max(ranges))
            choices.append((ranges[channel], -channel, -index, channel, index))
        if not choices:
            break
        _, _, _, channel, index = max(choices)
        box = sorted(boxes[index], key=lambda c: (c[channel], c))
        half = (sum(counts[c] for c in box) + 1) // 2
        cumulative, split = 0, 0
        for color in box[:-1]:
            cumulative += counts[color]
            split += 1
            if cumulative >= half:
                break
        boxes[index:index + 1] = [box[:split], box[split:]]
    result = []
    for box in boxes:
        n = sum(counts[c] for c in box)
        result.append(tuple((sum(c[ch] * counts[c] for c in box) * 2 + n) // (2 * n) for ch in range(3)))
    return result


def quantize(width, height, rgba, palette=None, max_colors=16):
    if len(rgba) != width * height * 4:
        raise ValueError("RGBA data does not match dimensions")
    if palette is None and (not isinstance(max_colors, int) or isinstance(max_colors, bool) or max_colors < 1):
        raise ValueError("max_colors must be a positive integer")
    counts = {}
    for i in range(0, len(rgba), 4):
        if rgba[i + 3]:
            color = tuple(rgba[i:i + 3])
            counts[color] = counts.get(color, 0) + 1
    colors = list(palette) if palette is not None else _median_palette(counts, max_colors)
    if counts and not colors:
        raise ValueError("palette must not be empty for opaque pixels")
    mapping = {}
    for color in sorted(counts):
        mapping[color] = tuple(min(colors, key=lambda p: sum((color[c] - p[c]) ** 2 for c in range(3))))
    out = bytearray(len(rgba))
    for i in range(0, len(rgba), 4):
        if rgba[i + 3]:
            out[i:i + 3] = bytes(mapping[tuple(rgba[i:i + 3])])
            out[i + 3] = rgba[i + 3]
    used = sorted(set(mapping.values()))
    return bytes(out), used


def process(img, palette=None, max_colors=16):
    scale, ox, oy = detect(img)
    width, height, rgba = downsample(img, scale, ox, oy)
    rgba, colors = quantize(width, height, rgba, palette, max_colors)
    return width, height, rgba, {"scale": scale, "offset": [ox, oy],
                                 "source_size": "%dx%d" % (img.width, img.height),
                                 "size": "%dx%d" % (width, height), "colors": len(colors),
                                 "palette": "style" if palette is not None else "quantized",
                                 "max_colors": None if palette is not None else max_colors}
