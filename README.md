# rpg-factory

`rpg-factory` is a Claude Code plugin that organises development work across the UnityIndie RPG MMO workspace. The workspace holds five repos:

| Repo key | Directory | Contents |
|---|---|---|
| `server` | `rpg-mmo-server` | Go gateway, Nakama plugin, C# realtime game server, Shared.GameLogic, deploy |
| `client` | `IndieRPGMMOAdventure` | thin Unity 6 client |
| `netcode` | `Netcode` | `com.cuvara.netcode` package |
| `unitydots` | `UnityDots` | `com.cuvara.dots` package |
| `uitoolkit` | `UIToolkit` | `com.cuvara.uitoolkit` package |

You give Claude a development request. The plugin works out, from the live state of the workspace, the following:

- which repo, module and specialised skill owns the change
- what else must change with it: cross-repo contracts, dependents, the changelog, docs, generated files
- which checks must run, which require a human, and what counts as evidence
- when to stop: at tags, at shared infrastructure, and at the release actions of the lead

Version 0.4.0 (see `VERSION`). Releases are tagged by the maintainer; agents never tag - the last
automated state of any release is **READY_TO_TAG**.

## Commands

| Command | What you get | Changes anything? |
|---|---|---|
| `/rpg-factory:status [--remote]` | pending cross-repo work with its owning skill (wire rollout stage, READY_TO_TAG packages, unpinned releases, package-CI pin drift), uncommitted work per repo, embedded clones, validation evidence (current vs STALE), fetch freshness | no |
| `/rpg-factory:route <repo> <path>... [--lead <skill>]` | lead / co-leads / legs / follow-ups for those files, touched contracts, checks by tier, gates - and why each skill was or was not chosen | no |
| `/rpg-factory:check <repo> [<path>...] [--status]` | runs the fast checks and grades them; `--status` grades stored evidence against the current tree (STALE / NOT_RUN) without running anything | runs builds/tests (not with `--status`) |
| `/rpg-factory:doctor` | install state (what this session loads), tripwire latches, registry validity, repos, state paths, tools, hooks | no |

Engineering work itself starts with the `factory-core` skill (the model invokes it; `/rpg-factory:factory-core`
works too).

## Execution modes

`analyze`, `plan`, `implement`, `validate`, `review`, `resume`. factory-core picks the mode from the request
and declares it (`factory-context.sh --mode <m>`); the hooks then **enforce** it for the session: in
`analyze` / `plan` / `review` every file write and state-changing command is denied, `validate` may only run
`run-checks.py`. Every mode except validate/resume still invokes the lead skill - a plan comes from the
lead's workflow. Switching (e.g. to `implement`) is only done when you ask for it.

### Plugin boundaries

| Use | For |
|---|---|
| `rpg-factory` | engineering changes in the five repos above: code, config, CI, deploy, measurement, their docs |
| `game-ai-workflows` | game design: GDD, feature registry lifecycle, design review |
| `web-game-factory` | web game projects outside this workspace |

`factory-core` stops a task that would invent gameplay rules or numbers (`phase-plumbing-only`).

## Architecture

```
                         Developer task
                               │
                               ▼
                  ┌──────────────────────────┐
                  │  factory-core (skill)    │  resume → scope → baseline → ROUTE → branch → plan → implement
                  │                          │  → obligations → VALIDATE (runner) → verify → review → report
                  └────────────┬─────────────┘
                               │ factory-context.sh + registry.json      factory-status.py (derived
                               │ (modules, contracts, routing: lead /     cross-repo state: rollout
                               │  co-leads / legs / follow-ups, checks,   stage, READY_TO_TAG, pins,
                               │  gates, facts)                           in-flight topic branches)
              ┌────────────────┴─────────────────┐
              ▼                                  ▼
     cross-repo drivers                     repo skills (one leg each)
     wire-contract  server → Netcode → client     server-realtime   (C# game server, SGL)
     pin-bump       released tag → client pins    server-services   (Go gateway, Nakama, Redis, migrations)
     measure        benchmarks / baselines        server-ops        (Docker, k8s/Agones, monitoring, CD)
                                                  unity-package     (Netcode, UnityDots, UIToolkit)
                                                  client-integration(VContainer, Nakama/session, HUD, build)
              └────────────────┬─────────────────┘
                               ▼
         run-checks.py (fast / extended / external, graded states + evidence JSON)
                         → verify-a-result → /code-review → report

 hooks: SessionStart  install-status.py (stale install warning) · tripwire.py baseline
        PreToolUse    git-guard.py (Bash + PowerShell) · tripwire.py fingerprint
        PostToolUse   tripwire.py (STOP + latch on unexpected git state change)
```

