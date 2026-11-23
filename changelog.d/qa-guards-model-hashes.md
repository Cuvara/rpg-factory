### Added

- **asset-gen model hashes.** `assetgen.py model-hashes [--models-dir DIR | --comfy-dir DIR] [--desktop-dir DIR] [--instance NAME|ID] [--kind K]... [--json]`
  writes the model sha256 cache that `manifest` reads (`<persistent state dir>/comfy/model-hashes.json`, or
  `ASSETGEN_MODEL_HASHES`), so the local-stage manifest records checkpoints, LoRAs, ControlNet, upscale and annotator
  models as verified instead of unverified. It resolves the models directory from `--models-dir`, a headless
  `--comfy-dir`, or the Comfy Desktop instance (`--desktop-dir`, `COMFY_DESKTOP_DIR`, the per-OS default), exits 2 with a
  one-line message when none exists, and writes only Factory state through `fstate`. Files are hashed in 1 MiB chunks, and a
  row is reused without reading the file while its size and mtime are unchanged. The schema stays
  `rpg-factory.comfy-model-hashes/1`: `size` and `mtime_ns` per row and `models_dir` are additive fields the reader ignores.
  A backslash in a model name (ComfyUI on Windows) now reads as `/` in the cache key and the manifest lookup.
