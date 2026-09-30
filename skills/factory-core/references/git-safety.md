# Git safety

The policy has three layers: the rules below, which you follow; the PreToolUse guard
(`scripts/git-guard.py`, Bash **and** PowerShell), which asks the user (or denies, for tags) when a
command would break them; and the tripwire (`scripts/tripwire.py`), which detects git state changes
the guard could not see (scripts, interpreters) and stops the session. Following the rules means
neither ever fires.

## Rules

1. **Snapshot first.** Paths that are dirty or untracked before your task are the user's
   *baseline*. Do not modify, stage, stash, restore, clean, reset or commit them unless the
   user names them. Example: in the client, modified `Packages/com.gdk.*` submodule pointers,
   untracked `Assets/Samples/...` imports and scratch scenes are the user's work in progress.
2. **Right repo.** The workspace root is not a repo. Run git with `git -C <repo>` or from
   inside the repo, and check the snapshot's repo and branch before acting.
3. **Branch.** Default and protected branches are per repo in `registry.json` `repos.<key>`
   (server/client/Netcode: develop; UnityDots/UIToolkit: main). Commits go to `<type>/<area>/<topic>`
   branches created from an up-to-date default branch (`feat/gateway/redirect-ttl`). A cross-repo
   task uses the **same topic** in every repo (`feat/wire/party` in server, Netcode, client) so
   `factory-status.py` links the legs and can resume them.
4. **Stage explicit paths.** `git add <path>...` only. Never `add -A`, `add .`, `add :/`,
   `commit -a`.
5. **Commit, push, PR, merge only on request; never tag.** Commit messages follow Conventional
   Commits with a lowercase scope (`fix(gateway): ...`). PRs target `develop`, and the repos
   squash-merge. Tags are never created by agents in any repo (`v*`, `sgl-v*`, `core-baseline-*` belong to the lead); skills stop at "ready to tag".
6. **No history rewrites** on shared branches: no force push, rebase of pushed commits,
   amend of pushed commits, or filter-branch.
7. **Generated files only via their generator:**

   | Generated | Generator |
   |---|---|
   | `backend/shared/proto/gen/`, `backend/gameserver-dotnet/GameServer/Net/Generated/` | `backend/shared/proto/generate.sh` (protoc + protoc-gen-go at the CI pins - registry facts) |
   | `Shared.GameLogic/GoldenVectors/*.json` | `GOLDEN_REGEN=1 dotnet test --filter Regenerate` |
   | `Assets/Samples/Netcode/DOTS Sample/` | recopy from com.cuvara.netcode `Samples~/DOTSSample` + `.sample-source` |
   | `Assets/Samples/Cuvara */<version>/` | Unity Package Manager sample import |
   | `**/*.uxml.g.cs` | com.cuvara.uitoolkit UXML codegen |
   | `*.meta`, root `*.csproj` / `*.sln` (client) | Unity Editor |

8. **Never edit** the `Packages/com.gdk.*` submodules, the `unity-build-workflows`
   submodule content, or the gitignored embedded `Packages/com.cuvara.*` clones from the
   client repo. Changes go to their own repos.
9. **Never commit `file:` package paths.** `toggle-packages.sh dev` writes them and leaves
   `packages-lock.json` untouched.
10. **Worktrees.** They're fine for parallel server work (`isolation: "worktree"` for
    subagents). Avoid them for the client, where each worktree needs a multi-GB Unity
    `Library/` import.
11. **Leave the tree as you found it plus your change.** Before reporting, `git status` in
    each touched repo must show exactly the baseline plus your files.

## What the guard does

Inside the workspace (any repo or worktree under it), for Bash and PowerShell. The command is
expanded first: wrappers (`env`, `sudo`, `timeout`, `nohup`, `nice`, `command`, `exec`, `xargs`,
`find -exec`) are peeled, nested shells (`bash/sh -c`, `eval`, `cmd /c`, `powershell -c`) are
parsed recursively, repo git aliases are expanded, and PowerShell is tokenized with its own
quoting (`` ` `` escape, `&` call operator, `git.exe`).

| Command | Decision | Why |
|---|---|---|
| `tag <name>`, `tag -d`, `push --tags/--follow-tags`, pushing tag refs (`refs/tags/*`, `v*`, `sgl-v*`, `core-baseline*`), `gh api .../git/refs\|tags`, `gh release create` | **deny** | agents never tag |
| `reset --hard/--merge/--keep`, `reset <commit>` on a protected branch, `checkout -- <p>` / `checkout .` / `checkout -f`, `restore <p>` (not `--staged`), `switch -f/--discard-changes` | ask | discards work or moves a protected branch |
| `clean -f...` | ask | deletes untracked files |
| `stash` (push/save/pop/drop/clear) | ask | moves or drops uncommitted changes |
| `branch -D`, `branch -f`, `checkout -B`, `switch -C`, `update-ref`, `gc --prune`, `reflog expire`, `prune` | ask | rewrites or drops refs |
| `push` (any; force and delete-ref variants named) | ask | publishes or rewrites remote state |
| `add -A/--all/./:/`, `commit -a` | ask | stages the user's changes |
| `commit`, `merge`, `cherry-pick`, `revert`, `am`, `pull --rebase` on a protected branch (per repo in the registry; a worktree uses its main checkout's list) | ask | protected branch |
| `commit --amend`, `rebase`, `filter-branch/filter-repo` | ask | rewrites history |
| `submodule update/deinit/sync/foreach` | ask | changes submodule checkouts |
| `worktree remove/prune --force` | ask | deletes a worktree with its changes |
| git run through an interpreter one-liner, or a program that is `$VAR` / `$(...)` / backticks | ask | the guard cannot see what runs |
| any command matching `registry.json` `human_gates[].match` (kubectl/helm/k3d/ssh/scp/rsync, `gh workflow run`, `gh pr create/merge`, `kubeconfig.local`/`.env`, `toggle-packages.sh`, `make up/flow-up/reset/down`, `stack.sh up`, `run-clients.sh`, ...) | ask (or the gate's `decision`) | human gate |

The guard ignores quoted text and heredoc bodies (a commit message mentioning `git tag` is fine),
follows `cd <dir> &&` and `git -C <dir>`, knows that `git checkout -b feat/x && git commit`
commits on the new branch, and stays silent outside the workspace. `RPG_FACTORY_GUARD=off`
disables it for a session - never set it yourself.

## Tripwire

- **SessionStart** records a baseline: the user's dirty/untracked files, submodule pointers and a
  sample of dirty files inside submodules (the client's `com.gdk.*`).
- **Pre/PostToolUse** (Bash, PowerShell) compare ref fingerprints (branches, tags,
  remote-tracking refs, stash, HEAD) around every command. Changes are expected only in a repo
  the command visibly ran git in.
- **Violations:** any tag change; ref/HEAD/stash/push changes without a visible git command in
  that repo; a baseline file modified or deleted; a user submodule moved or its dirty files
  changed.
- On a violation the tool result carries **"STOP - rpg-factory tripwire: ..."** and the session is
  latched: the guard denies every non-read-only command.

After a STOP: do nothing else. Do not repair, reset, delete the tag, re-push or "normalise"
anything. Report the message verbatim to the user. Only the user clears the latch
(`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/tripwire.py --ack`) after reviewing the state.

Limits: git run by a background process started earlier, or by another agent runtime, is only
seen at the next command; file edits by Write/Edit tools are not checked against the baseline
until the next Bash/PowerShell call.
