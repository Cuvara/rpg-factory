# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **Parallel-work policy.** New `skills/factory-core/references/parallel-work.md` is the single policy for
  delegated work: the main session is the lead and integrator; one worktree per implementation task (Orca-managed
  or `isolation: "worktree"`, never a second clone); one Unity writer per client project; shared exclusive
  resources go to one task at a time and a task without one reports `NOT_RUN`; QA and review run in parallel on
  a recorded candidate commit; the lead re-verifies, integrates in dependency order and cleans up only its own
  worktrees, keeping task branches (`orca worktree rm` also deletes a merged checked-out branch, so it is only for
  disposable branches). Orca is the preferred coordinator (load `orca skills get orchestration`; never a decision gate for
  routine work) with Claude Code worktree agents as the fallback. Tags, releases, deploys and `human_gates` keep
  their rules; nothing new asks or blocks. factory-core `SKILL.md`, `git-safety.md` (rule 10 now points here,
  rule 5 names the lead's integration-branch merges), `report.md` (optional parallel-work ledger) and
  `.claude/CLAUDE.md` point to it without copying it.
- `tests/skills-lint.sh` checks the policy is linked, exists in one copy (by its signature phrases), contains no
  blocking wording (ask/prompt the user, wait for / get / require approval or confirmation, until the user,
  `permissionDecision`) and keeps the release and `human_gates` rules; `tests/parallel-policy.test.sh` proves those
  checks fail on a mutated plugin copy; `tests/orca-commands.test.sh` verifies every cited `orca` command against
  `orca --help` and every `--flag` cited with it against that command's `--help` (skipped when Orca is not
  installed, and in `--no-workspace` runs), including that `orca worktree rm` still deletes branches as the
  policy warns.

### Fixed
- **Truthful check evidence.** A check's identity scope now includes its own module's paths, so editing
  `backend/content/` makes a `content-loader-tests` PASS (run in `backend/gameserver-dotnet`) STALE; a record
  made under another scope is STALE (`check scope changed`), so pre-upgrade records re-grade once. `factory-status`
  grades evidence against the current registry definition (a changed `run` is STALE there too, like
  `run-checks --status`) and a record of a check no longer declared is STALE. Two modules sharing one command each
  get a record graded with their own definition and identity (both PASS right after the run). A check whose
  `needs` prerequisite did not PASS in this run (failed, skipped by `--only`, listed after it) is BLOCKED.
  `run-checks` exits 2 on an unknown `--tier`/`--only` name, a bad `--timeout` and a `--paths` entry outside the
  repo checkout and its linked worktrees (a path inside a linked worktree routes by its repo-relative form), and
  prints `none registered` when no check is declared for the paths.

## [1.0.5] - 2026-10-22

Stability release after a full audit of 1.0.4 (hooks, session state, routing, install, release workflow). Hooks stay
advisory-only and never block; nothing asks for approval. Fixes: tag/push/destructive commands the guard missed
(git-bash `/c/` paths, shell blocks and functions, heredocs read by a shell, `gh --repo`), a missing or failing hook
script can no longer return Claude Code's blocking exit code, atomic and lossless session state and evidence under
concurrency, absolute `--paths` routing on Windows, stale-install detection, workspace worktrees in file-guard, and a
pre-tag `scripts/release-check.py`. Update the plugin (`claude plugin marketplace update rpg-factory && claude plugin
update rpg-factory@rpg-factory`) and start a new session. Evidence stored by 1.0.4 shows as NOT_RUN once (new
workspace key). No command-line or registry changes for users.

### Changed
- **Release policy wording matches practice.** The docs, skills, registry rule `no-tags`, snapshot header and guard
  advisories said agents never tag, while 1.0.4 was tagged and released by an agent on the user's explicit
  authorization. They now say: without explicit release authorization from the user in the current task, stop at
  READY_TO_TAG and the lead tags; with it, perform exactly the authorized merge, version, tag and release steps after
  the release checks pass on the tagged commit (never move, delete or reuse a tag). No behaviour change: the guard
  flags the same commands at the same advisory level, nothing blocks or asks. `run-all.sh` fails if the absolute
  "agents never tag" wording returns or a policy file drops the authorization rule.

### Fixed
- **Guard classification gaps.** `git-guard.py` stays advisory only (no permission decision, exit 0); these
  commands were missed or misread and now get the advisory they should:
  - Windows git-bash paths: `cd /c/...`, `git -C /c/...`, `/mnt/c/...` and such paths in the human-gate scan
    resolved to `C:\c\...` (no workspace, no advisory); they are mapped to drive paths first (`native_path`).
  - Shell reserved words hid git: `{ git tag v1; }`, `! git tag`, `if/then/else/elif`, `for/while/until ... do`,
    `f() { ...; }`, `function f { ... }`, PowerShell `if (...) { git tag v1 }` / `foreach (...) { ... }` (braces end
    a PowerShell command).
  - A heredoc read by a shell (`bash <<EOF`, `bash -s <<EOF`, `cat <<EOF | sh`) is analysed as commands; read by an
    interpreter (`python3 - <<PY`) and mentioning git/gh it is warn (opaque). Other heredocs (commit messages,
    `cat > file <<EOF`) stay data.
  - `gh --repo/-R/--hostname <x>` before the group or verb hid `release create`, `pr merge` and the `publish` gate.
  - Interpreter one-liners invoking `gh` (`python3 -c "...gh release create..."`, `node -e`) are warn like git.
  - Non-object JSON payloads (`[]`, `null`, `42`) crashed with a traceback (exit 1); stdin is read as UTF-8, so a
    non-ASCII cwd no longer breaks the workspace match on Windows.
  - `git tag --merged`, `--no-merged <c>`, `--no-contains <c>` and `--sort <full key>` / `--format '%(...)'` as
    separate words are listings (allow); a name after them, and the abbreviated `--sort -v:refname`, stay high.
  - Speed: read-only git subcommands (status, log, diff, ...) skip the per-repo git calls and the others are
    memoised per directory (30 x `git -C backend status`: ~1.36 s -> ~0.18 s on Windows); commands over 200 KB
    get one warn ("command too large to check") instead of minutes of parsing.
  - `factory-context.sh --mode <m>` run outside the workspace now records the mode (a stale read-only mode stayed),
    and the mode is only recorded when the script is actually run - `grep factory-context.sh --mode review` or
    `echo ... --mode plan` no longer switch it.
  - Wording: the module and `classify_gh` docstrings describe advisory levels high/warn, not deny/ask decisions.