## Skill map

| Typical task | Lead skill | Repos | Key validation |
|---|---|---|---|
| Add a message or field to the wire protocol, change the protocol version, JoinToken claims, or the Redis `servers:id` hash | `wire-contract` | server → netcode → client | `generate.sh` (protoc 29.3), `wire-parity.sh`, TestDotnetInterop, Netcode headless tests, pin-bump |
| Move the client to Netcode/UnityDots/UIToolkit vX.Y.Z or to sgl-vX.Y.Z; bump the unity-build-workflows toolkit | `pin-bump` | client (upstream read-only) | `pin-plan.py`, `pin-status.py`, DOTS Sample byte diff, CI 02-package-pins |
| Benchmark, encoding sweep, re-baseline, multi-client check | `measure` | server + client tools | expected value, control, run id, attribution; `bench.sh` legs |
| New game-server system, tick knob, metric, snapshot/AOI change, Shared.GameLogic | `server-realtime` | server | `dotnet test` + `verify-test-counters.py`, Deploy passthrough tests, golden regen, AOT publish |
| Gateway, Nakama RPC, Redis store, persistence migration | `server-services` | server | Go vet/test/build, MigratorTests (copy match), Nakama plugin image |
| Dockerfile, compose, k8s/Agones manifest, monitoring, backups, CD | `server-ops` | server | `validate-manifests.py`, autoscaler test, `docker compose --env-file .env.example config` |
| Netcode transport/prediction, UnityDots runtime, UIToolkit screens/codegen | `unity-package` | package repos | `check_metas.py`, Netcode headless tests, UXML drift, `package-ready.py` |
| Client DI wiring, Nakama/session flow, HUD/UI, DotsViews, build scripts | `client-integration` | client | Unity Test Runner via Unity MCP, CI 01-ci |

## How routing works

Each registry module lists its owning `skills`; each contract lists a `driver`. For the files a task
touches (`--paths`), `factory-context.sh` prints a **routing** block:

- **lead:** exactly one skill, chosen deterministically - a cross-repo contract driver first, then a
  repo-kind driver whose contract source changed, then the primary owner of a touched module, then a
  secondary owner; ties break on `skills.<name>.order` (wire-contract 10 … measure 80).
- **co-leads:** other lead candidates, run after the lead in that order (code → deploy → measurement).
- **legs:** same-repo skills the lead runs inside its workflow.
- **follow-ups:** work in other repos, reported for later (e.g. after a Shared.GameLogic change,
  `pin-bump` the client).
- **AMBIGUOUS:** printed only when the registry cannot decide; `--lead <skill>` overrides (validated,
  exit 2 when the skill is not a candidate). `--explain` shows why every skill was or was not chosen.

Files matching no module map to `<repo>.root` (repo-level files); `X.meta` routes like `X`; duplicate
module paths are rejected by `check-registry.sh`. The snapshot resolves the repo (or worktree) from
the current directory.

```bash
scripts/factory-context.sh --repo server --paths backend/shared/proto/wire.proto
# **Routing** lead `rpg-factory:wire-contract` · legs server-realtime, server-services · follow-ups pin-bump, unity-package
#   lead because: contract wire-generated (source touched); cross-repo dependent ... (class 0, order 10)
# Contract `wire-generated` (source touched, driver wire-contract): server:backend/shared/proto/gen/; ...; netcode:Runtime/Protocol/Generated/Wire.cs
# Gates for this change: **tag**
```

Tests: `tests/routing.test.sh` (task scenarios + 15 real historical commits replayed read-only) and
`tests/routing-properties.test.py` (the recent history of every repo: one lead per commit, lead set
independent of file order, no lead that is also a follow-up, full coverage).

