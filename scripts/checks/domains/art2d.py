"""Domain-specific 2D art production quality checks."""
import hashlib
import re
import struct
from pathlib import Path, PurePosixPath

from _api import Result


def _spec(item):
    return item.get('spec') if isinstance(item.get('spec'), dict) else {}


def _dimensions(path):
    """Read dimensions and alpha from PNG, JPEG, or the three WebP bitstreams."""
    data = path.read_bytes()
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        offset = 8
        header = None
        ended = False
        while offset + 12 <= len(data):
            size = int.from_bytes(data[offset:offset + 4], 'big')
            tag = data[offset + 4:offset + 8]
            start, finish = offset + 8, offset + 8 + size
            if finish + 4 > len(data):
                raise ValueError('truncated PNG chunk')
            if tag == b'IHDR':
                if header is not None or offset != 8 or size != 13:
                    raise ValueError('malformed PNG IHDR')
                header = data[start:finish]
            if tag == b'IEND':
                if size != 0:
                    raise ValueError('malformed PNG IEND')
                ended = True
                offset = finish + 4
                break
            offset = finish + 4
        if not header:
            raise ValueError('truncated or malformed PNG IHDR')
        if not ended:
            raise ValueError('truncated PNG; IEND chunk is missing')
        if offset != len(data):
            raise ValueError('malformed PNG data follows the IEND chunk')
        w, h = struct.unpack('>II', header[:8])
        color = header[9]
        if not w or not h or color not in (0, 2, 3, 4, 6):
            raise ValueError('invalid PNG dimensions or color type')
        return w, h, 'png', color in (4, 6)
    if data.startswith(b'\xff\xd8'):
        if b'\xff\xd9' not in data[2:]:
            raise ValueError('truncated JPEG; EOI marker is missing')
        offset = 2
        sof = {0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf}
        while offset < len(data):
            if data[offset] != 0xff:
                raise ValueError('malformed JPEG marker')
            while offset < len(data) and data[offset] == 0xff:
                offset += 1
            if offset >= len(data):
                break
            marker = data[offset]
            offset += 1
            if marker in (0xd8, 0xd9) or 0xd0 <= marker <= 0xd7:
                continue
            if offset + 2 > len(data):
                raise ValueError('truncated JPEG segment length')
            size = int.from_bytes(data[offset:offset + 2], 'big')
            if size < 2 or offset + size > len(data):
                raise ValueError('truncated or malformed JPEG segment')
            if marker in sof:
                if size < 7:
                    raise ValueError('truncated JPEG frame header')
                h, w = struct.unpack('>HH', data[offset + 3:offset + 7])
                if not w or not h:
                    raise ValueError('invalid JPEG dimensions')
                return w, h, 'jpeg', False
            offset += size
        raise ValueError('JPEG dimensions not found before end of file')
    if len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        riff_size = int.from_bytes(data[4:8], 'little')
        if riff_size + 8 > len(data) or riff_size < 12:
            raise ValueError('truncated or malformed WebP RIFF container')
        offset, end = 12, riff_size + 8
        vp8x = vp8 = vp8l = None
        while offset + 8 <= end:
            tag = data[offset:offset + 4]
            size = int.from_bytes(data[offset + 4:offset + 8], 'little')
            start, finish = offset + 8, offset + 8 + size
            if finish > end:
                raise ValueError('truncated WebP chunk')
            chunk = data[start:finish]
            if tag == b'VP8X':
                if size < 10:
                    raise ValueError('truncated WebP VP8X header')
                flags = chunk[0]
                w = 1 + int.from_bytes(chunk[4:7], 'little')
                h = 1 + int.from_bytes(chunk[7:10], 'little')
                vp8x = (w, h, bool(flags & 0x10))
            if tag == b'VP8 ':
                if size < 10 or chunk[3:6] != b'\x9d\x01\x2a':
                    raise ValueError('truncated or malformed WebP VP8 frame header')
                w = int.from_bytes(chunk[6:8], 'little') & 0x3fff
                h = int.from_bytes(chunk[8:10], 'little') & 0x3fff
                if not w or not h:
                    raise ValueError('invalid WebP VP8 dimensions')
                vp8 = (w, h, False)
            if tag == b'VP8L':
                if size < 5 or chunk[0] != 0x2f:
                    raise ValueError('truncated or malformed WebP VP8L header')
                bits = int.from_bytes(chunk[1:5], 'little')
                w, h = 1 + (bits & 0x3fff), 1 + ((bits >> 14) & 0x3fff)
                vp8l = (w, h, bool((bits >> 28) & 1))
            offset = finish + (size & 1)
        if offset != end:
            raise ValueError('truncated WebP chunk header or padding')
        if vp8x and not (vp8 or vp8l):
            raise ValueError('WebP VP8X header has no VP8 or VP8L image payload')
        if vp8x:
            return vp8x[0], vp8x[1], 'webp', vp8x[2]
        if vp8l:
            return vp8l[0], vp8l[1], 'webp', vp8l[2]
        if vp8:
            return vp8[0], vp8[1], 'webp', vp8[2]
        raise ValueError('WebP dimensions not found in supported VP8, VP8L, or VP8X chunk')
    raise ValueError('unsupported or invalid image header; supported formats are PNG, JPEG, and WebP')


