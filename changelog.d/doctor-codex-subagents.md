### Added

- **Doctor.** `/rpg-factory:doctor` reports the Codex subagent setup (dev tool `codex-subagents`, probe
  `codex:subagents`; used by `delivery`, so the routed snapshot does not list it): `codex features list` must show `multi_agent` on, and `agents.default_subagent_model` and
  `agents.subagent.model` of the Codex config (`CODEX_HOME` or `~/.codex/config.toml`) must be inside
  `pipeline.models.scope.codex`. Otherwise it is a WARN line that names the fix (`[agents] default_subagent_model` =
  the `pipeline.subagents` Codex model). Only those two keys are read, a value that is not a model id is never shown,
  and the config is never written.
- **Dispatch.** No Orca dispatch change: `orca worker-start` and `orca agent launch` take no Codex `-c` config
  override, so the subagent model stays a Codex config setting that doctor checks.
