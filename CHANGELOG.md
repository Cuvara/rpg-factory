# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.4.0] - 2026-09-30

### Security
- **GitHub mutations were unguarded.** `gh api graphql` could create tags (`createRef refs/tags/*`,
  `createRelease`), `gh repo delete` and branch-protection writes were allowed. The guard now applies a
  structural gh policy: the API method is derived the way gh does (`-X`, else POST when fields or
  `--input` are given); reads pass; tag/release creation (REST and GraphQL) and repository
  deletion/archival are denied; every other remote mutation (branch protection, rulesets, repo
  settings, secrets, variables, workflows, runs, PR/issue changes, GraphQL mutations or queries from a
  file) asks. `gh` commands naming a workspace repo are checked even outside the workspace. These
  changes are remote-only, so the tripwire cannot see them - the guard is the only control.
- Protected refs and remotes: `git pull` without `--ff-only` on a protected branch, renaming or
  deleting a protected branch, `fetch <src>:<dst>` into local branches (forced or not; into tag refs =
  deny), `remote add/set-url/remove/rename`, `config` writes to aliases / remote URLs / `insteadOf` /
  `hooksPath` / credential helpers, `symbolic-ref` writes, `submodule add/set-url` now ask.
- **File tools were unguarded.** New `scripts/file-guard.py` (PreToolUse
  `Write|Edit|MultiEdit|NotebookEdit|Read`): writes into embedded package clones, submodule content,
  registry generated paths, the user's baseline files or secrets ask; secret reads ask; writes while the
  tripwire is latched or while a read-only mode is declared are denied. MCP tools are not inspected
  (documented; the `unity-asset-edit` gate remains the control).
- **A tripwire STOP vanished with its session.** The latch is now also written per workspace in the
  persistent state root: a crashed or closed session leaves the next one latched, SessionStart says
  why, and only the user's `--ack` clears it (the ack now rebuilds the baseline immediately).

### Fixed
- **State paths could be relative.** With `TMPDIR` empty (as in some shells), relative or invalid, the
  tripwire and runner wrote `rpg-factory/<session>/` into the current directory. All state now resolves
  through `scripts/lib/fstate.py` (always absolute; scratch under a usable `$TMPDIR` or `/tmp`,
  persistent state under `$XDG_STATE_HOME/rpg-factory` / `~/.local/state/rpg-factory`);
  `netcode-headless.sh` rejects a relative/invalid `TMPDIR`. Read paths no longer create directories.
- **The first dirty file of each repo was not protected.** The tripwire baseline stripped the first
  porcelain line and lost the first character of its path (and mangled quoted paths); it now parses
  NUL-separated porcelain.
- `is_read_only` treated `2>/dev/null` / `2>&1` as writes.
- Command `!` lines must match their own `allowed-tools` pattern or Claude Code refuses them (found by
  installed dogfood; now linted). factory-core asks for Factory script paths exactly as printed
  (absolute): relative paths hit permission prompts, and allow-listing relative paths would auto-approve
  any repo's own `rpg-factory/scripts/`.
- CHANGELOG 0.3.0 said 16 human gates; the registry has 15.

### Added
- **Execution modes** `analyze`, `plan`, `implement`, `validate`, `review`, `resume`: declared with
  `factory-context.sh --mode <m>` (printed in the snapshot), recorded per session by the guard and
  enforced by both guards (analyze/plan/review read-only; validate only `run-checks.py`). factory-core
  owns the mode table; every skill honours it. A PreToolUse(Skill) hook also records an explicit mode
  from Factory skill arguments ("plan only", "mode: validate") - installed dogfood showed sessions that
  never ran the Route command. Evidence: in v0.3.0 dogfood every missed lead invocation came from a
  plan-only prompt.
- **Commands** `/rpg-factory:status`, `/rpg-factory:route`, `/rpg-factory:check`, `/rpg-factory:doctor`
  (one validating dispatcher, `scripts/factory-cmd.py`). No `ack` command: clearing a latch stays a
  user action.
