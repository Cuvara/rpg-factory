# CLAUDE.md - rpg-factory

Claude Code plugin providing Factory Core for the UnityIndie RPG MMO workspace. See README.md.

## Rules for changing this repo

- `registry.json` is the source of truth for module knowledge. Never hard-code module paths,
  commands, or rules in `SKILL.md` or the references - put them in the registry and read them.
- Keep `factory-context.sh`, `factory-status.py` and `scripts/checks/` read-only: no fetch (except
  opt-in `--remote` ls-remote), no writes into repos. State is derived from git; the only Factory
  files are per-session mode state and check evidence, resolved through `scripts/lib/fstate.py` (never `$TMPDIR`
  directly, never relative). Tests set `RPG_FACTORY_STATE_DIR` and `TMPDIR` to a temp dir.
- `run-checks.py` never runs a check in place when it would write into a product repo; pollution is FAIL.
- Hooks must stay fast (one guard process per command, no repository scan) and must never crash a session.
  No hook snapshots repository state, latches a session or needs an acknowledgement (the tripwire was
  removed on purpose; do not bring back a post-command lock under another name).
- No hook asks the user or blocks the agent: hooks emit only `additionalContext` advisories
  (`rpg-factory advisory (high|warn): ...`), never a `permissionDecision` (removed on purpose in 1.0.3; do not
  bring back ask/deny). The git guard never crashes a session (errors mean "no opinion"); `high` marks tag
  creation/deletion/pushes (incl. `gh api` tag refs, `gh release create`) and repo deletion. Every new bypass found gets a
  case in `tests/git-guard.test.sh` (and `tests/installed-safety.sh` for new classes). File-tool rules live
  in `scripts/file-guard.py`; execution modes are enforced by both guards. Each human gate regex and the git evaluation must fail independently.
- Every behaviour change gets a test in `tests/` and a `CHANGELOG.md` entry under [Unreleased].
- Before committing: `tests/run-all.sh` must report 0 failed. Report the pass count. CI
  (`.github/workflows/tests.yml`) runs only `--no-workspace --no-claude`; it does not replace the local run.
- English only. Conventional Commits (`feat(core): ...`, `fix(guard): ...`, `docs(registry): ...`).
- New or changed skills follow `skills/factory-core/references/skill-contract.md`; `tests/skills-lint.sh`
  enforces the mechanical part. Routing changes need a scenario in `tests/routing.test.sh`. New skills start
  from `scripts/new-skill.py` and are done when `scripts/skill-touchpoints.py <s>` is OK (`.claude/skills/skill-author`).
- A skill's `path:line` citation names the symbol it shows (anchor) and must pass
  `scripts/checks/skill-citations.py` against the integration branches; cite docs by section, not line.
- **Releases:** bump `VERSION`, `.claude-plugin/plugin.json` and `marketplace.json` together with a
  `CHANGELOG.md` section (run-all checks it). The local directory marketplace loads this checkout in
  place (what is checked out is what sessions run); the install record only updates on a version
  change: `claude plugin marketplace update rpg-factory && claude plugin update rpg-factory@rpg-factory`,
  restart, then `tests/run-all.sh --release` and `tests/dogfood.sh --installed`.
  Never create the tag - the maintainer does (READY_TO_TAG).
- Point-in-time values go in registry `facts[]` with a probe, never in skill prose.
- Registry facts must be verified against the product repos (file paths, CI workflow
  contents, run logs), not copied from docs that may be stale.

## Commands

