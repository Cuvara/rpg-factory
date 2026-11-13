### Added

- **Asset-gen hardware profiles.** UNTESTED on RTX 5060: `hardware.json` defines planning profiles and setup reports GPU, torch, profile, packs and models; the profile is printed only, never applied. No number is measured, and the checks never download models or install packs.

### Fixed

- **Comfy setup.** Check and install comfy-cli and register its path as COMFY_BIN for both MCP clients, fixing the live end-to-end failure with the bare `Error executing tool`.