- **Session state and evidence robustness.** Hooks stay advisory-only and never block; tests in
  `session-state.test.sh`, `run-checks.test.sh` and `factory-status.test.sh` cover each fix.
  - Evidence records and run records are written atomically (`fstate.write_json`, readers retry the Windows
    replace window); log and run-record names carry a pid + random suffix, so parallel or same-second runs never
    share or truncate a file. Only the newest 20 logs per check are kept (never the one the latest record names).
  - Valid JSON of the wrong shape in the evidence dir (`{"identity":"x"}`, `[1]`, no `state`) is treated as no
    evidence (NOT_RUN) instead of crashing `run-checks.py --status` and `factory-status.py`.
  - `run-checks.py --dry-run` writes nothing (no run record).
  - The auto-correction of an early tech skill to factory-core happens once per session even under parallel Skill
    calls (claimed by an exclusive `CORRECTED` file; the other calls get the lead-missing advisory).
  - The Skill hook's logs are one file per event (`SKILLS.d/`, `ADVISORIES.d/`): parallel appends lost lines on
    Windows. Legacy `SKILLS` / `ADVISORIES` files are still read. Read them with
    `factory_session.py --skills <session-id>` / `--advisories <session-id>` (used by git-guard.test.sh and dogfood.sh).
  - `MODE` is replaced atomically (no torn reads). A mode is recorded only when the command really runs
    `factory-context.sh` / `context.py` (`grep factory-context.sh --mode review` or `echo ...` no longer set it), and
    "do not implement" alone in Skill arguments is no longer a plan-mode declaration.
  - The hook prints its advisory / correction before logging; an unwritable log loses nothing the session sees,
    and with no usable session dir it advises without correcting.
  - Session ids go through one helper, `fstate.session_key()`: plain ids are unchanged, anything else (`..`, `.`,
    over 100 characters, characters a substitution would collide) becomes `s-<sha1>`.
  - A bare registry skill name (`go-backend` without `rpg-factory:`) is recorded and gated like the prefixed name.
  - `fstate.scratch()` skips a candidate whose `rpg-factory/` cannot be created; `persistent()` falls back to the
    platform temp dir (absolute on Windows too).
  - The evidence workspace key is the case-folded real path, and `run-checks.py` and `factory-status.py` resolve
    `RPG_FACTORY_WORKSPACE` the same way. Evidence stored under the old key shows as NOT_RUN once; rerun the checks.
