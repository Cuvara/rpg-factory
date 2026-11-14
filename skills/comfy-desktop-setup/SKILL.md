---
name: comfy-desktop-setup
description: How to set up, repair or verify the machine side of asset-gen - Comfy Desktop with a local instance, the vendored 9router image node copied into it, and comfy-mcp registered for Claude and Codex with the instance's real port - through the read-only-by-default script `scripts/comfy-desktop-setup.py`, including the human steps (New Instance, Stop + Launch) and the traps (Cloud instance, moving port, stdio server hang, nodes load at start). Use when asset-gen finds comfy-mcp missing, the image node absent from `server_info`, a COMFY_LOCAL_URL that does not answer, or a person asks to set up ComfyUI for image generation on a new machine. Not for running a workflow, templates or the node's run-time behaviour (`comfyui`), and not for deciding scope, gates or approving images (`asset-gen` and the art leads).
argument-hint: "[task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/comfy-desktop-setup.py:*)
---

# Comfy Desktop + 9router node + comfy-mcp setup (machine side of asset-gen)

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first. Honour the declared Factory mode: in `analyze`, `plan` and `review` apply this skill's workflow, rules and checklist to produce the analysis, plan or findings - change nothing; in `validate` only run and grade checks.

> **Supporting skill, never the owner:** invoke the lead (and co-leads) from the snapshot's routing line
> first - here `asset-gen`. If you have not, stop and invoke it now: rules, gates, validation and the
> report come only from it. This skill adds how the technology works; it decides nothing.

Task: $ARGUMENTS

