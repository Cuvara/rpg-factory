#!/usr/bin/env bash
# Registry facts stay true: every facts[] probe is re-run in a temporary HEAD export and must print
# the recorded value; toolchain "expected" pins must agree with the facts; skills must not
# hard-code volatile values that belong in facts[] or in the live scripts.
set -uo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/compat.sh"
. "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib/workspace.sh"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
R="${RPG_FACTORY_FACTS_REGISTRY:-$ROOT/registry.json}"   # override: the stale-detection self-test below
WS="${RPG_FACTORY_WORKSPACE:-$(rpgf_platform_path "$(jq -r .workspace.root_default "$R")")}"
pass=0; fail=0; skip=0
T="$(mktemp_win)"; trap 'rm -rf "$T"' EXIT
# Only the stale-value self-tests inherit this cache; fixture repos get their own exports.
CACHE="${RPG_FACTORY_FACTS_EXPORT_CACHE:-$T/exports}"
mkdir -p "$CACHE"
declare -A exports gitdirs dirty
while read -r enc; do
  id=$(base64 -d <<<"$enc" | jq -r .id); value=$(base64 -d <<<"$enc" | jq -r .value)
  repo=$(base64 -d <<<"$enc" | jq -r .repo); probe=$(base64 -d <<<"$enc" | jq -r .probe)
  dir="$WS/$(jq -r --arg r "$repo" '.repos[$r].path' "$R")"
  if [ ! -d "$dir" ]; then skip=$((skip + 1)); echo "SKIP  $id (repo $repo not present)"; continue; fi
  if [ -z "${exports[$repo]:-}" ]; then
    export_dir="$CACHE/export-$repo"
    mkdir -p "$export_dir"
    if ! gitdir=$(git -C "$dir" rev-parse --absolute-git-dir 2>/dev/null) ||
       { [ ! -f "$CACHE/ready-$repo" ] &&
         ! (set -o pipefail; git -C "$dir" archive HEAD | tar -xf - -C "$export_dir"); }; then
      fail=$((fail + 1)); echo "FAIL  $id: cannot export committed HEAD for repo $repo"; continue
    fi
    touch "$CACHE/ready-$repo"
    # Every probe gets a disposable index, including live drift probes. Optional locks alone
    # do not protect against an explicit index-writing command such as git update-index.
    # A failed read-tree leaves no usable index: FAIL this fact and skip it (the repo is retried by the next one).
    if ! GIT_DIR="$gitdir" GIT_INDEX_FILE="$T/index-$repo" GIT_OPTIONAL_LOCKS=0 git read-tree HEAD >/dev/null 2>&1; then
      fail=$((fail + 1)); echo "FAIL  $id: cannot read the HEAD tree into the disposable index for repo $repo"; continue
    fi
    exports[$repo]="$export_dir"; gitdirs[$repo]="$gitdir"
    # git archive leaves submodules as empty directories and LFS files as pointers; probes grade that export.
    # Report it (read-only git on HEAD, once per repo) instead of materializing them: the suite stays offline.
    submodules=$(GIT_DIR="$gitdir" GIT_OPTIONAL_LOCKS=0 git ls-tree -r HEAD 2>/dev/null | grep -c '^160000 ' || true)
    lfs=0
    if GIT_DIR="$gitdir" GIT_OPTIONAL_LOCKS=0 git grep -q 'filter=lfs' HEAD -- ':(glob)**/.gitattributes' 2>/dev/null; then
      lfs=$(cd "$export_dir" && GIT_DIR="$gitdir" GIT_WORK_TREE="$export_dir" GIT_INDEX_FILE="$T/index-$repo" GIT_OPTIONAL_LOCKS=0 \
        git ls-tree -r -z --name-only HEAD 2>/dev/null | GIT_DIR="$gitdir" GIT_WORK_TREE="$export_dir" GIT_INDEX_FILE="$T/index-$repo" GIT_OPTIONAL_LOCKS=0 \
        git check-attr -z --stdin --cached filter 2>/dev/null | tr '\0' '\n' | awk 'NR % 3 == 0 && $0 == "lfs" { n++ } END { print n + 0 }')
    fi
    if [ "${submodules:-0}" -gt 0 ] || [ "${lfs:-0}" -gt 0 ]; then
      parts=()
      [ "${submodules:-0}" -gt 0 ] && parts+=("omits $submodules submodule(s) (gitlinks)")
      [ "${lfs:-0}" -gt 0 ] && parts+=("leaves $lfs LFS-tracked file(s) as pointers")
      echo "NOTE  repo $repo: HEAD export ${parts[0]}${parts[1]:+ and ${parts[1]}}; probes grade the committed HEAD without them"
    fi
    dirty[$repo]=0
    if [ -f "$CACHE/dirty-$repo" ]; then
      dirty[$repo]=$(cat "$CACHE/dirty-$repo")
    else
      [ -z "$(GIT_OPTIONAL_LOCKS=0 git -C "$dir" status --porcelain --untracked-files=normal)" ] || dirty[$repo]=1
      printf '%s\n' "${dirty[$repo]}" > "$CACHE/dirty-$repo"
    fi
  fi
  # Keep explicit git-ref probes working, without creating a worktree or touching the source repo.
  got=$(cd "${exports[$repo]}" && GIT_DIR="${gitdirs[$repo]}" GIT_WORK_TREE="${exports[$repo]}" GIT_INDEX_FILE="$T/index-$repo" GIT_OPTIONAL_LOCKS=0 PYTHONDONTWRITEBYTECODE=1 timeout 120 bash -c "$probe" 2>/dev/null | head -1 | tr -d '\r')
  if [ "$got" = "$value" ]; then pass=$((pass + 1)); echo "PASS  $id = $value"
  else fail=$((fail + 1)); echo "FAIL  $id: registry says '$value', repo says '$got' - refresh registry facts (and anything that relies on them)"; fi
  if [ "${dirty[$repo]}" = 1 ]; then
    live=$(cd "$dir" && GIT_INDEX_FILE="$T/index-$repo" GIT_OPTIONAL_LOCKS=0 PYTHONDONTWRITEBYTECODE=1 timeout 120 bash -c "$probe" 2>/dev/null | head -1 | tr -d '\r')
    if [ "$live" != "$got" ]; then echo "NOTE  $id: uncommitted drift (HEAD '$got', working tree '$live'); graded HEAD"; fi
  fi
