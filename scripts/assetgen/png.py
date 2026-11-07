#!/usr/bin/env python3
"""Minimal PNG decode/encode for asset-gen QA (stdlib; Pillow used when present).

decode(path) -> Image(width, height, rgba: bytes, has_alpha: bool, decoder: "pillow"|"stdlib").
  Pillow decodes every PNG it supports. Without Pillow (or with ASSETGEN_NO_PIL=1) the stdlib decoder handles
  8-bit, non-interlaced PNGs of color types 0 (gray), 2 (RGB), 3 (palette), 4 (gray+alpha) and 6 (RGBA);
  anything else raises Unsupported (the caller grades NOT_AVAILABLE). A broken file raises Invalid.
  tRNS is applied as Pillow does: a gray (2 bytes) or RGB (6 bytes) key makes matching pixels alpha 0; palette
  entries take their tRNS alpha (255 past its end).
  has_alpha: the file can carry transparency (an alpha channel or a tRNS chunk).
encode(width, height, rgba, alpha=True) -> PNG bytes (8-bit RGBA, or RGB when alpha=False; filter 0).
encode_raw(width, height, bit_depth, color_type, rows, interlace=0, extra=()) -> PNG bytes from raw scanline bytes
  (test fixtures: formats the stdlib decoder does not handle; extra [(type, body)] chunks such as PLTE and tRNS go
  before IDAT).
text_keywords(data) -> the keywords of the tEXt, zTXt and iTXt chunks of PNG bytes (raises Invalid).
add_text(data, keyword, text) -> the PNG bytes with a tEXt chunk keyword=text inserted right before IEND (CRC set;
  every other chunk, and anything after IEND, kept byte for byte). text must be Latin-1 (JSON with ensure_ascii).
tile_2x2(img) -> PNG bytes (8-bit RGBA) of the Image repeated 2x2: a seam preview for tileable textures.
"""
import os
import struct
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


class Invalid(Exception):
    """Not a readable PNG."""


class Unsupported(Exception):
    """A valid PNG the available decoder cannot read (bit depth, interlace)."""


class Image:
    def __init__(self, width, height, rgba, has_alpha, decoder):
        self.width, self.height, self.rgba, self.has_alpha, self.decoder = width, height, rgba, has_alpha, decoder

    def pixel(self, x, y):
        i = (y * self.width + x) * 4
        return self.rgba[i:i + 4]


def pillow():
    if os.environ.get("ASSETGEN_NO_PIL"):
        return None
    try:
        from PIL import Image as PILImage
        return PILImage
    except ImportError:
        return None


def chunks(data):
    if data[:8] != SIGNATURE:
        raise Invalid("not a PNG signature")
    pos = 8
    while pos + 8 <= len(data):
        length, ctype = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if len(body) != length or pos + 12 + length > len(data):
            raise Invalid("truncated chunk " + ctype.decode("latin-1"))
        crc = struct.unpack(">I", data[pos + 8 + length:pos + 12 + length])[0]
        if zlib.crc32(ctype + body) & 0xFFFFFFFF != crc:
            raise Invalid("bad CRC in chunk " + ctype.decode("latin-1"))
        yield ctype, body
        pos += 12 + length
        if ctype == b"IEND":
            return
    raise Invalid("missing IEND")


def header(data):
    """(width, height, bit_depth, color_type, interlace) from IHDR; raises Invalid."""
    for ctype, body in chunks(data):
        if ctype != b"IHDR" or len(body) != 13:
            raise Invalid("first chunk is not IHDR")
        w, h, depth, ctype_, _comp, _filt, interlace = struct.unpack(">IIBBBBB", body)
        if w == 0 or h == 0 or ctype_ not in CHANNELS:
            raise Invalid("bad IHDR")
        return w, h, depth, ctype_, interlace
    raise Invalid("no chunks")


def paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def unfilter(raw, width, height, bpp):
    stride = width * bpp
    out = bytearray(stride * height)
    prev = bytearray(stride)
    pos = 0
    for y in range(height):
        if pos + 1 + stride > len(raw):
            raise Invalid("image data too short")
        ftype = raw[pos]
        line = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        if ftype == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif ftype == 2:
            line = bytearray((a + b) & 0xFF for a, b in zip(line, prev))
        elif ftype == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                up_left = prev[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + paeth(left, prev[i], up_left)) & 0xFF
        elif ftype != 0:
            raise Invalid("bad filter type %d" % ftype)
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return out