def _object_for(refs, value):
    pair = refs.get(value) if value else None
    return pair[1] if isinstance(pair, tuple) else pair


def _palette_result(path, guide, ctx):
    try:
        pillow = ctx.tools('pillow')
    except Exception:
        pillow = None
    if not pillow:
        return Result('art2d-palette', 'NOT_AVAILABLE', ['Pillow is unavailable; palette and transparency coverage were not inspected'])
    colors = [entry.get('hex', '').upper() for entry in _spec(guide or {}).get('palette', []) if isinstance(entry, dict)]
    if not colors:
        return Result('art2d-palette', 'NOT_AVAILABLE', ['art direction declares no palette colors to compare'])
    try:
        from PIL import Image
        with Image.open(path) as image:
            used = {'#%02X%02X%02X' % color[:3] for color in image.convert('RGBA').getdata()}
        allowed = {c[:7] for c in colors}
        extra = sorted(used - allowed)
        if extra:
            return Result('art2d-palette', 'FAIL', ['image uses colors outside the declared palette: ' + ', '.join(extra[:8])])
        return Result('art2d-palette', 'PASS')
    except Exception as exc:
        return Result('art2d-palette', 'NOT_AVAILABLE', ['Pillow could not inspect the image: ' + str(exc)])


def check(artifact, ctx):
    kind = artifact.get('kind')
    status = artifact.get('status')
    spec = _spec(artifact)
    results = []
    if kind in ('concept-2d', 'reference-2d'):
        if not artifact.get('schema_version') or not isinstance(artifact.get('sources'), list) or not isinstance(artifact.get('authors'), list):
            results.append(Result('art2d-metadata', 'FAIL', ['schema_version, sources, and authors metadata are required']))
        else:
            results.append(Result('art2d-metadata', 'PASS'))
        if status in ('verified', 'released'):
            results.append(Result('art2d-deliverable-state', 'FAIL', [kind + ' is not a production deliverable and cannot be ' + status]))
        else:
            results.append(Result('art2d-deliverable-state', 'PASS'))
        consumers = []
        for _, obj in ctx.artifacts.values():
            if obj.get('id') == artifact.get('id') or obj.get('kind') not in ('asset-spec-2d', 'runtime-export-2d'):
                continue
            if any((x if isinstance(x, str) else x.get('id')) == artifact.get('id') for x in obj.get('sources', []) + obj.get('upstream', [])):
                consumers.append(obj.get('id'))
        if consumers:
            results.append(Result('art2d-not-deliverable-source', 'FAIL', ['concept/reference used as production input by ' + ', '.join(consumers)]))
    if kind not in ('asset-spec-2d', 'runtime-export-2d'):
        return results
    direction = spec.get('art_direction_id') or artifact.get('art_direction_id')
    refs = ctx.artifacts
    guide = _object_for(refs, direction)
    if not direction or not guide or guide.get('kind') != 'art-direction-2d':
        results.append(Result('art2d-direction', 'FAIL', ['asset must reference an existing art-direction-2d artifact id']))
    else:
        results.append(Result('art2d-direction', 'PASS'))
    if kind == 'asset-spec-2d':
        exports = [obj for _, obj in refs.values() if obj.get('kind') == 'runtime-export-2d' and _spec(obj).get('asset_spec_id') == artifact.get('id')]
        usable = []
        details = []
        for export in exports:
            check_rows = check(export, ctx)
            integrity = next((row for row in check_rows if row.check == 'art2d-export-integrity'), None)
            if integrity and integrity.state == 'PASS':
                usable.append(export)
            elif integrity:
                details.extend(integrity.reasons)
        results.append(Result('art2d-runtime-export', 'PASS' if usable else 'FAIL', [] if usable else ['asset spec requires at least one existing runtime export with matching metadata'] + details))
        return results
    path_value = spec.get('file_path') or spec.get('path')
    repo_key = spec.get('repo')
    repo = ctx.registry.get('repos', {}).get(repo_key, {}) if repo_key else {}
    # Repository roots are supplied by the caller's artifact set as optional roots.
    root = ctx.registry.get('_repo_roots', {}).get(repo_key)
    if not root and repo_key == 'authoring':
        root = ctx.repo
    repo_roots = getattr(ctx, 'repo_roots', {})
    if not root and repo_key:
        root = repo_roots.get(repo_key)
    full = (Path(root) / Path(path_value)) if root and path_value else None
    try:
        if not path_value or not repo or not full or not full.is_file():
            raise ValueError('runtime export file path/repo is missing, unregistered, or does not exist in the registered repo')
        resolved_root = Path(root).resolve()
        full = full.resolve()
        if not full.is_relative_to(resolved_root):
            raise ValueError('runtime export path escapes the registered repository root')
        w, h, fmt, alpha = _dimensions(full)
        declared = spec.get('dimensions') if isinstance(spec.get('dimensions'), dict) else {}
        mismatch = []
        if declared.get('width') != w or declared.get('height') != h:
            mismatch.append('declared dimensions do not match image header')
        if str(spec.get('format', '')).lower().replace('jpeg', 'jpg') not in (fmt, fmt.replace('jpeg', 'jpg')):
            mismatch.append('declared format does not match image header')
        if bool(spec.get('alpha')) != alpha:
            mismatch.append('declared alpha does not match image header')
        expected = spec.get('sha256') or artifact.get('hash')
        actual = hashlib.sha256(full.read_bytes()).hexdigest()
        if not expected or expected.lower() != actual:
            mismatch.append('declared SHA-256 is missing or does not match file')
        direction_spec = _spec(guide or {})
        pattern = direction_spec.get('naming_pattern') or r'^[a-z0-9]+_[a-z0-9]+_[a-z0-9]+_[a-z0-9]+$'
        basename = PurePosixPath(str(path_value).replace('\\', '/')).stem
        try:
            name_ok = re.fullmatch(pattern, basename)
        except re.error as exc:
            raise ValueError('art direction naming pattern is invalid: ' + str(exc))
        if not name_ok:
            mismatch.append('filename does not match art-direction naming convention/default domain_category_name_variant')
        frames = spec.get('animation') or {}
        if frames:
            fw, fh, count = frames.get('frame_width'), frames.get('frame_height'), frames.get('frame_count')
            if not all(isinstance(x, int) and x > 0 for x in (fw, fh, count)) or w != fw * count or h != fh:
                mismatch.append('sprite sheet dimensions must equal frame_count x frame_width by frame_height')
        atlas = spec.get('atlas') or {}
        if atlas.get('power_of_two') and (w & (w - 1) or h & (h - 1)):
            mismatch.append('atlas requires power-of-two dimensions')
        if (atlas.get('max_width') and w > atlas['max_width']) or (atlas.get('max_height') and h > atlas['max_height']):
            mismatch.append('image exceeds declared atlas bounds')
        results.append(Result('art2d-export-integrity', 'FAIL' if mismatch else 'PASS', mismatch))
        results.append(_palette_result(full, guide, ctx))
    except (OSError, ValueError, struct.error) as exc:
        results.append(Result('art2d-export-file', 'FAIL', [str(exc)]))
        results.append(Result('art2d-export-integrity', 'FAIL', [str(exc)]))
    return results
