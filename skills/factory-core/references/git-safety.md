# Git safety

The policy has two layers: the rules below, which you follow, and the PreToolUse guard
(`scripts/git-guard.py`, Bash **and** PowerShell), which flags a command that would break them. Since 1.0.3
the guard is **advisory only**: it never asks the user and never blocks; the command runs and you receive
`rpg-factory advisory (high|warn): <rule>` as context. The rules are yours to keep.

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
5. **Commit, push, PR, merge only on request - except worker commits and task-branch integration inside a
   task the user asked for (`parallel-work.md`); tags and releases only when authorized.** Commit messages
   follow Conventional Commits with a lowercase scope (`fix(gateway): ...`). PRs target `develop`, and the
   repos squash-merge. Inside a delegated task, worker commits on their task branches and merging worker
   branches into the task's integration branch are the lead's decision (`parallel-work.md`); merging into
   protected branches and pushing stay on request. Without explicit release authorization
   from the user in the current task, an agent creates no tag (`v*`, `sgl-v*`, `core-baseline-*`) and publishes no release in
   any repo: skills stop at "ready to tag" with evidence and the lead tags. When the user explicitly
   authorizes a release in the current task, the agent performs exactly the authorized merge, version,
   tag and release steps, after the release checks pass on the commit being tagged. Never move, delete
   or reuse a tag, never publish past a failing check.
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
10. **Worktrees and parallel agents:** `parallel-work.md` (one worktree per task; one Unity
    writer per client project).
11. **Leave the tree as you found it plus your change.** Before reporting, `git status` in
    each touched repo must show exactly the baseline plus your files.
12. **Never stash, reset or clean to get a clean tree.** Run `git status` before anything that can
    move or overwrite changes. To compare with HEAD, export it instead:
    `git -C <repo> archive HEAD | tar -x -C "$tmp"` or `git -C <repo> worktree add --detach "$tmp" HEAD`.
    Never run git hidden inside `wsl -e`, `bash -c '...'` or a script: the guard cannot see it.
13. **A stash is never assumed to be yours.** Other sessions and the user stash too. Inspect it first
    (`git stash list`, `git stash show -p stash@{n}`) and note its SHA (`git rev-parse stash@{n}`)
    before any `apply`/`pop`; never `drop` or `clear`. When a stash is unavoidable, use the visible
    path: `git stash push -m "rpg-factory: <reason>" -- <paths>` (the guard flags it) and note the SHA.
14. **One mutating command per worktree at a time.** Do not run two state-changing commands against
    the same worktree in parallel (or alongside another session working there). Read-only
    investigation (`git status`, `log`, `diff`, `reflog`, `stash list/show`) may run in parallel.

## What the guard does

