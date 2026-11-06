### Fixed

- **`pipeline subplan` through the command entry point.** `factory-cmd.py pipeline` (and the `/rpg-factory:pipeline`
  slash command) rejected `subplan` with the usage error, so a task lead could not run `pipeline subplan validate`
  that way. `subplan` is now a pipeline verb and the usage text and `help` list it.
