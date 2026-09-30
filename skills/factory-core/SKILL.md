---
name: factory-core
description: Factory workflow for the UnityIndie RPG MMO workspace (rpg-mmo-server Go/C# backend + IndieRPGMMOAdventure Unity client). Use at the start of ANY code, config, CI, or docs change in those repos - features, fixes, refactors, tests, package bumps - and before reporting such work as done. Provides the live workspace snapshot, affected modules and dependents, required validation by tier, module rules, git safety, and the mandatory verify-a-result final report. Other rpg-factory skills build on it.
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
3. **Branch (M).** If the repo is on a protected branch and the task will produce a
   commit, create `type/module/topic` from the default branch first. Branching is local
   and allowed; committing, pushing, PRs, merges and tags are **H** (only on request).
4. **Plan (O/M).** Mandatory when the change spans modules, touches a cross-language
   contract, or a generated path. Use plan mode or a short written plan.
5. **Implement (M).** Only the requested scope. Follow the module rules. Generated paths
   change only through their generator. Never edit submodules or embedded package clones.
6. **Resolve validation (M).** Re-run the context script for exactly the files you changed:
   `bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh --repo <server|client> --paths <file>...`
   This yields touched modules, dependents, checks by tier, and obligations for *your* change,
   untouched by the user's baseline.
7. **Obligations (M).** CHANGELOG entry under `## [Unreleased]` per touched module; docs;
   regenerated artifacts; both sides of cross-language contracts; `.meta` files for Unity
   and Shared.GameLogic assets; version bump without tag where required.
8. **Validate (M).** Run by tier - see *Validation* below.
9. **Verify (M).** Apply the verify-a-result checklist to every number you will report.
10. **Review (O).** For non-trivial diffs run `/code-review` on the changed repo.
11. **Report (M).** Use the template in `references/report.md`. No other format.

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

## Git safety

The plugin's PreToolUse hook asks the user before destructive git (reset --hard, clean -f,
checkout -- / restore, stash, branch -D, force/any push, rebase), `add -A`/`add .`, commit on
protected branches, `commit -a/--amend`, tags, and submodule updates. The hook is a backstop,
not the policy - the policy is in `references/git-safety.md`. Stage explicit paths only.

## References - read when

- `references/repos.md` - first time in a repo, or the snapshot shows unmapped paths.
- `references/validation.md` - before running or reporting any check.
- `references/git-safety.md` - before any branch, stage, commit, or cleanup action.
- `references/report.md` - before writing the final report (always).
- `references/skill-contract.md` - when writing or running another rpg-factory skill.

All paths above are relative to `${CLAUDE_SKILL_DIR}`.
