# CLAUDE.md - rpg-factory

Claude Code plugin providing Factory Core for the UnityIndie RPG MMO workspace. See README.md.

## Rules for changing this repo

- `registry.json` is the source of truth for module knowledge. Never hard-code module paths,
  commands, or rules in `SKILL.md` or the references - put them in the registry and read them.
  It is generated: edit the fragments under `registry/` (`core.json`, `engineering/<repo>|skills|contracts.json`,
  `domains/<domain>.json`; placement rule in `scripts/lib/registry_src.py`), then `python3 -B scripts/build-registry.py`.
  run-all fails when `registry.json` is not the build (`--check`). After a merge, rebuild if `registry.json` conflicted.
- Keep `factory-context.sh`, `factory-status.py` and `scripts/checks/` read-only: no fetch (except
  opt-in `--remote` ls-remote), no writes into repos. State is derived from git; the only Factory
  files are per-session mode state and check evidence, resolved through `scripts/lib/fstate.py` (never `$TMPDIR`
  directly, never relative). Tests set `RPG_FACTORY_STATE_DIR` and `TMPDIR` to a temp dir. Exceptions, on
  purpose in the persistent state dir: run-all's full-run lock, tree records and suite PASS records (`run-all/`,
  `locks/`) and the routing history-replay cache (`routing-replay/`, pruned on write).
- `run-checks.py` never runs a check in place when it would write into a product repo; pollution is FAIL.
- Hooks must stay fast (one guard process per command, no repository scan) and must never crash a session.
  No hook snapshots repository state, latches a session or needs an acknowledgement (the tripwire was
  removed on purpose; do not bring back a post-command lock under another name).
- No hook asks the user or blocks the agent: hooks emit only `additionalContext` advisories
  (`rpg-factory advisory (high|warn): ...`), never a `permissionDecision` (removed on purpose in 1.0.3; do not
  bring back ask/deny). The git guard never crashes a session (errors mean "no opinion"); `high` marks tag
  creation/deletion/pushes (incl. `gh api` tag refs, `gh release create`) and repo deletion. Every new bypass found gets a
  case in `tests/git-guard.test.sh` (and `tests/installed-safety.sh` for new classes). File-tool rules live
  in `scripts/file-guard.py`; both guards raise mode advisories (never a block). Each human gate regex and the git evaluation must fail independently.
- Every behaviour change gets a test in `tests/` and a changelog fragment `changelog.d/<topic>.md` (`### Added|Changed|Fixed|...`
  sections; `changelog.d/README.md`). Never edit `CHANGELOG.md` `[Unreleased]` directly: it stays empty (run-all checks it).
- While iterating and in task QA: the tier command (`tests/run-all.sh --affected --base <base> -j 2`, or the task's
  suites with `--only-suites`); a task never runs the full suite. CI is the full-suite gate: before opening a PR,
  integration QA runs `tests/run-all.sh --workspace-only` (what CI cannot run) and must report 0 failed; after the
  PR opens, CI (`gh pr checks <pr> --watch`) must be green before merging, and while CI runs, start the next task. The full `tests/run-all.sh --release`
  and `tests/dogfood.sh --installed` run only for releases. Report the pass count. Tiers (with typical times):
  `delivery.md` section 10 "QA tiers". An implementer runs only its spec's targeted checks and, in a slow suite,
  only the cases its change touches (`--case`, `tests/affected.py cases`); tier S and docs-only tasks get lead QA.
  CI (`.github/workflows/tests.yml`) runs only `--no-workspace --no-claude`, so `--workspace-only` covers the rest.
- English only. Conventional Commits (`feat(core): ...`, `fix(guard): ...`, `docs(registry): ...`).
- New or changed skills follow `skills/factory-core/references/skill-contract.md`; `tests/skills-lint.sh`
  enforces the mechanical part. Routing changes need a scenario in `tests/routing.test.sh`. New skills start
  from `scripts/new-skill.py` and are done when `scripts/skill-touchpoints.py <s>` is OK (`.claude/skills/skill-author`).
- A skill's `path:line` citation names the symbol it shows (anchor) and must pass
  `scripts/checks/skill-citations.py` against the integration branches; cite docs by section, not line.
  A citation whose anchor moved to a unique line is MOVED (warning; FAIL under `--strict` / `run-all --release`):
  `--fix` rewrites its line spec in place.
