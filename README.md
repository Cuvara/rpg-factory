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

Version 0.2.0. It is tagged by the maintainer; agents never tag.

## Architecture

```
                         Developer task
                               │
                               ▼
                  ┌──────────────────────────┐
                  │  factory-core (skill)    │  scope → baseline → ROUTE → branch → plan → implement
                  │  + git guard (hook)      │  → obligations → validate → verify → review → report
                  └────────────┬─────────────┘
                               │ factory-context.sh + registry.json
                               │ (modules, dependents, cross-repo impact, contracts,
                               │  suggested skills with roles, checks by tier, human gates)
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
         validation (fast / extended / external) → verify-a-result → /code-review → report
```

## Skill map

| Typical task | Lead skill | Repos | Key validation |
|---|---|---|---|
| Add a message or field to the wire protocol, change the protocol version, JoinToken claims, or the Redis `servers:id` hash | `wire-contract` | server → netcode → client | `generate.sh` (protoc 29.3), `wire-parity.sh`, TestDotnetInterop, Netcode headless tests, pin-bump |
| Move the client to Netcode/UnityDots/UIToolkit vX.Y.Z or to sgl-vX.Y.Z | `pin-bump` | client (upstream read-only) | `pin-plan.py`, `pin-status.py`, DOTS Sample byte diff, CI 02-package-pins |
| Benchmark, encoding sweep, re-baseline, multi-client check | `measure` | server + client tools | expected value, control, run id, attribution; `bench.sh` legs |
| New game-server system, tick knob, metric, snapshot/AOI change, Shared.GameLogic | `server-realtime` | server | `dotnet test` + `verify-test-counters.py`, Deploy passthrough tests, golden regen, AOT publish |
| Gateway, Nakama RPC, Redis store, persistence migration | `server-services` | server | Go vet/test/build, MigratorTests (copy match), Nakama plugin image |
| Dockerfile, compose, k8s/Agones manifest, monitoring, backups, CD | `server-ops` | server | `validate-manifests.py`, autoscaler test, `docker compose --env-file .env.example config` |
| Netcode transport/prediction, UnityDots runtime, UIToolkit screens/codegen | `unity-package` | package repos | `check_metas.py`, Netcode headless tests, UXML drift, `package-ready.py` |
| Client DI wiring, Nakama/session flow, HUD/UI, DotsViews, build scripts | `client-integration` | client | Unity Test Runner via Unity MCP, CI 01-ci |

## How routing works

Each registry module lists its owning `skills`. Each contract lists a `driver`. For the files a task touches (`--paths`), `factory-context.sh` prints its suggested skills in three roles:

- **lead:** the driver of a touched contract, or else the owner of the touched module. Invoke it first.
- **leg:** a same-repo skill that the lead runs inside its workflow.
- **follow-up:** work in other repos, reported for later. Examples: after a Shared.GameLogic change, "pin the client" (`pin-bump`); after a Netcode change, "ship it to the client".

```bash
scripts/factory-context.sh --repo server --paths backend/shared/proto/wire.proto
#  lead: wire-contract · legs: server-realtime, server-services · follow-ups: unity-package, pin-bump
#  contract wire-generated: other ends backend/shared/proto/gen/, GameServer/Net/Generated/, Netcode Wire.cs
#  human gate: tag
```

`tests/routing.test.sh` pins this behaviour down with 25 task scenarios. It also replays 13 real historical commits read-only, and every one routes to the skill that did the work. Examples: `2b1418c` action_seq → wire-contract; `17b7737` Netcode pin plus DOTS recopy → pin-bump; `3b0211d` fleet knobs → server-realtime plus server-ops.

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

## Validation

Validation has three tiers, and results use named states (see `skills/factory-core/references/validation.md`):

- **fast:** always run, for touched modules and their dependents.
- **extended:** run when its trigger applies; ask before running.
- **external:** Unity Editor, CI, Docker stack or a cluster; ask, or report it as `not-run:external`.

A check counts as `passed` only when it shows the evidence named in the registry, such as test counts or byte-identity. The final report (`references/report.md`) requires one table per repo, a contract evidence table, and the routing.

These factory check scripts are read-only against the product repos:

| Script | Purpose |
|---|---|
| `scripts/checks/pin-status.py [--remote]` | For every client pin: manifest = lock, upstream tag exists, newer tags available, `.sample-source` |
| `scripts/checks/pin-plan.py <pkg> <tag> [--client-ref REF]` | Exact manifest/lock edits (lock hash = tag commit), dependency changes, DOTS Sample files |
| `scripts/checks/wire-parity.sh` | Netcode `Wire.cs` byte-identical to the server binding, and the protocol version equal in all three places |
| `scripts/checks/netcode-headless.sh` | Netcode headless tests from a temp copy (Netcode has no `.gitignore`), with .trx counters |
| `scripts/checks/package-ready.py <pkg-dir>` | "READY to tag vX.Y.Z", or the exact reasons it is not |
| `scripts/checks/unity-package-pins.py` | Local mirror of client CI 02-package-pins step 1 |

## Git safety and human gates

`hooks/hooks.json` runs `scripts/git-guard.py` as a PreToolUse(Bash) hook. Inside the workspace:

- It **denies** creating, deleting or pushing tags.
- It **asks** before:
  - destructive git: `reset --hard`, `clean -f`, `checkout --`/`restore`, `stash`, `branch -D`, `rebase`, `commit --amend`
  - any `push`
  - `add -A`
  - commits on each repo's protected branches
  - submodule updates
  - any command matching a registry `human_gates[].match` regex:
    - kubectl, helm, ssh and the infra scripts
    - `gh workflow run`, `gh pr create/merge`
    - `.env` and `kubeconfig.local`
    - `toggle-packages.sh`
    - Docker stack lifecycle
    - backup/restore scripts
    - load runs and multi-client runs
    - Unity batch builds
    - `schema_migrations` writes

The guard never approves anything. Quoted text and heredocs are ignored. A broken registry regex disables only that one gate. `RPG_FACTORY_GUARD=off` turns the guard off for a session.

## Installation

```bash
# from GitHub
claude plugin marketplace add Cuvara/rpg-factory
claude plugin install rpg-factory@rpg-factory --scope user

# from a local clone (development; edits take effect without reinstalling)
claude plugin marketplace add /mnt/c/Workspaces/UnityIndie/rpg-factory
claude plugin install rpg-factory@rpg-factory --scope user

# one session, no install
claude --plugin-dir /mnt/c/Workspaces/UnityIndie/rpg-factory
```

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

> Measure whether the new importance weighting improves bytes/player/tick.
  factory-core → measure: expected value + control + run id before running; bench.sh legs (asks first).
```

Explicit invocation: `/rpg-factory:<skill> <task>`.

## Development

- `registry.json` is the source of truth for module knowledge. Its schema is in `docs/registry.schema.json`, and it is validated by `scripts/check-registry.sh`, which also checks that every path exists.
- New skills follow `skills/factory-core/references/skill-contract.md` and are linted by `tests/skills-lint.sh`.
- `tests/run-all.sh` runs every local check: syntax, manifests, registry, guard (65 cases), skill lint, routing and history, the live check scripts, Netcode headless tests, and `claude plugin validate --strict`. It must report 0 failed.

## Known limitations

- **Unity tests run outside the shell.** They need the Unity Editor (through the Unity MCP on :23621) or CI, so they are always `external`. Testing unreleased package code in the client requires the human-gated `toggle-packages.sh` flow.
- **No Linux dotnet in WSL.** Only the Windows `dotnet.exe` is available. Build and test work through it, but the Linux AOT native interop check stays external (CI `ci-dotnet.yml`).
- **Local protoc is not the CI pin.** Local `protoc` is 3.21.12 against the CI pin of 29.3, so `generate.sh` output would drift locally. Leave regeneration to CI, or install 29.3.
- **No local cluster tooling.** kubectl, helm, promtool and kubeconform are not installed. Cluster checks are external and human-gated.
- **Plugin evals with Bash are blocked on this machine.** `claude plugin eval` refuses to grant Bash because of a symlink in `~/.docker`. Behaviour is verified instead with deterministic tests: routing plus the history replay, the guard, and the lint.
- **The guard reads command text.** Git called from inside a script file or through an alias bypasses it.
- **Pre-existing project issues** are recorded in `registry.json` `known_issues` and printed by every snapshot. They include stale docs (NETCODE.md, client CLAUDE.md, gateway CLAUDE.md), package CI SGL pins lagging the client, and the embedded package clones.
