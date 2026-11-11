# CLAUDE.md - rpg-factory

Claude Code plugin providing Factory Core for the UnityIndie RPG MMO workspace. See README.md.
Architecture and layout: `docs/architecture/overview.md`. Release procedure: `docs/releasing.md`. Script index and full command list: `scripts/README.md`.

## Rules for changing this repo

- `registry.json` is the source of truth for module knowledge. Never hard-code module paths, commands or rules in
  `SKILL.md` or the references; put them in the registry. It is generated: edit the fragments under `registry/`
  (placement rule: `scripts/lib/registry_src.py`), then `python3 -B scripts/build-registry.py`. run-all fails when
  `registry.json` is not the build (`--check`). After a merge, rebuild if `registry.json` conflicted.
- `factory-context.sh`, `factory-status.py` and `scripts/checks/` stay read-only: no fetch (except opt-in `--remote`
  ls-remote), no writes into repos. State is derived from git. The only Factory files are per-session mode state and
  check evidence, resolved through `scripts/lib/fstate.py` (never `$TMPDIR` directly, never relative); tests set
  `RPG_FACTORY_STATE_DIR` and `TMPDIR` to a temp dir. On purpose in the persistent state dir: run-all's lock, tree
  records and suite PASS records (`run-all/`, `locks/`), and the routing replay cache (`routing-replay/`, pruned on write).
- `run-checks.py` never runs a check in place when it would write into a product repo; pollution is FAIL.
- Hooks stay fast (one guard process per command, no repository scan) and never crash a session. No hook snapshots
  repository state, latches a session or needs an acknowledgement (the tripwire was removed on purpose; do not bring
  back a post-command lock under another name).
- No hook asks the user or blocks the agent: hooks emit only `additionalContext` advisories
  (`rpg-factory advisory (high|warn): ...`), never a `permissionDecision` (removed in 1.0.3; do not bring back
  ask/deny). Guard errors mean "no opinion". `high` marks tag creation/deletion/pushes (incl. `gh api` tag refs,
  `gh release create`) and repo deletion. Every new bypass gets a case in `tests/git-guard.test.sh` (new classes also
  `tests/installed-safety.sh`). File-tool rules live in `scripts/file-guard.py`. Each human gate regex and the git
  evaluation must fail independently.
- Every behaviour change gets a test in `tests/` and a fragment `changelog.d/<topic>.md` (`### Added|Changed|Fixed|...`;
  `changelog.d/README.md`). Never edit `CHANGELOG.md` `[Unreleased]`: it stays empty (run-all checks it).
- QA: while iterating and in task QA run the tier command (`tests/run-all.sh --affected --base <base> -j 2`, or
  `--only-suites`); a task never runs the full suite. Implementers run no suites (syntax check only); one verify
  session per task runs review, then the tier command once (`--case` in a slow suite, `tests/affected.py cases`).
  CI is the full-suite gate (`--no-workspace --no-claude` only): before a PR, integration QA runs
  `tests/run-all.sh --workspace-only` with 0 failed; CI (`gh pr checks <pr> --watch`) must be green before merging,
  and while it runs start the next task. Full `--release` and `tests/dogfood.sh --installed` run only for releases.
  Report the pass count. Tiers: `delivery.md` section 10 "QA tiers"; tier S and docs-only tasks get lead QA.
- English only. Conventional Commits (`feat(core): ...`, `fix(guard): ...`, `docs(registry): ...`).
- Skills follow `skills/factory-core/references/skill-contract.md` (`tests/skills-lint.sh` enforces the mechanical
  part). Routing changes need a scenario in `tests/routing.test.sh`. New skills start from `scripts/new-skill.py` and
  are done when `scripts/skill-touchpoints.py <s>` is OK (`.claude/skills/skill-author`).
- A skill's `path:line` citation names the symbol it shows (anchor) and must pass `scripts/checks/skill-citations.py`
  against the integration branches; cite docs by section, not line. A citation whose anchor moved to a unique line is
  MOVED (warning; FAIL under `--strict` / `run-all --release`): `--fix` rewrites it.
- Parallel plugin work follows `skills/delivery/references/delivery.md` (generic policy) and
  `skills/factory-core/references/parallel-work.md` (RPG specifics): one worktree and one task-lead session per task,
  never a second clone; the run lead integrates. Those two files are the only copies of the policy
  (`tests/skills-lint.sh`, `tests/parallel-policy.test.sh`).