## Contracts

| Contract | Source → copies | Driver |
|---|---|---|
| `wire-generated` | `wire.proto` → Go gen, C# gen, Netcode `Wire.cs` (byte copy) | wire-contract |
| `protocol-version` | C# `WireProtocol.ProtocolVersion` ↔ Go `WireProtocolVersion` ↔ Netcode `WireProtocolVersion.Current` (+ gateway flag) | wire-contract |
| `join-token` | gateway `transfer/join_token.go` ↔ `shared/jwt/` ↔ C# `JwtValidator.cs` | wire-contract |
| `redis-server-registry` | C# `RedisServerRegistry.cs` ↔ Go `redisstore/registry.go` | wire-contract |
| `nakama-rpc` | `nakama/main.go` + handlers ↔ gateway, game server and client callers | server-services |
| `sgl-pin` | Shared.GameLogic `package.json` (sgl-v tag) → client manifest + lock; package CI pins are watchers | pin-bump |
| `package-pins` | client manifest → lock + DOTS Sample; upstream package.json/tags | pin-bump |
| `gamestate-migrations` | `Persistence/Migrations/` → `deploy/db/migrations/gamestate/`, `init-gamestate.sql` | server-services |
| `server-knobs` | `ServerEnv.cs` → compose + Agones/k8s fleet env (co-edit clause for server-realtime) | server-realtime |
| `transport-security` | gateway/Nakama TLS + `GAMESERVER_SEALED` switches (`k8s/app/40-gateway.yaml`, fleets, compose) ↔ gateway TLS flags, `NakamaTlsPin.cs`, smoketest/verify pins, Netcode sealed client, client pin loading. Capabilities first, then the switch | server-ops |

Contract **watchers** are files that pin another repo without being a copy - the package CIs (Netcode CI
installs UnityDots at a tag, UnityDots CI installs Netcode and Shared.GameLogic at tags). `factory-status`
compares them with the client pin and the latest tag.

## Validation

`scripts/run-checks.py --repo <key> --paths <files>` resolves the registry checks for the touched
modules and their dependents, runs them, and grades each one:

| State | Meaning |
|---|---|
| PASS | ran, exit 0, the parser found evidence (tests executed > 0, expected line), no files left behind |
| FAIL | failed; or exit 0 without evidence (0 tests, all skipped); or it polluted the product repo |
| BLOCKED | a `needs` prerequisite failed, or the check directory is missing |
| NOT_AVAILABLE | a required tool is missing on this machine |
| HUMAN_REQUIRED | extended check not approved (`--approve <id>`), or external (Unity Editor, CI, Docker stack, cluster) |
| SKIPPED | excluded on purpose (`--only`, duplicate command) |
| NOT_RUN | (`--status`) declared for the change, never executed |
| STALE | (`--status`) executed, but HEAD, the diff or untracked files in the check's directory, or the check definition changed since |

Parsers: `go-test`, `dotnet-test`, `exit`, `regex:<pattern>`. Every executed check is stored with the
identity of the tree it ran on and its full log under `~/.local/state/rpg-factory/evidence/`;
`--status` re-grades that evidence against the tree as it is now, without running anything. The report
template (`skills/factory-core/references/report.md`) takes the runner table verbatim and requires a
`--status` pass with nothing STALE.

Read-only check scripts against the product repos:

| Script | Purpose |
|---|---|
| `scripts/factory-status.py [--remote] [--strict]` | Derived cross-repo state: contract consistency, wire rollout stage, package release state (READY_TO_TAG), pins vs latest tags, package-CI pins (watchers), build-toolkit refs, uncommitted work, embedded clones, validation evidence (current/STALE), fetch freshness, in-flight topic branches, pending items with owning skill. Never fetches: remote conclusions are labelled with the last fetch's age (stale after 24 h, with the `git fetch` to run) |
| `scripts/checks/pin-status.py [--remote]` | For every client pin: manifest = lock, upstream tag exists, newer tags available, `.sample-source` |
| `scripts/checks/pin-plan.py <pkg> <tag> [--client-ref REF]` | Exact manifest/lock edits (lock hash = tag commit), dependency changes, DOTS Sample files |
| `scripts/checks/wire-parity.sh` | Netcode `Wire.cs` byte-identical to the server binding, and the protocol version equal in all three places |
| `scripts/checks/netcode-headless.sh` | Netcode headless tests from a temp copy (Netcode has no `.gitignore`), with .trx counters |
| `scripts/checks/package-ready.py <pkg-dir>` | "READY to tag vX.Y.Z", or the exact reasons it is not |
| `scripts/checks/unity-package-pins.py` | Local mirror of client CI 02-package-pins step 1 |

