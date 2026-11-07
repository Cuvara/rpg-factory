"""Edge checks and post-processing of transparent asset-gen outputs (stdlib; png.py decodes and encodes).

Pixels are straight (not premultiplied) RGBA, as PNG stores them. "Opaque" means alpha >= OPAQUE (224): the image
service writes its bodies with alpha 251-254, not 255 (e2e barrel-prop-001), so a strict 255 would miss the body.

edge_fringe(img) -> (state, details): the png-edge-fringe QA row (qa.py adds it for purposes with qa.alpha required).
  A soft edge pixel has alpha 1-31 (FRINGE_MAX_ALPHA) and an opaque pixel within RADIUS (2) px (Chebyshev ring 1,
  else ring 2). Its reference colour is the mean RGB of the opaque pixels on the nearest ring that has any. It is
  off-colour when a channel differs from the reference by more than TOLERANCE (64) + 255 / (2 x alpha): the second
  term is the rounding a premultiplied round trip allows at that alpha (128 at alpha 1, 4 at alpha 31), so a clean
  edge re-exported through premultiplied alpha is not flagged. FAIL when at least FAIL_SHARE (5%) of the soft edge
  pixels, and at least FAIL_MIN (16) pixels, are off-colour; else PASS (also when there are no soft edge pixels).
  NOT_AVAILABLE when the image has no alpha channel or no pixel below alpha 255.
  Calibration: barrel-prop-001 (orange/red/yellow speckle in the RGB of alpha 1-31 pixels, e2e2) has 438 of 1910
  soft edge pixels (22.9%) off-colour; an anti-aliased edge whose soft pixels carry the body colour has 0%.
  The details also give the largest difference such a pixel makes when composited on black or on white
  (alpha x channel distance / 255, the same on both), and count body pixels with alpha 251-254 (noted, never a
  FAIL).
edge_fringe_stats(img) -> dict behind edge_fringe (None without alpha): soft_edge, off_colour, share,
  max_composite_delta, opaque, body_251_254.
defringe(img, alpha_floor=None, rings=8) -> (PNG bytes, stats): colour bleed into soft pixels. Every pixel with
  0 < alpha < OPAQUE takes the alpha-weighted mean RGB of its 8 neighbours that are opaque; pixels reached in
  ring k (k = 2..rings) take the mean of the neighbours recoloured in an earlier ring (weighted by their alpha). A
  ring is computed from the image before that ring, so the result does not depend on scan order. Alpha is never
  changed except that alpha_floor N (0..OPAQUE) sets every alpha below N to 0. Opaque pixels and alpha 0 pixels keep
  their bytes. Soft pixels no ring reaches (no opaque pixel within rings px) keep their colour (stats unreached).
  stats: soft, recoloured, unreached, rings_used, alpha_floor, floored.
composite(img, background) -> PNG bytes (8-bit RGB) of the image over a background: "dark" (#202020), "light"
  (#e0e0e0), "checker" (16 px squares of #999999 and #666666, top-left #999999) or an (r, g, b) tuple. A pixel
  with alpha 0 equals the background; out = round((c x a + bg x (255 - a)) / 255) per channel.
BACKGROUNDS: the named backgrounds in review order (dark, light, checker).
"""
import png

OPAQUE = 224
FRINGE_MAX_ALPHA = 31
RADIUS = 2
TOLERANCE = 64
FAIL_SHARE = 0.05
FAIL_MIN = 16
BODY_LOW, BODY_HIGH = 251, 254

BACKGROUNDS = ("dark", "light", "checker")
SOLID = {"dark": (0x20, 0x20, 0x20), "light": (0xe0, 0xe0, 0xe0)}
CHECKER = ((0x99, 0x99, 0x99), (0x66, 0x66, 0x66))
CHECKER_SIZE = 16

_SOFT = bytes(1 if 1 <= a <= FRINGE_MAX_ALPHA else 0 for a in range(256))


def _alpha(img):
    return img.rgba[3::4]


def edge_fringe_stats(img):
    alpha = _alpha(img)
    if not img.has_alpha or min(alpha) == 255:
        return None
    w, h, d = img.width, img.height, img.rgba
    soft = alpha.translate(_SOFT)
    edge = off = worst = 0
    pos = soft.find(1)
    while pos >= 0:
        x, y = pos % w, pos // w
        for r in range(1, RADIUS + 1):
            ref = [0, 0, 0]
            n = 0
            for yy in range(max(0, y - r), min(h, y + r + 1)):
                full_row = yy in (y - r, y + r)
                for xx in (range(max(0, x - r), min(w, x + r + 1)) if full_row else (x - r, x + r)):
                    if 0 <= xx < w and alpha[yy * w + xx] >= OPAQUE:
                        j = (yy * w + xx) * 4
                        ref[0] += d[j]
                        ref[1] += d[j + 1]
                        ref[2] += d[j + 2]
                        n += 1
            if n:
                a, i = alpha[pos], pos * 4
                dist = max(abs(d[i + k] - ref[k] / n) for k in range(3))
                edge += 1
                if dist > TOLERANCE + 255 / (2 * a):
                    off += 1
                worst = max(worst, a * dist / 255)
                break
        pos = soft.find(1, pos + 1)
    opaque = sum(1 for a in alpha if a >= OPAQUE)
    body = sum(1 for a in alpha if BODY_LOW <= a <= BODY_HIGH)
    return {"soft_edge": edge, "off_colour": off, "share": off / edge if edge else 0.0,
            "max_composite_delta": round(worst, 1), "opaque": opaque, "body_251_254": body}