Paths `scripts/`, `templates/` are the plugin root (`${CLAUDE_PLUGIN_ROOT}`). `setup` below is
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/comfy-desktop-setup.py`.

## Applies when / Not when

- **Applies:** `asset-gen` reports comfy-mcp not OK, `server_info` lacks `NineRouterImage`, a tool fails to reach
  ComfyUI, or a person wants image generation working on a new or changed machine (Windows primary).
- **Not when:** running a workflow, the template format, the node's behaviour or errors at run time (`comfyui`); scope,
  QA, review, approval and handoff of a run (`asset-gen`).

## Scope

Repos `authoring`. Owns no module, contract or check. The setup writes only on the person's machine, outside every
repository: the instance's `custom_nodes`, one venv, the two CLIs' MCP registrations. Changing the user's machine is
what the person asked for by invoking this; still ask before `--apply` when the request was only to analyse.

## Architecture

- **Pieces and who owns them:** Comfy Desktop (multi-instance app) hosts a local instance; the vendored node
  `templates/assetgen/comfy-node/comfyui_9router/__init__.py` (`NineRouterImage`, `NineRouterChat`; signature pinned to
  `scripts/assetgen/data/known-nodes.json` by `tests/comfy-desktop-setup.test.sh`) calls the 9router gateway; comfy-mcp
  (PyPI `comfy-mcp`, Comfy Org, stdio) is what the agent talks to. The node has no public repo: the plugin ships it.
- **The script** (`scripts/comfy-desktop-setup.py`; header docstring = usage and exit codes) is idempotent. `--check`
  (default) prints one row per step (`desktop`, `instance`, `provider`, `node`, `venv`, `port`, `node-live`,
  `mcp-claude`, `mcp-codex`) with OK, MISSING, OUTDATED, ACTION or FAIL and changes nothing; `--apply` does the missing
  steps; `--generate-test` (with `--apply`) runs one low-quality image. Exit 0 READY, 1 FAIL, 2 usage, 3 ACTION_NEEDED.
- **Hardware rows** (`scripts/comfy-desktop-setup.py` header docstring, advisory): `comfy-cli` (1.14.0+ in the comfy-mcp
  venv; `--apply` installs it there), `gpu`, `torch`, `profile`, `packs`, `models`. `profile` prints the best hardware
  profile the machine meets (`api-only`, `local-4gb`, `local-8gb`, `scripts/assetgen/data/hardware.json`) and why the
  higher ones fail: printed only, never applied; `asset-gen` resolve picks it up. `packs` and `models` list what that
  profile's templates still need; the person approves and installs them. The script never downloads a model, installs a
  pack or imports torch. `--check --json` also prints the `profile` object (`id`, `reasons`).
- **Where it lives:** `scripts/`, not `scripts/assetgen/` (that engine is scanned for URLs and credentials by
  `tests/assetgen.test.sh`) and not `scripts/checks/` (read-only by rule). It writes no Factory state.
- **Credentials:** the node reads `base_url` and the Authorization header at run time from the provider section the
  Codex config names (`references/platform-paths.md`). The script only tests that the names exist; it never prints,
  copies or stores a value, and never edits the Codex config (the `codex mcp` CLI writes it).

## Idioms

- **Order:** `setup --check` -> do the human steps it names -> `setup --apply` -> human restart -> `setup --check`
  until READY (exit 0) -> **save the profile** -> new session -> the `comfyui` run sequence. `--generate-test` proves the
  whole chain once.
- **Save the profile:** `assetgen.py resolve --profile auto` reads `<state>/assetgen/hardware-profile.json` and nothing
  else writes it (`scripts/assetgen/assetgen.py` `recorded_profile_path`; `<state>` is `scripts/lib/fstate.py`
  `persistent`: `$RPG_FACTORY_STATE_DIR` if absolute, else `$XDG_STATE_HOME/rpg-factory`, else `~/.local/state/rpg-factory`).
  In Git Bash: `mkdir -p ~/.local/state/rpg-factory/assetgen && python3 ${CLAUDE_PLUGIN_ROOT}/scripts/comfy-desktop-setup.py --check --json > ~/.local/state/rpg-factory/assetgen/hardware-profile.json`
  (adjust the directory when a state variable is set). The script exits 3 while a step needs action but still prints the
  JSON: never chain on its exit code. Save again after a GPU, driver or instance change; without the file `auto` means
  `api-only`.
- **Human steps an agent cannot do** (give them as a short list, then stop): (1) Desktop starts with only a "Comfy
  Cloud" instance: Dashboard > New Instance > Standalone / Local (for the `api-only` profile a CPU instance is enough, only API nodes run; the local profiles need the GPU the `profile` row reports). (2) Launch the
  instance. (3) After `--apply` copies the node: Stop + Launch the instance (custom nodes load only at start).
  (4) Start a new Claude/Codex session (a new MCP server loads only in a new session).
- **Port:** read the running port from Desktop's `comfy-procs/<installationId>.json`, else `port-locks/`; never assume.
  A changed port is registration remove + add (`--apply` does it per CLI).
- **Provider missing:** the script stops with FAIL and names what to add (`[model_providers.9router]`, `base_url`,
  `http_headers.Authorization`). Tell the person; never ask for or paste the key into a session.
- **Verify:** `GET /object_info/NineRouterImage` on the live port (the `node-live` row), then `server_info` in comfy-mcp.
  The default image model is the template's `model` param; never hard-code an id.

## Pitfalls

- **Comfy Cloud cannot host the node and comfy-mcp cannot reach it:** only a local instance listed in
  `installations.json` works (`scripts/comfy-desktop-setup.py` `pick_instance`).
- **The port is not fixed:** Desktop took 8189 while another ComfyUI held 8188 and 8188 afterwards; the registry
  services are hints (`registry/core.json` services `comfyui`, `comfyui-desktop`). A stale `COMFY_LOCAL_URL` fails
  every comfy-mcp tool (`scripts/comfy-desktop-setup.py` `find_port`, `check_mcp`).
- **Never run `comfy-mcp --help` (or the exe bare):** it is a stdio server and hangs waiting for a client. The script
  only registers the path (`scripts/comfy-desktop-setup.py` header docstring).
- **A copied node is not live until the instance restarts:** `node-live` ACTION is the signal, not a failure
  (`scripts/comfy-desktop-setup.py` `node_live`).
- **Windows:** use Git Bash, never WSL (a WSL git once rewrote the shared config); `chmod +x` does not set git's exec
  bit (`git update-index --chmod=+x`); `uv` or Python 3.14 may lack torch wheels, irrelevant for the Desktop route
  because the instance ships its own env with torch, numpy and PIL (`.claude/CLAUDE.md` Operating lessons).
- **The gateway does not list the image model and returns other sizes** (1254x1254 for a 1024 request): see the
  `comfyui` Pitfalls; a `--generate-test` size difference is not a setup failure (`scripts/assetgen/data/known-nodes.json` `warn_values`, `skills/comfyui/SKILL.md`).
- **A pack or model install needs the person's yes:** list the missing packs and models (the `packs` and `models` rows,
  with kind, name and size) and ask. Never `install_node`, `download_model`, update ComfyUI or fetch a weight on your
  own; the cut-out node also downloads its weight on its first run, which needs the same yes. Never substitute a model
  silently.
- **The local profiles are UNTESTED on RTX 5060** (8 GB): the user tests them after merge. The `profile` row reports
  what the machine meets, not a measured result; claim no VRAM number, timing or generation (`rpg-factory:comfyui`
  Idioms "Hybrid and local runs").
- **macOS and Linux paths are UNVERIFIED** (`references/platform-paths.md`): the output says so; pass
  `--desktop-dir` when the default is wrong and report what you found.

## Testing

- `tests/comfy-desktop-setup.test.sh`: the vendored node (signature equals `known-nodes.json`, run-time provider
  lookup against a loopback fake gateway, no key value in the source) and the script against a temp fake Desktop data
  dir, a fake ComfyUI and fake `claude`/`codex` CLIs: `--check` writes nothing, `--apply` is idempotent, a changed port
  is remove + add, `--generate-test` posts the low-quality graph, no output carries the key. No network.
- Against the real machine only `setup --check` (read-only). Never `--apply` or `--generate-test` on a working setup
  to "see what happens"; a real generation spends credits.

## Tools

- `comfy-mcp`: the thing this skill installs and registers; after READY and a new session `server_info` is the live
  check. Not OK: `setup --check` shows the missing step; the fallback is the `asset-gen` one (render only,
  generation `NOT_RUN`).
