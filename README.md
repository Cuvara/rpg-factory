# rpg-factory

A Claude Code plugin that gives AI agents the development workflow for the **UnityIndie RPG
MMO** workspace: the `rpg-mmo-server` Go/C# backend and the `IndieRPGMMOAdventure` Unity 6
client.

Its first component is **Factory Core**, the shared contract every future Factory skill
(feature, fix, refactor, review, release, and so on) builds on.

## Why it exists

Agent rules for this project are spread across about ten `CLAUDE.md` files, `backend/TEAM.md`,
a 4,000-line ADR document, `MEASUREMENT.md`, and a client-only `verify-a-result` skill.
Nothing told an agent, for the files a change touches:

- which module rules apply,
- which checks must run (including the checks for dependent modules),
- what else must change with it: changelog, docs, generated bindings, golden vectors,
  `.meta` files, and the package lock.

Nothing stopped an agent from `git add -A`-ing the user's in-progress work either. The
workspace settings auto-allow `git add`, `commit` and `checkout`.

Factory Core puts that knowledge in one versioned place, computes the live state on demand,
and makes a "done" claim carry evidence.

## Architecture

```
Claude Code session (workspace root, or a teammate inside one repo)
 └─ rpg-factory plugin
     ├─ hooks/hooks.json ── PreToolUse(Bash) → scripts/git-guard.py   (asks before risky git)
     └─ skills/factory-core/SKILL.md          (auto-invoked for dev work, or /rpg-factory:factory-core)
          ├─ live snapshot   ← scripts/factory-context.sh  (git + registry → modules, checks, obligations)
          ├─ global rules    ← registry.json .global_rules
          ├─ workflow        scope → baseline → branch → plan → implement → obligations
          │                  → validate (fast / extended / external) → verify → review → report
          └─ references/     repos · validation · git-safety · report · skill-contract
                  ▲
      future skills (feature, fix, release, …) consume the same snapshot + registry
```

| Path | Role |
|---|---|
| `.claude-plugin/plugin.json` | Plugin manifest (`rpg-factory`) |
| `.claude-plugin/marketplace.json` | Single-plugin marketplace, the same layout as `Cuvara/game-art-mcp` |
| `registry.json` | **Source of truth** for repos, modules, rules, docs, changelogs, generated paths, dependencies, checks by tier, tools, and known issues |
| `docs/registry.schema.json` | Registry schema. Open to extension: unknown keys are ignored |
| `scripts/factory-context.sh` | Live, read-only workspace snapshot (markdown or `--json`) |
| `scripts/lib/resolve.jq` | Maps paths to modules and dependents, then to checks and obligations |
| `scripts/git-guard.py` | PreToolUse hook: returns `ask` for destructive or high-impact git |
| `scripts/check-registry.sh` | Validates registry structure and that every path it names exists |
| `scripts/checks/unity-package-pins.py` | Local mirror of client CI `02-package-pins` step 1, plus a `file:` guard |
| `skills/factory-core/` | The Factory Core skill and its references |
| `tests/` | `run-all.sh` (every local check) and `git-guard.test.sh` |
| `evals/` | `claude plugin eval` smoke cases |

## Installation

Requirements: Claude Code 2.1+, `bash`, `jq`, `python3`, `git`. The workspace is expected at
`/mnt/c/Workspaces/UnityIndie`; otherwise set `RPG_FACTORY_WORKSPACE`.

```bash
# from GitHub
claude plugin marketplace add Cuvara/rpg-factory
claude plugin install rpg-factory@rpg-factory --scope user

# or from a local clone (development)
claude plugin marketplace add /mnt/c/Workspaces/UnityIndie/rpg-factory
claude plugin install rpg-factory@rpg-factory --scope user

# one-off session without installing
claude --plugin-dir /mnt/c/Workspaces/UnityIndie/rpg-factory
```

Use **user scope**, because agents are also started inside `rpg-mmo-server/` or
`IndieRPGMMOAdventure/`. The hook does nothing outside the workspace, and the skill's
description limits it to this workspace.

## Usage

- Claude invokes `factory-core` automatically at the start of development work in either
  repo. You can also invoke it explicitly: `/rpg-factory:factory-core add region to the redirect response`.
- Snapshot from a terminal:

  ```bash
  scripts/factory-context.sh                      # both repos, markdown
  scripts/factory-context.sh --repo server --json
  scripts/factory-context.sh --repo server --paths backend/shared/proto/wire.proto
  ```

  `--paths` resolves only the files you name. Use it when the working tree already holds
  the user's changes, so that validation is derived from the task alone.

### Snapshot content

Every run recomputes the snapshot and stores nothing. It covers:

- **Toolchain:** what is resolved, the local version, and the version CI pins. `dotnet`
  falls back to `dotnet.exe`.
