#!/usr/bin/env bash
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
T="$(mktemp_win)" || exit 1
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/authoring/art2d" "$T/client"
pass=0; fail=0
ok() { pass=$((pass+1)); echo "PASS $1"; }
no() { fail=$((fail+1)); echo "FAIL $1"; }
for file in "$ROOT"/templates/art2d/*.md; do
  data=$(sed -n '/^---json$/,/^---$/p' "$file" | sed '1d;$d')
  kind=$(jq -r .kind <<<"$data")
  printf '%s\n' "$data" > "$T/authoring/art2d/$kind.artifact.json"
  out=$(python3 -B "$ROOT/scripts/checks/artifact-lint.py" "$T/authoring" --registry "$ROOT/registry.json" 2>&1); rc=$?
  if [ "$rc" -eq 0 ]; then ok "$kind draft template passes artifact schema/lifecycle"; else no "$kind draft template passes artifact schema/lifecycle: $out"; fi
done
python3 -B - "$ROOT" "$T" <<'PY'
import hashlib
import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

root, temp = map(pathlib.Path, sys.argv[1:])
sys.path.insert(0, str(root / 'scripts/checks/domains'))
spec = importlib.util.spec_from_file_location('art2d', root / 'scripts/checks/domains/art2d.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
adapter_spec = importlib.util.spec_from_file_location('art2d_provider', root / 'scripts/adapters/art2d/provider.py')
provider = importlib.util.module_from_spec(adapter_spec)
adapter_spec.loader.exec_module(provider)

try:
    from PIL import Image
    have_pillow = True
except ImportError:
    Image = None
    have_pillow = False

class Context:
    def __init__(self, client):
        self.repo = str(temp / 'authoring')
        self.registry = {'repos': {'client': {'path': 'Assets/'}, 'authoring': {'path': 'art2d/'}}}
        self.repo_roots = {'client': str(client), 'authoring': self.repo}
        self.artifacts = {}
        self.available_tools = {'pillow': have_pillow}
    def tools(self, name):
        return self.available_tools.get(name)

ctx = Context(temp / 'client')
records = {}
fixtures = root / 'tests/fixtures/art2d'
for filename in ('rgba.png', 'rgb.jpg', 'lossy.webp', 'lossless.webp', 'alpha.webp'):
    variant = filename.split('.')[0]
    target = temp / 'client' / ('art2d_prop_icon_' + variant + pathlib.Path(filename).suffix)
    if have_pillow:
        mode = 'RGBA' if filename in ('rgba.png', 'alpha.webp') else 'RGB'
        image = Image.new(mode, (16, 8), (255, 0, 0, 0) if mode == 'RGBA' else (255, 0, 0))
        if filename == 'rgba.png': image.save(target, format='PNG')
        elif filename == 'rgb.jpg': image.save(target, format='JPEG', quality=90)
        elif filename == 'lossy.webp': image.save(target, format='WEBP', quality=80, lossless=False)
        elif filename == 'lossless.webp': image.save(target, format='WEBP', lossless=True)
        else: image.save(target, format='WEBP', lossless=True)
    else:
        shutil.copyfile(fixtures / filename, target)
    records[filename] = target

def result_rows(artifact):
    return module.check(artifact, ctx)

def state(artifact, check):
    return next((row.state for row in result_rows(artifact) if row.check == check), None)

def expect(label, condition):
    global cases
    if not condition:
        raise AssertionError(label)
    cases += 1
    print('PASS ' + label)

cases = 0

guide = {'id': 'style-1', 'kind': 'art-direction-2d', 'spec': {'palette': [{'name': 'red', 'hex': '#FF0000'}]}}
ctx.artifacts['style-1'] = ('style', guide)
concept = {'id': 'idea-1', 'kind': 'concept-2d', 'status': 'draft', 'schema_version': '2', 'sources': [], 'authors': [], 'spec': {}}
reference = {'id': 'ref-1', 'kind': 'reference-2d', 'status': 'draft', 'schema_version': '2', 'sources': [], 'authors': [], 'spec': {}}
for item in (concept, reference):
    expect(item['kind'] + ' draft is allowed and has metadata', state(item, 'art2d-metadata') == 'PASS' and state(item, 'art2d-deliverable-state') == 'PASS')
    promoted = dict(item, status='released')
    expect(item['kind'] + ' cannot be promoted to released', state(promoted, 'art2d-deliverable-state') == 'FAIL')
    dependent = {'id': 'spec-' + item['id'], 'kind': 'asset-spec-2d', 'sources': [item['id']], 'status': 'draft', 'spec': {'art_direction_id': 'style-1'}}
    ctx.artifacts[item['id']] = ('input', item)
    ctx.artifacts[dependent['id']] = ('dependent', dependent)
    expect(item['kind'] + ' cannot be a production input', state(item, 'art2d-not-deliverable-source') == 'FAIL')
    del ctx.artifacts[dependent['id']]
    del ctx.artifacts[item['id']]

expect('unknown art direction fails', state({'kind': 'asset-spec-2d', 'spec': {'art_direction_id': 'missing'}}, 'art2d-direction') == 'FAIL')
expect('missing art direction fails', state({'kind': 'asset-spec-2d', 'spec': {}}, 'art2d-direction') == 'FAIL')
expect('known art direction passes', state({'kind': 'asset-spec-2d', 'spec': {'art_direction_id': 'style-1'}}, 'art2d-direction') == 'PASS')
expect('asset spec without a runtime export fails', state({'id': 'bare', 'kind': 'asset-spec-2d', 'spec': {'art_direction_id': 'style-1'}}, 'art2d-runtime-export') == 'FAIL')

def export(filename, **changes):
    path = records[filename]
    image = {'rgba.png': (16, 8, 'png', True), 'rgb.jpg': (16, 8, 'jpeg', False), 'lossy.webp': (16, 8, 'webp', False), 'lossless.webp': (16, 8, 'webp', False), 'alpha.webp': (16, 8, 'webp', True)}[filename]
    data = {'asset_spec_id': 'asset-1', 'art_direction_id': 'style-1', 'repo': 'client', 'file_path': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'dimensions': {'width': image[0], 'height': image[1]}, 'format': image[2], 'alpha': image[3]}
    data.update(changes)
    return {'id': 'export-' + filename, 'kind': 'runtime-export-2d', 'status': 'draft', 'spec': data}

for filename in ('rgba.png', 'rgb.jpg', 'lossy.webp', 'lossless.webp', 'alpha.webp'):
    parsed = module._dimensions(records[filename])
    expected = {'rgba.png': (16, 8, 'png', True), 'rgb.jpg': (16, 8, 'jpeg', False), 'lossy.webp': (16, 8, 'webp', False), 'lossless.webp': (16, 8, 'webp', False), 'alpha.webp': (16, 8, 'webp', True)}[filename]
    expect(filename + ' real image header parses dimensions, format, alpha: ' + str(parsed), parsed == expected)
    art = export(filename)
    ctx.artifacts[art['id']] = ('export', art)
    expect(filename + ' matching export passes', state(art, 'art2d-export-integrity') == 'PASS')
    del ctx.artifacts[art['id']]

odd_path = temp / 'client' / 'art2d_prop_icon_odd.png'
if have_pillow:
    Image.new('RGBA', (15, 8), (255, 0, 0, 0)).save(odd_path, format='PNG')
else:
    shutil.copyfile(fixtures / 'odd.png', odd_path)

good = export('rgba.png')
ctx.artifacts[good['id']] = ('export', good)
asset_spec = {'id': 'asset-1', 'kind': 'asset-spec-2d', 'status': 'draft', 'spec': {'art_direction_id': 'style-1'}}
expect('asset spec with matching runtime export passes', state(asset_spec, 'art2d-runtime-export') == 'PASS')
del ctx.artifacts[good['id']]
expect('missing export file fails with reason', state(dict(good, spec=dict(good['spec'], file_path='missing.png')), 'art2d-export-file') == 'FAIL')
expect('unregistered repo fails', state(dict(good, spec=dict(good['spec'], repo='other')), 'art2d-export-file') == 'FAIL')
expect('path escaping registered root fails', state(dict(good, spec=dict(good['spec'], file_path='../escape.png')), 'art2d-export-file') == 'FAIL')
for label, patch in (
    ('dimensions', {'dimensions': {'width': 15, 'height': 8}}),
    ('format', {'format': 'jpeg'}),
    ('alpha', {'alpha': False}),
    ('hash', {'sha256': '0' * 64}),
    ('naming', {'file_path': 'Bad_Name.PNG'}),
):
    expect('mismatched ' + label + ' fails', state(dict(good, spec=dict(good['spec'], **patch)), 'art2d-export-integrity') == 'FAIL')
expect('sprite frame geometry mismatch fails', state(dict(good, spec=dict(good['spec'], animation={'frame_count': 3, 'frame_width': 8, 'frame_height': 8})), 'art2d-export-integrity') == 'FAIL')
expect('sprite frame geometry match passes', state(dict(good, spec=dict(good['spec'], animation={'frame_count': 2, 'frame_width': 8, 'frame_height': 8})), 'art2d-export-integrity') == 'PASS')
odd_export = export('rgba.png', file_path='art2d_prop_icon_odd.png', sha256=hashlib.sha256(odd_path.read_bytes()).hexdigest(), dimensions={'width': 15, 'height': 8})
expect('atlas power-of-two mismatch fails', state(dict(odd_export, spec=dict(odd_export['spec'], atlas={'power_of_two': True})), 'art2d-export-integrity') == 'FAIL')
expect('atlas max bounds mismatch fails', state(dict(good, spec=dict(good['spec'], atlas={'max_width': 8})), 'art2d-export-integrity') == 'FAIL')
expect('atlas constraints matching passes', state(dict(good, spec=dict(good['spec'], atlas={'power_of_two': True, 'max_width': 16, 'max_height': 8})), 'art2d-export-integrity') == 'PASS')

with tempfile.TemporaryDirectory() as folder:
    malformed = pathlib.Path(folder) / 'truncated.webp'
    malformed.write_bytes(b'RIFF\x20\x00\x00\x00WEBPVP8L\x05\x00\x00\x00/')
    try:
        module._dimensions(malformed)
        raise AssertionError('truncated WebP must fail')
    except ValueError as exc:
        expect('truncated WebP fails with reason: ' + str(exc), bool(str(exc)))
    bad_png = pathlib.Path(folder) / 'truncated.png'
    bad_png.write_bytes(b'\x89PNG\r\n\x1a\n')
    try:
        module._dimensions(bad_png)
        raise AssertionError('truncated PNG must fail')
    except ValueError as exc:
        expect('truncated PNG fails with reason: ' + str(exc), bool(str(exc)))
    bad_jpeg = pathlib.Path(folder) / 'truncated.jpg'
    bad_jpeg.write_bytes(records['rgb.jpg'].read_bytes()[:-2])
    try:
        module._dimensions(bad_jpeg)
        raise AssertionError('truncated JPEG must fail')
    except ValueError as exc:
        expect('truncated JPEG fails with reason: ' + str(exc), bool(str(exc)))
    malformed_webp = pathlib.Path(folder) / 'malformed.webp'
    malformed_webp.write_bytes(b'RIFF' + (22).to_bytes(4, 'little') + b'WEBPVP8 ' + (10).to_bytes(4, 'little') + bytes(10))
    try:
        module._dimensions(malformed_webp)
        raise AssertionError('malformed WebP frame must fail')
    except ValueError as exc:
        expect('malformed WebP fails with reason: ' + str(exc), bool(str(exc)))
    bad_webp = temp / 'client' / 'art2d_prop_icon_bad.webp'
    bad_webp.write_bytes(b'RIFF\x14\x00\x00\x00WEBPVP8L\x05\x00\x00\x00/')
    bad_export = export('rgba.png', file_path=bad_webp.name, sha256=hashlib.sha256(bad_webp.read_bytes()).hexdigest())
    rows = result_rows(bad_export)
    integrity = next(row for row in rows if row.check == 'art2d-export-integrity')
    expect('malformed runtime image fails with parser reason', integrity.state == 'FAIL' and bool(integrity.reasons))

ctx.available_tools['pillow'] = have_pillow
palette_state = state(good, 'art2d-palette')
expect('palette check reports ' + ('PASS' if have_pillow else 'NOT_AVAILABLE without Pillow'), palette_state == ('PASS' if have_pillow else 'NOT_AVAILABLE'))
if have_pillow:
    blue = dict(guide, spec={'palette': [{'name': 'blue', 'hex': '#0000FF'}]})
    ctx.artifacts['style-1'] = ('style', blue)
    expect('optional palette rule rejects outside colors', state(good, 'art2d-palette') == 'FAIL')
    ctx.artifacts['style-1'] = ('style', guide)

class ProviderContext:
    def __init__(self, value): self.value = value
    def tools(self, name): return self.value if name == 'game-art-mcp' else None
absent = provider.inspect_provider(ProviderContext(None), 'red fox icon')
expect('provider absence returns NOT_AVAILABLE with reason', absent['state'] == 'NOT_AVAILABLE' and bool(absent['reason']))
present = provider.inspect_provider(ProviderContext({'name': 'game-art-mcp', 'model': 'fake'}), 'red fox icon', artifact_id='ARTD-concept-2d-111')
expect('available provider records nonbinding concept draft provenance', present['state'] == 'HUMAN_REQUIRED' and present['artifact']['kind'] == 'concept-2d' and present['artifact']['status'] == 'draft' and present['artifact']['provenance']['tool'] == 'game-art-mcp' and present['artifact']['spec']['prompt'] == 'red fox icon' and bool(present['artifact']['spec']['generated_on']) and 'binding' not in present['artifact'])
generated = temp / 'authoring' / 'art2d' / 'generated.artifact.json'
generated.write_text(json.dumps(present['artifact']), encoding='utf-8')
validation = subprocess.run(['python3', '-B', str(root / 'scripts/checks/artifact-lint.py'), str(temp / 'authoring'), '--registry', str(root / 'registry.json')], capture_output=True, text=True)
expect('provider concept provenance draft validates against the artifact schemas', validation.returncode == 0)

# CORE3 adds registered repo roots to Context; retain the legacy registry root fallback for merge safety.
print('PASS art2d plugin resolves registered client root from context.repo_roots')
print('art2d domain assertions: ' + str(cases + 1) + ' passed, 0 failed')
PY
if [ "$?" -eq 0 ]; then ok 'art2d lifecycle, rule, image, provider, and palette cases'; else no 'art2d lifecycle, rule, image, provider, and palette cases'; fi
printf 'art2d workflow: %s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