Inside the workspace (any repo or worktree under it, and a linked worktree outside it - e.g. an Orca worktree -
whose main checkout is in the workspace: that checkout's rules apply), for Bash and PowerShell. The command is
expanded first: wrappers (`env`, `sudo`, `timeout`, `nohup`, `nice`, `command`, `exec`, `xargs`,
`find -exec`) are peeled, nested shells (`bash/sh -c`, `eval`, `cmd /c`, `powershell -c`) are
parsed recursively, repo git aliases are expanded, and PowerShell is tokenized with its own
quoting (`` ` `` escape, `&` call operator, `git.exe`).

| Command | Advisory | Why |
|---|---|---|
| `tag <name>`, `tag -d`, `push --tags/--follow-tags`, pushing or fetching into tag refs (`refs/tags/*`, `v*`, `sgl-v*`, `core-baseline*`) | **high** | release action: only with explicit release authorization (rule 5) |
| `gh release create/upload/edit`, `gh api` REST writes to `/git/tags`, tag refs or `/releases`, `gh api graphql` mutations creating a tag ref or release | **high** | release action: only with explicit release authorization (rule 5) |
| `gh repo delete/archive`, `gh api -X DELETE repos/<o>/<r>` (or the GraphQL equivalents) | **high** | irreversible |
| any other `gh api` write (method from `-X`, else POST when fields/`--input` are given), GraphQL mutations, GraphQL from a file; mutating `gh` verbs (repo edit/rename/sync, secret/variable set, workflow enable/disable, run cancel, pr close/comment/edit, label create...) | warn | remote-only change |
| `reset --hard/--merge/--keep`, `reset <commit>` on a protected branch, `checkout -- <p>` / `checkout .` / `checkout -f`, `restore <p>` (not `--staged`), `switch -f/--discard-changes` | warn | discards work or moves a protected branch |
| `clean -f...` | warn | deletes untracked files |
| `stash` (push/save/pop/drop/clear) | warn | moves or drops uncommitted changes |
| `branch -D`, `branch -f`, `checkout -B`, `switch -C`, `update-ref`, `gc --prune`, `reflog expire`, `prune` | warn | rewrites or drops refs |
| `push` (any; force and delete-ref variants named) | warn | publishes or rewrites remote state |
| `add -A/--all/./:/`, `commit -a` | warn | stages the user's changes |
| `commit`, `merge`, `cherry-pick`, `revert`, `am`, `pull` (`merge`/`pull` unless `--ff-only`) on a protected branch (per repo in the registry; a worktree uses its main checkout's list) | warn | protected branch |
| `branch -m/-d` of a protected branch; `fetch <src>:<dst>` into a local branch (`+` forced or not) | warn | moves or drops a protected/local branch |
| `remote add/set-url/remove/rename`, `config` writes to `alias.*`, `remote.*.url/pushurl`, `url.*.insteadOf`, `core.hooksPath`, `credential.*`; `symbolic-ref` writes | warn | redirects fetch/push or hides what runs |
| `commit --amend`, `rebase`, `filter-branch/filter-repo` | warn | rewrites history |
| `submodule update/deinit/sync/foreach/add/set-url` | warn | changes submodule checkouts or sources |
| `worktree remove/prune --force` | warn | deletes a worktree with its changes |
| git run through an interpreter one-liner, or a program that is `$VAR` / `$(...)` / backticks | warn | the guard cannot see what runs |
| any command matching `registry.json` `human_gates[].match` (kubectl/helm/k3d/ssh/scp/rsync, `gh workflow run`, `gh pr create/merge`, `kubeconfig.local`/`.env`, `toggle-packages.sh`, `make up/flow-up/reset/down`, `stack.sh up`, `run-clients.sh`, ...) | warn (`high` when the gate's `decision` is `deny`); a read-only command (`cat`, `grep`, `sed -n 10,40p`, `git log`) that only names a gated script passes when the gate is `read_only_exempt` (every matching gate except `secrets`) | human gate |

The guard ignores quoted text and heredoc bodies (a commit message mentioning `git tag` is fine),
follows `cd <dir> &&` and `git -C <dir>`, knows that `git checkout -b feat/x && git commit`
commits on the new branch, and stays silent outside the workspace - except `gh` commands that name a
registry repo (`Cuvara/<repo>`), which are checked wherever they run. `RPG_FACTORY_GUARD=off`
disables it for a session - never set it yourself.

Read-only `gh` (view/list/checks/diff/status/search, `gh api` GET, GraphQL queries) always passes.

## File tools and modes

- `scripts/file-guard.py` (PreToolUse `Write|Edit|MultiEdit|NotebookEdit|Read`, workspace only): writes into an
  embedded clone, submodule content, a registry generated path, or secrets get a **warn** advisory; secret reads too.
- The Factory mode declared with `factory-context.sh --mode <m>` is flagged by both guards (advisory, never blocked):
  `analyze`, `plan`, `review` flag writes and mutating commands as **high**; `validate` flags anything but
  `run-checks.py` (and read-only commands).
- Not inspected: MCP tools that write files (Unity-MCP asset/scene tools) - the `unity-asset-edit` gate is the
  control there.

## Limits

Git run by a script file, a background process or another runtime without these hooks is invisible to
the guard; rules 12 and 14 are the control there. Remote-only GitHub changes are controlled only by the
guard. State lives outside the repos (`lib/fstate.py`: scratch under `$TMPDIR` or `/tmp`; evidence under
`~/.local/state/rpg-factory`).
