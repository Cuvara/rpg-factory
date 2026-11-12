### Added

- **asset-gen setup.** New tech skill `comfy-desktop-setup` and `scripts/comfy-desktop-setup.py`: `--check` (read-only, default) and `--apply` set up a local Comfy Desktop instance, the 9router image node (vendored under `templates/assetgen/comfy-node/comfyui_9router/`, signature pinned to `known-nodes.json`) and comfy-mcp for Claude and Codex with the instance's real port; `--generate-test` runs one low-quality image. Never prints the provider key. Windows verified; macOS and Linux paths unverified. Covered by `tests/comfy-desktop-setup.test.sh`, a routing scenario, a dogfood scenario and an eval.

### Changed

- **Registry.** The `comfyui` and `comfyui-desktop` service ports are marked as hints (Desktop picks a free port per start); `comfyui` Setup points to `comfy-desktop-setup`.
