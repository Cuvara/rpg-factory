# scripts/

One line per entrypoint: purpose, then the suite that covers it (`run-all` = an inline check in
`tests/run-all.sh`). Run Python with `python3 -B`. Rules: `.claude/CLAUDE.md`; architecture: `docs/architecture/overview.md`.

## Hook entrypoints (`hooks/hooks.json`, Codex through `codex_hook.py`; advisory only, never block)

- `git-guard.py` - PreToolUse Bash|PowerShell: git, `gh`, process-kill and human-gate advisories. `tests/git-guard.test.sh`, `tests/installed-safety.sh`
- `file-guard.py` - PreToolUse Write|Edit|MultiEdit|NotebookEdit|Read: clone, submodule, generated-path, secret and mode advisories. `tests/file-guard.test.sh`
- `factory_session.py` - PreToolUse Skill: records the execution mode, keeps tech skills behind their leads. `tests/session-state.test.sh`
- `install-status.py` - SessionStart: is the loaded plugin the installed, current version. `tests/install-status.test.sh`
- `codex_hook.py` - Codex hook input mapped onto the guards above (context only). `tests/codex-plugin.test.sh`

## User / agent CLI

- `factory-context.sh` - live snapshot and routing (lead, legs, checks, gates); read-only. `tests/routing.test.sh`, `tests/domains.test.sh`
- `factory-status.py` - pending cross-repo work derived from git (rollout, READY_TO_TAG, pin drift, STALE). `tests/factory-status.test.sh`
- `run-checks.py` - runs and grades registry checks, writes evidence; `--status` regrades. `tests/run-checks.test.sh`
- `factory-cmd.py` - entry point behind the slash commands (`status`, `route`, `check`, `doctor`, `ui*`, `assetgen`). `tests/commands.test.sh`, `tests/ui-commands.test.sh`
- `assetgen/assetgen.py` - asset-gen engine: list, show, resolve, render (`workflow.json` and `workflow.ui.json`), lint, graph-lint (workflow style guide check of templates or a run's `workflow.ui.json`; exit 0 PASS/WARN, 1 FAIL, 2 usage), review-cmd (prints the Codex command), defringe, embed, qa, finalize (defringe for alpha purposes, embed and qa in that order, stops at the first FAIL), budget (read-only spend guard: used versus `spec.budget`), manifest, publish (uploads `workflow.ui.json` to a ComfyUI's Workflows > assetgen; exit 3 NOT_AVAILABLE when unreachable), approve-record (the approval record a person asked for), promote-anchor (an output as a style-lock anchor; `--external PNG --origin --rights-note` proposes one from existing art with an `external_source` record, a person activates it and attests the source), reject (records an asset or direction rejection), drift (read-only: records on an older style version), `style init|derive|bump|report` (authoring verbs for a game style, see below); `resolve --profile api-only|local-4gb|local-8gb|auto` routes the template per hardware profile (`auto` reads `<state>/assetgen/hardware-profile.json`, else api-only; UNTESTED on RTX 5060, `docs/hardware.md`) and `graph-lint --profile` checks templates under a profile; writes into the given run directory, except approve-record (also `approvals/AGEN-<run-id>/`), promote-anchor and reject (`assetgen/styles/<style>/` in the authoring repo); `style init` writes `assetgen/project.json` and draft styles, `style derive --apply` writes a draft style (without `--apply` it prints the proposal only), `style bump` writes the draft `assetgen/styles/<ID>/versions/<N+1>.json` and proposed anchors (`--list-only` writes nothing), `style report` is read-only; none of them edits core data or activates anything; publish is the only network call and writes nothing locally. `tests/assetgen.test.sh`
- `comfy-desktop-setup.py` - machine setup for asset-gen: Comfy Desktop local instance, the vendored 9router node (`templates/assetgen/comfy-node/`), a comfy-mcp venv and its registration for Claude and Codex. `--check` (default) is read-only, `--apply` writes only on the person's machine (custom_nodes, venv, `claude`/`codex mcp add`), `--generate-test` spends one low-quality image; exit 0 READY, 1 FAIL, 2 usage, 3 ACTION_NEEDED; never prints the provider key. `--check` also prints advisory hardware rows (`gpu`: nvidia-smi name, VRAM and compute capability; `torch`: version and CUDA build read from the instance env without importing torch; `profile`: the best `assetgen/data/hardware.json` profile the machine meets and why not the higher ones, printed only and never applied; `packs` and `models`: what that profile still lacks, never downloaded or installed), and `--json` adds a top-level `profile` object. UNTESTED on RTX 5060 (`docs/hardware.md`). Saving the `--check --json` output to `<state>/assetgen/hardware-profile.json` is what `assetgen.py resolve --profile auto` reads; nothing writes it automatically (exact command: `docs/hardware.md` "Saving the profile for --profile auto"). Not under `assetgen/` (that engine is scanned for URLs) nor `checks/` (read-only). `tests/comfy-desktop-setup.test.sh`
- `factory-workflow.py` - plan, status, dispatch and report registry-routed artifact workflows. `tests/workflow.test.sh`
- `orca-wait.sh` - the run lead's single waiter for one Orca Run: loops `orca orchestration check --wait` until a worker_done, escalation, question or status message arrives (`--types` changes the set) and prints that batch (exit 0). On Orca 1.4.250+ a check marks the whole batch handled and sends no deliveryId, so a printed delivery is already read (`orca orchestration inbox` finds it again); on older Orca a heartbeat-only batch is acked and a real delivery stays unacked for the caller. Between waits it polls the Run's workers and exits 5 on a stalled one (`--stall-poll-ms`, 0 disables the poll; `--stall-ms`, 0 disables only the frozen-output check); it exits 6 when its parent process is gone (a delivery that arrives after that is saved to `<lock>.orphan.<pid>.json`); one instance per Run through a lock under the state dir (exit 3 when held). `tests/orca-wait.test.sh`

