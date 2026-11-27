### Changed

- The generic pipeline defaults (`skills/delivery/pipeline-defaults.json`, used with `--registry none`) name the built-in Claude Code subagent type `Explore` for read-only scouts instead of the RPG plugin's `rpg-factory:factory-explorer`, so a dispatch in a project without the plugin names an agent type that exists there; the RPG registry keeps `rpg-factory:factory-explorer`. `tests/delivery-generic.test.sh` checks both types, the subagent policy of both, and the type a lead and implement dispatch names.