```bash
tests/run-all.sh                    # every local suite; must end with 0 failed
tests/run-all.sh --no-workspace     # skip checks needing the RPG MMO workspace on disk
tests/run-all.sh --no-claude        # skip `claude plugin validate`
tests/run-all.sh --release          # + installed plugin CURRENT, source committed, installed-safety.sh

# single suites (each standalone; sets its own temp TMPDIR / RPG_FACTORY_STATE_DIR)
tests/git-guard.test.sh
env -u TMPDIR tests/session-state.test.sh  # run-all runs session-state/file-guard/commands with TMPDIR unset
tests/routing.test.sh [--no-history]       # task scenarios (+ real commits replayed read-only)
python3 -B tests/routing-properties.test.py
tests/skills-lint.sh                       # skill contract, tech sections, ## Tools vs dev_tools
env -u TMPDIR tests/devtools.test.sh       # dev tool probes, snapshot/doctor lines, no secrets printed
scripts/check-registry.sh [--structure-only]
env -u TMPDIR tests/skill-citations.test.sh  # citation checker on fixture repos
python3 -B scripts/checks/skill-citations.py [--skill <s>] [--suggest]   # skill path:line vs integration branches
python3 -B scripts/new-skill.py --name <s> --kind tech|repo|cross-repo ... [--dry-run]  # scaffold (see .claude/skills/skill-author)
python3 -B scripts/skill-touchpoints.py <s>|--all  # every place a skill must appear
env -u TMPDIR tests/new-skill.test.sh      # scaffolder + touchpoints on a throwaway plugin copy

# routing / state, read-only against the workspace
scripts/factory-context.sh --repo server --paths backend/shared/proto/wire.proto [--explain] [--json]
python3 -B scripts/factory-status.py
python3 -B scripts/run-checks.py --repo <key> --paths <files> [--status]

tests/dogfood.sh [--installed]      # real headless Claude sessions; spends tokens, not in run-all
```

Workspace defaults to `/mnt/c/Workspaces/UnityIndie`; override with `RPG_FACTORY_WORKSPACE`. Python
scripts are run with `-B` (run-all deletes `__pycache__`).

## How it fits together

- **Routing:** `factory-context.sh` → `lib/context.py` collects git state per repo (worktree-aware) and
  pipes it through `lib/resolve.jq` over `registry.json`. Output: touched modules, dependents, contracts,
  lead / co-leads / legs / follow-ups, checks by tier (fast / extended / external), and human gates. The lead
  is deterministic: contract driver, then repo-kind driver, then primary owner, then secondary owner. Ties
  break on `skills.<name>.order`. Unmapped files fall back to `<repo>.root`.
- **Validation:** `run-checks.py` runs registry checks and grades them (PASS / FAIL / BLOCKED / NOT_AVAILABLE /
  HUMAN_REQUIRED / SKIPPED / NOT_RUN / STALE). Evidence is keyed by tree identity and written through
  `lib/evidence.py`. `--status` regrades that evidence without running checks.
- **Derived state:** `factory-status.py` covers rollout stage, READY_TO_TAG, pin drift, uncommitted work and
  STALE evidence. Nothing is stored; it re-derives everything from git each time.
- **Hooks** (`hooks/hooks.json`):
  - SessionStart: `install-status.py --session`.
  - PreToolUse Bash|PowerShell: `git-guard.py`.
  - PreToolUse Write|Edit|MultiEdit|NotebookEdit|Read: `file-guard.py`.
  - PreToolUse Skill: `factory_session.py --skill`, which records the execution mode and gives a `kind: tech` skill a `high`
    advisory until one of its `used_by` leads ran in the session (it still runs). Both guards import `factory_session` for the mode.
  - No PostToolUse hooks.
- **Slash commands** (`commands/*.md`: status, route, check, doctor) call `scripts/factory-cmd.py` and are
  covered by `tests/commands.test.sh`.
- **Skills:** `factory-core` (references: git-safety, report, repos, validation, skill-contract) routes to
  8 specialised skills: wire-contract, pin-bump, measure, server-realtime, server-services, server-ops,
  unity-package, client-integration. 5 tech skills (`kind: tech`: dotnet-gameserver, go-backend,
  unity-client-tech, unity-dots, netcode-client) own no module, are never routed, and appear as `routing.tech` for their `used_by`.
- **Dev tools:** registry `dev_tools[]` → `lib/devtools.py` probes (PATH, TCP services, MCP server and
  plugin names only - never config values) → snapshot "Tools for this change" and doctor "Dev tools".
  Every non-core skill's `## Tools` names exactly its `used_by` tools (skills-lint).

## Layout

- `.claude-plugin/` manifests - `skills/` - `commands/` - `scripts/` (+ `lib/`, `checks/` read-only evidence
  scripts) - `hooks/hooks.json` - `tests/` (+ `fixtures/`) - `evals/` - `docs/registry.schema.json`