## Checks (`checks/`, read-only evidence scripts)

- `artifact-lint.py` - artifact metadata and schema validation. `tests/artifacts.test.sh`
- `artifact-trace.py` - artifact revisions, trace coverage, signed approvals. `tests/artifacts.test.sh`, `tests/artifact-quality.test.sh`
- `artifact-review.py` - git identity and SSH signature helpers for the artifact checks. `tests/artifact-quality.test.sh`
- `artifact-quality.py` - aggregates artifact checks and the domain plugins. `tests/artifact-quality.test.sh`
- `domains/*.py` - per-domain quality plugins (`_api.py` contract; design, ui, art2d, art3d, vfx, assetgen, noop). `tests/artifact-quality.test.sh`, `tests/<domain>-workflow.test.sh`
- `domains/assetgen.py` - gen-run quality plugin: reviewer model differs from the prompt author (`SAME_MODEL:<model>` fallback grades WARN), review files bound to the current prompt and outputs, `qa.json` PASS with every required check, output hashes, provenance, refs; the workflow-style check of the run's `workflow.ui.json` (WARN only, never FAIL); the light review tier (`assetgen/data/review-tiers.json`: icon, ui-element, texture-tileable without selected anchors) makes Claude's own image review optional, the Codex reviews stay required. `tests/assetgen.test.sh`
- `asset-manifest.py` - asset manifest records against registered repos. `tests/asset-manifest.test.sh`
- `registry-ownership.py` - cross-domain ownership and handoff invariants. `tests/handoff-e2e.test.sh`
- `portable-paths.py` - report tracked machine-specific paths; `--enforce` fails on findings. `tests/portable-paths.test.sh`
- `english-only.py` - English-only content policy (`--enforce`). `tests/english-only.test.sh`, `tests/skills-lint.sh`
- `workspace-readers.sh` - workspace reader guard: jq readers of the registry default workspace map the path on the same line, Python readers use the shared helper (`ROOT` argument, exit 1 on a violation). `tests/workspace-default.test.sh`; run-all runs it as a repo-wide guard line
- `skill-citations.py` - skill `path:line` citations against the integration branches. `tests/skill-citations.test.sh`
- `netcode-headless.sh` - Netcode headless tests without writing into the repo. `tests/netcode-headless.test.sh`
- `wire-parity.sh` - wire-generated and protocol-version contract evidence. `tests/checks-candidate.test.sh`
- `sgl-determinism.py` - ADR-10 determinism budget in Shared.GameLogic. run-all
- `unity-package-pins.py` - local mirror of the client's package-pins CI step plus a `file:` guard. run-all
- `pin-status.py` - client git-URL pins against upstream tags. run-all
- `pin-plan.py` - exact edits for moving one client pin. run-all
- `package-ready.py` - release readiness of a `com.cuvara.*` package repo. run-all

