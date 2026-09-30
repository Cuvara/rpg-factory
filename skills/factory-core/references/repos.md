# Repositories and modules

Module facts (paths, rules, docs, changelogs, checks, generated paths, dependencies) live
only in `${CLAUDE_PLUGIN_ROOT}/registry.json`. This page explains the shape of the
workspace and how to query the registry. It does not repeat module data.

## Workspace

`/mnt/c/Workspaces/UnityIndie` is **not a git repository**. It contains independent repos:

| Repo key | Path | Stack | Factory v1 |
|---|---|---|---|
| `server` | `rpg-mmo-server/` | Go 1.26 modules (no go.work) + C# .NET 10 game server | in registry |
| `client` | `IndieRPGMMOAdventure/` | Unity 6 (DOTS, UI Toolkit, VContainer) | in registry |
| - | `Netcode/`, `UIToolkit/`, `UnityDots/` | com.cuvara.* UPM package sources | not yet (see skill-contract.md) |
| - | `game-art-mcp/`, `rpg-factory/` | tooling | out of scope |

Communication: Unity client -> Nakama (auth/economy/social) and -> Gateway (auth +
redirect only, ADR-3) -> Game server (direct TCP/KCP). Wire: 4-byte BE length prefix +
Protobuf (legacy JSON accepted), defined once in `backend/shared/proto/wire.proto`.
`Shared.GameLogic` is pure C# shared by the server and the Unity client (ADR-10), pinned by
the client as a UPM git dependency `com.rpgmmo.shared-gamelogic#sgl-vX.Y.Z`.

## Where instructions live

- Workspace: `CLAUDE.md` (root) - overview and cross-project conventions.
- Server: `rpg-mmo-server/CLAUDE.md`, `backend/TEAM.md` (team contract, current-phase
  directive, verification rules), each module's `CLAUDE.md`,
  `backend/docs/ARCHITECTURE-DECISIONS.md` (authoritative ADRs; older docs may be stale),
  `backend/docs/MEASUREMENT.md` (incident catalogue behind verify-a-result).
- Client: `IndieRPGMMOAdventure/CLAUDE.md` (build, package pins, DOTS Sample, CI, conventions),
  `.claude/agents/unity-netcode.md` (networking-layer agent), `.claude/skills/` (Unity MCP
  tool skills + `verify-a-result`).

## How path -> module mapping works

Every module lists repo-relative `paths`; the **longest matching prefix wins**. So
`backend/shared/proto/wire.proto` maps to `server.proto`, not `server.shared`, and
`Assets/Samples/Netcode/DOTS Sample/...` maps to `client.dots-sample`, not
`client.samples-imported`. `depends_on` is inverted into *dependents*: a change in
`server.shared` makes gateway, nakama, smoketest, loadtest, verify-probe and the integration
suite dependents that need their fast checks.

A path with no module is reported as **unmapped**: decide by hand, and consider adding a
module to the registry (see skill-contract.md).

## Registry query recipes

```bash
R="${CLAUDE_PLUGIN_ROOT}/registry.json"
jq -r '.modules[] | "\(.id)\t\(.repo)\t\(.paths | join(", "))"' "$R"          # module map
jq '.modules[] | select(.id == "server.gateway")' "$R"                          # one module
jq -r '.modules[] | select(.depends_on | index("server.shared")) | .id' "$R"    # direct dependents
jq -r '.repos.server | .default_branch, .branch_pattern, .commit_style' "$R"   # git conventions
jq -r '.known_issues[] | "\(.id): \(.summary)"' "$R"                            # known issues
```

## Known issues that affect Factory work

Read `.known_issues` in the registry. At v0.1.0 they cover: the dangling `verify-a-result`
reference in `TEAM.md`, stale docs claiming the wire-compat E2E suite does not run on PRs
(it does, via `ci.yml` `test-integration`), `toggle-packages.sh` not updating
`packages-lock.json`, local `protoc` vs CI pin, and `dotnet.exe`-only WSL.
