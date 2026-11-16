#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d "${RPG_FACTORY_STATE_DIR:-${TMPDIR:-/tmp}}/portable-paths.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/tests/fixtures" "$TMP/docs/plans"
git -C "$TMP" init -q
CHECK="$ROOT/scripts/checks/portable-paths.py"
printf '{"workspace":{"root_default":"/home/workspaceowner/project"}}\n' > "$TMP/registry.json"
: > "$TMP/tests/fixtures/portable-paths-allow.txt"
python3 - "$TMP" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
s = '/'
b = chr(92)
home = 'Users'
name = 'alice'
bad = [
    'C:' + s + home + s + name + s + 'repo',
    'C:' + b + home + b + name + b + 'repo',
    'C:' + b*2 + home + b*2 + name + b*2 + 'repo',
    s + 'c' + s + home + s + name,
    s + 'mnt' + s + 'c' + s + home + s + name,
    s + 'home' + s + name,
    s + home + s + name,
    'C:' + s + home + s + name + s + 'AppData' + s + 'Local',
    'C:' + s + home + s + name + s + 'AppData' + s + 'Roaming',
    'C:' + s + home + s + name + s + 'AppData' + s + 'LocalLow',
    'C:' + s + 'tmp' + s + 'repo',
    'D:' + b + 'temp' + b + 'repo',
    'E:' + b*2 + 'tmp' + b*2 + 'repo',
]
good = ['%APPDATA%', '%USERPROFILE%', '$HOME', '${HOME}', '~', '$env:LOCALAPPDATA',
        'https://example.org/home/alice/repo', 'http://example.org/Users/alice',
        '/home/workspaceowner/project/child', '/home/', '/Users/']
good += ['C:' + s + home + s + n + s + 'repo' for n in
         ['person', 'example', 'user', 'username', 'name', 'me', 'you', 'someone',
          'runner', 'runneradmin', 'RUNNER~1', 'x', '<name>', '<user>', '{user}', '$USER', '...']]
(root / 'bad.txt').write_text('\n'.join(bad) + '\n', encoding='utf-8')
(root / 'good.txt').write_text('\n'.join(good) + '\n', encoding='utf-8')
(root / 'docs/plans/skip.md').write_text(bad[0] + '\n', encoding='utf-8')
PY
git -C "$TMP" add .
report=$(python3 -B "$CHECK" --root "$TMP" --report)
for n in {1..13}; do
  [[ "$report" == *"bad.txt:$n: "* ]] || { echo "FAIL missing bad line $n: $report"; exit 1; }
done
[[ "$report" != *"good.txt:"* && "$report" != *"docs/plans/skip.md:"* ]] || { echo "FAIL allowed input: $report"; exit 1; }
set +e
python3 -B "$CHECK" --root "$TMP" --enforce >/dev/null
rc=$?
set -e
[[ $rc -eq 1 ]] || { echo "FAIL enforce finding exit $rc"; exit 1; }
printf 'bad.txt # Fixture deliberately contains paths.\n' > "$TMP/tests/fixtures/portable-paths-allow.txt"
python3 -B "$CHECK" --root "$TMP" --enforce >/dev/null
printf 'bad.txt:AppData # Suppress only application data.\n' > "$TMP/tests/fixtures/portable-paths-allow.txt"
report=$(python3 -B "$CHECK" --root "$TMP")
[[ "$report" != *"bad.txt:8:"* && "$report" == *"bad.txt:1:"* ]] || { echo "FAIL regex allowlist: $report"; exit 1; }
printf 'bad.txt\n' > "$TMP/tests/fixtures/portable-paths-allow.txt"
set +e
python3 -B "$CHECK" --root "$TMP" >/dev/null 2>&1
rc=$?
set -e
[[ $rc -eq 2 ]] || { echo "FAIL invalid allowlist exit $rc"; exit 1; }
printf 'bad.txt # Fixture deliberately contains paths.\n' > "$TMP/tests/fixtures/portable-paths-allow.txt"
printf '{"workspace":{"root_default":"/home/anotherowner/project"}}\n' > "$TMP/registry.json"
set +e
report=$(python3 -B "$CHECK" --root "$TMP" --enforce)
rc=$?
set -e
[[ $rc -eq 1 && "$report" == *"good.txt:9:"* ]] || { echo "FAIL changed workspace: $report"; exit 1; }
# A drive-based registry default permits each platform spelling and descendants.
python3 - "$TMP" <<'PYCODE'
from pathlib import Path
import json, sys
root = Path(sys.argv[1])
slash = '/'
backslash = chr(92)
base = 'Users' + slash + 'workspaceowner' + slash + 'project'
(root / 'registry.json').write_text(json.dumps({'workspace': {'root_default': 'C:' + slash + base}}))
(root / 'good.txt').write_text('\n'.join(['C:' + slash + base + slash + 'child',
    'C:' + backslash + base.replace(slash, backslash) + backslash + 'child',
    slash + 'c' + slash + base + slash + 'child',
    slash + 'mnt' + slash + 'c' + slash + base + slash + 'child']) + '\n')
PYCODE
python3 -B "$CHECK" --root "$TMP" --enforce >/dev/null
echo 'PASS portable-paths fixture cases'