- **Tree-bound evidence.** `run-checks.py` stores each executed check with the identity of the tree it
  ran on (HEAD + diff and untracked files in the check's directory and its module's same-repo
  dependencies + the check definition) and its full log; `--status` grades the declared checks against
  the current tree without running anything: **STALE** after any relevant change, **NOT_RUN** when never
  executed.
- `factory-status.py`: package-CI pins from contract watchers (the real UnityDots CI -> Netcode v0.41.0
  vs the client's v0.45.0 drift is now pending), remote-knowledge **freshness** per repo (never fetches;
  prints the `git fetch` when older than 24 h), uncommitted work per repo, embedded clones, and stored
  evidence graded against the current tree. Status scans run in parallel.
- Workspace model: registry `repos.<key>.embedded_clones` (the client's gitignored
  `Packages/com.cuvara.*`): tripwire fingerprints them and samples their dirty files before/after each
  command (the user's own concurrent edits are not flagged); a snapshot run inside one says so
  instead of silently showing the canonical repos.
- Registry: contract `transport-security` (driver server-ops; TLS / `GAMESERVER_SEALED` switches vs the
  server, Netcode, client-pin and smoketest/verify capabilities - history `ed090ab`, `437a3db`);
  `package-pins` watchers; modules `server.bench` (measure leads benchmark harnesses) and
  `netcode.measurement` (measure co-leads).
- Skills: server-ops rollout order for security switches; unity-package package-CI pins;
  client-integration Unity-MCP hand-off (`references/unity-mcp.md`); measure ownership; factory-core
  game-ai-workflows hand-off.
- Tests: guard 252 (GitHub, refs/remotes/config, modes), tripwire 40, file guard 29, commands 30,
  run-checks 35 (evidence), factory-status 22, worktree 13 (clones), routing 52 (transport-security,
  bench, follow-up noise), installed-safety 83; dogfood gains analyze/plan/validate-only and command
  scenarios (13 real sessions against the installed plugin).

### Changed
- Performance (same harness, /mnt/c): SessionStart baseline ~12 s (was ~14 s; repos and clones now scanned in
  parallel), read-only command hooks ~0.19 s (was ~0.18 s), state-changing ~0.8 s (was ~0.9 s; signatures and
  clone samples in parallel), factory-status ~4.3 s (was ~4.8 s; parallel scans, one git grep), file guard
  ~0.09 s per file-tool call (new). Plugin scripts append (not prepend) their paths to sys.path so stdlib
  imports never stat /mnt/c first.
- `git pull` on a protected branch now asks unless `--ff-only`.
- Routing: a cross-repo dependent adds only its module's primary owner as a follow-up (a secondary owner
  such as `measure` on `netcode.measurement` is not downstream work of a wire change). Replay of all 358
  post-split commits against v0.3.0: 0 lead changes; co-leads/follow-ups differ only where intended
  (measure on 26 Netcode measurement commits, transport-security on 5 TLS commits).

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
  read-only probe commands (re-verified by `tests/facts.test.sh`), 15 human gates (incl. `sgl-release`; this entry originally said 16).
- `VERSION` file; run-all checks VERSION == plugin.json == marketplace == CHANGELOG section.
- Tests: guard bypass matrix (145 cases incl. PowerShell and wrappers), tripwire simulations,
  routing properties over real history, worktree, check runner, factory-status rollout fixtures,
  install-status (both load modes), facts; `tests/installed-safety.sh` drives the installed hooks
  against a disposable workspace (63 cases incl. tripwire STOP and latch; part of
  `run-all --release`); `tests/dogfood.sh --installed` runs headless sessions against the installed
  plugin and asserts the loaded source/version/path and the invoked skills.
- `--paths` normalisation: repo-prefixed (`rpg-mmo-server/backend/...`), absolute, comma-joined and
  glob paths resolve to repo-relative files (they used to fall to the repo fallback and lose routing).
  factory-core routes by the files the task writes (a benchmark writes the harness/BENCHMARK.md).
- Cross-repo tasks have one lead: a downstream contract end (e.g. the client's `PartyService.cs` for
  `nakama-rpc`) prints a **Cross-repo** line naming the upstream driver; factory-core says so.
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
