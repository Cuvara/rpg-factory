---
type: llm
weight: 2
---

Routes through `factory-core` to lead `asset-gen` and loads `comfy-desktop-setup`. Plans `comfy-desktop-setup.py --check` first (read-only), then `--apply`, then `--check` again; names the human steps (Dashboard > New Instance > Standalone / Local because the Cloud instance cannot host nodes or be reached by comfy-mcp; Stop + Launch the instance after the node is copied; a new session for the new MCP server); says the port is read from Desktop's files rather than assumed; never runs `comfy-mcp --help` (a stdio server that hangs); asks for or prints no credential and says the provider config is only checked by names; claims nothing ran.
