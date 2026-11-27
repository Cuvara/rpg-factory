### Added

- **UnityVFX repo.** The UnityVFX repo (`com.cuvara.vfx`) is registered: `repos.unityvfx` and the engineering
  modules `unityvfx.runtime`, `unityvfx.editor`, `unityvfx.sandbox`, `unityvfx.tests`, `unityvfx.package` and the
  fallback `unityvfx.root`, with `.meta`, asmdef, recipe and package checks, the external checks `sandbox-capture`
  and Unity tests (NOT_RUN or HUMAN_REQUIRED without an editor), and the obligation that a recipe change rebuilds
  its `.vfx` and its capture. Facts record the Sandbox editor, VFX Graph and Sandbox Unity-MCP versions; the dev tool
  `unity-mcp-cli` and the known issues `vfx-graph-internal-api` and `unityvfx-untagged` are added.
  `unity-package` owns the modules and documents the package (scope row and package map).
- **Untagged packages in the status scripts.** `factory-status.py`, `pin-plan.py` and `package-ready.py` know
  `com.cuvara.vfx` and report a package with no tag and no client pin as untagged and unpinned, instead of failing
  or reporting it READY.

### Changed

- **`package-ready.py` refuses an unreleased repo.** A package repo with no `v*` tag is NOT READY unless
  `--first-release` is given, and a repo with no git remote or no `CHANGELOG.md` is NOT READY with that reason
  (before: READY for an untagged repo, a traceback for a missing changelog).
- **`pipeline.no_worktree_markers`** gains `Sandbox~/ProjectSettings/ProjectVersion.txt` (also in
  `skills/delivery/pipeline-defaults.json`), so a package repo with a nested Unity Sandbox project gets no task worktree.
