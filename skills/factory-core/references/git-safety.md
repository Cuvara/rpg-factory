# Git safety

The policy has two layers: the rules below, which you follow, and the plugin's PreToolUse
hook (`scripts/git-guard.py`), which asks the user (or denies, for tags) when a command would break them. The
hook is a backstop. Following the rules means it never has to fire.

## Rules

1. **Snapshot first.** Paths that are dirty or untracked before your task are the user's
   *baseline*. Do not modify, stage, stash, restore, clean, reset or commit them unless the
   user names them. Example: in the client, modified `Packages/com.gdk.*` submodule pointers,
   untracked `Assets/Samples/...` imports and scratch scenes are the user's work in progress.
2. **Right repo.** The workspace root is not a repo. Run git with `git -C <repo>` or from
   inside the repo, and check the snapshot's repo and branch before acting.
3. **Branch.** Default and protected branches are per repo in `registry.json` `repos.<key>`
   (server/client/Netcode: develop; UnityDots/UIToolkit: main). Commits go to `type/module/topic`
   branches created from an up-to-date default branch (`feat/gateway/redirect-ttl`).
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

## What the hook does

Inside the workspace (any repo under it), per command segment:

| Command | Decision | Why |
|---|---|---|
| `tag <name>`, `tag -d`, `push --tags/--follow-tags`, pushing `refs/tags/*` / `v*` / `sgl-v*` / `core-baseline*` refs | **deny** | agents never tag |
| `reset --hard/--merge/--keep`, `checkout -- <p>` / `checkout .` / `checkout -f`, `restore <p>` (not `--staged`), `switch -f/--discard-changes` | ask | discards working-tree changes |
| `clean -f...` | ask | deletes untracked files |
| `stash` (push/save/pop/drop/clear) | ask | moves or drops uncommitted changes |
| `branch -D` | ask | force-deletes a branch |
| `push` (any; force and delete-ref variants named) | ask | publishes or rewrites remote state |
| `add -A/--all/./:/`, `commit -a` | ask | stages the user's changes |
| `commit` on a protected branch (per repo in the registry: server/client develop, staging, main; Netcode develop, main, release/*, sync-main/*; UnityDots/UIToolkit main, develop) | ask | protected branch |
| `commit --amend`, `rebase`, `filter-branch/filter-repo` | ask | rewrites history |
| `submodule update/deinit/sync/foreach` | ask | changes submodule checkouts |
| `worktree remove/prune --force` | ask | deletes a worktree with its changes |
| any command matching `registry.json` `human_gates[].match` (kubectl/helm/k3d/ssh/scp/rsync, `gh workflow run`, `gh pr create/merge`, `gh release create`, `kubeconfig.local`/`.env`, `toggle-packages.sh`, `make up/flow-up/reset/down`, `stack.sh up`, `run-clients.sh`) | ask (or the gate's `decision`) | human gate |

The hook ignores quoted text and heredoc bodies (a commit message mentioning `git tag` is fine),
follows `cd <dir> &&` and `git -C <dir>`, knows that `git checkout -b feat/x && git commit`
commits on the new branch, and stays silent outside the workspace. `RPG_FACTORY_GUARD=off`
disables it for a session - never set it yourself.
