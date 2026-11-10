# Plugin review checklist

Review checklist for a change to the rpg-factory plugin repo itself. A plugin task has no routed lead skill, so a reviewer uses this file.
Each item names its source: a rule in `.claude/CLAUDE.md` or the test or script that enforces it.

- Behaviour change has a fragment `changelog.d/<topic>.md`, and `CHANGELOG.md` `[Unreleased]` stays empty (`scripts/changelog.py check`, run-all, CLAUDE.md "Rules for changing this repo").
- Behaviour change has a test in `tests/`; a routing change has a scenario in `tests/routing.test.sh` (CLAUDE.md "Rules for changing this repo").
- `registry.json` is the build of `registry/`: edit the fragments, never the output (`python3 -B scripts/build-registry.py --check`, run-all).
- No bare `bash` in a subprocess call: use `find_bash()` from `scripts/lib/shells.py` (`tests/compat.test.sh`, CLAUDE.md "Git Bash, never WSL, on Windows").
- A new executable script gets its bit with `git update-index --chmod=+x <file>`, because `chmod +x` does not set it on Windows (CLAUDE.md "Operating lessons").
- Hooks never block and never crash: every `hooks/hooks.json` command ends with `; exit 0`, and a hook emits `additionalContext` advisories only, never `permissionDecision` (CLAUDE.md "Rules for changing this repo"; `tests/git-guard.test.sh`, `tests/file-guard.test.sh`).
- Read-only scripts (`scripts/factory-context.sh`, `scripts/factory-status.py`, `scripts/checks/`) write nothing into a product repo and fetch nothing (CLAUDE.md "Rules for changing this repo", `scripts/lib/procrun.py` pollution check).
- State paths go through `scripts/lib/fstate.py`, never `$TMPDIR` or a relative path (CLAUDE.md "Rules for changing this repo").
- English only, in code, comments, docs, changelog and commit messages (`scripts/checks/english-only.py`, `tests/english-only.test.sh`).
- A skill `path:line` citation names the symbol it shows and passes `python3 -B scripts/checks/skill-citations.py` (CLAUDE.md "Rules for changing this repo").
- No machine-specific absolute path (a user home, the drive letter of one machine) in docs or plans (`tests/parallel-policy.test.sh`, check "docs/plans contains no machine-specific absolute paths").
