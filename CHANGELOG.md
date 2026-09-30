# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.3.0] - 2026-09-30

### Fixed
- **Install state was invisible.** `claude plugin list` still reported 0.1.0 while the source was
  0.2.0, and nothing checked what sessions load. `scripts/install-status.py` reports the load mode
  and state (CURRENT / STALE / CONTENT_MISMATCH / RESTART_REQUIRED / NOT_INSTALLED); a SessionStart
  hook warns when not CURRENT and the snapshot header shows the runtime version and load path.
  Observed with Claude Code 2.1.280: a **directory** marketplace (this workspace) loads the plugin
  in place from the marketplace directory - the version-keyed cache copy is only used by other
  marketplace types, where `claude plugin update` is a no-op until the version changes. README
  "Updating" documents both; the v0.3 roadmap's premise that v0.2.0 sessions ran v0.1.0 content is
  not supported by this evidence (only the install record was stale).
- **Guard: `xargs` tag creation** (`echo v9 | xargs git tag`) was allowed because the peeled command
  looked like a tag listing; xargs input is now modelled as an extra argument (deny). Found by
  `tests/installed-safety.sh`; the tripwire had caught it after the fact.
- **Guard bypasses.** The guard now covers the PowerShell tool (matcher `Bash|PowerShell`,
  PowerShell tokenizer with backtick escapes and the `&` call operator) and expands commands before
  classifying: wrappers (`env`, `sudo`, `timeout`, `nohup`, `nice`, `command`, `exec`, `xargs`,
  `find -exec`), nested shells (`bash/sh -c`, `eval`, `cmd /c`, `powershell -c`), repo git aliases;
  `$VAR` / `$(...)` as the program and interpreter one-liners running git ask.
- Guard: `gh api .../git/refs|tags` and `gh release create` are denied; `merge`, `cherry-pick`,
  `revert`, `am`, `pull --rebase`, `reset <commit>` on protected branches ask; `checkout -B`,
  `switch -C`, `branch -f`, `update-ref`, `gc --prune`, `reflog expire`, `prune` ask. Worktrees use
  their main checkout's protected branches.
- Routing: `backend/content/` was mapped by two modules (winner depended on registry order).

### Added
- **Tripwire** (`scripts/tripwire.py`, SessionStart/PreToolUse/PostToolUse): detects git state
  changes the guard could not see (tags, pushes, branch/HEAD/stash moves without a visible git
  command in that repo, modified or deleted baseline files, moved user submodules, changed dirty
  files inside submodules). Emits "STOP - rpg-factory tripwire" and latches the session (the guard
  denies non-read-only commands) until `tripwire.py --ack`.
- **Deterministic routing**: one primary lead (cross-repo driver > repo-kind driver on a touched
  source > primary owner > secondary owner > `skills.<name>.order`), ordered co-leads, AMBIGUOUS,
  `--lead` override (validated) and `--explain`. `.meta` paths route like their asset; unmapped
  files route to per-repo fallback modules `<repo>.root`.
- **Worktree-aware context**: the snapshot resolves the repo or worktree from the current directory.
- **Check runner** `scripts/run-checks.py`: runs the registry checks for the touched modules and
  grades them PASS / FAIL / BLOCKED / NOT_AVAILABLE / HUMAN_REQUIRED / SKIPPED with per-check
  parsers (`go-test`, `dotnet-test`, `exit`, `regex:`), `needs` dependencies, extended-tier approval
  (`--approve`), pollution detection (before/after `git status`) and an evidence JSON.
- **Derived cross-repo status** `scripts/factory-status.py`: contract consistency, the wire rollout
  chain (server bindings → Netcode copy → Netcode release → client pin), package release state
  (released / unreleased changes / READY_TO_TAG), pins vs latest tags, CI SGL watchers,
  unity-build-workflows refs and gitlink (`--remote`), in-flight `<type>/<area>/<topic>` branches
  linked across repos, and pending items with their owning skill. No stored state.
- Registry schema v3: `skills.order`, fallback modules, check `parser` / `needs`, `facts[]` with
  read-only probe commands (re-verified by `tests/facts.test.sh`), 16 human gates (`sgl-release`).
- `VERSION` file; run-all checks VERSION == plugin.json == marketplace == CHANGELOG section.
- Tests: guard bypass matrix (145 cases incl. PowerShell and wrappers), tripwire simulations,
  routing properties over real history, worktree, check runner, factory-status rollout fixtures,
  install-status (both load modes), facts; `tests/installed-safety.sh` drives the installed hooks
  against a disposable workspace (63 cases incl. tripwire STOP and latch; part of
  `run-all --release`); `tests/dogfood.sh --installed` runs headless sessions against the installed
  plugin and asserts the loaded source/version/path and the invoked skills.
- Snapshot routing prints an explicit "Next: invoke the Skill tool with the lead" line (installed
  dogfood showed sessions naming the lead without invoking it).