done < <(jq -r '.facts[] | @base64' "$R")
# toolchain pins agree with facts
for pair in "protoc:protoc-ci-pin" "protoc-gen-go:protoc-gen-go-ci-pin"; do
  tool=${pair%%:*}; fact=${pair##*:}
  exp=$(jq -r --arg t "$tool" '.tools[$t].expected // ""' "$R"); val=$(jq -r --arg f "$fact" '.facts[] | select(.id == $f) | .value' "$R")
  case "$exp" in *"$val"*) pass=$((pass + 1)); echo "PASS  tools.$tool.expected contains fact $fact ($val)";;
    *) fail=$((fail + 1)); echo "FAIL  tools.$tool.expected '$exp' does not contain fact $fact '$val'";; esac
done
# skills carry no volatile values (they drift silently); historical examples are labelled
bad=$(grep -rnE "Total 12|[0-9]+ document\(s\) validated, [1-9]|30 discovered|CIs? (bootstrap|pin) \`?sgl-v[0-9]|currently sgl-v|at \`?5023a3d\`?:|protoc 29\.[0-9]|Google\.Protobuf 3\.[0-9]" "$ROOT/skills" || true)
if [ -z "$bad" ]; then pass=$((pass + 1)); echo "PASS  skills carry no volatile point-in-time values"
else fail=$((fail + 1)); echo "FAIL  volatile values in skills:"; echo "$bad" | head -5; fi
# stale detection: a registry value that no longer matches the repo must FAIL (one fact per repo kind)
if [ -z "${RPG_FACTORY_FACTS_REGISTRY:-}" ]; then
  # A fixture proves HEAD grading, drift reporting, and stale committed-value detection independently
  # of the optional product workspace. The dirty source file must remain untouched.
  mkdir -p "$T/ws/client/ProjectSettings"
  git -C "$T/ws/client" init -q
  printf 'm_EnterPlayModeOptionsEnabled: 1\nm_EnterPlayModeOptions: 0\n' > "$T/ws/client/ProjectSettings/EditorSettings.asset"
  git -C "$T/ws/client" add ProjectSettings/EditorSettings.asset
  git -C "$T/ws/client" -c user.name=Fixture -c user.email=fixture@example.invalid commit -qm fixture
  jq '.facts |= map(select(.id == "enter-playmode-options")) | .repos.client.path = "client"' "$R" > "$T/fixture.json"
  o=$(RPG_FACTORY_WORKSPACE="$T/ws" RPG_FACTORY_FACTS_REGISTRY="$T/fixture.json" bash "$0" 2>&1); rc=$?
  if [ "$rc" -eq 0 ] && grep -q '^PASS  enter-playmode-options = enabled=1 options=0$' <<<"$o" && ! grep -q '^NOTE ' <<<"$o"; then
    pass=$((pass + 1)); echo "PASS  clean fixture grades HEAD without a drift note"
  else fail=$((fail + 1)); echo "FAIL  clean fixture HEAD grading (rc=$rc): $o"; fi
  printf 'm_EnterPlayModeOptionsEnabled: 1\nm_EnterPlayModeOptions: 3\n' > "$T/ws/client/ProjectSettings/EditorSettings.asset"
  o=$(RPG_FACTORY_WORKSPACE="$T/ws" RPG_FACTORY_FACTS_REGISTRY="$T/fixture.json" bash "$0" 2>&1); rc=$?
  if [ "$rc" -eq 0 ] && grep -q '^PASS  enter-playmode-options = enabled=1 options=0$' <<<"$o" &&
     grep -q "^NOTE  enter-playmode-options: uncommitted drift (HEAD 'enabled=1 options=0', working tree 'enabled=1 options=3'); graded HEAD$" <<<"$o" &&
     grep -q '^m_EnterPlayModeOptions: 3$' "$T/ws/client/ProjectSettings/EditorSettings.asset"; then
    pass=$((pass + 1)); echo "PASS  uncommitted fixture drift is noted without failing or changing the source"
  else fail=$((fail + 1)); echo "FAIL  dirty fixture HEAD grading (rc=$rc): $o"; fi
  jq '.facts[0].value = "enabled=1 options=3"' "$T/fixture.json" > "$T/fixture-stale.json"
  o=$(RPG_FACTORY_WORKSPACE="$T/ws" RPG_FACTORY_FACTS_REGISTRY="$T/fixture-stale.json" bash "$0" 2>&1); rc=$?
  if [ "$rc" -ne 0 ] && grep -q "^FAIL  enter-playmode-options: registry says 'enabled=1 options=3', repo says 'enabled=1 options=0'" <<<"$o"; then
    pass=$((pass + 1)); echo "PASS  fixture registry matching only the dirty tree still fails"
  else fail=$((fail + 1)); echo "FAIL  fixture stale HEAD fact not detected (rc=$rc): $o"; fi
  # Exercise index-writing Git commands and explicit refs in both exported and live probes.
  # Hash AND nanosecond mtime catch content changes and refresh-only index rewrites.
  index_stamp() { python3 -B -c 'import hashlib,os,sys;p=sys.argv[1];print(str(os.stat(p).st_mtime_ns)+":"+hashlib.sha256(open(p,"rb").read()).hexdigest())' "$T/ws/client/.git/index"; }
  before=$(index_stamp)
  jq '.facts[0] |= (.id = "index-isolation" | .value = "committed" | .probe = "git update-index --refresh >/dev/null; git status --porcelain >/dev/null; git show HEAD:ProjectSettings/EditorSettings.asset >/dev/null && echo committed")' "$T/fixture.json" > "$T/index.json"
  o=$(RPG_FACTORY_WORKSPACE="$T/ws" RPG_FACTORY_FACTS_REGISTRY="$T/index.json" bash "$0" 2>&1); rc=$?
  if [ "$rc" -eq 0 ] && grep -q '^PASS  index-isolation = committed$' <<<"$o" && [ "$before" = "$(index_stamp)" ]; then
    pass=$((pass + 1)); echo "PASS  exported and live Git probes preserve source index hash and mtime and resolve explicit refs"
  else fail=$((fail + 1)); echo "FAIL  source index isolation or explicit-ref probe (rc=$rc): $o"; fi
  # Only an untracked file differs: tracked-file-only drift checks would miss this note.
  git -C "$T/ws/client" show HEAD:ProjectSettings/EditorSettings.asset > "$T/ws/client/ProjectSettings/EditorSettings.asset"
  printf 'untracked\n' > "$T/ws/client/new-fact.txt"
  jq '.facts[0] |= (.id = "untracked-drift" | .value = "absent" | .probe = "if [ -f new-fact.txt ]; then cat new-fact.txt; else echo absent; fi")' "$T/fixture.json" > "$T/untracked.json"
  before=$(index_stamp)
  o=$(RPG_FACTORY_WORKSPACE="$T/ws" RPG_FACTORY_FACTS_REGISTRY="$T/untracked.json" bash "$0" 2>&1); rc=$?
  if [ "$rc" -eq 0 ] && grep -q '^PASS  untracked-drift = absent$' <<<"$o" &&
     grep -q "^NOTE  untracked-drift: uncommitted drift (HEAD 'absent', working tree 'untracked'); graded HEAD$" <<<"$o" &&
     [ "$(cat "$T/ws/client/new-fact.txt")" = untracked ] && [ "$before" = "$(index_stamp)" ]; then
    pass=$((pass + 1)); echo "PASS  untracked-only fixture drift is noted without changing source or index"
  else fail=$((fail + 1)); echo "FAIL  untracked-only fixture drift (rc=$rc): $o"; fi
  # HEAD export caveats and a failing disposable index, on fixture repos only (never a product repo).
  fixture_repo() {  # $1 dir: one committed ProjectSettings/EditorSettings.asset
    mkdir -p "$1/ProjectSettings"; git -C "$1" init -q
    printf 'm_EnterPlayModeOptionsEnabled: 1\nm_EnterPlayModeOptions: 0\n' > "$1/ProjectSettings/EditorSettings.asset"
    git -C "$1" add ProjectSettings/EditorSettings.asset
  }
  fixture_commit() { git -C "$1" -c user.name=Fixture -c user.email=fixture@example.invalid commit -qm fixture; }
  # A gitlink plus two LFS-tracked files: one NOTE for the repo, naming both counts, and the fact still passes.
  fixture_repo "$T/ws-caveat/client"
  git -C "$T/ws-caveat/client" update-index --add --cacheinfo 160000,1111111111111111111111111111111111111111,vendor/sub
  printf '*.bin filter=lfs diff=lfs merge=lfs -text\n' > "$T/ws-caveat/client/.gitattributes"
  mkdir -p "$T/ws-caveat/client/art"
  printf 'pointer-a\n' > "$T/ws-caveat/client/art/a.bin"; printf 'pointer-b\n' > "$T/ws-caveat/client/b.bin"; printf 'plain\n' > "$T/ws-caveat/client/c.txt"
  git -C "$T/ws-caveat/client" add .gitattributes art/a.bin b.bin c.txt
  fixture_commit "$T/ws-caveat/client"
  o=$(RPG_FACTORY_WORKSPACE="$T/ws-caveat" RPG_FACTORY_FACTS_REGISTRY="$T/fixture.json" bash "$0" 2>&1); rc=$?
  if [ "$rc" -eq 0 ] && grep -q '^PASS  enter-playmode-options = enabled=1 options=0$' <<<"$o" &&
     [ "$(grep -c '^NOTE ' <<<"$o")" = 1 ] &&
     grep -q '^NOTE  repo client: HEAD export omits 1 submodule(s) (gitlinks) and leaves 2 LFS-tracked file(s) as pointers; ' <<<"$o"; then
    pass=$((pass + 1)); echo "PASS  submodule and LFS caveats of the HEAD export are noted once per repo"
  else fail=$((fail + 1)); echo "FAIL  submodule/LFS NOTE (rc=$rc): $o"; fi
  # A submodule only: no LFS part in the NOTE. (The clean fixture above proves a repo with neither prints no NOTE.)
  git -C "$T/ws-caveat/client" rm -q --cached .gitattributes art/a.bin b.bin
  fixture_commit "$T/ws-caveat/client"
  o=$(RPG_FACTORY_WORKSPACE="$T/ws-caveat" RPG_FACTORY_FACTS_REGISTRY="$T/fixture.json" bash "$0" 2>&1); rc=$?
  if [ "$rc" -eq 0 ] && [ "$(grep -c '^NOTE ' <<<"$o")" = 1 ] &&
     grep -q '^NOTE  repo client: HEAD export omits 1 submodule(s) (gitlinks); probes grade' <<<"$o"; then
    pass=$((pass + 1)); echo "PASS  a submodule-only repo notes just the submodule"
  else fail=$((fail + 1)); echo "FAIL  submodule-only NOTE (rc=$rc): $o"; fi
  # A HEAD tree object that cannot be read makes read-tree fail. A ready cache skips git archive, so the failure
  # reaches the read-tree check: it must FAIL the fact (naming fact and repo), not pass on a missing index.
  fixture_repo "$T/ws-broken/client"; fixture_commit "$T/ws-broken/client"
  sub_oid=$(git -C "$T/ws-broken/client" rev-parse HEAD:ProjectSettings)
  sub_obj="$T/ws-broken/client/.git/objects/${sub_oid:0:2}/${sub_oid:2}"
  mkdir -p "$T/cache-broken/export-client"; : > "$T/cache-broken/ready-client"
  chmod u+w "$sub_obj" 2>/dev/null; rm -f "$sub_obj"
  o=$(RPG_FACTORY_WORKSPACE="$T/ws-broken" RPG_FACTORY_FACTS_EXPORT_CACHE="$T/cache-broken" RPG_FACTORY_FACTS_REGISTRY="$T/fixture.json" bash "$0" 2>&1); rc=$?
  if [ "$rc" -ne 0 ] && [ ! -e "$sub_obj" ] &&
     grep -q '^FAIL  enter-playmode-options: cannot read the HEAD tree into the disposable index for repo client$' <<<"$o" &&
     ! grep -q '^PASS  enter-playmode-options' <<<"$o"; then
    pass=$((pass + 1)); echo "PASS  a failing git read-tree is a FAIL for the fact and skips it"
  else fail=$((fail + 1)); echo "FAIL  read-tree failure not reported (rc=$rc): $o"; fi
  for f in sgl-langversion tick-rates-default enter-playmode-options; do
    jq --arg f "$f" '.facts |= map(select(.id == $f) | .value += "-STALE")' "$R" > "$T/reg.json"
    o=$(RPG_FACTORY_FACTS_EXPORT_CACHE="$CACHE" RPG_FACTORY_FACTS_REGISTRY="$T/reg.json" bash "$0" 2>&1); rc=$?
    if [ $rc -ne 0 ] && grep -q "^FAIL  $f: registry says '.*-STALE', repo says" <<<"$o"; then pass=$((pass + 1)); echo "PASS  stale fact $f is detected"
    elif grep -q "^SKIP  $f" <<<"$o"; then skip=$((skip + 1)); echo "SKIP  stale detection $f (repo not present)"
    else fail=$((fail + 1)); echo "FAIL  stale fact $f NOT detected (rc=$rc)"; fi
  done
fi
total=$((pass + fail + skip)); echo "facts tests: $total run, $pass passed, $fail failed, $skip skipped"
[ "$pass" -gt 0 ] && [ "$fail" -eq 0 ]