Two conventions every new script under `scripts/` (so every new check in `checks/`) must meet; a new check that skips one fails run-all:

- **UTF-8 stdio block** (`tests/compat.test.sh`): a Python script with a `__main__` entry point reconfigures stdout and
  stderr to UTF-8 first, because Windows pipes default to cp1252. The test greps each such file in `scripts/*.py`,
  `scripts/checks/*.py` and `scripts/lib/context.py` for the literal `_stream.reconfigure(encoding="utf-8"`; copy the
  block from `checks/english-only.py` (`for _stream in (sys.stdout, sys.stderr): if hasattr(_stream, "reconfigure"):
  _stream.reconfigure(encoding="utf-8", errors="replace")`). Every `subprocess` call with `text=True` also names
  `encoding="utf-8"`.
- **Workspace reader guard** (reader rules: `checks/workspace-readers.sh`; its self-test and the literal rule:
  `tests/workspace-default.test.sh`): never write the workspace default as a literal (`/mnt/c/Workspaces/UnityIndie`
  is allowed only in `lib/workspace.sh`, `lib/workspace.py` and this README). Shell
  reads the default through `rpgf_default_workspace` from `lib/workspace.sh`; a shell line that reads the registry's
  workspace `root_default` key with jq must pass the value through `rpgf_platform_path` on that same line. In Python,
  only `lib/workspace.py` and `lib/fstate.py` may name `root_default`, and a script outside `scripts/lib/` calls
  `default_workspace` only with the registry it already loaded (`default_workspace(registry=reg)`), never with empty
  parentheses.

## Maintenance (plugin repo only)

- `build-registry.py` - builds `registry.json` from `registry/` fragments (`--check`, `--split`). `tests/registry-fragments.test.sh`
- `check-registry.sh` - registry structure and that every named path exists. `tests/check-registry.test.sh`
- `changelog.py` - `changelog.d/` fragments: check, preview, release assembly. `tests/changelog.test.sh`
- `ci-plan.py` - plans the CI suites from `tests/affected.py`, one matrix row per `{suite, os}` (anything unsure plans every suite).
  `tests/ci-plan.test.sh`
- `release-check.py` - read-only release gate (versions, changelog, tag, clean tree). `tests/release-check.test.sh`
- `new-skill.py` - scaffolds a skill and its registry entry. `tests/new-skill.test.sh`
- `skill-touchpoints.py` - every place a skill must appear. `tests/new-skill.test.sh`, `tests/skills-lint.sh`

## Libraries

