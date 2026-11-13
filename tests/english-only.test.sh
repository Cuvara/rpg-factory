#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C.UTF-8  # printf %b only expands \uXXXX in a UTF-8 locale (CI runners default to C/POSIX)
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d "${RPG_FACTORY_STATE_DIR:-${TMPDIR:-/tmp}}/english-only.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/docs" "$TMP/tests/fixtures" "$TMP/scripts/checks" "$TMP/scripts/lib"
# the check imports the shared detection from ../lib: copy both so the frozen layout resolves it
cp "$ROOT/scripts/checks/english-only.py" "$TMP/scripts/checks/english-only.py"
cp "$ROOT/scripts/lib/english.py" "$TMP/scripts/lib/english.py"
CHECK="$TMP/scripts/checks/english-only.py"
printf '%b\n' 'Plain English \u2192 arrow \u2014 dash \u2264 limit' > "$TMP/README.md"
printf '%b\n' 'Ti\u1ebfng Vi\u1ec7t c\u1ea7n ki\u1ec3m tra' '\u6c49\u5b57 sample' > "$TMP/docs/sample.md"
printf '{"description":"\\u65e5\\u672c\\u8a9e"}\n' > "$TMP/registry.json"
: > "$TMP/tests/fixtures/english-allow.txt"
report=$(python3 -B "$CHECK" --root "$TMP" --report)
[[ "$report" == *"docs/sample.md:1:"* && "$report" == *"docs/sample.md:2:"* && "$report" == *"registry.json:1:"* ]] || { echo "FAIL report missed Unicode findings"; echo "$report"; exit 1; }
[[ "$report" == *"3 findings"* ]] || { echo "FAIL unexpected report count"; echo "$report"; exit 1; }
set +e
python3 -B "$CHECK" --root "$TMP" --enforce >/dev/null
rc=$?
set -e
[[ "$rc" -eq 1 ]] || { echo "FAIL enforce exit=$rc, expected 1"; exit 1; }
printf 'docs/sample.md:1 # approved fixture text\nregistry.json:* # registry fixture\n' > "$TMP/tests/fixtures/english-allow.txt"
clean=$(python3 -B "$CHECK" --root "$TMP" --report)
[[ "$clean" == *"1 findings"* && "$clean" != *"docs/sample.md:1:"* && "$clean" != *"registry.json:1:"* ]] || { echo "FAIL allowlist did not suppress entries"; echo "$clean"; exit 1; }
set +e
python3 -B "$CHECK" --root "$TMP" --enforce >/dev/null
rc=$?
set -e
[[ "$rc" -eq 1 ]] || { echo "FAIL enforce with remaining CJK exit=$rc, expected 1"; exit 1; }
printf '%b\n' 'Plain English \u2192 arrow \u2014 dash \u2264 limit' > "$TMP/docs/sample.md"
printf '{"description":"English words"}\n' > "$TMP/registry.json"
clean=$(python3 -B "$CHECK" --root "$TMP" --enforce)
[[ "$clean" == *"0 findings"* ]] || { echo "FAIL clean English rejected"; echo "$clean"; exit 1; }
# shared module scripts/lib/english.py (also used by file-guard and git-guard): detection, threshold, allowlist loader
python3 -B - "$ROOT/scripts/lib" "$TMP" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import english

bad = []
def check(label, ok):
    if not ok:
        bad.append(label)

viet = "Ti\u1ebfng Vi\u1ec7t c\u1ea7n ki\u1ec3m tra"
check("vietnamese trips", english.classify(viet) != [] and english.first_offending_line(viet) == (1, viet))
check("cjk trips as non-Latin", english.classify("\u6c49\u5b57 sample")[0].startswith("non-Latin letters: CJK UNIFIED IDEOGRAPH-"))
check("cyrillic trips", english.classify("\u043f\u0440\u0438\u0432\u0435\u0442 world") != [])
check("plain english passes", english.classify("Plain English text, nothing else.") == [])
check("code passes", english.classify("def f(x): return x + 1  # ok; a_b = {'k': [1, 2]}") == [])
check("symbols are not letters", english.classify("arrow \u2192 dash \u2014 limit \u2264 sign \u00a7 bullet \u2022") == [])
check("one accented letter passes (needs two)", english.classify("a caf\u00e9 menu") == [])
check("two accented letters in short text trip", english.classify("r\u00e9sum\u00e9") != [])
# 5 percent threshold: 100 letters with 5 non-ASCII Latin sits on the boundary (trips), 105 letters with 5 stays below it
at = "a" * 95 + "\u00e9" * 5
below = "a" * 100 + "\u00e9" * 5
over = "a" * 94 + "\u00e9" * 6
check("exactly 5 percent trips", english.classify(at) != [])
check("4.8 percent passes", english.classify(below) == [])
check("6 percent trips", english.classify(over) != [])
check("reason text names the ratio", english.classify(at) == ["non-ASCII Latin letters: 5/100"])
text = "first line is English\nsecond line is fine\n" + viet + "\nlast"
check("first offending line number", english.first_offending_line(text) == (3, viet))
check("english block has none", english.first_offending_line("one\ntwo\nthree\n") is None)
check("empty text has none", english.first_offending_line("") is None)
check("ascii fast path has none", english.first_offending_line("def f():\n    return 1\n") is None)
# allowlist loader
from pathlib import Path
allow = Path(sys.argv[2]) / "allow-shared.txt"
allow.write_text("# comment\n\ndocs/a.md:3 # fixture\ndocs/b.md:* # whole file\n", encoding="utf-8")
check("allowlist parses entries", english.allowlist(allow) == {"docs/a.md:3": "fixture", "docs/b.md:*": "whole file"})
check("missing allowlist is empty", english.allowlist(Path(sys.argv[2]) / "absent.txt") == {})
allow.write_text("docs/a.md:3 missing reason\n", encoding="utf-8")
try:
    english.allowlist(allow)
    check("malformed allowlist raises", False)
except ValueError:
    pass
if bad:
    print("FAIL shared module: " + "; ".join(bad))
    sys.exit(1)
PY
echo "PASS english-only: Vietnamese and CJK findings, report/enforce, allowlist, registry strings, allowed symbols, shared module (threshold, fast path, allowlist loader)"