- Parallel plugin work follows `skills/delivery/references/delivery.md` (the generic policy, one copy) and, for the RPG
  specifics, `skills/factory-core/references/parallel-work.md`: one worktree and one task-lead
  session per task (Orca-managed or `isolation: worktree`), never a second clone; the main session (run lead)
  integrates. Those two files are the only copies of the policy (`tests/skills-lint.sh`, `tests/parallel-policy.test.sh`).
- **Developing this plugin:** every plugin task (new or split skill, core change) runs through `factory-pipeline.py`
  with a `plan.json` whose `repos` entry names this checkout (`"plugin": {"path": "<this checkout>"}`), small tasks
  with disjoint owned paths, and cross-model review. The run lead starts each task's lead with
  `dispatch --phase lead`; the task lead runs its subtasks, review and QA in that task's worktree. How:
  `delivery.md` sections 1 and 10 and section 8 "Session lifecycle" (RPG specifics: `parallel-work.md`); the session-level steps (tier, plan,
  `dispatch --phase lead`, `status` to resume, review pairing, gate, cleanup) are factory-core `SKILL.md` steps 6, 7, 11, 12.
- **Releases:** bump `VERSION`, `.claude-plugin/plugin.json`, `marketplace.json`, `.codex-plugin/plugin.json` (and the
  Codex marketplace `.agents/plugins/marketplace.json` if it carries a version) and the README "Version" line, and gather the
  fragments into the `CHANGELOG.md` section with `python3 -B scripts/changelog.py release X.Y.Z [--summary TEXT]` (run-all and
  `release-check.py` check it: section present, `[Unreleased]` empty, no fragment left). The local directory marketplace loads this checkout in
  place (what is checked out is what sessions run); the install record only updates on a version
  change: `claude plugin marketplace update rpg-factory && claude plugin update rpg-factory@rpg-factory`,
  restart, then `tests/run-all.sh --release` and `tests/dogfood.sh --installed`.
  Tag and GitHub release: without explicit release authorization from the user in the current task, stop at
  READY_TO_TAG - the maintainer tags and publishes. When the user explicitly authorizes the release in the current
  task, perform the authorized merge, version bump, annotated tag (`vX.Y.Z`, message `rpg-factory X.Y.Z`, on the
  verified merge commit) and GitHub release yourself, within that scope and only after `run-all.sh --release` and
  dogfood pass on that exact commit. Never move, delete or reuse a tag, and never bypass a failing check.
  Authorized release order (`scripts/release-check.py` is read-only; exit 0/1):
  1. merge the release PR; 2. check out the merge commit (`main` == `origin/main`, clean tree);
  3. `python3 -B scripts/release-check.py` (versions agree, Codex manifest included when present, `## [X.Y.Z]` present, `[Unreleased]` empty, tag
  absent locally and on origin, HEAD == origin/main, clean); 4. `tests/run-all.sh --release` and
  `tests/dogfood.sh --installed` on that commit; 5. `git tag -a vX.Y.Z -m "rpg-factory X.Y.Z"`;
  6. `python3 -B scripts/release-check.py --verify-tag` (annotated, message, points to HEAD, VERSION at the tag);
  7. push the tag, `python3 -B scripts/release-check.py --verify-tag --notes > notes.md` and
  `gh release create vX.Y.Z --verify-tag -F notes.md`.
- Point-in-time values go in registry `facts[]` with a probe, never in skill prose.
- Registry facts must be verified against the product repos (file paths, CI workflow
  contents, run logs), not copied from docs that may be stale.

## Operating lessons

Learned the hard way while building 1.3-1.5. Each rule names its reason; delivery-flow lessons (Orca, Codex,
sessions, load limits) live only in `skills/factory-core/references/parallel-work.md`, dogfood practice in
`docs/dogfood.md`.

- **No worktree or branch creation while `tests/run-all.sh` runs.** Every checkout shares one `.git/config`, and
  run-all's shared-config check fails when it changes mid-run (a new worktree or tracking branch writes to it).
- **Create branches with `git switch --no-track -c <branch>`.** A tracking branch writes `branch.<name>.*` into
  the shared `.git/config`, which races with other sessions' runs.
- **Git Bash, never WSL, on Windows** (every agent runtime). A WSL git run once wrote `core.worktree=/mnt/c/...`
  into the shared config and broke every checkout of the repo.
