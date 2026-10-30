#!/usr/bin/env bash
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
T="$(mktemp_win)"; trap 'rm -rf "$T"' EXIT
python3 - "$T" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]); good={'id':'A2D-sprite-001','kind':'art2d-asset','domain':'art2d','status':'draft','source_uri':'https://example.test/sprite','hash':'abc123','license':'CC0-1.0','provenance':'library','delivery':{'repo':'client','path':'Assets/Art/sprite.png'}}
(p/'good.asset.json').write_text(json.dumps(good)); bad=dict(good); bad['license']=''; bad['delivery']={'repo':'authoring','path':'../../outside'}; (p/'bad.asset.json').write_text(json.dumps(bad))
PY
python3 -B "$ROOT/scripts/checks/asset-manifest.py" "$T/good.asset.json" --registry "$ROOT/registry.json" | grep -q '^asset-manifest: 1 checked, 1 passed, 0 failed' || exit 1
result=$(python3 -B "$ROOT/scripts/checks/asset-manifest.py" "$T/bad.asset.json" --registry "$ROOT/registry.json" 2>&1); rc=$?
if [ $rc -ne 0 ] && grep -q 'delivery path must stay inside' <<<"$result" && grep -q 'license must be non-empty' <<<"$result"; then echo 'PASS rejects missing license and escaping delivery path'; else echo 'FAIL bad manifest accepted'; exit 1; fi
echo 'asset-manifest tests: 2 run, 2 passed, 0 failed'