## Resuming interrupted work

There is no workflow database: state is derived from git each time (plus two small files outside the
repos: the tripwire latch and the check evidence). `factory-status.py` answers "what is left" after a
crash, a failed leg or a new session - including uncommitted work and which validation is STALE - e.g. `server bindings ✓ · Netcode copy ✓ ·
Netcode release ✗ (READY_TO_TAG netcode v0.46.0) · client pin ✗`. Cross-repo tasks use one branch topic
in every repo (`feat/wire/party` in server, Netcode and client) so the legs are linked.

## Git safety and human gates

Four layers, all inside the workspace (plus `gh` commands naming a workspace repo, wherever they run):

1. **Rules** in `skills/factory-core/references/git-safety.md` (baseline preservation, explicit
   staging, `<type>/<area>/<topic>` branches, never tag).
2. **Guard** - `scripts/git-guard.py`, PreToolUse on **Bash and PowerShell**. It expands a command
   into what actually runs: wrappers (`env`, `sudo`, `timeout`, `nohup`, `nice`, `command`, `exec`,
   `xargs`, `find -exec`), nested shells (`bash -c`, `sh -c`, `eval`, `cmd /c`, `powershell -c`),
   repo git aliases, PowerShell quoting and the `&` call operator.
   - **Denies:** creating, deleting or pushing tags; tag/release creation through `gh` (REST
     `git/tags`, tag refs, `/releases`; GraphQL `createRef refs/tags/...`, `createRelease`;
     `gh release create/edit/upload`); repository deletion/archival (`gh repo delete/archive`,
     `DELETE repos/<o>/<r>`).
   - **Asks:** every other GitHub mutation - `gh api` writes (method as gh decides it), GraphQL
     mutations or queries from a file, branch protection / rulesets, `gh repo edit/rename/sync`,
     secrets, variables, workflows, runs, PR/issue mutations. Read-only `gh` passes.
   - **Asks:** destructive git (`reset --hard`, `clean -f`, `checkout --`, `restore`, `stash`,
     `branch -D/-f`, `checkout -B`, `switch -C`, `update-ref`, `gc --prune`, `reflog expire`), any
     `push`, `add -A`, `commit`/`merge`/`cherry-pick`/`revert`/`am`/`pull --rebase`/`reset <commit>`
     on protected branches (worktrees use their main checkout's list), `pull` without `--ff-only`,
     renaming/deleting a protected branch, `fetch` into local branches, `remote add/set-url/remove`,
     `config` writes to aliases / remote URLs / `insteadOf` / `hooksPath` / credential helpers,
     `symbolic-ref` writes, history rewrites, submodule updates/additions, git hidden behind an interpreter one-liner or `$VAR`/`$(...)` as the program, and every
     registry `human_gates[].match` (kubectl/helm/ssh, `gh workflow run`, `gh pr create/merge`,
     `.env`/`kubeconfig.local`, `toggle-packages.sh`, Docker stack lifecycle, backups, load runs,
     Unity batch builds, `schema_migrations` writes).
3. **File guard** - `scripts/file-guard.py`, PreToolUse on `Write|Edit|MultiEdit|NotebookEdit|Read`:
   writes into embedded clones, submodule content, registry generated paths, the user's baseline files
   or secrets ask; secret reads ask; writes while latched or in a read-only mode are denied.
4. **Tripwire** - `scripts/tripwire.py`. SessionStart records the user's baseline (dirty files,
   submodule pointers, samples of dirty files inside submodules and embedded clones). Around every
   Bash/PowerShell call it compares branch/tag/remote/stash/HEAD fingerprints (embedded clones
   included); a change the command did not visibly ask for (a tag from a script, a push from Python,
   a reset of a user file) returns **"STOP - rpg-factory tripwire"** and latches the **workspace**:
   writes and state-changing commands are denied - also in later sessions after a crash - until the
   user runs `! python3 scripts/tripwire.py --ack` (denied to the agent). `/rpg-factory:doctor` shows it.

