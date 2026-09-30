# Unity-MCP hand-off

This skill decides **what** changes in the Unity project; the client's Unity-MCP skills
(`IndieRPGMMOAdventure/.claude/skills/`: assets-*, gameobject-*, scene-*, prefab, component-*,
tests-run, profiler-*) are **how** Editor-owned files are changed or tests are run. Hand-offs:

| Need | Use | Factory keeps |
|---|---|---|
| create/modify a scene, prefab, ScriptableObject, material, `.meta` | the matching Unity-MCP skill/tool in the open Editor | the human gate `unity-asset-edit` (state asset + change, get a yes), then `git status` of the asset and its `.meta` |
| EditMode/PlayMode tests | `tests-run` via the `ai-game-developer` MCP server | grading: total/passed/failed/skipped per mode; zero executed = FAIL |
| Editor not reachable (snapshot: `unity-mcp` down) | nothing - do not hand-edit YAML | report HUMAN_REQUIRED (Editor closed) |

Factory's hooks do not inspect MCP tool calls (their inputs are tool-specific): the gate above is the
control, so ask before every asset edit.

## Running the Unity Test Runner

If the snapshot shows `unity-mcp` reachable and the session has the client's `ai-game-developer` MCP server, run
the `tests-run` tool with `testMode` EditMode then PlayMode, filtered by `testAssembly` `NDC.Tests.Editor` /
`NDC.Tests.Runtime`. Save open scenes first (dirty scenes abort the run). `unity-mcp-cli` is not installed in WSL;
the tool call is the MCP one. Evidence: total/passed/failed/skipped per mode; zero executed = FAIL. Otherwise
HUMAN_REQUIRED (external) (Editor closed).
