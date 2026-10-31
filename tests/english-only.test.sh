#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C.UTF-8  # printf %b only expands \uXXXX in a UTF-8 locale (CI runners default to C/POSIX)
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d "${RPG_FACTORY_STATE_DIR:-${TMPDIR:-/tmp}}/english-only.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/docs" "$TMP/tests/fixtures"
cp "$ROOT/scripts/checks/english-only.py" "$TMP/english-only.py"
printf '%b\n' 'Plain English \u2192 arrow \u2014 dash \u2264 limit' > "$TMP/README.md"
printf '%b\n' 'Ti\u1ebfng Vi\u1ec7t c\u1ea7n ki\u1ec3m tra' '\u6c49\u5b57 sample' > "$TMP/docs/sample.md"
printf '{"description":"\\u65e5\\u672c\\u8a9e"}\n' > "$TMP/registry.json"
: > "$TMP/tests/fixtures/english-allow.txt"
report=$(python3 -B "$TMP/english-only.py" --root "$TMP" --report)
[[ "$report" == *"docs/sample.md:1:"* && "$report" == *"docs/sample.md:2:"* && "$report" == *"registry.json:1:"* ]] || { echo "FAIL report missed Unicode findings"; echo "$report"; exit 1; }
[[ "$report" == *"3 findings"* ]] || { echo "FAIL unexpected report count"; echo "$report"; exit 1; }
set +e
python3 -B "$TMP/english-only.py" --root "$TMP" --enforce >/dev/null
rc=$?
set -e
[[ "$rc" -eq 1 ]] || { echo "FAIL enforce exit=$rc, expected 1"; exit 1; }
printf 'docs/sample.md:1 # approved fixture text\nregistry.json:* # registry fixture\n' > "$TMP/tests/fixtures/english-allow.txt"
clean=$(python3 -B "$TMP/english-only.py" --root "$TMP" --report)
[[ "$clean" == *"1 findings"* && "$clean" != *"docs/sample.md:1:"* && "$clean" != *"registry.json:1:"* ]] || { echo "FAIL allowlist did not suppress entries"; echo "$clean"; exit 1; }
set +e
python3 -B "$TMP/english-only.py" --root "$TMP" --enforce >/dev/null
rc=$?
set -e
[[ "$rc" -eq 1 ]] || { echo "FAIL enforce with remaining CJK exit=$rc, expected 1"; exit 1; }
printf '%b\n' 'Plain English \u2192 arrow \u2014 dash \u2264 limit' > "$TMP/docs/sample.md"
printf '{"description":"English words"}\n' > "$TMP/registry.json"
clean=$(python3 -B "$TMP/english-only.py" --root "$TMP" --enforce)
[[ "$clean" == *"0 findings"* ]] || { echo "FAIL clean English rejected"; echo "$clean"; exit 1; }
echo "PASS english-only: Vietnamese and CJK findings, report/enforce, allowlist, registry strings, allowed symbols"