Where Factory keeps state (`scripts/lib/fstate.py`, always absolute, never inside a repo): per-session
scratch under `$TMPDIR` if it is a usable absolute directory, else `/tmp`; the workspace latch and
check evidence under `$XDG_STATE_HOME/rpg-factory` (default `~/.local/state/rpg-factory`).

Workspace model: the five **workspace repos** (registry), **git submodules** inside them (`com.gdk.*`,
`unity-build-workflows`: pointers are user state), **embedded clones** (gitignored
`IndieRPGMMOAdventure/Packages/com.cuvara.*`: user work in progress, never the canonical package checkout -
a snapshot run inside one says so), **git worktrees** (resolved from the cwd), and **external repos**
(e.g. `Cuvara/unity-build-workflows` itself: only its consumer side - submodule pointer and `@vN` refs -
is modelled).

The guard never approves anything and never crashes a session (errors mean "no opinion"); a broken
registry regex disables only that gate. `RPG_FACTORY_GUARD=off` turns the guard off for a session.

## Installation

```bash
# from GitHub
claude plugin marketplace add Cuvara/rpg-factory
claude plugin install rpg-factory@rpg-factory --scope user

# from a local clone
claude plugin marketplace add /mnt/c/Workspaces/UnityIndie/rpg-factory
claude plugin install rpg-factory@rpg-factory --scope user

# one session against the working tree, no install (development only)
claude --plugin-dir /mnt/c/Workspaces/UnityIndie/rpg-factory
```

### Updating - what a session actually loads

Observed with Claude Code 2.1.280 (`tests/dogfood.sh --installed` checks it on every release):

| Marketplace | Sessions load | New content reaches sessions | `claude plugin update` |
|---|---|---|---|
| **directory** (`marketplace add /path/to/rpg-factory`, this workspace) | the marketplace directory **in place** (`installLocation` in `known_marketplaces.json`); the cache copy under `~/.claude/plugins/cache/` is not what runs | at the next session start - including uncommitted edits in that checkout | refreshes the install **record** (`claude plugin list` version); a no-op while `plugin.json`'s version is unchanged |
| **GitHub** (`marketplace add Cuvara/rpg-factory`) - *not verified here* | expected: the version-keyed cache copy `~/.claude/plugins/cache/rpg-factory/rpg-factory/<version>/` | only after a version bump + update (or uninstall + install) and a restart | a no-op while the version is unchanged |

```bash
claude plugin marketplace update rpg-factory
claude plugin update rpg-factory@rpg-factory      # picks up a new version; restart Claude Code afterwards
# same version, new content (GitHub marketplace): reinstall
claude plugin uninstall rpg-factory@rpg-factory && claude plugin install rpg-factory@rpg-factory --scope user
```

`python3 scripts/install-status.py` reports the mode, what the install loads, the session's
`CLAUDE_PLUGIN_ROOT`, and a state: `CURRENT`, `STALE` (record or copy older than the source),
`CONTENT_MISMATCH` (cache mode, same version, different files), `RESTART_REQUIRED` (the session runs
another copy) or `NOT_INSTALLED`. The SessionStart hook warns when it is not CURRENT, and the
snapshot header shows `rpg-factory runtime <version> (<how it was loaded>)`. With a directory
marketplace, keep the checkout on a released commit: whatever is checked out is what sessions run.

Requirements:

- Claude Code 2.1+
- bash, jq, python3 (pyyaml; jsonschema is optional and used for schema validation), git
- `dotnet` or the Windows `dotnet.exe`, for .NET checks

The workspace root is `/mnt/c/Workspaces/UnityIndie`. Override it with `RPG_FACTORY_WORKSPACE`.