- **Fix citation drift right before a release gate:** `python3 -B scripts/checks/skill-citations.py --fix`.
  Citations are checked against client and Netcode `develop`, which merge refactors every 30-60 minutes; in 1.3.0
  they drifted between the fix and the gate four times. Check their open PRs before starting the gate.
- **One full run per machine: the run-all lock** (a second full `tests/run-all.sh` waits; `--no-wait` exits 3).
  Four parallel full runs made every suite 2-4x slower and timed some out; other sessions use the tier command
  (`delivery.md` section 10 "QA tiers").
- **Targeted runs take a test slot** (`--affected` / `--only-suites`: `RPG_FACTORY_TEST_SLOTS` slots machine-wide,
  default 2): a busy machine makes a run wait with a message instead of slowing every suite 2-4x. The slot belongs
  to the run, not the session: stop a QA worker's background test run before abandoning the worker, or it keeps its
  slot (an aborted QA once held one for 45 min). Frozen copies of a suite go under a temp dir, never into `tests/`.
- **Task worktrees must be visible in Orca** (maintainer, 2026-11-09). A `git worktree add --no-track` worktree has
  no Orca lineage and lands in Orca's hidden section: run `orca worktree set --worktree path:<dir>
  --parent-worktree path:<parent> --display-name <topic>-<task> --workspace-status in-progress` before
  `orca agent launch` (`delivery.md` section 4 "Orca visibility"; `dispatch --phase lead` prints it).
- **On Windows `chmod +x` does not set git's executable bit:** use `git update-index --chmod=+x <file>`, or the
  script is committed as 100644 and fails on Linux CI.
- **Quote shell examples in messages in single quotes, or put them in a file.** Backticks inside a double-quoted
  shell argument (for example an `orca orchestration send --body`) are command substitution: they run in the
  sender's shell and the message loses the example.
- **Learning loop.** A new operating lesson goes into this section, or into the policy file it belongs to
  (`parallel-work.md`, `docs/dogfood.md`, `git-safety.md`), with its reason and a test when it can have one.
  Private agent memory only points here: Codex, other machines and new sessions never see it.

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
tests/orca-commands.test.sh                # orca commands cited in parallel-work.md exist (SKIP without orca)
env -u TMPDIR tests/release-check.test.sh  # release gate on a throwaway repo with a local bare origin
tests/changelog.test.sh                    # changelog fragments: validation, preview, release assembly
tests/registry-fragments.test.sh           # registry/ fragments: build, placement, scaffolder, parallel merge
python3 -B scripts/build-registry.py [--check|--split]   # registry.json from registry/ (--check read-only)
python3 -B scripts/changelog.py check|preview|release X.Y.Z [--summary TEXT]   # changelog.d fragments
tests/codex-plugin.test.sh                 # Codex manifest, marketplace, hook config, codex_hook.py, hook wiring
python3 -B scripts/release-check.py [--no-remote] [--verify-tag] [--notes]   # read-only release gate
env -u TMPDIR tests/pipeline.test.sh       # delivery pipeline on a throwaway workspace (server + Unity client)
python3 -B scripts/factory-pipeline.py tier|agents|validate|subplan|planner|dispatch|verdict|gate|status|cleanup ...  # delivery pipeline (parallel-work.md section 10)
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

## How it fits together

- **Routing:** `factory-context.sh` → `lib/context.py` collects git state per repo (worktree-aware) and
  pipes it through `lib/resolve.jq` over `registry.json`. Output: touched modules, dependents, contracts,
  lead / co-leads / legs / follow-ups, checks by tier (fast / extended / external), and human gates. The lead
  is deterministic: contract driver, then repo-kind driver, then primary owner, then secondary owner. Ties
  break on `skills.<name>.order`. Unmapped files fall back to `<repo>.root`.
- **Validation:** `run-checks.py` runs registry checks and grades them (PASS / FAIL / BLOCKED / NOT_AVAILABLE /
  HUMAN_REQUIRED / SKIPPED / NOT_RUN / STALE). Evidence is keyed by tree identity and written through
  `lib/evidence.py`. `--status` regrades that evidence without running checks.
- **Derived state:** `factory-status.py` covers rollout stage, READY_TO_TAG, pin drift, uncommitted work and
  STALE evidence. Nothing is stored; it re-derives everything from git each time.
- **Hooks** (`hooks/hooks.json`): every command ends with `; exit 0` (bash and PowerShell both accept it): exit 2
  is Claude Code's blocking code and python exits 2 on a missing script, so a missing or broken script must never
  block; stdout still passes through (run-all tests both).
  - SessionStart: `install-status.py --session` (never tracebacks; malformed plugin records mean no advisory).
  - PreToolUse Bash|PowerShell: `git-guard.py`.
  - PreToolUse Write|Edit|MultiEdit|NotebookEdit|Read: `file-guard.py`.
  - PreToolUse Skill: `factory_session.py --skill`, which records the execution mode and keeps `kind: tech` skills behind
    their leads without blocking: requested before factory-core, the call is auto-corrected to factory-core
    (`updatedInput`, once per session); before one of its `used_by` leads, it runs with a `high` advisory. Each advisory
    is logged to the session's `ADVISORIES` file (tests, dogfood). Both guards import `factory_session` for the mode.
  - No PostToolUse hooks.
- **Slash commands** (`commands/*.md`: status, route, check, doctor, workflow, pipeline, ui, ui-figma, ui-components, ui-screen,
  ui-review, assetgen) call `scripts/factory-cmd.py` and are covered by `tests/commands.test.sh`; the `ui*` verbs run
  `scripts/ui/ui_plan.py` (read-only UI plan; data in `scripts/ui/data/`), covered by `tests/ui-commands.test.sh`;
  `assetgen` forwards the read-only verbs of `scripts/assetgen/assetgen.py` (asset-gen engine, `tests/assetgen.test.sh`).
- **Skills:** `factory-core` (references: git-safety, report, repos, validation, skill-contract, parallel-work, engineering, workflows) routes to
  14 specialised skills: wire-contract, pin-bump, measure, server-realtime, server-services, server-ops,
  unity-package, client-integration, game-design, ui-ux, art-2d, art-3d, vfx and asset-gen. 11 tech skills (`kind: tech`: dotnet-gameserver, go-backend,
  unity-client-tech, unity-dots, netcode-client, the UI skills ui-orchestrator, ui-component-selection, ui-figma-import,
  ui-toolkit-screen, ui-validation, and comfyui) own no module, are never routed, and appear as `routing.tech` for their `used_by`;
  a registry `paths` list narrows that to matching changed files (the UI skills: UXML/USS/TSS and UI folders; comfyui: `assetgen/`), and the
  snapshot's Next line loads the UI skills through `ui-orchestrator`, whose UI plan names the subset
  (`docs/architecture/ui-skills.md`). `delivery` (kind `core`, generic: the two-level delivery flow, agent routing, review,
  QA tiers and the plan/verdict/gate pipeline for any repository, in any project; one reference, `delivery.md`) owns no module and is never
  routed; factory-core steps 6, 7, 11 and 12 load it, and `factory-pipeline.py --registry none` reads its `pipeline-defaults.json`.
- **Delivery pipeline:** `factory-pipeline.py` (settings: registry `pipeline`; plan schema
  `docs/schemas/pipeline-plan.schema.json`, a task lead's subplan `docs/schemas/pipeline-subplan.schema.json`; verdicts under the persistent state dir `pipeline/<plan id>/`) prints Orca
  or Agent dispatch commands and grades READY_FOR_PR; it never runs agents, pushes or creates worktrees. A repo with
  `worktrees: false` (Unity project) never gets a worktree: tasks run in sequence in the main checkout. Two levels
  (run lead, one task lead per task worktree) as in `parallel-work.md`. Every dispatch carries `--model/--effort` from the
  registry `pipeline.models` policy (`lib/model_policy.py`; `parallel-work.md` "Model choice").
- **Dev tools:** registry `dev_tools[]` → `lib/devtools.py` probes (PATH, TCP services, MCP server and
  plugin names only - never config values) → snapshot "Tools for this change" and doctor "Dev tools".
  Every non-core skill's `## Tools` names exactly its `used_by` tools (skills-lint).

## Layout

- `AGENTS.md` (Codex entry: points here, Codex-only notes) - `.claude-plugin/` manifests (Codex: `.codex-plugin/`, `.agents/plugins/`, `docs/codex.md`) - `skills/` - `commands/` - `agents/` (read-only plugin agent `factory-explorer`, auto-discovered) - `scripts/` (index: `scripts/README.md`; + `lib/`, `checks/` read-only evidence
  scripts, `ui/` read-only UI plan engine, catalog, selection and Figma environment check) - `hooks/hooks.json` - `tests/` (+ `fixtures/`) - `evals/` - `docs/registry.schema.json`
