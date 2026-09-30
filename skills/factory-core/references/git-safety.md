# Git safety

The policy has two layers: the rules below, which you follow, and the plugin's PreToolUse
hook (`scripts/git-guard.py`), which asks the user when a command would break them. The
hook is a backstop. Following the rules means it never has to fire.

## Rules

1. **Snapshot first.** Paths that are dirty or untracked before your task are the user's
   *baseline*. Do not modify, stage, stash, restore, clean, reset or commit them unless the
   user names them. Example: in the client, modified `Packages/com.gdk.*` submodule pointers,
   untracked `Assets/Samples/...` imports and scratch scenes are the user's work in progress.
2. **Right repo.** The workspace root is not a repo. Run git with `git -C <repo>` or from
   inside the repo, and check the snapshot's repo and branch before acting.
3. **Branch.** Default branch is `develop` in both repos. Protected branches: develop,
   staging, main, master (server), release-*. Commits go to `type/module/topic` branches
   created from an up-to-date default branch (`feat/gateway/redirect-ttl`).
4. **Stage explicit paths.** `git add <path>...` only. Never `add -A`, `add .`, `add :/`,
   `commit -a`.
5. **Commit, push, PR, merge, tag only on request.** Commit messages follow Conventional
   Commits with a lowercase scope (`fix(gateway): ...`). PRs target `develop`, and the repos
   squash-merge. Tags are never created by agents; `sgl-v*` and `v*` belong to the lead.
6. **No history rewrites** on shared branches: no force push, rebase of pushed commits,
   amend of pushed commits, or filter-branch.
7. **Generated files only via their generator:**

   | Generated | Generator |
   |---|---|
   | `backend/shared/proto/gen/`, `backend/gameserver-dotnet/GameServer/Net/Generated/` | `backend/shared/proto/generate.sh` (protoc 29.3 + protoc-gen-go v1.36.6) |
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

## What the hook asks about

The hook asks inside the workspace (any repo under it) for:

| Command | Why |
|---|---|
| `reset --hard/--merge/--keep`, `checkout -- <p>` / `checkout .` / `checkout -f`, `restore <p>` (not `--staged`), `switch -f/--discard-changes` | discards working-tree changes |
| `clean -f...` | deletes untracked files |
| `stash` (push/save/pop/drop/clear) | moves or drops uncommitted changes |
| `branch -D` | force-deletes a branch |
| `push` (any), plus the force, delete-ref and `--tags` variants | publishes, rewrites or deletes remote state |
| `add -A/--all/./:/`, `commit -a` | stages the user's changes |
| `commit` on develop/staging/main/master/release-* | protected branch |
| `commit --amend`, `rebase`, `filter-branch/filter-repo` | rewrites history |
| `tag <name>` (not `-l`) | release action reserved for the lead |
| `submodule update/deinit/sync/foreach` | changes submodule checkouts |
| `worktree remove/prune --force` | deletes a worktree with uncommitted changes |

The decision is `ask`, never `deny`, and the user stays in control. The hook tokenizes
commands and ignores quoted text and heredoc bodies, so a commit message mentioning
`reset --hard` does not trigger it. It follows `cd <dir> &&` and `git -C <dir>`, and knows
that `git checkout -b feat/x && git commit` commits on the new branch. Outside the workspace
it stays silent. `RPG_FACTORY_GUARD=off` disables it for a session.