def decode_stdlib(data):
    w, h, depth, ctype, interlace = header(data)
    if depth != 8 or interlace:
        raise Unsupported("stdlib decoder reads 8-bit non-interlaced PNGs only (bit depth %d, interlace %d); "
                          "install Pillow for this file" % (depth, interlace))
    idat, palette, trns = bytearray(), None, None
    for kind, body in chunks(data):
        if kind == b"IDAT":
            idat += body
        elif kind == b"PLTE":
            palette = body
        elif kind == b"tRNS":
            trns = body
    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error as exc:
        raise Invalid("bad image data: %s" % exc)
    n = CHANNELS[ctype]
    px = unfilter(raw, w, h, n)
    rgba = bytearray(w * h * 4)
    if ctype == 6:
        rgba[:] = px
    elif ctype == 2:
        key = struct.unpack(">HHH", trns) if trns and len(trns) == 6 else None
        rgba[0::4], rgba[1::4], rgba[2::4] = px[0::3], px[1::3], px[2::3]
        rgba[3::4] = b"\xff" * (w * h)
        if key:
            for i in range(w * h):
                if tuple(px[i * 3:i * 3 + 3]) == key:
                    rgba[i * 4 + 3] = 0
    elif ctype in (0, 4):
        g = px[0::n]
        rgba[0::4] = rgba[1::4] = rgba[2::4] = g
        rgba[3::4] = px[1::2] if ctype == 4 else b"\xff" * (w * h)
        key = struct.unpack(">H", trns)[0] if ctype == 0 and trns and len(trns) == 2 else None
        if key is not None:
            for i in range(w * h):
                if g[i] == key:
                    rgba[i * 4 + 3] = 0
    else:
        if palette is None:
            raise Invalid("palette image without PLTE")
        alpha = trns or b""
        for i, idx in enumerate(px):
            if idx * 3 + 3 > len(palette):
                raise Invalid("palette index out of range")
            rgba[i * 4:i * 4 + 3] = palette[idx * 3:idx * 3 + 3]
            rgba[i * 4 + 3] = alpha[idx] if idx < len(alpha) else 255
    return Image(w, h, bytes(rgba), ctype in (4, 6) or trns is not None, "stdlib")


def decode(path):
    with open(path, "rb") as f:
        data = f.read()
    header(data)  # signature, IHDR and chunk CRCs are checked the same way with or without Pillow
    pil = pillow()
    if pil is None:
        return decode_stdlib(data)
    try:
        img = pil.open(path)
        img.load()
    except Exception as exc:  # Pillow raises many types for broken files
        raise Invalid("Pillow could not decode: %s" % exc)
    has_alpha = "A" in img.getbands() or "transparency" in img.info
    rgba = img.convert("RGBA")
    return Image(rgba.width, rgba.height, rgba.tobytes(), has_alpha, "pillow")


def chunk(ctype, body):
    return struct.pack(">I", len(body)) + ctype + body + struct.pack(">I", zlib.crc32(ctype + body) & 0xFFFFFFFF)


def encode_raw(width, height, bit_depth, color_type, rows, interlace=0, extra=()):
    raw = b"".join(b"\x00" + bytes(r) for r in rows)
    ihdr = struct.pack(">IIBBBBB", width, height, bit_depth, color_type, 0, 0, interlace)
    return (SIGNATURE + chunk(b"IHDR", ihdr) + b"".join(chunk(t, b) for t, b in extra)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def encode(width, height, rgba, alpha=True):
    n = 4 if alpha else 3
    rows = []
    for y in range(height):
        line = rgba[y * width * 4:(y + 1) * width * 4]
        rows.append(line if alpha else bytes(b for i, b in enumerate(line) if i % 4 != 3))
    return encode_raw(width, height, 8, 6 if n == 4 else 2, rows)


TEXT_CHUNKS = (b"tEXt", b"zTXt", b"iTXt")


def text_keywords(data):
    return {body.split(b"\0", 1)[0].decode("latin-1") for ctype, body in chunks(data) if ctype in TEXT_CHUNKS}


def add_text(data, keyword, text):
    key = keyword.encode("latin-1")
    if not 1 <= len(key) <= 79 or b"\0" in key:
        raise ValueError("tEXt keyword must be 1-79 Latin-1 bytes without NUL")
    body = key + b"\0" + text.encode("latin-1")
    pos = 8
    for ctype, cbody in chunks(data):  # validates signature, lengths and CRCs up to IEND
        if ctype == b"IEND":
            return data[:pos] + chunk(b"tEXt", body) + data[pos:]
        pos += 12 + len(cbody)
    raise Invalid("missing IEND")


def tile_2x2(img):
    stride = img.width * 4
    rows = [img.rgba[y * stride:(y + 1) * stride] * 2 for y in range(img.height)]
    return encode_raw(img.width * 2, img.height * 2, 8, 6, rows + rows)