def edge_fringe(img):
    s = edge_fringe_stats(img)
    if s is None:
        return "NOT_AVAILABLE", ["no alpha channel or no pixel below alpha 255: no transparent edge to check"]
    body = "body: %d of %d opaque pixels (alpha >= %d) have alpha %d-%d (noted, not graded)" % (
        s["body_251_254"], s["opaque"], OPAQUE, BODY_LOW, BODY_HIGH)
    if not s["soft_edge"]:
        return "PASS", ["no soft edge pixels (alpha 1-%d within %d px of an opaque pixel)" % (FRINGE_MAX_ALPHA, RADIUS), body]
    bad = s["off_colour"] >= FAIL_MIN and s["share"] >= FAIL_SHARE
    return ("FAIL" if bad else "PASS"), [
        "%d of %d soft edge pixels (alpha 1-%d within %d px of an opaque pixel) off-colour: %.1f%% "
        "(channel distance from the nearest opaque pixels > %d + 255/(2 x alpha); FAIL at >= %d%% and >= %d pixels)"
        % (s["off_colour"], s["soft_edge"], FRINGE_MAX_ALPHA, RADIUS, s["share"] * 100, TOLERANCE,
           round(FAIL_SHARE * 100), FAIL_MIN),
        "largest composite difference on black or white: %.1f of 255" % s["max_composite_delta"],
        body] + (["run assetgen.py defringe on the run, then QA again"] if bad else [])


def defringe(img, alpha_floor=None, rings=8):
    if alpha_floor is not None and not (isinstance(alpha_floor, int) and not isinstance(alpha_floor, bool)
                                        and 0 <= alpha_floor <= OPAQUE):
        raise ValueError("alpha_floor must be an integer from 0 to %d" % OPAQUE)
    if not (isinstance(rings, int) and rings >= 1):
        raise ValueError("rings must be an integer >= 1")
    w, h = img.width, img.height
    out = bytearray(img.rgba)
    alpha = bytes(img.rgba[3::4])
    weight = [a if a >= OPAQUE else 0 for a in alpha]  # the sources of the next ring
    pending = [p for p, a in enumerate(alpha) if 0 < a < OPAQUE]
    soft, recoloured, used = len(pending), 0, 0
    for _ring in range(rings):
        done, rest = [], []
        for p in pending:
            x, y = p % w, p // w
            s = r = g = b = 0
            for yy in range(max(0, y - 1), min(h, y + 2)):
                for xx in range(max(0, x - 1), min(w, x + 2)):
                    q = yy * w + xx
                    wt = weight[q]
                    if wt and q != p:
                        j = q * 4
                        s += wt
                        r += wt * out[j]
                        g += wt * out[j + 1]
                        b += wt * out[j + 2]
            if s:
                done.append((p, (r + s // 2) // s, (g + s // 2) // s, (b + s // 2) // s))
            else:
                rest.append(p)
        if not done:
            break
        used += 1
        for p, r, g, b in done:
            out[p * 4:p * 4 + 3] = bytes((r, g, b))
            weight[p] = alpha[p]
        recoloured += len(done)
        pending = rest
    floored = 0
    if alpha_floor:
        for p, a in enumerate(alpha):
            if 0 < a < alpha_floor:
                out[p * 4 + 3] = 0
                floored += 1
    stats = {"soft": soft, "recoloured": recoloured, "unreached": len(pending), "rings_used": used,
             "alpha_floor": alpha_floor, "floored": floored}
    return png.encode(w, h, bytes(out)), stats


def _blend_table(bg):
    """table[a << 8 | c] = round((c x a + bg x (255 - a)) / 255)."""
    return bytes((c * a + bg * (255 - a) + 127) // 255 for a in range(256) for c in range(256))


def composite(img, background):
    if isinstance(background, str):
        if background == "checker":
            colours = CHECKER
        elif background in SOLID:
            colours = (SOLID[background],)
        else:
            raise ValueError("background must be one of %s or an (r, g, b) tuple" % ", ".join(BACKGROUNDS))
    elif isinstance(background, (tuple, list)) and len(background) == 3 and all(
            isinstance(v, int) and 0 <= v <= 255 for v in background):
        colours = (tuple(background),)
    else:
        raise ValueError("background must be one of %s or an (r, g, b) tuple" % ", ".join(BACKGROUNDS))
    tables = {}
    for colour in colours:
        for v in colour:
            if v not in tables:
                tables[v] = _blend_table(v)
    w, h, d = img.width, img.height, img.rgba
    rows = []
    for y in range(h):
        row = bytearray(w * 3)
        for x in range(w):
            colour = colours[((x // CHECKER_SIZE) + (y // CHECKER_SIZE)) % len(colours)]
            i = (y * w + x) * 4
            a = d[i + 3]
            o = x * 3
            if a == 255:
                row[o:o + 3] = d[i:i + 3]
            elif a == 0:
                row[o:o + 3] = bytes(colour)
            else:
                k = a << 8
                row[o] = tables[colour[0]][k | d[i]]
                row[o + 1] = tables[colour[1]][k | d[i + 1]]
                row[o + 2] = tables[colour[2]][k | d[i + 2]]
        rows.append(bytes(row))
    return png.encode_raw(w, h, 8, 2, rows)
