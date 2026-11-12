### Fixed

- **asset-gen loads comfyui in every mode.** The skill told the session to invoke `rpg-factory:comfyui` only in step 1 of
  its workflow, so a `plan` or `analyze` task (and the dogfood scenario `asset-gen`, which failed with "expected comfyui
  not invoked" since 1.7.0) answered without it. The prerequisite block now asks for it first, in every mode.
