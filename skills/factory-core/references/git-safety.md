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
12. **Never stash, reset or clean to get a clean tree.** Run `git status` before anything that can
    move or overwrite changes. To compare with HEAD, export it instead:
    `git -C <repo> archive HEAD | tar -x -C "$tmp"` or `git -C <repo> worktree add --detach "$tmp" HEAD`.
    Never run git hidden inside `wsl -e`, `bash -c '...'` or a script: the guard cannot see it and the
    tripwire stops the workspace.
13. **A stash is never assumed to be yours.** Other sessions and the user stash too. Inspect it first
    (`git stash list`, `git stash show -p stash@{n}`) and note its SHA (`git rev-parse stash@{n}`)
    before any `apply`/`pop`; never `drop` or `clear`. When a stash is unavoidable, use the visible,
    auditable path: `git stash push -m "rpg-factory: <reason>" -- <paths>` (the guard asks; the
    tripwire appends it to `audit/<workspace>.jsonl` with the stash SHA before and after).
14. **One mutating command per worktree at a time.** Do not run two state-changing commands against
    the same worktree in parallel (or alongside another session working there). Read-only
    investigation (`git status`, `log`, `diff`, `reflog`, `stash list/show`) may run in parallel.

## What the guard does

Inside the workspace (any repo or worktree under it), for Bash and PowerShell. The command is
expanded first: wrappers (`env`, `sudo`, `timeout`, `nohup`, `nice`, `command`, `exec`, `xargs`,
`find -exec`) are peeled, nested shells (`bash/sh -c`, `eval`, `cmd /c`, `powershell -c`) are
parsed recursively, repo git aliases are expanded, and PowerShell is tokenized with its own
quoting (`` ` `` escape, `&` call operator, `git.exe`).

| Command | Decision | Why |
|---|---|---|
| `tag <name>`, `tag -d`, `push --tags/--follow-tags`, pushing or fetching into tag refs (`refs/tags/*`, `v*`, `sgl-v*`, `core-baseline*`) | **deny** | agents never tag |
| `gh release create/upload/edit`, `gh api` REST writes to `/git/tags`, tag refs or `/releases`, `gh api graphql` mutations creating a tag ref or release | **deny** | agents never tag |
| `gh repo delete/archive`, `gh api -X DELETE repos/<o>/<r>` (or the GraphQL equivalents) | **deny** | irreversible |
| any other `gh api` write (method from `-X`, else POST when fields/`--input` are given), GraphQL mutations, GraphQL from a file; mutating `gh` verbs (repo edit/rename/sync, secret/variable set, workflow enable/disable, run cancel, pr close/comment/edit, label create...) | ask | remote-only change the tripwire cannot see |
| `reset --hard/--merge/--keep`, `reset <commit>` on a protected branch, `checkout -- <p>` / `checkout .` / `checkout -f`, `restore <p>` (not `--staged`), `switch -f/--discard-changes` | ask | discards work or moves a protected branch |
| `clean -f...` | ask | deletes untracked files |
| `stash` (push/save/pop/drop/clear) | ask | moves or drops uncommitted changes |
| `branch -D`, `branch -f`, `checkout -B`, `switch -C`, `update-ref`, `gc --prune`, `reflog expire`, `prune` | ask | rewrites or drops refs |
| `push` (any; force and delete-ref variants named) | ask | publishes or rewrites remote state |
| `add -A/--all/./:/`, `commit -a` | ask | stages the user's changes |
| `commit`, `merge`, `cherry-pick`, `revert`, `am`, `pull` (unless `--ff-only`) on a protected branch (per repo in the registry; a worktree uses its main checkout's list) | ask | protected branch |
| `branch -m/-d` of a protected branch; `fetch <src>:<dst>` into a local branch (`+` forced or not) | ask | moves or drops a protected/local branch |
| `remote add/set-url/remove/rename`, `config` writes to `alias.*`, `remote.*.url/pushurl`, `url.*.insteadOf`, `core.hooksPath`, `credential.*`; `symbolic-ref` writes | ask | redirects fetch/push or hides what runs |
| `commit --amend`, `rebase`, `filter-branch/filter-repo` | ask | rewrites history |
| `submodule update/deinit/sync/foreach/add/set-url` | ask | changes submodule checkouts or sources |
| `worktree remove/prune --force` | ask | deletes a worktree with its changes |
| git run through an interpreter one-liner, or a program that is `$VAR` / `$(...)` / backticks | ask | the guard cannot see what runs |
| any command matching `registry.json` `human_gates[].match` (kubectl/helm/k3d/ssh/scp/rsync, `gh workflow run`, `gh pr create/merge`, `kubeconfig.local`/`.env`, `toggle-packages.sh`, `make up/flow-up/reset/down`, `stack.sh up`, `run-clients.sh`, ...) | ask (or the gate's `decision`) | human gate |

The guard ignores quoted text and heredoc bodies (a commit message mentioning `git tag` is fine),
follows `cd <dir> &&` and `git -C <dir>`, knows that `git checkout -b feat/x && git commit`
commits on the new branch, and stays silent outside the workspace - except `gh` commands that name a
registry repo (`Cuvara/<repo>`), which are checked wherever they run. `RPG_FACTORY_GUARD=off`
disables it for a session - never set it yourself.

Read-only `gh` (view/list/checks/diff/status/search, `gh api` GET, GraphQL queries) always passes.

## File tools and modes

- `scripts/file-guard.py` (PreToolUse `Write|Edit|MultiEdit|NotebookEdit|Read`, workspace only): writes into an
  embedded clone, submodule content, a registry generated path, a file that was already dirty/untracked when
  the session started, or secrets **ask**; secret reads ask; writes while latched are **denied**.
- The Factory mode declared with `factory-context.sh --mode <m>` is enforced by both guards: `analyze`, `plan`,
  `review` deny writes and mutating commands; `validate` allows only `run-checks.py` (and read-only commands).
- Not inspected: MCP tools that write files (Unity-MCP asset/scene tools) - the `unity-asset-edit` gate is the
  control there.

## Tripwire

- **SessionStart** records a baseline: the user's dirty/untracked files, submodule pointers, a
  sample of dirty files inside submodules (the client's `com.gdk.*`) and inside embedded clones
  (`Packages/com.cuvara.*`, compared before/after each command so the user's own edits in Unity are
  not flagged).
- **Pre/PostToolUse** (Bash, PowerShell) compare ref fingerprints (branches, tags,
  remote-tracking refs, stash, HEAD) around every command. Each tool call has its own snapshot
  (`pre-<tool_use_id>.json`); a denied call's snapshot is never compared by a later command and is
  pruned after 2 h. Changes are expected only in a repo the command visibly ran git in, or when another
  session's (or a parallel call's) *completed* command saw the same ref reach the same value through git
  subcommands that make that kind of change (its own checked-out branch for `commit`/`reset`/..., new
  branches for `branch`/`switch -c`, remote-tracking refs for `fetch`/`push`, `refs/stash` for `stash`).
  Failing commands are checked too (PostToolUseFailure).
- **Violations:** any tag change (never explained by anyone's git); ref/HEAD/stash/push changes
  without a visible git command in that repo; a baseline file modified or deleted; a user submodule
  moved or its dirty files changed. A visible `git stash` is not a violation; it is appended to the
  stash audit.
- On a violation the tool result carries **"STOP - rpg-factory tripwire ... (event <id>)"**, an event
  file is written (command, session, tool call id, ref values before/after, recovery hints) and the
  **workspace** is latched: every non-read-only command and file write is denied - in every session
  and worktree of the workspace (a crash does not clear it; SessionStart reports it) - until the user
  acknowledges. A second incident is a second event; nothing overwrites another session's evidence.

After a STOP: do nothing else. Do not repair, reset, stash, drop, delete the tag, re-push or
"normalise" anything. The change may come from another session, a background job or the user, not
your command. Recovery:

1. Report the STOP verbatim and run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/tripwire.py --status`
   (read-only): open events with the command, the old and new SHA of every changed ref and recovery
   hints (`stash show -p <sha>`, `reflog show <ref>`).
2. Investigate read-only (`git status`, `log`, `reflog`, `stash list`, `stash show -p`, `branch --list`
   stay allowed while latched). Restoring anything (`git stash apply <sha>`, a rescue branch) is the
   user's decision - an event's old SHA stays reachable until `git gc`.
3. The user acknowledges with the command the STOP prints (quoted, forward slashes):
   `! python3 "<plugin root>/scripts/tripwire.py" --ack` (all events open at that moment) or
   `--ack <event-id>` (one). It reports `latch is now CLEAR` (exit 0) or `still LATCHED: <ids>` /
   `NOT cleared: ...` (exit 1); repeating it is safe. Events are archived to `acked/`, never deleted.
   The guard denies `--ack` to the agent at all times.

Limits: git run by a background process, or by another runtime without these hooks, is attributed to
whichever command's window it lands in (a STOP, never a silent pass); so is another session's command
that has not finished when this one's PostToolUse runs. A hidden change to exactly the ref a concurrent
visible git command could make (for example a script moving the branch another session is committing on)
is attributed to that command, as it always was within one command. Remote-only GitHub changes are invisible to it
(the guard is the only control). State lives outside the repos (`lib/fstate.py`: scratch under
`$TMPDIR` or `/tmp`; events, audit and evidence under `~/.local/state/rpg-factory`).