- **Developing this plugin:** every plugin task runs through `factory-pipeline.py` with a `plan.json` whose `repos` entry
  names this checkout (`"plugin": {"path": "<this checkout>"}`), small tasks with disjoint owned paths and cross-model review.
  Steps: `skills/factory-core/SKILL.md` step 6; policy: `skills/delivery/references/delivery.md`.
- **Releases:** bump versions and gather fragments with `scripts/changelog.py release`. Without
  explicit release authorization from the user in the current task, stop at READY_TO_TAG: the maintainer tags and publishes.
  With it, never move, delete or reuse a tag and never bypass a failing check. Procedure and order: `docs/releasing.md`.
- Point-in-time values go in registry `facts[]` with a probe, never in skill prose.
- Registry facts must be verified against the product repos (paths, CI workflows, run logs), not copied from stale docs.

## Operating lessons

Each lesson names its reason. Delivery-flow lessons (Orca, Codex, sessions, load limits) live in
`skills/factory-core/references/parallel-work.md`, dogfood practice in `docs/dogfood.md`.

- **No worktree or branch creation while `tests/run-all.sh` runs:** every checkout shares one `.git/config`, and run-all's shared-config check fails when a new worktree or tracking branch writes to it.
- **Create branches with `git switch --no-track -c <branch>`:** a tracking branch writes `branch.<name>.*` into the shared `.git/config` and races with other sessions' runs.
- **Git Bash, never WSL, on Windows:** a WSL git run once wrote `core.worktree=/mnt/c/...` into the shared config and broke every checkout.
- **Fix citation drift right before a release gate** (`python3 -B scripts/checks/skill-citations.py --fix`): client and Netcode `develop` merge refactors every 30-60 minutes and drifted four times in 1.3.0; check their open PRs first.
- **One full run per machine (the run-all lock):** a second full `tests/run-all.sh` waits (`--no-wait` exits 3); four parallel full runs made every suite 2-4x slower and timed some out. Other sessions use the tier command.
- **Targeted runs take a test slot** (`RPG_FACTORY_TEST_SLOTS`, default 2, machine-wide): a busy machine waits instead of slowing every suite 2-4x. The slot belongs to the run, not the session: stop a QA worker's background run before abandoning it (an abort once held a slot 45 min). Frozen suite copies go under a temp dir, never into `tests/`.
- **Task worktrees must be visible in Orca** (maintainer, 2026-11-09): a `git worktree add --no-track` worktree has no Orca lineage and lands in the hidden section. Run `orca worktree set --worktree path:<dir> --parent-worktree path:<parent> --display-name <topic>-<task> --workspace-status in-progress` before `orca agent launch` (`delivery.md` section 4 "Orca visibility"). Never `orca worktree create` for lineage: it writes `branch.<name>.base` into the shared `.git/config`.
- **On Windows `chmod +x` does not set git's executable bit:** use `git update-index --chmod=+x <file>`, or the script is committed as 100644 and fails on Linux CI.
- **Quote shell examples in messages in single quotes, or put them in a file:** backticks inside a double-quoted argument (an `orca orchestration send --body`) are command substitution and the message loses the example.
- **Never stop a process by pattern (`pkill -f <name>`):** a worker that did so to stop its own duplicate skills-lint run may have killed other sessions' runs; stop only the PID you started.
- **Learning loop:** a new lesson goes here or into its policy file (`parallel-work.md`, `docs/dogfood.md`, `git-safety.md`) with its reason and a test when possible. Private agent memory only points here: Codex, other machines and new sessions never see it.

## Commands

```bash
tests/run-all.sh --affected --base <base> -j 2   # tier command: suites touched since <base> (not the PR gate)
tests/run-all.sh --only-suites a,b               # only the named suites (--list-suites prints names)
tests/run-all.sh --workspace-only                # what CI cannot run; integration QA before a PR
tests/run-all.sh --release                       # full release gate (releases only, under the lock)
tests/git-guard.test.sh                          # also: skills-lint.sh, routing.test.sh, pipeline.test.sh, new-skill.test.sh
python3 -B scripts/build-registry.py [--check]   # registry.json from registry/
python3 -B scripts/changelog.py check|preview    # changelog fragments (release X.Y.Z: docs/releasing.md)
```

Workspace defaults to `/mnt/c/Workspaces/UnityIndie`; override with `RPG_FACTORY_WORKSPACE`. Run Python with `-B`.
Every other command and single suite: `scripts/README.md` "Commands".
