# Paths, files and commands per OS (comfy-desktop-setup)

Verified means exercised on a real machine; UNVERIFIED means derived from the Windows layout and Electron's usual
locations. The script's `--desktop-dir`, `--venv`, `--codex-config` and `COMFY_DESKTOP_DIR` override every default.

| Item | Windows (verified) | macOS (UNVERIFIED) | Linux (UNVERIFIED) |
|---|---|---|---|
| Desktop data dir | `%APPDATA%\Comfy Desktop` | `~/Library/Application Support/Comfy Desktop` | `$XDG_CONFIG_HOME` or `~/.config`, `Comfy Desktop` |
| Instances | `installations.json` in the data dir: entries with `id`, `name`, `sourceId`, `installPath` | same | same |
| Local instance install | `%LOCALAPPDATA%\Comfy-Desktop\ComfyUI-Installs\<name>` | read `installPath` | read `installPath` |
| Custom nodes dir | `<installPath>\ComfyUI\custom_nodes` | `<installPath>/ComfyUI/custom_nodes` | same |
| Instance python | `<installPath>\standalone-env\python.exe` (py 3.13, torch, numpy, PIL) | not needed by the script | not needed by the script |
| Running port | `comfy-procs\<installationId>.json` key `port`; else `port-locks\port-<n>.json` | same | same |
| comfy-mcp venv | `~/.comfy-mcp-venv`, exe `Scripts\comfy-mcp.exe` | exe `bin/comfy-mcp` | exe `bin/comfy-mcp` |
| Codex config | `~/.codex/config.toml` | same | same |

## Instance kinds

`sourceId` `cloud` is Comfy Cloud: no custom nodes, not reachable by comfy-mcp. `standalone` is the local instance the
setup targets (`launchArgs` `--cpu` is fine). The script prefers `standalone`, then the most recently launched; pass
`--instance <name|id>` to choose.

## Registration commands (what `--apply` runs)

- Claude: `claude mcp add comfy-mcp --scope user -e COMFY_LOCAL_URL=<url> -- <exe>`; read back with `claude mcp get comfy-mcp`.
- Codex: `codex mcp add comfy-mcp --env COMFY_LOCAL_URL=<url> -- <exe>`; read back with `codex mcp get comfy-mcp --json`.
  It writes `~/.codex/config.toml`, which also holds the gateway provider: use the CLI only, never edit or print the file.
- A changed port is `mcp remove comfy-mcp` + `mcp add`. A new server appears only in a new session.

## Provider section the node needs (names only)

`[model_providers.<name>]` with `base_url` and `http_headers.Authorization` in the Codex config; name `9router`
unless `NINEROUTER_PROVIDER` says otherwise, file overridable with `NINEROUTER_CODEX_CONFIG`. The values are the
person's; nothing in the plugin, a template, a log or a record may carry them.
