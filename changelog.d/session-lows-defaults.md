### Fixed

- **Asset-gen style lock.** A dollar word directly before a slash in prose (for example "$USD/month") is no longer
  refused as an environment-variable path; a real `$NAME/` or `${NAME}/` path variable is still refused.

### Changed

- **Delivery defaults (tests only).** `tests/workflow.test.sh` pins the default Agent-tool runners
  (`pipeline.agents.<agent>.agent_runner`: `codex:codex-rescue` for Codex, `general-purpose` for Claude) in
  `registry.json`, `registry/core.json` and `skills/delivery/pipeline-defaults.json`, and checks that a codex-routed
  workflow node dispatches with `subagent_type` `codex:codex-rescue`. The test comment records the upstream evidence:
  openai/codex-plugin-cc ships plugin `codex` with agent `codex-rescue` (`plugins/codex/agents/codex-rescue.md`).