- **Services:** whether the Unity MCP endpoint (`:23621`) is reachable.
- **Each repo:**
  - branch (flagged if protected), HEAD, and upstream ahead/behind as of the last fetch
    (the script never fetches)
  - changed paths, each mapped to a module
  - submodules not at their recorded commit
  - touched modules and dependents
  - generated paths touched
  - unmapped paths
  - required checks by tier, with evidence expectations
  - obligations: which CLAUDE.md to read, changelog, docs, and module rules

### Validation tiers

| Tier | Examples | Policy |
|---|---|---|
| **fast** | `go vet`, `go test -race`, `go build`, `dotnet build/test` + `verify-test-counters.py`, `check_metas.py`, package pins | always, for touched modules **and dependents** |
| **extended** | integration E2E (`-tags integration`), AOT publish, `generate.sh`, golden-vector regen | when the trigger applies; ask first |
| **external** | Unity Test Runner, GitHub CI, Docker stack, deploy | ask, or report `not-run:external` |

Result states are `not-required`, `passed`, `failed`, `skipped`,
`not-run:needs-confirmation`, `not-run:external` and `not-run:tool-missing`. A `passed`
state needs the evidence named in the registry, such as test counts (discovered, passed,
failed, skipped) or summary lines. The final report template
(`skills/factory-core/references/report.md`) enforces this.

### Git safety guard

`scripts/git-guard.py` runs before every Bash tool call. Inside the workspace it returns a
PreToolUse `permissionDecision: "ask"` with reasons for:

- destructive commands: `reset --hard`, `clean -f`, `checkout -- <path>`, `restore`,
  `stash`, `branch -D`
- any `push`, including force, delete and `--tags`
- `add -A` / `add .` and `commit -a`
- commits on develop, staging, main, master or `release-*`
- `commit --amend`, `rebase` and `filter-branch`
- creating tags
- submodule updates

It never denies and never auto-approves. It ignores quoted text and heredoc bodies, and
follows `cd` / `git -C`. Set `RPG_FACTORY_GUARD=off` to disable it for a session. Full
rules: `skills/factory-core/references/git-safety.md`.

## Registry

`registry.json` describes each module with these fields:

- `id`, `repo`, `paths` (longest prefix wins), `responsibility`
- `depends_on` (inverted into dependents), `claude_md`, `docs`, `changelog`
- `rules`, `generated`, `tools`
- `checks.{fast,extended,external}[]` with `id`, `cwd`, `run`, `trigger`, `evidence`
- `obligations`

Placeholders in `run` are `{dotnet}` and `{plugin_root}`. The top-level sections are
`workspace`, `tiers`, `result_states`, `tools`, `services`, `global_rules`, `repos` and
`known_issues`. See `docs/registry.schema.json`.

## Developing future Factory skills

Read `skills/factory-core/references/skill-contract.md`. In short:

- Add `skills/<name>/SKILL.md` that says to follow `rpg-factory:factory-core` and declares
  its task types, scope, owned steps and extra gates.
- Put module knowledge in `registry.json`, never in the skill.
- Agents preload Core with `skills: [factory-core]`.
- After any change, run `tests/run-all.sh`.

## Validating the plugin

```bash
tests/run-all.sh                   # JSON, syntax, exec bits, manifests, registry, guard, resolver, live snapshot, claude plugin validate
claude plugin validate --strict .  # marketplace manifest
claude plugin validate --strict .claude-plugin/plugin.json
claude plugin eval . --no-publish --runs 1   # smoke evals (spends model tokens)
```

## Known limitations

- **Scope is v1:** the server and client only. The `Netcode`, `UIToolkit` and `UnityDots`
  package repos are not in the registry yet.
- **The guard is heuristic:**
  - It reads the command text. A git call hidden in a script file or an alias won't trigger it.
  - It doesn't look at non-Bash tools.
  - Whether `ask` prompts in every permission mode is documented Claude Code behaviour; we
    have not tested every mode.
- **Client tests can't run from the shell.** They need the Unity Editor (via Unity MCP) or
  CI, so they are always `external`.
- **WSL only has the Windows `dotnet.exe`:**
  - Build and test work.
  - Environment variables need `WSLENV`.
  - AOT publish produces a Windows binary, so CI's Linux native interop check is external.
- **Local `protoc` may differ from the CI pin (29.3).** The snapshot shows the difference.
- **Ahead/behind counts are only as fresh as the last `git fetch`.** The script never
  touches the network.

### Pre-existing project issues (recorded in `registry.json` `known_issues`, not fixed here)

- `backend/TEAM.md` points to a `verify-a-result` skill in the server repo. It exists only
  in the client repo.
- Comments in `ci-dotnet.yml` and `backend/deploy/docs/CICD.md` ("Known gap: wire-compat
  coverage") say the cross-language E2E suite runs only on push. `ci.yml`'s
  `test-integration` job actually runs it on every PR (run 36089393362: 25 PASS including
  `TestDotnetInterop_FullFlow`).
- The workspace-root `toggle-packages.sh` rewrites `manifest.json` but not
  `packages-lock.json`, so committing its output fails `02-package-pins`.
