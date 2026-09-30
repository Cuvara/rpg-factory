---
name: factory-core
description: Engineering workflow for the UnityIndie RPG MMO workspace - rpg-mmo-server (Go/C# backend), IndieRPGMMOAdventure (Unity client) and the Netcode, UnityDots and UIToolkit package repos. Use at the start of ANY code, config, CI, deploy, measurement or docs change in those repos, when resuming interrupted cross-repo work, and before reporting such work as done. Provides the live snapshot, deterministic routing to the specialised skill, cross-repo status, Factory-run validation with evidence, human gates, git safety and the verify-a-result report. Not for game design / GDD / feature-registry lifecycle (game-ai-workflows) or web game projects (web-game-factory).
argument-hint: "[task description]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-status.py:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/run-checks.py:*)
---

# Factory Core - RPG MMO workspace

The Factory workflow every rpg-factory skill builds on. Task: $ARGUMENTS

## Live snapshot (computed now - changed paths shown are the user's baseline)

!`bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh`

Module rules, docs, changelogs, generated paths, dependencies, checks, contracts and facts live
in `${CLAUDE_PLUGIN_ROOT}/registry.json`; read them through the scripts, never guess them. If the
header says the install state is not CURRENT, tell the user (this session may run an old copy).

## Workflow

Steps are **M** mandatory, **O** optional, **H** need the user.

1. **Resume (M for cross-repo or interrupted work).** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-status.py`
   lists pending work derived from the repos (wire rollout stage, READY_TO_TAG packages,
   released-but-unpinned, in-flight `<type>/<area>/<topic>` branches) with the owning skill.
2. **Scope (M).** Name repos and modules; read each touched module's `claude_md`. A task that
   would invent gameplay rules or numbers stops here (**H**, `phase-plumbing-only`).
3. **Baseline (M).** Snapshot paths are the user's; never modify, stage, stash, clean, reset or
   commit them unless named. Submodule contents are user state unless the task is about them.
4. **Route (M).** `bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh --repo <key> --paths <files the task will write>`
   (repo-relative; for a benchmark or measurement that is the bench harness / `docs/BENCHMARK.md` /
   results, not the code being measured).
   Then **call the Skill tool with the lead** (`rpg-factory:<lead>`) before planning or editing -
   also when the user only wants a plan or a review; naming the lead is not enough, its workflow,
   validation and gates are in that skill. The lead runs its **legs**.
   **Co-leads** run after the lead in the order shown (code before deploy before measurement).
   **Follow-ups** are later work in other repos - name them in the report. **AMBIGUOUS** means the
   registry cannot decide: ask the user, or pass `--lead <skill>` (validated). `--explain` shows
   why every skill was or was not selected.
5. **Branch (M).** On a protected branch, create `<type>/<area>/<topic>` from the default branch
   before committing; reuse the **same topic** in every repo of a cross-repo task (factory-status
   links them). Commit, push, PR, merge are **H** (only on request); tags are never done by agents.
6. **Plan (O/M).** Mandatory across modules, contracts or generated paths.
7. **Implement (M).** Requested scope only; module rules; generated paths only via their generator.
8. **Obligations (M).** CHANGELOG `[Unreleased]` per touched module, docs, regenerated artifacts,
   both sides of contracts, `.meta` files, version bump (never a tag).
9. **Validate (M).** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/run-checks.py --repo <key> --paths <changed files>`.
   The runner executes and grades the checks; its table and evidence file are the only
   acceptable evidence. Extended checks: ask the user, then rerun with `--approve <check-id>`.
10. **Verify (M).** verify-a-result on every number you report (below).
11. **Review (O).** `/code-review` on non-trivial diffs.
12. **Report (M).** `references/report.md`, including the runner table and routing. A release
    ends at **READY_TO_TAG** - the lead creates the tag.

## Validation states (from run-checks.py)

| State | Meaning | Done? |
|---|---|---|
| PASS | ran, exit 0, evidence found (tests executed > 0, expected line present) | yes |
| FAIL | failed, no evidence (0 tests / all skipped), or left files in a product repo | no - fix |
| BLOCKED | a needed check failed, or its directory is missing | no |
| NOT_AVAILABLE | a required tool is missing here | no - say so |
| HUMAN_REQUIRED | extended check not approved, or external (CI, Unity Editor, cluster, Docker stack) | report as open |
| SKIPPED | excluded on purpose (`--only`, duplicate command) | n/a |

Never write PASS yourself; never convert NOT_AVAILABLE / HUMAN_REQUIRED into success. Details and
per-tool evidence: `references/validation.md`.

## verify-a-result (non-negotiable)

Count passes (exit 0 on zero tests is not a pass); prove a zero can be non-zero; name the object a
number describes; write the expected value before running; an absent CI check is not a pass.
Canonical: `IndieRPGMMOAdventure/.claude/skills/verify-a-result/SKILL.md`, `rpg-mmo-server/backend/docs/MEASUREMENT.md`.

## Git safety and human gates

- The guard (Bash **and** PowerShell) **denies** tag creation/deletion/push, `gh api` tag refs and
  `gh release create`; it **asks** before destructive git, any push, `add -A`, commits/merges/
  cherry-picks/reverts on protected branches, ref rewrites, submodule updates, commands it cannot
  see through (interpreters, `$VAR`/`$(...)` as the program) and registry `human_gates`.
- If a tool result contains **"STOP - rpg-factory tripwire"**, stop immediately: do not repair,
  reset or retry anything. Report what it says to the user. Mutating commands stay denied until
  the user acknowledges (`tripwire.py --ack`).
- Stage explicit paths only. Policy: `references/git-safety.md`.

## Skills

| Situation | Lead skill |
|---|---|
| wire message/field, protocol version, JSON encoding, JoinToken claims, Redis servers:id | `wire-contract` (server → Netcode → client) |
| move a client pin (package / sgl tag) or the unity-build-workflows submodule | `pin-bump` |
| C# game server, ECS systems, knobs, metrics, content, Shared.GameLogic | `server-realtime` |
| Go gateway, Nakama RPCs, Redis store, persistence/migrations | `server-services` |
| Docker, compose, k8s/Agones, monitoring, backups, CD | `server-ops` |
| Netcode / UnityDots / UIToolkit package code, up to READY_TO_TAG | `unity-package` |
| client VContainer wiring, Nakama/session, HUD/UI, DotsViews, build scripts | `client-integration` |
| benchmark, encoding sweep, re-baseline, multi-client verification | `measure` |

## References - read when

- `references/repos.md` - first time in a repo, unmapped or repo-level paths.
- `references/validation.md` - before running or reporting any check.
- `references/git-safety.md` - before any branch, stage, commit, cleanup, or after a tripwire STOP.
- `references/report.md` - before the final report (always).
- `references/skill-contract.md` - routing precedence and how skills compose.

All paths above are relative to `${CLAUDE_SKILL_DIR}`.