## Usage examples

```text
> Add a configurable tick-rate knob to the game server and expose it as a metric.
  factory-core → server-realtime (lead), server-ops leg for the env lines (contract server-knobs);
  dotnet test incl. Deploy passthrough tests; METRICS.md; CHANGELOG.

> Add `region` to EnterWorldResponse and ship it to the client.
  factory-core → wire-contract: server leg → Netcode Wire.cs leg → "ready to tag Netcode vX.Y.Z" (stop)
  → after your tag: pin-bump.

> Move the client to Netcode v0.46.0.
  factory-core → pin-bump: pin-plan.py, manifest+lock+hash, DOTS Sample recopy, CHANGELOG, pin-status.py.

> What is still open from yesterday's wire change?
  factory-status.py: rollout stage, READY_TO_TAG packages, unpinned releases, in-flight topic branches.

> Measure whether the new importance weighting improves bytes/player/tick.
  factory-core → measure: expected value + control + run id before running; bench.sh legs (asks first).
```

Explicit invocation: `/rpg-factory:<skill> <task>`.

## Development

- `registry.json` (schema v3) is the source of truth for module knowledge: modules, contracts,
  checks with parsers, human gates, `facts[]` with probe commands. Schema in
  `docs/registry.schema.json`; validated by `scripts/check-registry.sh` (paths exist, unique skill
  order, no duplicate module paths, one fallback per repo).
- Skills follow `skills/factory-core/references/skill-contract.md` and are linted by
  `tests/skills-lint.sh` (contract, plugin boundaries, no rules copied from the registry).
- `tests/run-all.sh` runs every local suite: guard bypass matrix, tripwire, worktree, check runner,
  factory-status fixtures, install-status, facts, routing properties and history replay, the live
  check scripts, Netcode headless tests, and `claude plugin validate --strict`. `--release` also
  requires the installed plugin to be CURRENT. It must report 0 failed.
- `tests/dogfood.sh` runs real headless Claude sessions and asserts which skills were invoked;
  `--installed` uses the installed plugin (no `--plugin-dir`) and asserts the runtime version.

## Known limitations

- **Unity tests run outside the shell.** They need the Unity Editor (through the Unity MCP on :23621) or CI, so they are always HUMAN_REQUIRED. Testing unreleased package code in the client requires the human-gated `toggle-packages.sh` flow.
- **No Linux dotnet in WSL.** Only the Windows `dotnet.exe` is available. Build and test work through it, but the Linux AOT native interop check stays external (CI `ci-dotnet.yml`).
- **Local protoc is not the CI pin** (registry fact `protoc-ci-pin`). `generate.sh` output would drift locally; leave regeneration to CI, or install the pinned version.
- **No local cluster tooling.** kubectl, helm, promtool and kubeconform are not installed. Cluster checks are external and human-gated.
- **Plugin evals with Bash are blocked on this machine** (`claude plugin eval` refuses Bash because of a symlink in `~/.docker`). Behaviour is verified with deterministic tests and headless dogfood sessions instead.
- **The guard reads command text.** Anything it cannot see through asks; git run by a script file or a background process is caught by the tripwire after the fact (detection, not prevention). Remote-only GitHub changes are only controlled by the guard (the tripwire cannot see them). Another agent runtime (e.g. Codex) is outside all layers.
- **MCP tools are not inspected.** Unity-MCP asset/scene edits are controlled by the `unity-asset-edit` human gate (policy), not by a hook.
- **Evidence identity** covers the check's directory plus the paths of its module's same-repo dependencies (registry `depends_on`); untracked files count by name, size and mtime (not contents). Changes in *another* repo are not part of it (a package's new tag reaches a consumer through its pin file, which is in the consumer repo).
- **Tripwire cost.** The session baseline takes ~13 s (submodule scan, once per session); each mutating command adds ~0.9 s, read-only commands ~0.17 s (measured on /mnt/c, 2026-09-30).
- **Pre-existing project issues** are recorded in `registry.json` `known_issues` and printed for the touched repos. They include stale docs, package CI SGL pins lagging the client, and the embedded package clones.