- `lib/` - `context.py` + `resolve.jq` (routing engine), `snapshot_render.py` (snapshot text, domain views, Next line),
  `workspace.py` (workspace and checkout path helpers shared by the hooks and routing; `default_workspace`), `workspace.sh`
  (`rpgf_default_workspace`: the same platform default for shell callers), `english.py` (shared english-only detection
  used by `checks/english-only.py`, `file-guard.py` and the git guard), `gitguard.py` (git guard
  facade; loads the `rpgf_guard/` package by path as `rpgf_guard`: `common`, `shell`, `git`, `process`, `gates`, `mode`,
  `runtime`), `hookspeed.py` (hook bytecode cache, Store-alias check), `procrun.py` (check processes, timeouts,
  pollution fingerprints), `runchecks_grade.py` (check parser choice and result grading for `run-checks.py`),
  `artifacts.py` (artifact discovery and quality), `orca_cmd.py` (Orca and Agent dispatch
  argv, with `--model`/`--effort`), `model_policy.py` (model scope, role and grade profiles, personal override; `delivery.md`
  section 10 "Model choice"), `evidence.py`, `fstate.py` (state paths), `devtools.py`, `tools.py`, `registry_src.py`, `shells.py`,
  `pluginroot.py`, `plugin_registry.py` (plugin root and `registry.json` loader for the pin checks), `codexconfig.py`, `compat.sh` and `gitcfg-guard.sh` (sourced by tests).
  `tests/routing-properties.test.py`, `tests/compat.test.sh`, `tests/devtools.test.sh`, `tests/git-env-isolation.test.sh`,
  `tests/hook-perf.test.sh`, `tests/workspace-default.test.sh`
- `ui/` - UI plan engine (`ui_plan.py`, data in `ui/data/`), `ui_catalog.py`, `ui_select.py`, `figma_env.py`.
  `tests/ui-commands.test.sh`, `tests/ui-catalog.test.sh`, `tests/ui-skill-routing.test.sh`, `tests/ui-figma-env.test.sh`
