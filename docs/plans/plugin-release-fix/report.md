# Run report: plugin-release-fix

Fixes for the 1.9 release gate. `tests/run-all.sh --release` on the 1.9.0 merge commit (60d726d) failed 7 of 529
checks on a Windows host with `core.autocrlf=true`; the causes were the plugin's own Windows assumptions, not the
1.9.0 changes. Plan: `docs/plans/plugin-release-fix.json`. Integration branch `plugin-release-fix`, base main 60d726d.

## Outcome

- **frontmatter:** the `description` of `skills/pin-bump/SKILL.md`, `skills/unity-client-tech/SKILL.md` and
  `commands/assetgen.md` had an unquoted colon, so the YAML frontmatter did not parse. Now a quoted string with the
  same text. `claude plugin validate --strict .` and `... .claude-plugin/plugin.json` exit 0 (were 1 at main).
- **crlf-hosts:** `scripts/checks/wire-parity.sh` compared the Wire.cs working-tree files byte for byte; with autocrlf
  the server checkout is CRLF and Netcode LF, so files whose committed blobs are identical (sha256 5d67a41f81db,
  server 633a792, Netcode 406a1b6) reported a drift. It now ignores carriage returns (the working tree is still
  compared, an uncommitted edit still fails) and tests cover both cases. `tests/registry-fragments.test.sh` compares
  the split round trip with CR removed; `tests/art2d-workflow.test.sh` runs `sys.executable` instead of the Store
  stub `python3`. This also fixes `candidate tree checks`.

Of the 7 failures, these four groups are fixed here (6 checks). The seventh, `check runner state model`, needed a
runnable Go: Smart App Control blocked the unsigned `go.exe` until the maintainer turned it off (Go 1.27.4 installed
with winget).

## Sessions and verdicts

Codex was available this run (`RPG_FACTORY_AGENTS=claude,codex`: the maintainer uses an API key, which Orca's account
list does not see). Task leads: Claude Opus 5.5 medium.

| Task | Orca Run | Review | QA |
|---|---|---|---|
| frontmatter | run_3add7e21a9a0 | PASS fa1e41b (codex) | PASS fa1e41b (codex) |
| crlf-hosts | run_9c0b88ad747a | FAIL a85aa6f (claude: the OK line lost 'byte-identical', which the registry parser needs), PASS 8f381c8 (claude; implementers were codex) | PASS 8f381c8 |
| integration:plugin | run_d27e7341bae5 | n/a | see Checks |

## Checks

Integration QA on the final HEAD (workspace-only, `RPG_FACTORY_WORKSPACE` set, `jq`, a real `python3` and `go` on
PATH); the result is the integration verdict note. The release itself is gated by `tests/run-all.sh --release` and
`tests/dogfood.sh --installed` on the merge commit.

## Limitations

- A Codex verify worker's first shell call went through WSL bash (`wsl.exe` on PATH). It ran only read-only git
  commands and `core.worktree` was checked afterwards (unset); the rule in `.claude/CLAUDE.md` still holds.
- `claude plugin validate` prints the non-failing notes LICENSE_MISSING and ICON_MISSING.
- run-all's default workspace `/mnt/c/Workspaces/UnityIndie` does not resolve from Git Bash; checks need
  `RPG_FACTORY_WORKSPACE` set to a Windows path.

### Cost

| Task | Session role | Model | Effort | Tokens / cost | Source |
|---|---|---|---|---|---|
| all tasks | task lead, implementer, reviewer, QA | see Sessions | see Sessions | NOT_AVAILABLE | no usage reported through Orca |
| run lead (total) | run lead | claude-sonnet-5-5 | - | NOT_AVAILABLE | n/a |

## Cleanup

Task worktrees and branches `plugin-release-fix-frontmatter` and `-crlf-hosts` are removed after the PR is merged.
