### Added

- **asset-gen model hashes follow extra model paths.** `assetgen.py model-hashes` also hashes the model folders that
  ComfyUI extra model path files name for the hashed kinds (checkpoints, loras, controlnet, upscale_models,
  annotators): `<comfy root>/extra_model_paths.yaml`, the Comfy Desktop `<data dir>/instance-model-paths/<instance id>.yaml`
  of the picked instance, and every `--extra-model-paths FILE` (repeatable; `--no-extra-model-paths` turns off only the
  auto-discovery). The reader covers the subset ComfyUI and Comfy Desktop write (named sections, `base_path`,
  `is_default`, block scalars with several folders per kind) with the standard library only. Folder order follows
  ComfyUI (`is_default` sections first, then the main folder, then the rest); a model name already taken by an earlier
  folder is skipped with a warning, and rows are still reused by size and mtime. A malformed or unreadable file is a
  warning (`extra model paths <file>: ...; file ignored`), not a crash or a failure; an explicit file that does not exist
  exits 2. `--json` gains an additive `extra_model_paths` field and the cache schema is unchanged.
