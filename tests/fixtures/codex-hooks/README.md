# Codex hook payload fixtures

Captured from real `codex-cli 0.164.0` `codex exec` hooks on Windows, then
sanitized: session/turn/tool IDs and paths are placeholders; shell commands and
patch targets were replaced with the scenarios below. The malformed case is
synthetic. JSON fields and tool names retain the captured shapes.

| Fixture | Adapter argument | Expected advisory |
|---|---|---|
| `pre-tool-use-push-tags.json` | `pre-tool-use` | high |
| `pre-tool-use-status.json` | `pre-tool-use` | none |
| `pre-tool-use-skill-read.json` | `pre-tool-use` | none (Codex loads skills by reading) |
| `pre-tool-use-force-push.json` | `pre-tool-use` | warn |
| `pre-tool-use-protected-patch.json` | `pre-tool-use` | warn |
| `pre-tool-use-plain-patch.json` | `pre-tool-use` | none |
| `pre-tool-use-move-to-protected.json` | `pre-tool-use` | warn |
| `pre-tool-use-malformed.json` | `pre-tool-use` | none |
| `session-start-startup.json` | `session-start` | warn when not installed; none when current |

Replay in an isolated environment: create a temporary workspace with the files
listed by `registry.json`'s `workspace.root_markers`, initialize its
`rpg-mmo-server` as a Git repository, replace each fixture's `cwd` with that
server's absolute native path, and set `RPG_FACTORY_WORKSPACE` to the temporary
workspace. Set `RPG_FACTORY_STATE_DIR` and `TMPDIR` to temporary directories;
clear `RPG_FACTORY_GUARD`, `CLAUDE_PLUGIN_ROOT`, `PLUGIN_ROOT`, and any registry
override. Use a fresh empty `CODEX_HOME` for the warn SessionStart case (or the
verified current isolated install for none). No fixture command/patch is executed:
pipe the JSON into `python3 -B scripts/codex_hook.py <argument>`.

Every invocation exits 0. Stdout is empty for none, otherwise exactly one JSON
object containing only `hookSpecificOutput.hookEventName` and
`hookSpecificOutput.additionalContext`; the advisory string contains
`rpg-factory advisory (warn)` or `rpg-factory advisory (high)`.

Observed payload fields: `session_id`, `transcript_path`, `cwd`,
`hook_event_name`, `model`, `permission_mode`; SessionStart adds `source`, and
PreToolUse adds `turn_id`, `tool_name`, `tool_input`, `tool_use_id`. Shells,
including Windows PowerShell, report `tool_name: "Bash"` and
`tool_input.command`. File edits report `tool_name: "apply_patch"` with the raw
patch in `tool_input.command`. Patch move source and destination both need checks.

Installed plugin hooks receive `PLUGIN_ROOT`, `PLUGIN_DATA`, and compatibility
`CLAUDE_PLUGIN_ROOT`; shell tools do not receive plugin-specific root variables.
The model's skill catalog supplies the installed `SKILL.md` path. The root is two
directories above `skills/<name>/SKILL.md`'s containing skill directory.

Verification: an isolated `CODEX_HOME` registered this checkout with
`codex plugin marketplace add <checkout>` and installed with
`codex plugin add rpg-factory@rpg-factory`. It copied into
`$CODEX_HOME/plugins/cache/rpg-factory/rpg-factory/1.4.0`; a real session listed
all 24 namespaced skills there.
The CLI's `plugin add` refreshes local contents even at the same version; restart
existing sessions afterward. `codex exec --dangerously-bypass-hook-trust` was
used only for these vetted temporary probes. Normal installations need hook trust
review before hooks run. Existing Claude command templates use `$ARGUMENTS` and
inline shell expansion; Codex 0.164's install-time command migration skips those
templates, so the Codex manifest intentionally omits `commands`. Run the matching
`scripts/factory-cmd.py` verb explicitly from the resolved plugin root.

Format and behavior references (also checked against real CLI captures):
- https://developers.openai.com/plugins/build/plugins
- https://learn.chatgpt.com/docs/hooks
- https://github.com/openai/codex/blob/rust-v0.164.0/codex-rs/core-plugins/src/manifest.rs
- https://github.com/openai/codex/blob/rust-v0.164.0/codex-rs/core-plugins/src/command_migration.rs
- https://github.com/openai/codex/blob/rust-v0.164.0/codex-rs/core-plugin-common/src/installed.rs
