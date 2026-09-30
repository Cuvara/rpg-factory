# Local dev loop for the Cuvara packages

Verified 2026-09-30 against the three repos, `toggle-packages.sh` and the client manifest.
Run everything from the package repo root unless a `cwd` is given. `{dotnet}` is the binary
resolved by the Factory snapshot (`dotnet.exe` in WSL).

## 1. Fast checks (all three repos, read-only)

| Check | Command | Evidence | Source |
|---|---|---|---|
| package.json fields | `jq -e '.name and .version and .displayName and .description and .unity' package.json` | `true`, exit 0 | `validate` job, `.github/workflows/ci.yml` |
| CHANGELOG has version | `grep -aq "\[$(jq -r .version package.json)\]" CHANGELOG.md` | exit 0 | same (`-a`: local `grep` is ugrep 7.8.4 and skips UIToolkit's non-UTF-8 CHANGELOG as binary without it) |
| .meta coverage | `python3 .github/scripts/check_metas.py` | `All N Unity-visible tracked file(s) and M folder(s) have a .meta.` | `.github/scripts/check_metas.py` |
| asmdef names | `for f in $(git ls-files '*.asmdef'); do [ "$(jq -r .name "$f")" = "$(basename "$f" .asmdef)" ] \|\| echo "$f"; done` | no output | CI only prints names; this is stricter |

`check_metas.py` walks `git ls-files`: an **untracked** new file is invisible to it. Stage
your explicit paths (`git add <path>...`) before running it, or it passes over them.

Netcode `Samples~` meta coverage (not covered by `check_metas.py`):

```bash
git ls-files 'Samples~' | python3 -c "import sys;f=[l.strip() for l in sys.stdin];h=set(f);m=[p for p in f if not p.endswith('.meta') and p+'.meta' not in h];print(len(m),'missing',m)"
```

Expected today: `0 missing []` (355 tracked files). UnityDots (8) and UIToolkit (17) sample
files have no `.meta` today - pre-existing, report it but do not treat as your regression.

### UIToolkit extras (`validate` job)

```bash
PYTHONDONTWRITEBYTECODE=1 python3 .github/scripts/check_standalone.py   # "standalone: no host-framework references"
PYTHONDONTWRITEBYTECODE=1 python3 .github/scripts/check_uss_prefix.py   # "uss-prefix: every exported class name starts with 'cuvara-'"
PYTHONDONTWRITEBYTECODE=1 python3 .github/scripts/check_samples.py      # "checked 4 of 4 declared sample(s)" ...
jq -e '(.dependencies|keys) - ["com.gdk.core","com.gdk.3rd"] == (.dependencies|keys)' package.json
```

### UnityDots extras

```bash
PYTHONDONTWRITEBYTECODE=1 python3 .github/scripts/test_assert_test_floors.py
```

`PYTHONDONTWRITEBYTECODE=1` is required: `.github/scripts/__pycache__/*.pyc` are **tracked**
in UnityDots, and importing `assert_test_floors` rewrites them, dirtying the tree.

## 2. Extended checks

### Netcode headless tests (fast; Factory runner)

```bash
bash ${CLAUDE_PLUGIN_ROOT}/scripts/checks/netcode-headless.sh
```

It copies `Runtime/`, `Tests/`, `Tests~/` to a temp dir and runs what CI's `headless` job runs
(`dotnet test --logger 'trx;LogFileName=results.trx'` in `Tests~/Headless`), then prints the trx
Counters: `discovered/executed/passed/failed`; `executed == 0` is a failure (CI asserts the same).
The csproj compiles only `Runtime/Transport/{FrameBuffer,WireFraming,TransportException}.cs` and
`Tests/Editor/{FrameBufferTests,TransportReadPumpTests}.cs`; a `using UnityEngine` in any of them
breaks this build by design. Verified 2026-09-30: 30 discovered, 30 passed.

### UIToolkit UXML codegen drift (extended; temp copy)

Run the registry command (`jq -r '.modules[]|select(.id=="uitoolkit.codegen-cli").checks.extended[0].run' ${CLAUDE_PLUGIN_ROOT}/registry.json`,
substitute `{dotnet}`/`{plugin_root}`, cwd = UIToolkit root). It copies the package into a temp dir
under the plugin, runs `UxmlCodegenCli -- .` there and deletes the copy, because UIToolkit has no
`.gitignore` and an in-place run leaves `Tools~/UxmlCodegenCli/{bin,obj}` in the user's tree.

Evidence: `uxml-codegen drift check: N enrolled UXML file(s) checked` then
`all generated bindings are up to date`, exit 0. N today: 2 (`Tests/Runtime/ConfirmPopup.uxml`,
`Samples~/EcsHud/VitalsView.uxml`) - verified 2026-09-30. The CLI only checks; regeneration is the
Editor menu "Assets/Cuvara/Generate UXML Bindings" or the reimport postprocessor (external).

## 3. Unity tests through the client (gate `client-package-toggle`)

Package tests run only inside a Unity project. The client lists all three packages in
`Packages/manifest.json` `testables`, but resolves them from git tags, so local edits are not
seen until the client points at the local clone. This edits the user's client tree: ask first.

1. Back up: `mkdir -p /tmp/rpgf-pkg && cp IndieRPGMMOAdventure/Packages/{manifest.json,packages-lock.json} /tmp/rpgf-pkg/`.
2. Point **only** the package under test at the clone, with a path the Editor can resolve.
   Workspace-root `toggle-packages.sh dev` switches all three at once, writes WSL
   `file:/mnt/c/...` paths, and leaves `packages-lock.json` alone (registry known issue
   `toggle-packages-lock`). The client `CLAUDE.md` describes clones at `/mnt/e/CuvaraPackages/`
   that do not exist on this machine; the clones are the workspace-root repos.
3. The user lets the Editor resolve; run EditMode + PlayMode for the package assemblies via
   the client's `tests-run` Unity MCP skill (`unity-mcp` reachable). Report totals per assembly.
4. Restore: copy both files back from `/tmp/rpgf-pkg/` and `cmp` them. Do **not** use
   `toggle-packages.sh release`: it sets each package to the newest local `v*` tag (after a
   `git fetch --tags`), not to the pin that was there.
5. Never commit a `file:` pin. `git -C IndieRPGMMOAdventure status` must show only the
   user's baseline afterwards.
