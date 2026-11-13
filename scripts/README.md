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
- `assetgen/assetgen.py` - asset-gen engine: list, show, resolve, render, lint, review-cmd (prints the Codex command), qa, manifest; writes only into the given run directory. `tests/assetgen.test.sh`
- `factory-workflow.py` - plan, status, dispatch and report registry-routed artifact workflows. `tests/workflow.test.sh`
- `orca-wait.sh` - the run lead's single waiter for one Orca Run: loops `orca orchestration check --wait` for worker_done, escalation or question, acks heartbeats, prints the first real message (left unacked for the caller); one instance per Run through a lock under the state dir. `tests/orca-wait.test.sh`

## Checks (`checks/`, read-only evidence scripts)

- `artifact-lint.py` - artifact metadata and schema validation. `tests/artifacts.test.sh`
- `artifact-trace.py` - artifact revisions, trace coverage, signed approvals. `tests/artifacts.test.sh`, `tests/artifact-quality.test.sh`
- `artifact-review.py` - git identity and SSH signature helpers for the artifact checks. `tests/artifact-quality.test.sh`
- `artifact-quality.py` - aggregates artifact checks and the domain plugins. `tests/artifact-quality.test.sh`
- `domains/*.py` - per-domain quality plugins (`_api.py` contract; design, ui, art2d, art3d, vfx, assetgen, noop). `tests/artifact-quality.test.sh`, `tests/<domain>-workflow.test.sh`
- `domains/assetgen.py` - gen-run quality plugin: reviewer model differs from the prompt author (`SAME_MODEL:<model>` fallback grades WARN), review files bound to the current prompt and outputs, `qa.json` PASS with every required check, output hashes, provenance, refs. `tests/assetgen.test.sh`
- `asset-manifest.py` - asset manifest records against registered repos. `tests/asset-manifest.test.sh`
- `registry-ownership.py` - cross-domain ownership and handoff invariants. `tests/handoff-e2e.test.sh`
- `english-only.py` - English-only content policy (`--enforce`). `tests/english-only.test.sh`, `tests/skills-lint.sh`
- `skill-citations.py` - skill `path:line` citations against the integration branches. `tests/skill-citations.test.sh`
- `netcode-headless.sh` - Netcode headless tests without writing into the repo. `tests/netcode-headless.test.sh`
- `wire-parity.sh` - wire-generated and protocol-version contract evidence. `tests/checks-candidate.test.sh`
- `sgl-determinism.py` - ADR-10 determinism budget in Shared.GameLogic. run-all
- `unity-package-pins.py` - local mirror of the client's package-pins CI step plus a `file:` guard. run-all
- `pin-status.py` - client git-URL pins against upstream tags. run-all
- `pin-plan.py` - exact edits for moving one client pin. run-all
- `package-ready.py` - release readiness of a `com.cuvara.*` package repo. run-all

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
  (`rpgf_default_workspace`: the same platform default for shell callers), `gitguard.py` (git guard
  facade; loads the `rpgf_guard/` package by path as `rpgf_guard`: `common`, `shell`, `git`, `process`, `gates`, `mode`,
  `runtime`), `hookspeed.py` (hook bytecode cache, Store-alias check), `procrun.py` (check processes, timeouts,
  pollution fingerprints), `runchecks_grade.py` (check parser choice and result grading for `run-checks.py`),
  `artifacts.py` (artifact discovery and quality), `orca_cmd.py` (Orca and Agent dispatch
  argv, with `--model`/`--effort`), `model_policy.py` (model scope, role and grade profiles, personal override; `delivery.md`
  section 10 "Model choice"), `evidence.py`, `fstate.py` (state paths), `devtools.py`, `tools.py`, `registry_src.py`, `shells.py`,
  `pluginroot.py`, `codexconfig.py`, `compat.sh` and `gitcfg-guard.sh` (sourced by tests).
  `tests/routing-properties.test.py`, `tests/compat.test.sh`, `tests/devtools.test.sh`, `tests/git-env-isolation.test.sh`,
  `tests/hook-perf.test.sh`, `tests/workspace-default.test.sh`
- `ui/` - UI plan engine (`ui_plan.py`, data in `ui/data/`), `ui_catalog.py`, `ui_select.py`, `figma_env.py`.
  `tests/ui-commands.test.sh`, `tests/ui-catalog.test.sh`, `tests/ui-skill-routing.test.sh`, `tests/ui-figma-env.test.sh`
- `assetgen/` - asset-gen engine modules: `layers.py` (core and game layers, override and extends), `lint.py` (offline data
  and workflow lint against `data/known-nodes.json`), `qa.py` and `png.py` (deterministic image QA, stdlib PNG decoder), `runfiles.py` (review verdict
  binding and required QA checks, shared with `checks/domains/assetgen.py`).
  `tests/assetgen.test.sh`
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
tests/run-all.sh --only-suites LIST # only the named suites (comma list, unioned with --affected; task QA: the task's checks);
                                    # with --affected or --only-suites, live blocks and script checks (skill-citations,
                                    # factory-context, pin-plan, package-ready, netcode-headless...) are gated like suites
tests/run-all.sh --inline-only      # only the inline checks, no suite; CI runs it on both OSes
python3 -B scripts/ci-plan.py --base REF   # print the CI plan (suites and OS matrix) as JSON
tests/run-all.sh --list-suites      # print the suite names --only-suites accepts (read-only, runs no checks)
tests/run-all.sh --reuse            # exit 0 at once on a PASS record of the same clean tree and coverage (integration QA)
tests/run-all.sh --no-wait          # exit 3 instead of waiting when another full run holds the per-machine lock
tests/run-all.sh --no-reuse         # run every suite; by default a suite whose input hash already passed is reused
tests/run-all.sh -j 4               # up to 4 suites at once; same lines, order, count and exit code as -j 1 (default);
                                    # live-workspace checks one at a time, run1 suites alone; CI uses -j 4
tests/run-all-parallel.test.sh      # run-all -j scheduler on stand-in suites (order, counts, cap, live lane, run1)

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

Workspace defaults to `/mnt/c/Workspaces/UnityIndie`; override with `RPG_FACTORY_WORKSPACE`. Python
scripts are run with `-B` (run-all deletes `__pycache__`).
