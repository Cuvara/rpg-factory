### Added

- **Delivery.** New skill `rpg-factory:delivery`, usable in any repository or workspace: the two-level flow (run lead,
  task leads, short sub-sessions), agent routing with model fallback, cross-model review, child worktrees, session
  release, Orca waiting, QA tiers and the plan/verdict/gate pipeline. Its reference
  `skills/delivery/references/delivery.md` is the single copy of the generic policy; factory-core loads it for its
  delivery steps. README gives a one-line pointer for `~/.claude/CLAUDE.md` and Codex `AGENTS.md`.
- **Pipeline.** `factory-pipeline.py` runs without the RPG registry: with `--registry none`, `RPG_FACTORY_PIPELINE_REGISTRY=none`
  (a pipeline-only variable) or a missing registry file it reads `skills/delivery/pipeline-defaults.json`, and every command
  it prints for a next session (task-lead spec, planner spec, `status` next lines) carries `--registry none`.
  The installed plugin always ships `registry.json`, so there the flag or the variable selects the defaults. A plan may set `no_worktree_markers`
  to replace the default markers. `tests/delivery-generic.test.sh` covers tier, validate, dispatch, verdict and gate
  on a throwaway repo outside any workspace.

### Changed

- **Policy.** `skills/factory-core/references/parallel-work.md` keeps only the UnityIndie specifics (Unity no-worktree
  repos, the `unity-test` resource, registry repos, human gates and release rules) and points to `delivery.md`.
  Dispatch specs cite `references/delivery.md`.