- `assetgen/` - asset-gen engine modules: `layers.py` (core and game layers, override and extends), `lint.py` (offline data
  and workflow lint against `data/known-nodes.json`), `qa.py` and `png.py` (deterministic image QA, stdlib PNG decoder), `runfiles.py` (review verdict
  binding and required QA checks, shared with `checks/domains/assetgen.py`), `finalize.py` (sequences defringe, embed and qa),
  `budget.py` (advisory spend guard, read-only), `graphstyle.py` (workflow style guide rules, used by lint, graph-lint and
  the check), `uiworkflow.py` (the ComfyUI frontend graph with groups, notes and colours from a template's ui block),
  `nodesync.py` (offline, no network: `data/known-nodes.json` entries from a saved object_info JSON; prints them, `--write`
  merges them, `--check` exits 1 naming the entries a merge would change), `stylelock.py` (style lock data side:
  project config, anchors, rejections, selection, drift), `style_cmd.py` (`style init` and `style bump`),
  `style_derive.py` (`style derive`: palette, tone and canvas proposed from the active anchors) and `style_report.py`
  (`style report`: read-only run, QA and rejection statistics with suggested thresholds, never applied); review tiers
  are data in `data/review-tiers.json`. `tests/assetgen.test.sh` (covers all of them)
- `adapters/` - optional domain tool adapters (`art2d/provider.py`, `art3d/blender-stats.py` run inside Blender,
  `vfx/unity.py`). `tests/art2d-workflow.test.sh`, `tests/art3d-workflow.test.sh`, `tests/vfx-workflow.test.sh`

## Commands

```bash
tests/run-all.sh                    # every local suite (releases and manual full runs, under the lock); must end with 0 failed
tests/run-all.sh --workspace-only   # only what CI cannot run (live-workspace suites and checks, claude plugin validate),
                                    # with the suite reuse; integration QA before a PR (`gh pr checks <pr> --watch` follows once the PR is open)
tests/run-all.sh -h | --help        # print the usage header, exit 0; an unknown argument exits 2 and never starts a run
tests/run-all.sh --no-workspace     # skip checks needing the RPG MMO workspace on disk
tests/run-all.sh --no-claude        # skip `claude plugin validate`
tests/run-all.sh --release          # + installed plugin CURRENT, source committed, installed-safety.sh
tests/run-all.sh --affected [--base REF]  # only suites touched since merge-base (tests/affected.py); not the PR gate
tests/run-all.sh --affected --base REF --within LIST -j 1  # task QA: only the named check suites (comma list) that the
                                    # change selects, each with its affected cases; a named suite the change misses still
                                    # runs in full; the rest of the selection is left to CI (one 'left to CI: N suites' line)
tests/run-all.sh --workspace-only --base REF  # integration QA: only the workspace checks the change reaches (no --base: all)
tests/run-all.sh --only-suites LIST # only the named suites (comma list, unioned with --affected); the explicit suite
                                    # selector, no longer the task QA; with --affected or --only-suites, live blocks and
                                    # script checks (skill-citations,
                                    # factory-context, pin-plan, package-ready, netcode-headless...) are gated like suites
tests/run-all.sh --inline-only      # only the inline checks, no suite; CI runs it on both OSes
python3 -B scripts/ci-plan.py --base REF   # print the CI plan (suites and OS matrix) as JSON
tests/run-all.sh --list-suites      # print the suite names --only-suites accepts (read-only, runs no checks)
tests/run-all.sh --reuse            # exit 0 at once on a PASS record of the same clean tree and coverage (integration QA)
tests/run-all.sh --no-wait          # exit 3 instead of waiting when another full run holds the per-machine lock
tests/run-all.sh --no-reuse         # run every suite; by default a suite whose input hash already passed is reused
tests/run-all.sh --last-result [--checkout DIR]  # print the newest result record of a checkout (read-only; exit 0, or 1 when none);
                                    # adds a `running:` line while a slot or the full-run lock of that checkout is live
tests/run-all.sh --attach           # with a live run of the same checkout and arguments: wait for it, print its record, exit with
                                    # its status (5 when it died without a record); without it that second run starts nothing and exits 4, naming the holder
                                    # (slot, pid, winpid, started, args). Every admitted run writes its record at exit, also after INT/TERM/HUP
tests/run-all.sh -j 4               # up to 4 suites at once; same lines, order, count and exit code as -j 1 (default);
                                    # live-workspace checks one at a time, run1 suites alone; CI uses -j 4
tests/run-all-parallel.test.sh      # run-all -j scheduler on stand-in suites (order, counts, cap, live lane, run1)
tests/assetgen.test.sh [--case NAMES] [--list-cases]  # asset-gen engine; --case takes comma-separated group names (--list-cases prints them, read-only); a group's prerequisites run first
                                    # groups: list-show resolve render-golden ui-workflow ui-layout filename-prefix lint graph-style
                                    # fixture-pngs png-qa review-cmd embed e2e3 sheet-sizes sheet-failures sheet-repeat sheet-cli
                                    # sheet-discard pixel-grid output-filter fit finalize-core discard budget publish manifest
                                    # gen-run-plugin local-hybrid engine-notes style-lock style-cli anchor-target profile-routing
                                    # style-qa gen-run-style style-init style-derive style-bump style-report selftests hygiene

# single suites (each standalone; sets its own temp TMPDIR / RPG_FACTORY_STATE_DIR)
tests/git-guard.test.sh
env -u TMPDIR tests/session-state.test.sh  # run-all runs session-state/file-guard/commands with TMPDIR unset
tests/routing.test.sh [--no-history]       # task scenarios (+ real commits replayed read-only)
python3 -B tests/routing-properties.test.py
tests/skills-lint.sh                       # skill contract, tech sections, ## Tools vs dev_tools
env -u TMPDIR tests/devtools.test.sh       # dev tool probes, snapshot/doctor lines, no secrets printed
scripts/check-registry.sh [--structure-only]
env -u TMPDIR tests/skill-citations.test.sh  # citation checker on fixture repos
env -u TMPDIR tests/netcode-headless.test.sh  # netcode-headless.sh server resolution (--server, worktrees)
python3 -B scripts/checks/skill-citations.py [--skill <s>] [--suggest] [--strict] [--fix]   # skill path:line vs integration branches
python3 -B scripts/new-skill.py --name <s> --kind tech|repo|cross-repo ... [--dry-run]  # scaffold (see .claude/skills/skill-author)
python3 -B scripts/skill-touchpoints.py <s>|--all  # every place a skill must appear
env -u TMPDIR tests/new-skill.test.sh      # scaffolder + touchpoints on a throwaway plugin copy
env -u TMPDIR tests/parallel-policy.test.sh  # parallel-work lint bites on a throwaway plugin copy
tests/orca-commands.test.sh                # orca commands cited in delivery.md, parallel-work.md and pipeline-cli.md exist (SKIP without orca)
env -u TMPDIR tests/release-check.test.sh  # release gate on a throwaway repo with a local bare origin
tests/changelog.test.sh                    # changelog fragments: validation, preview, release assembly
tests/registry-fragments.test.sh           # registry/ fragments: build, placement, scaffolder, parallel merge
python3 -B scripts/build-registry.py [--check|--split]   # registry.json from registry/ (--check read-only)
python3 -B scripts/changelog.py check|preview|release X.Y.Z [--summary TEXT]   # changelog.d fragments
tests/codex-plugin.test.sh                 # Codex manifest, marketplace, hook config, codex_hook.py, hook wiring
python3 -B scripts/release-check.py [--no-remote] [--verify-tag] [--notes]   # read-only release gate
env -u TMPDIR tests/pipeline.test.sh       # delivery pipeline on a throwaway workspace (server + Unity client)
python3 -B scripts/factory-pipeline.py tier|agents|validate|subplan|planner|dispatch|verdict|gate|status|cleanup ...  # delivery pipeline (`delivery.md` section 10; flags `docs/pipeline-cli.md`)
python3 -B scripts/factory-pipeline.py agents <plan> [--down A [--reason T] | --up A]  # per-run MODEL_UNAVAILABLE marks

# routing / state, read-only against the workspace
scripts/factory-context.sh --repo server --paths backend/shared/proto/wire.proto [--domain <id>] [--explain] [--json]
scripts/factory-context.sh --domain <id> [--json]
scripts/factory-context.sh --kind <artifact-kind> [--lead <skill>] [--json]
python3 -B scripts/factory-status.py
python3 -B scripts/run-checks.py --repo <key> --paths <files> [--status]

# UI plan, catalog and selection (read-only)
python3 -B scripts/factory-cmd.py ui [--json] [--project DIR] [--uitoolkit-ref REF] <request>   # UI plan (exit 3 = NEEDS_CONTEXT)
python3 -B scripts/ui/ui_catalog.py [--uitoolkit DIR] [--ref REF] [--kind K]... [--json]       # com.cuvara.uitoolkit catalog at a ref
python3 -B scripts/ui/ui_select.py (--screen S | --need N...) [--ref REF] [--json]              # reuse > configure > compose > missing
python3 -B scripts/ui/figma_env.py --project <unity project> [--json] [--probe-pipeline]       # Figma connector environment check
tests/ui-catalog.test.sh                   # catalog + selection on a UIToolkit git fixture
tests/ui-commands.test.sh                  # UI plan: schema, intents, skills per verb, NEEDS_CONTEXT
env -u TMPDIR tests/ui-skill-routing.test.sh  # UI plan golden matrix, selection, path-scoped routing.tech
env -u TMPDIR tests/ui-figma-env.test.sh   # figma_env.py on fixture Unity projects
tests/ui-skills.test.sh                    # UI skills content, docs, snapshot Next line for UI paths

tests/dogfood.sh [--installed]      # real headless Claude sessions; spends tokens, not in run-all
tests/dogfood-codex.sh [--dry-run]  # real `codex exec` sessions in a throwaway CODEX_HOME; spends tokens, not in run-all
```

The workspace default depends on the platform: `/c/Workspaces/UnityIndie` on Git Bash (drive form; Python on Windows
uses `C:/Workspaces/UnityIndie`), `/mnt/c/Workspaces/UnityIndie` elsewhere (WSL form); `RPG_FACTORY_WORKSPACE`
overrides it. Python scripts are run with `-B` (run-all deletes `__pycache__`).
