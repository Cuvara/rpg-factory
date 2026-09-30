---
name: factory-core
description: Factory workflow for the UnityIndie RPG MMO workspace - rpg-mmo-server (Go/C# backend), IndieRPGMMOAdventure (Unity client) and the Netcode, UnityDots and UIToolkit package repos. Use at the start of ANY code, config, CI, deploy, measurement or docs change in those repos, and before reporting such work as done. Provides the live snapshot (modules, dependents, cross-repo impact, contracts, suggested specialised skill), required validation by tier, human gates, git safety and the mandatory verify-a-result report. Every other rpg-factory skill runs on top of it.
argument-hint: "[task description]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*)
---

# Factory Core - RPG MMO workspace

You are running the Factory workflow for this workspace. It is the contract every
rpg-factory skill builds on. Task: $ARGUMENTS

## Live snapshot (computed now - pre-existing changes shown here belong to the user)

The snapshot below includes the project-wide rules (`global_rules`) and known issues from
the registry. Follow those rules for every task.

!`bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh`

Module-level rules, docs, changelogs, generated paths, dependencies and checks live in
`${CLAUDE_PLUGIN_ROOT}/registry.json`. Do not restate or guess them - read the snapshot,
or re-run the context script.

## Workflow

Steps are **M** mandatory, **O** optional, **H** need the user.

1. **Scope (M).** Name the repo(s) and module(s) the task touches. Read each touched
   module's `claude_md` and the repo instructions listed in the registry. If the task
   would invent a gameplay rule, stop and ask (**H**, rule `phase-plumbing-only`).
2. **Baseline (M).** Record the snapshot's changed paths as the *user's baseline*. Never
   modify, stage, stash, clean, reset or commit baseline paths unless the user names them.
   For a repo not in the default snapshot, run `factory-context.sh --repo <key>`.
3. **Route (M).** Resolve the files the task will touch:
   `bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh --repo <key> --paths <file>...` and read
   **Suggested Factory skills**. You MUST invoke every **lead** skill with the Skill tool before
   planning or editing (reading its guidance from the snapshot is not enough) and follow it; it runs its
   **legs**. **Follow-ups** are later work in other repos: name them in the report. If nothing is
   suggested, continue with Core alone. Skill map: `references/skill-contract.md` §Routing.
4. **Branch (M).** If the repo is on a protected branch and the task will produce a
   commit, create `type/module/topic` from the default branch first. Branching is local
   and allowed; committing, pushing, PRs, merges and tags are **H** (only on request).
5. **Plan (O/M).** Mandatory when the change spans modules, touches a cross-language
   contract, or a generated path. Use plan mode or a short written plan.
6. **Implement (M).** Only the requested scope. Follow the module rules. Generated paths
   change only through their generator. Never edit submodules or embedded package clones.
7. **Resolve validation (M).** Re-run the context script for exactly the files you changed:
   `bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh --repo <key> --paths <file>...`
   This yields touched modules, dependents, checks by tier, and obligations for *your* change,
   untouched by the user's baseline.
8. **Obligations (M).** CHANGELOG entry under `## [Unreleased]` per touched module; docs;
   regenerated artifacts; both sides of cross-language contracts; `.meta` files for Unity
   and Shared.GameLogic assets; version bump without tag where required.
9. **Validate (M).** Run by tier - see *Validation* below.
10. **Verify (M).** Apply the verify-a-result checklist to every number you will report.
11. **Review (O).** For non-trivial diffs run `/code-review` on the changed repo.
12. **Report (M).** Use the template in `references/report.md`. No other format.

## Validation

| Tier | Policy | If not run, report |
|---|---|---|
| **fast** | Always run for touched modules **and dependents**. | `failed` or `not-run:tool-missing` - never silently skip |
| **extended** | Required when its `trigger` applies. Ask the user first (slow, environment-sensitive). | `not-run:needs-confirmation` |
| **external** | Unity Test Runner, CI, Docker stack, deploys. Ask, or state what is needed. | `not-run:external` + reason |

Result states: `not-required`, `passed`, `failed`, `skipped`, `not-run:needs-confirmation`,
`not-run:external`, `not-run:tool-missing`. A check is `passed` only with the evidence its
registry entry names (counts, exit code, summary line). Commands use `cwd` relative to the repo
root; `{dotnet}` is already resolved in the snapshot (WSL often has only `dotnet.exe`).

Details, evidence parsing per tool, and environment caveats: `references/validation.md`.

## verify-a-result (non-negotiable)

- Count passes. `go test` / `dotnet test` exit 0 on zero selected tests; report discovered /
  passed / failed / skipped, and treat zero executed as a failure.
- Prove a zero can be non-zero before trusting it. Name the object a number describes.
- Write the expected result before running. Compare, do not rationalise.
- CI: count jobs that passed; an absent check is not a pass.
- Canonical checklist: `IndieRPGMMOAdventure/.claude/skills/verify-a-result/SKILL.md` and
  `rpg-mmo-server/backend/docs/MEASUREMENT.md`. Never write "tests look good".

## Git safety and human gates

The plugin's PreToolUse hook **denies** creating, deleting or pushing tags (agents never tag -
stop at "ready to tag <repo> <tag>"). It **asks** before destructive git (reset --hard, clean -f,
checkout -- / restore, stash, branch -D, rebase), any push, `add -A`/`add .`, commits on
protected branches, `commit -a/--amend`, submodule updates, and before commands matching a
registry `human_gates` entry (kubectl/helm/ssh, workflow dispatch, secrets, toggle-packages.sh,
local stack). The hook is a backstop; the policy is `references/git-safety.md`. Stage explicit
paths only.

## Skills

| Situation | Lead skill |
|---|---|
| wire message/field, protocol version, JSON encoding, Redis servers:id hash | `wire-contract` (drives server → Netcode → client) |
| move a client pin to a released package / sgl tag | `pin-bump` |
| C# game server, ECS systems, knobs, metrics, Shared.GameLogic, golden vectors | `server-realtime` |
| Go gateway, Nakama RPCs, Redis store, persistence/migrations | `server-services` |
| Docker, compose, k8s/Agones, monitoring, backups, CD | `server-ops` |
| Netcode / UnityDots / UIToolkit package code, up to ready-to-tag | `unity-package` |
| client VContainer wiring, Nakama/session, HUD/UI, DotsViews, build scripts | `client-integration` |
| benchmark, encoding sweep, re-baseline, multi-client verification | `measure` |

## References - read when

- `references/repos.md` - first time in a repo, or the snapshot shows unmapped paths.
- `references/validation.md` - before running or reporting any check.
- `references/git-safety.md` - before any branch, stage, commit, or cleanup action.
- `references/report.md` - before writing the final report (always).
- `references/skill-contract.md` - when writing or running another rpg-factory skill.

All paths above are relative to `${CLAUDE_SKILL_DIR}`.
