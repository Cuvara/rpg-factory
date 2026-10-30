# Validation

Factory Core **discovers** the checks (registry + context script) and **runs and grades** them
with `scripts/run-checks.py`. The runner's table and evidence JSON are the validation record;
the agent never writes a state itself.

## Running checks

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/run-checks.py" --repo server --paths backend/gateway/redirect.go
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/run-checks.py" --repo server --paths ... --dry-run      # list only
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/run-checks.py" --repo server --paths ... --approve integration-e2e
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/run-checks.py" --repo server --paths ... --json         # machine record
```

- Use `--paths` with the files *you* changed. Without it the runner resolves the whole working
  tree, which includes the user's pre-existing changes.
- Run it from inside your worktree: the runner targets the git toplevel of the cwd (or `--repo-path <worktree>`), so
  checks and their evidence describe your tree. Only a cwd outside every worktree of the repo falls back to the
  registry's canonical checkout, and the output then prints a `NOTE:` saying so. When a run targets a worktree, a
  `runner/canonical-checkout-guard` row compares the canonical checkout's status (tracked, untracked, ignored) before
  and after; a FAIL there means a check wrote into the user's protected checkout - remove the files and fix the check.
  Checks run with `PYTHONDONTWRITEBYTECODE=1` and `PYTHONPYCACHEPREFIX=<scratch>`, so no `.pyc` is written in a checkout.
- The list covers touched modules and their dependents; identical commands run once; the second check
  is graded on the shared output with its own definition (reason "output shared").
- `--tier fast` (default) runs fast checks and reports extended/external ones as HUMAN_REQUIRED.
  `--approve <id>` runs a named extended check after the user agreed. `--only <id>` narrows.
- Each check is graded by its registry `parser` (`go-test`, `dotnet-test`, `exit`,
  `regex:<pattern>`); `needs` makes a check BLOCKED unless its prerequisite PASSes in the same run (failed, skipped or listed after it: BLOCKED).
- Each executed check is compared with its own pre-run snapshot. Changes to already-dirty files
  and newly untracked files are FAIL pollution attributed to the check that made them. Gitignored
  outputs are outside this Git-status based check. On Windows Git Bash is selected when installed;
  otherwise the selected bash runtime is probed once. Timed out checks are killed in a Windows Job
  Object or POSIX process group, and cleanup is verified before it can be reported as successful.
  A timeout is always FAIL; cleanup errors appear in the reason.
- Every check receives `RPG_FACTORY_WORKSPACE`, `RPG_FACTORY_REPO_DIR`, `RPG_FACTORY_REPO_KEY`,
  and `RPG_FACTORY_HEAD`. WSL bash uses `wslpath` plus `WSLENV` for those values and
  `PYTHONDONTWRITEBYTECODE`; the runner verifies they arrived. Git Bash uses forward slash drive
  paths (`C:/...`). If translation or the WSL environment contract fails, the check is BLOCKED.
- Every executed check is stored with the **identity of the tree it ran on** (HEAD, diff and untracked
  files in the check's directory, check definition) and its full log, under
  `~/.local/state/rpg-factory/evidence/`. Cite the log path; the table carries the summary.
- `run-checks.py ... --status` grades the declared checks against the current tree **without running
  anything**: the stored state when nothing changed, **STALE** after any change, **NOT_RUN** when never
  executed. Run it before reporting: a PASS from before your last edit is not evidence.
- Exit 1 when any fast check is not PASS or anything FAILed.

## Factory check scripts (read-only against product repos)

| Script | Answers |
|---|---|
| `scripts/checks/pin-status.py [--remote] [--json]` | every client git-URL pin: manifest == lock, tag exists upstream, newer tags, `.sample-source` agreement |
| `scripts/checks/pin-plan.py <package> <tag> [--client-ref REF]` | exact manifest/lock edits (hash = tag commit), upstream dependency changes, DOTS Sample recopy files |
| `scripts/checks/wire-parity.sh` | Netcode `Wire.cs` byte-identical to the server binding; protocol version equal in C#, Go, Netcode |
| `scripts/checks/netcode-headless.sh` | runs Netcode's headless dotnet tests from a temp copy (Netcode has no .gitignore) and prints .trx counters |
| `scripts/checks/package-ready.py <pkg-dir>` | release readiness of a package repo -> "READY to tag vX.Y.Z" or the exact reasons |
| `scripts/checks/unity-package-pins.py <client>` | local mirror of client CI 02-package-pins step 1 + no `file:` pins |

Product-repo scripts are run with `PYTHONDONTWRITEBYTECODE=1` (UnityDots tracks `__pycache__`).

## Tiers

- **fast** - vet / test / build / cheap static checks. Always run by the runner.
- **extended** - integration E2E, AOT publish, proto regeneration, golden-vector regeneration.
  Required when the `trigger` applies. Ask the user, then `--approve <id>`; otherwise it stays
  HUMAN_REQUIRED and the report names the trigger.
- **external** - Unity Test Runner, GitHub CI, Docker stack, deploy pipeline. Always
  HUMAN_REQUIRED from the runner; report what is needed (Editor open, PR opened, stack up).

## Result states (run-checks.py)

| State | Meaning | Done? |
|---|---|---|
| `PASS` | Ran, exit 0, parser evidence found (tests executed > 0, expected line present), no pollution | yes |
| `FAIL` | Ran and failed; or exit 0 with no evidence (0 tests, all skipped); or left files in the repo | no |
| `BLOCKED` | A `needs` prerequisite did not PASS in this run (failed, skipped or not run before it), or the check's directory is missing | no |
| `NOT_AVAILABLE` | A required tool is not resolved on this machine | no - say so |
| `HUMAN_REQUIRED` | Extended check not approved, or an external environment | open item |
| `SKIPPED` | Excluded on purpose (`--only`, `--tier`, `--dry-run`) | n/a |
| `NOT_RUN` | (`--status`) declared for this change, never executed | no |
| `STALE` | (`--status`) executed, but the tree or the check changed since | no - rerun |

No registered check for the touched modules is reported as "none registered", not as PASS.

Engineering tool evidence, WSL environment notes and CI coverage facts: see [engineering.md](engineering.md).