### Changed
- Snapshot diet: compact output filtered to the touched repos, toolchain probed lazily
  (all repos 16.1 KB / 15.3 s → 3.3 KB / 4.9 s; one repo with `--paths` 13.9 KB → 2.4 KB).
- `factory-core`: Resume step (factory-status), routing with lead/co-leads, validation through the
  runner, tripwire STOP rule, same branch topic across repos, plugin boundary clause
  (game-ai-workflows, web-game-factory).
- `pin-bump`: also moves the unity-build-workflows toolkit (submodule gitlink and reusable-workflow
  `@vN` refs); submodule bumps route to it.
- `wire-contract`: resumes at the first incomplete rollout stage; compatibility, rollout order and
  rollback table; `--min-protocol-version` on gateway and game server.
- `client-integration`: package-version awareness (codes against the pinned tag) and hand-off table.
- `server-realtime` trimmed; volatile values in skills replaced by registry facts;
  `skills-lint` flags rule sentences copied from the registry and missing plugin boundaries.

## [0.2.0] - 2026-09-30

### Added
- Eight specialised skills on top of Factory Core: cross-repo drivers `wire-contract`, `pin-bump`,
  `measure`; repo skills `server-realtime`, `server-services`, `server-ops`, `unity-package`,
  `client-integration`. Each follows `references/skill-contract.md` (Core first, registry facts,
  validation delta, generated paths, human gates, review checklist, report additions).
- Registry schema v2: repos `netcode`, `unitydots`, `uitoolkit`; 52 modules (deploy split into
  k8s/compose/monitoring/db, plus persistence, content, measurement-docs, wire-conformance, and 17
  package modules); `skills`; 9 `contracts` (wire-generated, protocol-version, join-token,
  redis-server-registry, nakama-rpc, sgl-pin, package-pins, gamestate-migrations, server-knobs with a
  `co_edit` clause); 15 `human_gates`; module `skills`/`gates`; 26 verified `known_issues`.
- `factory-context.sh`: cross-repo dependents (advisory), suggested skills with roles
  (lead / leg / follow-up), touched contracts with other ends / upstream / watchers, human gates,
  known issues; all five repos in the default snapshot.
- Check scripts: `pin-status.py`, `pin-plan.py` (incl. `--client-ref` historical replay),
  `wire-parity.sh`, `netcode-headless.sh` (temp-copy test run), `package-ready.py`.
- Tests: `tests/routing.test.sh` (25 task scenarios + 13 real historical commits replayed
  read-only), `tests/skills-lint.sh` (skill contract), JSON Schema validation in
  `check-registry.sh`; `tests/dogfood.sh` (opt-in headless sessions asserting the invoked skills -
  8 scenarios verified with sonnet).
- Evals: routing cases for server-realtime, server-ops, unity-package, server-services, plus
  wire-contract / pin-bump graders.

### Changed
- Contributor instructions moved from `CLAUDE.md` to `.claude/CLAUDE.md` (a root CLAUDE.md is not
  plugin context and fails `claude plugin validate --strict`).
- Plugin/marketplace descriptions describe the full workflow set.
- Git guard hardened: one invalid `human_gates` regex no longer disables the whole guard (each gate
  and the git evaluation fail independently).
- Git guard: creating, deleting or pushing tags is now **denied** (agents never tag); commands
  matching registry `human_gates[].match` (kubectl/helm/ssh, workflow dispatch, secrets,
  toggle-packages.sh, local stack) now ask. Protected branches come from each repo's registry entry.
- `factory-core`: new Route step (invoke the suggested lead skill), skill map, updated references.
- `server.gameserver-dotnet` knob rule corrected: passthrough is enforced against compose and fleet
  manifests (ComposeEnvPassthroughTests / FleetEnvPassthroughTests), not `20-configmaps.yaml`.

## [0.1.0] - 2026-09-30

### Added
- Factory Core v1 plugin (`rpg-factory`) with single-plugin marketplace.
- `factory-core` skill: workflow (scope, baseline, branch, plan, implement, obligations,
  validate, verify, review, report), live snapshot injection, global rules from the registry,
  and references for repos, validation, git safety, report template and skill contract.
- `registry.json` (27 modules across rpg-mmo-server and IndieRPGMMOAdventure) with
  `docs/registry.schema.json`.
- `scripts/factory-context.sh`: read-only live snapshot (branch, working tree, branch diff,
  submodules, touched modules and dependents, checks by tier, obligations, toolchain with
  `dotnet` -> `dotnet.exe` fallback, Unity MCP reachability); `--paths` and `--json` modes.
- `scripts/git-guard.py` PreToolUse(Bash) hook asking before destructive or high-impact git.
- `scripts/check-registry.sh`, `scripts/checks/unity-package-pins.py`.
- `tests/run-all.sh`, `tests/git-guard.test.sh`, and three `claude plugin eval` smoke cases.
