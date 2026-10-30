---
name: factory-core
description: Shared Factory workflow for every registered discipline domain in the UnityIndie game workspace (rpg-mmo-server, IndieRPGMMOAdventure, Netcode, UnityDots, UIToolkit and the domains' authoring artifacts). Use at the start of ANY task that changes code, configuration, CI, deployment, measurements, documents or domain artifacts there, when resuming interrupted cross-repo work, and before reporting such work as done. Provides the live snapshot, deterministic domain and skill routing, coordination, validation with evidence, human gates, git safety and the verify-a-result report; domain workflows live with their registered leads. Game Design is a native domain for design artifacts. Not for web-game projects; web-game-factory owns those.
argument-hint: "[mode: analyze|plan|implement|validate|review|resume] [task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-status.py:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/run-checks.py:*)
---

# Factory Core

The Factory workflow for every discipline domain. Engineering is the first domain and keeps its existing behavior. Task: $ARGUMENTS
**Domains:** use `--domain` / `--kind` for domain entry points; non-engineering leads come from registry `domains`.

## Live snapshot (computed now - uncommitted paths shown are the user's baseline, not routed)

!`bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh`

Domain-specific artifact knowledge belongs to the registered domain lead; Factory Core coordinates the shared workflow.

Module rules, docs, changelogs, generated paths, dependencies, checks, contracts and facts live
in `${CLAUDE_PLUGIN_ROOT}/registry.json`; read them through the scripts, never guess them. If the
header says the install state is not CURRENT, tell the user (this session may run an old copy).

## Mode (decide first, declare it, and keep to it)

| Mode | When the user... | Does | Never |
|---|---|---|---|
| `analyze` | asks what exists, what a change would touch, "look into" | route, invoke the lead, explain | change files or git state |
| `plan` | asks for a plan / approach / "don't implement yet" | route, **invoke the lead**, produce its plan (files, legs, obligations, checks, gates) | change files or git state |
| `implement` | asks for the change (default when they ask to build/fix/add) | the full workflow below | skip validation |
| `validate` | asks to test / verify existing changes | `run-checks.py --status`, then run the checks, report | change files |
| `review` | asks to review a diff / branch | lead skill's review checklist + registry rules | change files |
| `resume` | asks to continue interrupted work | `factory-status.py`, then continue at the first incomplete step (implement rules) | redo finished legs |

Declare it when you invoke a Factory skill (put `mode: <mode>` in the skill arguments) and in the Route call
(`factory-context.sh --mode <mode> ...`). The hooks then **flag** departures (advisory only, they never block):
in analyze/plan/review every file write and mutating command gets a `high` advisory; validate flags anything but
`run-checks.py`. Respect the mode yourself. Switch mode only when the user asks for it (e.g. "now implement it").
Every mode except validate/resume invokes the lead skill: its workflow is where the plan comes from.
Parallel work: the main session leads and integrates; delegate in worktrees and follow `references/parallel-work.md`.

## Workflow

Steps are **M** mandatory, **O** optional, **H** need the user.

1. **Resume (M for cross-repo or interrupted work).** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/factory-status.py`
   lists pending work derived from the repos (wire rollout stage, READY_TO_TAG packages,
   released-but-unpinned, in-flight `<type>/<area>/<topic>` branches) with the owning skill.
2. **Scope (M).** Name repos and modules; read each touched module's `claude_md`. A task that
   would bind gameplay values without verified approval stops here (**H**, `phase-scope`).
3. **Baseline (M).** Snapshot paths are the user's; never modify, stage, stash, clean, reset or
   commit them unless named. Submodule contents are user state unless the task is about them.
4. **Route (M).** `bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh --mode <mode> --repo <key> --paths <files the task will write>`
   - run Factory scripts with the **absolute path exactly as printed here** (the permission allowlist matches
     it; a shortened relative path needs manual approval and stalls unattended sessions)
   (repo-relative; for a benchmark or measurement that is the bench harness / `docs/BENCHMARK.md` /
   results, not the code being measured).
   The bare snapshot never routes uncommitted baseline paths; only this call (or branch commits) routes the task.
   Then **call the Skill tool with the lead** (`rpg-factory:<lead>`) before planning or editing -
   also when the user only wants a plan or a review; naming the lead is not enough, its workflow,
   validation and gates are in that skill. The lead runs its **legs**. A task spanning repos has
   **one** lead: the driver of the contract that links them (e.g. a Nakama RPC used by the client →
   `server-services`; a wire field → `wire-contract`), shown as **Cross-repo** in the downstream
   repo's routing; the other repos' skills are its follow-ups. `no specialised lead - factory-core only` means no
   Skill call: follow the named CLAUDE.md with this workflow. A `Warning: not routed` path needs its own `--repo`.
   **Co-leads** run after the lead in the order shown (code before deploy before measurement).
   **Tech** skills (routing `tech`) are never leads, legs or follow-ups. The lead invokes them (Skill
   tool) before implementing, debugging or reviewing code, or answering how it works or how to test it -
   in every mode. A tool in "Tools for this change" that is not OK means its fallback applies; say which.
   **Follow-ups** are later work in other repos - name them in the report. **AMBIGUOUS** means the
   registry cannot decide: ask the user, or pass `--lead <skill>` (validated). `--explain` shows
   why every skill was or was not selected.
5. **Branch (M).** On a protected branch, create `<type>/<area>/<topic>` from the default branch
   before committing; reuse the **same topic** in every repo of a cross-repo task (factory-status
   links them). Commit, push, PR, merge are **H** (only on request); tags and releases only with the user's
   explicit release authorization in this task (`references/git-safety.md` rule 5).
6. **Plan (O/M).** Mandatory across modules, contracts or generated paths.
7. **Implement (M).** Requested scope only; module rules; generated paths only via their generator.
8. **Obligations (M).** CHANGELOG `[Unreleased]` per touched module, docs, regenerated artifacts,
   both sides of contracts, `.meta` files, version bump (no tag unless the release is authorized).
9. **Validate (M).** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/run-checks.py --repo <key> --paths <changed files>`.
   The runner executes and grades the checks; its table and evidence are the only acceptable
   evidence. Evidence is bound to the tree it ran on: after any further edit, `--status` shows it
   **STALE** - rerun before reporting. Extended checks: ask the user, then `--approve <check-id>`.
10. **Verify (M).** verify-a-result on every number you report (below).
11. **Review (O).** Non-trivial diffs: `/code-review`, then the lead's review checklist and the review
    file of every `routing.tech` skill that has one (e.g. the `unity-dots` ECS review checklist).
12. **Report (M).** `references/report.md`, including the runner table and routing. A release
    ends at **READY_TO_TAG** - the lead creates the tag, unless the user explicitly authorized the release in this task.

## Validation states (from run-checks.py)

| State | Meaning | Done? |
|---|---|---|
| PASS | ran, exit 0, evidence found (tests executed > 0, expected line present) | yes |
| FAIL | failed, no evidence (0 tests / all skipped), or left files in a product repo | no - fix |
| BLOCKED | a needed check did not PASS in this run, or its directory is missing | no |
| NOT_AVAILABLE | a required tool is missing here | no - say so |
| HUMAN_REQUIRED | extended check not approved, or external (CI, Unity Editor, cluster, Docker stack) | report as open |
| SKIPPED | excluded on purpose (`--only`, `--tier`, `--dry-run`) | n/a |
| NOT_RUN | (`--status`) declared for this change, never executed | no - run it |
| STALE | (`--status`) ran, but the tree changed since (HEAD, diff, untracked, check definition) | no - rerun |

Never write PASS yourself; never convert NOT_AVAILABLE / HUMAN_REQUIRED into success. Details and
per-tool evidence: `references/validation.md`.

## verify-a-result (non-negotiable)

Count passes (exit 0 on zero tests is not a pass); prove a zero can be non-zero; name the object a
number describes; write the expected value before running; an absent CI check is not a pass.
Canonical: `IndieRPGMMOAdventure/.claude/skills/verify-a-result/SKILL.md`, `rpg-mmo-server/backend/docs/MEASUREMENT.md`.

## Git safety and human gates

- The hooks are **advisory only** (1.0.3): they never ask the user and never block. A tool call that
  matches a rule runs, and you receive `rpg-factory advisory (high|warn): <rule>` as context - weigh it
  and follow the policy in `references/git-safety.md`.
- `high` (Bash **and** PowerShell): tag creation/deletion/push, `gh api` tag refs, `gh release create`,
  repository deletion; `warn`: destructive git, any push, `add -A`, commits/merges/cherry-picks/reverts
  on protected branches, ref rewrites, submodule updates, commands the guard cannot see through
  (interpreters, `$VAR`/`$(...)` as the program), other remote `gh` mutations and registry `human_gates`.
- File tools (Write/Edit/MultiEdit/NotebookEdit) get a `warn` advisory for embedded clones
  (`Packages/com.cuvara.*`), submodule content, generated paths or secrets.
- Stage explicit paths only. Policy: `references/git-safety.md`.

## Commands (the user types these; they are read-only except `check`)
`/rpg-factory:status` · `/rpg-factory:route <repo> <paths>` · `/rpg-factory:check <repo> [paths] [--status]` ·
`/rpg-factory:doctor`. Suggest them when the user asks "what is pending", "what would this touch", "is it
validated", "is Factory healthy".

## Skills

Engineering leads (the registry remains authoritative); supporting Engineering skills: `dotnet-gameserver`, `go-backend`, `unity-client-tech`, `unity-dots`, `netcode-client`.

| Situation | Lead skill |
|---|---|
| Game concepts, mechanics, GDDs, feature specs and design decisions | `game-design` (optional authoring repo) |
| UI flows and interface specifications | `ui-ux` (optional authoring repo) |
| 2D art briefs and delivery manifests | `art-2d` (optional authoring repo) |
| 3D art briefs and delivery manifests | `art-3d` (optional authoring repo) |
| VFX specifications and delivery manifests | `vfx` (optional authoring repo) |
| wire message/field, protocol version, JSON encoding, JoinToken claims, Redis servers:id | `wire-contract` (server → Netcode → client) |
| move a client pin (package / sgl tag) or the unity-build-workflows submodule | `pin-bump` |
| C# game server, ECS systems, knobs, metrics, content, Shared.GameLogic | `server-realtime` |
| Go gateway, Nakama RPCs, Redis store, persistence/migrations | `server-services` |
| Docker, compose, k8s/Agones, monitoring, backups, CD; TLS / sealed-transport switches (contract `transport-security`) | `server-ops` |
| Netcode / UnityDots / UIToolkit package code, up to READY_TO_TAG | `unity-package` |
| client VContainer wiring, Nakama/session, HUD/UI, DotsViews, build scripts | `client-integration` |
| benchmark harness (`GameServer.Tests/Bench/`), encoding sweep, re-baseline, multi-client verification | `measure` |

Orientation only, not routing: naming a lead from this table is not doing the task. In every mode, run
Route (step 4) and **invoke** the lead it prints before answering; supporting skills come after the lead.
The Skill hook never blocks: a supporting skill requested before factory-core loads factory-core instead;
one requested before its lead runs with an advisory - then route and invoke the lead. Engineering-specific tool details are in [references/engineering.md](references/engineering.md).

## References - read when
- `references/repos.md` - first time in a repo, unmapped or repo-level paths.
- `references/validation.md` - before running or reporting any check.
- `references/engineering.md` - Engineering repository map, tool evidence and procedures.
- `references/git-safety.md` - before any branch, stage, commit or cleanup.
- `references/report.md` - before the final report (always).
- `references/skill-contract.md` - routing precedence and how skills compose.
- `references/parallel-work.md` - before delegating, dispatching workers or integrating their branches.

All paths above are relative to `${CLAUDE_SKILL_DIR}`.