- **Routing, install and docs.**
  - `factory-context.sh --paths` with an absolute (`C:\`, `C:/`, git-bash `/c/`, WSL `/mnt/c/`) or glob path
    routed nowhere on Windows (`relpath` returned backslashes, lead null). Paths are normalised to repo-relative
    forward slashes; another drive no longer raises. New routing scenarios (absolute forms, glob).
  - A missing hook script made python exit 2, Claude Code's blocking code. Every `hooks.json` command now ends
    with `; exit 0` (bash and PowerShell); stdout still passes through. run-all checks the wiring and runs each
    command against a missing and an exit-2 script.
  - `install-status.py` reported CURRENT for an old cache copy on Windows (backslash `CLAUDE_PLUGIN_ROOT` missed
    the `/.claude/plugins/cache/` test) and whenever the runtime version differed from the source; both are now
    RESTART_REQUIRED. `--session` never tracebacks on malformed `installed_plugins.json` /
    `known_marketplaces.json` and always exits 0. New informational note (doctor, `--json` `notes`) when the
    source HEAD is not the commit of tag `v<VERSION>` (`source 1.0.4 + N commits past v1.0.4`); no state change.
  - `file-guard.py`: linked worktrees of a workspace repo (`.wt-client-cleanup/`) get that repo's rules (via the
    git common dir); paths outside the workspace get no advisory even with `RPG_FACTORY_WORKSPACE` set; the mode
    advisory command is quoted with forward slashes; secret names match case-insensitively (`.ENV`).
  - `tests/dogfood.sh` looks for the session's `ADVISORIES` / `MODE` under both `fstate.scratch()` and
    `persistent()/tmp` (headless hooks on Windows Python 3.14 fall back to the latter).
  - Agent-facing wording said the hooks enforce or deny (snapshot mode line, `tag (deny)` in Human gates, pin-bump
    "denied by the guard", `.claude/CLAUDE.md`); it now says advisory (`tag (high)`), pin-bump names the explicit
    release authorization, README marks the pre-1.0.3 "denied" note historical and states the Windows scratch
    root, and the `--mode` / path forms are documented in the usage headers. run-all fails if
    `denied by the guard`, `hooks enforce` or `(deny)` returns in agent-facing text.
  - New `scripts/release-check.py` (read-only) gates a release before the tag (versions agree, CHANGELOG section,
    empty `[Unreleased]`, tag absent locally and on origin, HEAD == origin/main, clean tree; `--notes` prints the
    release notes) and verifies it afterwards (`--verify-tag`: annotated, `rpg-factory X.Y.Z`, at HEAD, VERSION).
    `tests/release-check.test.sh` (throwaway repo, local bare origin) runs in run-all; the order is in
    `.claude/CLAUDE.md` "Releases".

## [1.0.4] - 2026-10-22

Fix: tech skills stay behind their lead skills under the advisory-only hooks of 1.0.3, still without blocking or
asking. A tech skill requested before factory-core loads factory-core instead (auto-corrected); one requested
before its lead runs with an advisory. Update the plugin (`claude plugin marketplace update rpg-factory && claude
plugin update rpg-factory@rpg-factory`) and start a new session. No command-line or registry changes.

### Fixed
- **Skill order under advisory-only hooks (1.0.3 dogfood regression, `tech-go` and `tech-dots`).** With the
  Skill hook advisory-only, a model could load a tech skill before its lead; dogfood reported it as a failure
  and nothing showed whether the session corrected itself. The hook still never blocks or asks:
  - a tech skill requested **before factory-core** is auto-corrected: the call loads `rpg-factory:factory-core`
    instead (`updatedInput`; Claude Code honours it for the Skill tool - verified in a headless session, not
    documented for Skill), with an advisory naming the route command and the leads. Once per session (factory-core
    is then recorded), so it cannot repeat or loop. If a Claude Code version ignores `updatedInput`, the tech skill
    loads and the advisory still applies;
  - requested **after factory-core but before its lead**, it runs with an actionable advisory ("this call
    continues", the route command, the leads). No auto-correction there: two to four leads use each tech skill and
    only routing knows which applies.
  - every advisory is logged to the session's `ADVISORIES` file, and `SKILLS` records what actually loaded.
  - `tests/dogfood.sh` now grades what loaded (the "Launching skill" results, so an auto-corrected call counts as
    factory-core) and passes a tech-first session only with evidence: the hook's advisory for it, one of its leads
    loading afterwards, and a finished session. New scenario `tech-first` forces the auto-correction. The mode check
    reads the real session state path (`fstate.scratch()`, not `/tmp/rpg-factory`).
  - regression cases in `git-guard.test.sh` (early go-backend, early unity-dots, normal order, no second
    auto-correction, never a permission decision, the hook always exits 0) and `session-state.test.sh`.
- The README "Version" line still said 1.0.0 through 1.0.1-1.0.3; `run-all.sh`'s version check now covers it
  (VERSION == plugin.json == marketplace == CHANGELOG section == README).

## [1.0.3] - 2026-10-22

Hotfix: the hooks never ask for confirmation and never block; every former ask/deny rule reaches the agent
as an advisory. Update the plugin (`claude plugin marketplace update rpg-factory && claude plugin update
rpg-factory@rpg-factory`) and start a new session. Also ships the citation drift guard (PR #6, new optional
registry field `skills.<s>.cite_roots`) and the skill authoring workflow (PR #9). No command-line changes.

### Added
- **Skill authoring workflow.** Adding a skill meant about 25 hand edits across the registry, skills,
  tests, docs and evals, and several lists had already gone stale (unity-dots and netcode-client were missing
  from the factory-core tech list, the README diagram and tech table, and dogfood; go-backend and
  dotnet-gameserver had no eval grader).
  - `scripts/new-skill.py` scaffolds a lead or tech skill: `SKILL.md` with every section skills-lint
    requires and `SCAFFOLD:` markers, plus the registry entry (order after the existing skills of its kind,
    so it never outranks one in routing ties; module ownership or contract driver; `dev_tools.used_by`;
    `cite_roots`). It refuses anything it cannot validate and rewrites `registry.json` only when a JSON
    round trip reproduces it byte for byte.
  - `scripts/skill-touchpoints.py` (read-only, run by `skills-lint.sh --all`) checks that every skill is
    in the factory-core Skills section, the skill-contract diagram, the README diagram and tables,
    `.claude/CLAUDE.md` (names and counts), the plugin manifests' lead count, a routing scenario, a
    dogfood scenario and an eval grader - and that no `SCAFFOLD:` marker is left.
  - Repo-local skill `.claude/skills/skill-author/` (not a plugin skill): the order of work from the
    learning-loop gate to a green run-all.
  - The stale places were fixed; new dogfood scenarios `tech-dots`, `tech-netcode` and evals
    `go-single-test`, `dotnet-single-test`. The routing test's tech list and the Skill-hook test now come
    from the registry, so a new tech skill needs no edit there. `tests/new-skill.test.sh` (22 cases).
- **Citation drift guard (`scripts/checks/skill-citations.py`).** Skills cite product code by
  `path:line`; nothing checked those lines, and a smoke test after 1.0.0 found 9 of 12 sampled server
  citations pointing at the wrong code (e.g. `WriteLoopAsync` cited at `Connection.cs:841`, now 1019). The
  checker reads every line citation in `SKILL.md` and `references/*.md` (full paths, ranges, lists, bare
  `:N` continuations, bare basenames, `dots:`/`client:` and repo-name prefixes) and resolves it at each
  repo's integration branch (`origin/<default_branch>`, `--ref repo=REF` to override) - never the working
  tree. Each line citation needs an **anchor**, the symbol it shows written in backticks before it; the
  anchor must occur within the cited lines +/- 3, else `drift` (with `--suggest`, the corrected line).
  Lines past the end, missing or ambiguous files and line citations outside backticks fail too; a missing
  repo is SKIP. New registry field `skills.<s>.cite_roots` (schema + `check-registry.sh`) says where a
  skill's paths resolve. `skills-lint.sh` runs the repo-free part (`--offline`: backticked and anchored),
  `run-all.sh` the fixture suite `tests/skill-citations.test.sh` and the live check against the workspace.
  The rule is in `skill-contract.md` ("Line citations are checked against the code").

- `check-registry.sh` rejects duplicate keys in `registry.json`: they are valid JSON and jq and Python
  silently keep the last one (a duplicated `cite_roots` hid that another skill had none).

### Changed
- **Hooks are advisory only: they never ask the user and never block the agent.** Agents using the plugin
  still stopped for a human Yes/No: every guard rule returned a `permissionDecision` - `ask` (destructive git,
  any push, rebase, stash, human gates, file-guard rules) shows a confirmation prompt only a person can answer,
  and `deny` (tags and GitHub Releases, `gh repo delete/archive`, read-only execution modes, a tech skill before
  its lead) blocked the call. Now `git-guard.py`, `file-guard.py` and `factory_session.py --skill` never emit a
  `permissionDecision`. A match is returned as `additionalContext`
  `rpg-factory advisory (high|warn): <rule>` - `high` for the former deny class, `warn` for the former ask
  class - and the tool call proceeds through Claude Code's normal permission flow (the user's own settings
  are untouched). The classifiers and rule texts are unchanged; the policy in `git-safety.md` stays as
  guidance for the agent.
- Tests read the advisory level (`high` / `warn` / `allow`) instead of a decision, and every test command
  fails if any hook output contains `permissionDecision`. `tests/session-state.test.sh` adds direct probes
  (rebase, force push, tag, `gh repo delete`, `reset --hard`, multi-client, `kubectl`, a tech skill before its
  lead). `installed-safety.sh` still executes only commands with no advisory.
- `skill-contract.md` "New skill" names every required registry field (`order`, `used_by`, `cite_roots`).

### Fixed
- The skills' line citations, refreshed against the integration branches: drifted lines moved, every
  citation anchored, claims that no longer hold corrected.

## [1.0.2] - 2026-10-21

Fix: read-only inspection of a gated script (`sed -n`, `cat`, `grep`, `head`) no longer asks for a human
gate. Update the plugin (`claude plugin marketplace update rpg-factory && claude plugin update
rpg-factory@rpg-factory`) and start a new session. No command-line changes; the registry gains the optional
`human_gates[].read_only_exempt` field.

### Fixed
- **Human gates no longer ask for read-only inspection of a gated script.** The gate regexes match script
  names anywhere in a command, so `sed -n 300,340p Tools/verify-multiclient.sh` asked under `multi-client`
  exactly like running the script (same for `cat bench.sh`, `grep x backup.sh`, `head toggle-packages.sh`).
  New registry field `human_gates[].read_only_exempt` (schema): the git guard skips such a gate when the
  whole command is read-only (`factory_session.is_read_only`, the classifier the execution modes use). Set
  on every gate with a `match` except `secrets`, whose point is reading. Running, editing (`sed -i`),
  redirecting, or piping a gated script into a shell still asks.
- `is_read_only` accepts print-only `sed` (`N,Mp`, `/re/p`, `Nq`, with `-n`/`-e`/`-E`); `-i`, `-f`, the
  `e` and `w` commands, `s///` and multi-command scripts stay non-read-only. A read-only mode therefore
  allows `sed -n 10,40p file`.

## [1.0.1] - 2026-10-21

Hotfix: the tripwire and its workspace latch are removed. Update the plugin (`claude plugin marketplace
update rpg-factory && claude plugin update rpg-factory@rpg-factory`) and start a new session: hooks bind at
session start, so a running session keeps the old hooks until it is restarted. No registry schema or
command-line changes.

### Changed
- The execution-mode and tech-skill-order logic moved from `scripts/tripwire.py` to
  `scripts/factory_session.py` (Skill hook: `factory_session.py --skill`). Behaviour is unchanged.

### Removed
- **The tripwire and its latch, on purpose.** `tripwire.py` snapshotted every workspace repo around each
  non-read-only Bash/PowerShell call. Any ref or baseline-file change in that window, whoever made it,
  raised a STOP and latched the whole workspace for every session until the user ran `tripwire.py --ack`.
  In practice the Unity Editor saving `ProjectSettings/ProjectSettings.asset` latched it within minutes,
  during read-only commands, and blocked autonomous work in every session. Removed with it:
  - the SessionStart baseline scan, the `--pre` PreToolUse hook and the PostToolUse /
    PostToolUseFailure `--post` hooks;
  - the latch deny in `git-guard.py` (`latch_hits`) and `file-guard.py`, and the guard rule that denied
    `tripwire.py --ack` to the agent (`ack_hits`);
  - the file guard's "already dirty when the session started" ask, which read the tripwire baseline;
  - `fstate` latch, audit and activity paths and `ack_command()`; the doctor "Tripwire latches" section;
  - the STOP, ack and recovery instructions in `factory-core`, `git-safety.md`, `report.md` and the
    doctor command;
  - `tests/tripwire.test.sh`.

  State files left by older versions (`latch/`, `audit/`, `activity/` under the persistent state root, a
  session `LATCH`) are no longer read and can be deleted. `tests/session-state.test.sh` (new) checks that
  stale latch files block nothing (`git fetch --tags`, commits, writes), that no hook or script reads them,
  and keeps the state-path checks from the old suite. The git guard (tag deny, destructive-git asks, human
  gates), the file guard's other rules and the execution modes are unchanged.

## [1.0.0] - 2026-10-20

First stable release. Supported environments: Linux, WSL and Windows (Git for Windows bash with native
Windows Python). No registry schema, hook or command-line changes are required of users:
update the plugin (`claude plugin marketplace update rpg-factory && claude plugin update
rpg-factory@rpg-factory`) and restart the session. Legacy single-file latches from 0.5.0 and earlier are
still read and migrated on `--ack`.

### Added
- **Game rules live only in Shared.GameLogic (ADR-10).** Until now the rule existed only in the
  client's stale `unity-netcode` agent. Factory said nothing when a client or package change
  reimplemented movement, combat or validation logic that the server must agree with. New module rules
  cover `client.scripts`, `netcode.runtime` and `unitydots.runtime`: never copy a game rule. Stop the leg
  and hand the rule to `server-realtime`, then to `pin-bump`. A new rule on `server.gameserver-dotnet`
  says that logic the client must reproduce goes into `Shared.GameLogic`, not only into `GameServer/`.
  `client-integration` has a new workflow step and a new hand-off row, and `server-realtime` step 2 names
  the placement. `tests/routing.test.sh` asserts that each of the four snapshots carries the rule.
- **Tech skill `unity-dots`** (Entities/Burst/Jobs in UnityDots and the client): the ECS-vs-classic
  decision (ECS for many homogeneous per-frame entities; services, UI and request/response state stay
  VContainer + UI Toolkit), the group tree and bootstrap install, `SystemOrderVerifier`, the package ECB
  singleton, the measured `ParallelScheduling` thresholds, archetype-stable spawning, sync points,
  allocators, change filters and ECS tests, every claim cited. References `dots-patterns.md` and
  `ecs-review.md` (the review checklist). Used by unity-package, client-integration and measure.
- **Tech skill `netcode-client`** (com.cuvara.netcode on the client): TCP gateway hop vs KCP-only
  gameplay and its PlayerLoop pump, KcpCrypto (CRC, no integrity) vs the sealed session, codecs,
  snapshot interning and merge, the interpolation clock, movement prediction and reconciliation with
  clock steering, reconnect policy, per-packet allocations, the headless suite. Replaces the client's
  stale `unity-netcode` agent. Used by unity-package, wire-contract, client-integration and measure.
- `unity-client-tech` reference `ui-toolkit.md`: View/ViewModel/Presenter, one-way binding, the
  package list adapters and virtualization, screen flow and subscription lifecycle, the two ways game
  state reaches UI, VContainer scopes and lifetimes. ECS idioms moved to `unity-dots`.
- `measure` reference `client-profiling.md` (markers, Performance Testing, MCP `profiler-*` as point
  samples, no budget without a baseline) and `legs.md` sections for server profiling, the seeded
  network-adversity suites and soak (NOT_AVAILABLE until a harness exists).
- `server-realtime` reference `gameplay-systems.md`: where combat, abilities, statuses, inventory,
  loot and content live, the authority checklist for a new input or command, SGL determinism, and the
  known structural debt.
- **Fast check `sgl-determinism`** (`scripts/checks/sgl-determinism.py`, module
  `server.shared-gamelogic`): fails on any `Math`/`MathF` transcendental in Shared.GameLogic (ADR-10),
  ignoring comments and strings. Fixture tests in `run-all.sh`.
- Registry facts `entities-version`, `burst-version`, `collections-version`, `unity-physics-version`,
  `vcontainer-version`, `unitask-version`, `perf-testing-version`; dev tool `dotnet-diagnostics`
  (`dotnet-counters` / `dotnet-trace`, optional, fallback the server's OTel metrics).
- Evals `dots-spawn-system`, `prediction-reconcile-bug`, `claim-faster-frame`, `inventory-list-screen`,
  `new-command-authority`, `ecs-or-service`; routing scenarios for the new tech skills.
- **CI.** `.github/workflows/tests.yml` runs `tests/run-all.sh --no-workspace --no-claude` on every pull
  request and push to `main` (read-only token, pinned actions, log artifact, FAIL/SKIP summary). The
  runner has no RPG MMO workspace, so workspace checks show as SKIP there; `tests/run-all.sh` with the
  workspace is still required locally before a release.
- **Stash audit.** A visible `git stash` (the approved path) is appended to `audit/<workspace>.jsonl`
  with session, tool call id, command and the stash SHA before and after. It does not latch.

### Changed
- **A tech skill waits for its lead (Skill hook).** The release-gate dogfood `tech-go` failed 4/4 runs: asked
  how to run one gateway test, the model invoked `go-backend` right after `factory-core`, before routing and
  before `server-services`, so the answer skipped the lead's rules and gates. `tripwire.py --skill` now records
  each Factory skill a session runs and denies a `kind: tech` skill until one of its registry `used_by` skills
  ran, with a message naming the route command and those leads; it fails open without a registry. The
  `go-backend` description now has the same "how it works / not for scope" form as the other tech skills.
  `tests/dogfood.sh` counts only Skill calls that ran (a denied call is not an invocation); 12 cases in
  `git-guard.test.sh`.
- **`routing.tech` lists a tech skill only when the snapshot's repo is in its `repos`.** A measure run
  on the server no longer suggests `unity-dots`/`netcode-client`, and a client `Tools/` change no longer
  suggests `dotnet-gameserver` (`scripts/lib/resolve.jq`, skill-contract "Tech skills").
- factory-core step 11 (Review) applies the lead's checklist and the review file of every
  `routing.tech` skill after `/code-review`; the report template gains **Review** and **Lessons**.
- Skill contract: a **learning loop** (a verified failure lands in exactly one of: regression test,
  cited Pitfall, `known_issues`, `facts[]`), version-specific API advice names its fact, and every tech
  skill Pitfall cites a file or issue (`skills-lint.sh` enforces it).
- `known_issues` for the stale client/server CLAUDE.md text and the `unity-netcode` agent name the
  product-repo branches that fix them; remove each entry when its branch reaches the default branch.
- **Tripwire events instead of one latch file.** Each incident is `latch/<workspace>/<event-id>.json` with
  the command, session, tool call id, ref values before and after, and recovery hints (for a dropped
  stash: its SHA and `git stash apply <sha>`). A second incident no longer overwrites the first. `--ack`
  archives events to `acked/` (kept 30 days) instead of deleting them; `--ack <event-id>` acknowledges one,
  and an event created while an ack runs stays open. The latch stays global per workspace. A legacy
  `latch/<workspace>.json` still blocks and is migrated into `acked/` on ack.
- `--status` lists open events with ref values, recovery hints, recent audited stash operations and the
  exact ack command.
- While latched, read-only investigation is allowed: `git reflog` (not `expire`/`delete`/`drop`/`write`,
  which rewrite the history the recovery hints point at), `git stash show` and `git branch --list <pattern>`.
- Snapshots of calls without a `tool_use_id` are keyed by the command, so parallel calls do not share one.
  A second legacy latch is archived next to the first instead of overwriting it.
- git-safety: never stash/reset/clean to get a clean tree (export HEAD instead), never assume a stash is
  yours, one mutating command per worktree, and the recovery procedure after a STOP.

### Fixed
- **Windows (git-bash + native Windows Python) is a supported environment.** On Windows `tests/run-all.sh`
  failed 12 checks before any Factory change. Causes and fixes:
  - `jq -r` writes CRLF there, so `$(jq -r ...)` loops kept a carriage return (`skills/foo<CR>/SKILL.md` does
    not exist): 10 skills-lint failures. New `scripts/lib/compat.sh` (sourced by every test suite and
    `check-registry.sh`) strips it on MSYS/MINGW/CYGWIN only, and adds `mktemp_win`, `is_abs`, `fwd`,
    `path_entry` and `dir_readonly`/`dir_writable` (an ACL, since `chmod 555` does nothing on NTFS).
  - Test scripts passed MSYS paths (`/c/...`, `/tmp/...`) to native Python, which cannot resolve them
    (`No module named 'fstate'`, fixture workspaces never found). `ROOT` now comes from `pwd -W` and temp dirs
    from `mktemp_win` (`C:/...`). `install-status.test.sh` also sets `USERPROFILE`: Windows Python ignores `HOME`.
  - Tests compared native Python paths (`C:\x`) as strings with bash paths (`C:/x`); they now normalise.
  - **Output encoding.** Python entry points wrote cp1252 into pipes (the snapshot showed `?` for `·`,
    `pin-plan.py` crashed on `→`), and 16 `subprocess` calls decoded git and jq output as cp1252. Every
    entry point now writes UTF-8 and every `text=True` call decodes UTF-8 (`errors="replace"`).
  - **Tool lookup ignored `PATHEXT`.** `context.which` and `devtools.which` looked for `python3`, not
    `python3.exe`, so the snapshot said `python3 MISSING` and listed every Python-based fast check as MISSING
    (not run) on Windows. Both now try the `PATHEXT` extensions.
  - **Every check that calls a Factory script failed on Windows.** `{plugin_root}` was substituted as
    `C:\...\rpg-factory`, and `run-checks.py` runs each check through `bash -c`, which drops the backslashes
    (`can't open file '...WorkspacesUnityIndierpg-factory\scripts\checks\sgl-determinism.py'`). It is
    substituted with forward slashes; `run-checks.test.sh` runs a `{plugin_root}` check with a backslash root.
    The guard's mode denial printed the same broken form (`bash C:/x\scripts\factory-context.sh`); it now
    prints a quoted forward-slash path (`git-guard.test.sh` checks it with a backslash root).
  - Registry fact `netcode-vendored-protobuf` probed with `strings`, which git-bash lacks; the probe is
    Python now (same value, 3.29.3). `ci-integration-on-pull-request` opens `ci.yml` as UTF-8.
- **`netcode-headless.sh` compiled nothing since Netcode's prediction tests need Shared.GameLogic.** The temp
  copy had no sibling `rpg-mmo-server`, so `Vec2`/`MapBounds` were missing and no `.trx` was produced. The check
  now does what Netcode CI does: Shared.GameLogic at the tag `package.json` pins (`x-manualDependencies`), taken
  with `git archive` from the workspace server repo into the temp dir, passed as `-p:SglDir` (352/352 run).
  The path is converted for Windows `dotnet.exe`: `cygpath -m` in git-bash, `wslpath -m` in WSL.
- **`package-ready.py` crashed in WSL and read a failed `git status` as a clean tree.** Over `/mnt/c` a cold
  index made `git status` exceed the 30 s timeout (traceback, no verdict). git calls now allow 120 s; a git
  timeout or a failing `git status` exits 2 with "readiness unknown" instead of continuing as if the tree were
  clean (`run-all.sh` covers the non-repo case).
- **Per-project MCP servers were never found on Windows.** `~/.claude.json` keys projects as `C:/x/y`; the
  probe looked up `C:\x\y`, so a project-scoped server such as `ai-game-developer` showed as not configured.
  Keys are compared normalised.
- `run-all.sh`: when live `pin-status` fails and the client's pin files hold uncommitted user changes (the
  local `file:` toggle), the committed HEAD is verified through a read-only export and the live check is
  reported as SKIP with that result, never as PASS. New `tests/compat.test.sh` covers the helpers, UTF-8
  output under a cp1252 stdout, the `PATHEXT` lookup and (by AST) that every `text=True` call decodes UTF-8.
  README has a Windows section with requirements and troubleshooting. A clean tree that fails still fails. `py_compile` now
  covers `scripts/lib/*.py`, reads UTF-8 and treats `SyntaxWarning` as an error.
- `unity-client-tech` cited the client `CLAUDE.md` by line numbers, which had drifted by about 15 lines.
  The citations now use section names.
- **Tripwire false STOPs across sessions.** The pre-command snapshot was one `pre.json` per session,
  consumed by whichever PostToolUse came next. A call denied by the guard (PreToolUse ran, PostToolUse
  never does) left its snapshot behind, and the next read-only command (`tripwire.py --status`) compared
  against it and was blamed for every ref another session had changed in between. Parallel calls of one
  session overwrote each other's snapshot. Snapshots are now per tool call (`pre-<tool_use_id>.json`),
  read only by the same call, written atomically, and pruned after 2 h when a call never completes.
  Without a `tool_use_id`, a snapshot of a different command is discarded.
- **Concurrent sessions.** A ref change is explained when another session's (or a parallel call's)
  completed command saw that same ref reach that same value while its own visible git ran in that repo,
  and its subcommands could make that change: `commit`/`merge`/`reset`/... move only the branch it had
  checked out, `branch`/`switch`/`checkout -b` create branches, `fetch`/`push` move remote-tracking refs,
  `stash` moves `refs/stash`. A read-only `git log`, a different ref, a tag or an unfinished call never
  explains anything, so a hidden reset of `develop` still trips while another session commits elsewhere.
- **Failing commands were never checked.** A Bash call that exits non-zero fires `PostToolUseFailure`,
  not `PostToolUse`; the tripwire now runs `--post` on both (`hooks.json`).
- **A worktree ref change was reported twice** (once per checkout sharing the refs); it is now reported
  once, under the worktree the command ran in.
- Cache writes that fail (Windows: `os.replace` onto a file another hook has open) are retried, never
  leave temp files, and never cost the comparison.
- **The printed ack command did not work.** `os.path.join` produced `C:/.../rpg-factory\scripts\tripwire.py`;
  bash dropped the backslashes and the user's ack silently failed. Every message (STOP, guard denials,
  file guard, SessionStart, doctor) now prints `fstate.ack_command()`: quoted, forward slashes.
- **`--ack` reported success it had not checked** and always exited 0. It now re-reads the state and
  prints `latch is now CLEAR` (exit 0) or `still LATCHED: <ids>` / `NOT cleared: <reason>` (exit 1;
  2 = invalid id). Repeating it is safe; unknown ids are reported.

### Security
- The guard now denies `tripwire.py --ack` to the agent at all times, not only while latched, so an agent
  cannot dismiss an incident another session raised a moment earlier. It matches any Python invocation of
  the script (options before it, `py -3`, `python -c ... run_path`, the path behind a variable) and no
  longer denies `grep -- --ack tripwire.py`.
- **The git guard ignored a workspace when `RPG_FACTORY_WORKSPACE` named another one.** The env root was tried
  before the cwd, so a second checkout of the workspace (or a `cd` into it) counted as "outside the workspace"
  and `git tag`, `push --tags` and `reset --hard` there passed without a decision. The nearest workspace above
  the cwd now wins and the env root is the fallback; after a `cd` the new directory's workspace applies.
- **`git -C <workspace repo> ...` from outside the workspace was not checked** when `RPG_FACTORY_WORKSPACE`
  was unset (`git -C .../rpg-mmo-server tag v1` from another directory was allowed). The workspace is now
  resolved from the directory git works in. Cases in `git-guard.test.sh` and `installed-safety.sh`.
- **The guard went silent on Windows path and encoding differences.** It compared paths as strings, so a
  payload cwd `C:/ws/x` did not match the workspace found as `C:\ws` and every command there was skipped; and a
  non-ASCII branch name (a UTF-8 byte cp1252 cannot decode) raised inside the guard, which counts as "no
  opinion". Paths are compared normalised and git output is decoded as UTF-8. New `git-guard.test.sh` cases
  cover both, the env-root case and `cd` between workspaces.

## [0.5.0] - 2026-10-01

### Security
- **Unity batch-mode test runs were ungated.** Factory treats Unity tests as external
  (HUMAN_REQUIRED), but the new tech skill and the client's Unity MCP reference offered a batchmode
  `-runTests` run as the agent's fallback when the Editor is closed. Nothing gated it, and the run opens
  the user's project, which can rewrite `packages-lock.json` and settings and triggers a reimport. The
  `unity-batch` human gate now also matches `-runTests` and the `_SampleBuild` build entries
  (`PlayClientBuilder`, `SampleBuilder`), which the remap had brought under that gate without its
  regex. The skills now hand the user the batchmode command instead of running it.

### Added
- **Dev tools per skill.** New registry `dev_tools[]` records the MCP servers, plugins and binaries
  the skills use: `unity-mcp`, `lsp-go`, `lsp-csharp`, `pg-aiguide`, `context-mode`, `codex`,
  `dotnet`, `go`, `protoc` and `docker`. Each entry has `probes`, `used_by` skills, `required` and a
  `fallback`. `scripts/lib/devtools.py` probes them: PATH, registry tools, TCP services, MCP server
  names (from workspace/repo `.mcp.json` and `~/.claude.json`) and enabled plugins. Config files are
  parsed in memory, but only server and plugin names leave the module. Env, headers and URLs are
  never returned, printed or stored.
- The snapshot prints a **Services** line and, per repo, **Tools for this change** (OK / DOWN /
  MISSING, with the fallback) for the routed skills. `/rpg-factory:doctor` has a **Dev tools**
  section that also lists skills missing a required tool.
- `check-registry.sh` and the schema validate `dev_tools`: fields, probe syntax, known tools,
  services and skills, and a fallback for every tool. They also accept the new skill kind
  `tech`, which needs `used_by` (repo or cross-repo skills) and must not own a module or contract.
  Known issues `no-csharp-lsp`,
  `golangci-lint-missing` and `gameserver-claude-stale` were added, and `client-claude-stale` was
  extended.
- Tests:
  - `tests/devtools.test.sh` adds scenarios over the real registry in a controlled environment: all
    tools OK; Unity Editor closed (`unity-mcp` DOWN, not MISSING or OK); no C# LSP (`lsp-csharp`
    MISSING with its fallback, doctor still exits 0); a malformed config with a planted secret
    surfaces no content or traceback.
  - `tests/facts.test.sh` proves a stale registry value is caught by re-probing the repo.
  - `tests/routing.test.sh` checks that `--lead <tech skill>` is rejected.
  - `tests/dogfood.sh` adds `tech-dotnet`, `tech-go` and `tech-unity`: real sessions must invoke the
    repo skill and its tech skill, and apply the reported tool fallback.
- `tests/devtools.test.sh` covers the probes, the snapshot, doctor, planted secrets that must never
  be printed, and malformed registry entries.
- **Tech skills** (new skill kind `tech`) explain how a technology works in this workspace. Repo
  skills keep where a change goes and which rules apply. Tech skills own no module, so they are never
  lead, leg or follow-up. `resolve.jq` emits `routing.tech`: the tech skills used by a working skill
  (lead, co-lead or leg). The snapshot prints it in the routing line and the Next hint.
  - `dotnet-gameserver` (used by server-realtime, wire-contract and measure): tick order (the tick
    gathers and connection write tasks encode/send), rates, ECS world locking, zero-alloc idioms and
    what each guard covers, SGL compiler limits, the Net layer, xUnit idioms and filters, NativeAOT.
  - `go-backend` (used by server-services and wire-contract): six modules that `replace` shared
    without go.work, gateway entry points, storage seams, test doubles (`miniredis.RunT`, httptest,
    embedded `runtime.NakamaModule`), single-test commands, and when the dotnet interop tests skip.
  - `unity-client-tech` (used by client-integration, unity-package and pin-bump): Entities system
    install and world lifecycle, Task vs UniTask boundaries, main-thread rules, VContainer, asmdef and
    test-assembly rules, domain reload, WebGL limits, single tests through Unity MCP `tests-run`
    filters (with the Editor closed, the batchmode command is handed to the user).
- Every repo, cross-repo and tech skill has a `## Tools` section that names its `dev_tools` and the
  step each one is for. `tests/skills-lint.sh` enforces it in both directions: each `used_by` skill
  names the tool, and each tool a bullet leads with is registered for that skill. Tech skills need
  the sections Architecture / Idioms / Pitfalls / Testing / Tools, and every `used_by` skill names
  `rpg-factory:<tech>`.
- Routing properties P7 (a tech skill is never routed) and P8 (`routing.tech` only lists skills
  whose `used_by` is a working skill), plus 7 task scenarios in `tests/routing.test.sh`.
- Registry facts with probes: `sgl-langversion`, `sgl-target-frameworks`, `tick-rates-default`,
  `aoi-parallel-gather-min-viewers`, `nakama-version`, `enter-playmode-options`.

### Changed
- `server-realtime`, `server-services` and `client-integration` were deepened and point to their tech
  skill.
  - server-realtime names `SnapshotAllocationTests` (snapshot path only) and the single-test filter,
    and cites ADR-7/8/13/22/25.
  - server-services cites ADR-1/4/6 and adds an evidence rule: skipped interop tests are NOT_RUN,
    never PASS.
  - client-integration is trimmed to 149 lines, covers `_SampleBuild`, adds CI `01-ci-docs.yml`
    (its green result is not evidence) and `02-package-pins.yml`, and its Unity MCP reference gains
    the `tests-run` filters.
- `server-ops` is trimmed to about 150 lines and gains ADR-17 (one replica; `Recreate` on the
  `hostPort` workloads).
- Registry modules:
  - `Assets/_SampleBuild/` maps to `client.buildscripts`, which brings its build gates (it used to
    fall through to `client.unity-assets`).
  - `client.ui` now describes what it actually holds (the theme). The HUD UXML/USS live in
    `client.scripts`, which gains `docs/UI-ARCHITECTURE.md` and the `ci-uxml-drift` external check.
- Known issue `dotnet-wsl` is corrected: a Linux SDK may exist off PATH at `~/.dotnet/dotnet`, and the
  Go interop tests use it.

### Fixed
- **Tech skills were not loaded for "how does it work / how do I test it" questions.** A real session
  routed to `server-realtime` but never invoked `dotnet-gameserver`: the pointer sat only in the
  "place the code" step and said "read", not "invoke". The repo skill, `factory-core` and the
  snapshot's Next line now give one rule: the lead invokes the tech skill (Skill tool) before
  implementing, debugging or reviewing code, or answering how it works or how to test it, in every
  mode. A tech skill is supporting context, not a follow-up.
- **A session could use a tech skill as the owner.** In one of three real Go sessions the model
  invoked `go-backend` and `dotnet-gameserver` but never the routed lead or co-lead, so no rules, gates
  or validation were loaded. Every tech skill now opens with a "Supporting skill, never the owner:
  invoke the lead first" guard (lint-enforced). `tests/dogfood.sh` fails any session that invokes a
  tech skill before an owning skill.
- `/rpg-factory:status` answers dropped each Pending item's owning skill (`[unity-package]`), which is
  the point of the report. On this branch the installed and A/B sessions failed 3/3, against 2/2 on 0.4.0,
  although the status output was byte-identical. The command now says to keep the brackets as printed
  (3/3 after the fix).
- The `factory-core` Skills table let a session name the lead by lookup and stop. It is now marked
  orientation-only: run Route and invoke the lead before answering, with tech skills after the lead.
  Known residual: `netcode-change` still sometimes names the lead without invoking it, at the 0.4.0
  rate (0.4.0 passed 5 of 6 sessions, this release 6 of 7).
- `--explain` said a tech skill was "not selected - no touched path maps to its modules ()". It now
  reports `tech (supporting)` with the skill that uses it, or names its users when none works on the
  change.
- The git guard denied `git tag --sort=...` / `--format=...` (a read) as tag creation. Listing
  options in their `=` form are now a listing. A tag name after them, or a separated `--sort <value>`,
  is still denied.
- `go-backend`: only the `*_test.go` files of `integration_test` carry the build tag; the
  `mock_client.go` helper does not.
- `server-ops` reference: the Nakama plugin is built by `deploy/nakama-plugin.Dockerfile`.
  `docker/Dockerfile.nakama-plugin` is not referenced by anything.
- **The `services.unity-mcp` probe never ran.** Skills branch on "the snapshot shows `unity-mcp`
  reachable", but no script read `services`. The snapshot now probes each service over TCP
  (0.3 s timeout) and reports it in markdown and `--json`.

### Documentation
- README: plugin hooks bind at session start. A session running before rpg-factory was installed or
  enabled has no Factory hooks at all (compaction does not load them); start or resume a session, and
  check with `/rpg-factory:doctor`. Found in the post-release audit of the v0.4.0 tagging session;
  fresh, resumed and `--plugin-dir` sessions were verified to deny tag creation and enforce modes.

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
