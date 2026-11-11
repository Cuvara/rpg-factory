# Changelog

All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [1.8.0] - 2026-11-11

Slimmer task workflow (CLAUDE.md and delivery.md split, tier XS, base health, run-report loop), lean QA, in-session subagent rules and generic delivery skill.

### Added

- **Pipeline known failures.** A plan may list `known_failing` (`[{check, reason}]`) for checks that already fail at the
  task base. `validate` warns per entry and rejects malformed ones. The task-lead, task QA and integration QA specs carry
  the list with the rule: a failure of a listed check that also fails at the base is `FAIL_AT_BASE` (named on the QA
  report, not a task FAIL), and a listed check that now passes is reported as fixed. `dispatch --phase lead` prints a
  base health hint (`gh run list --branch <base> --limit 1`, print only) for a repo with a GitHub remote.
  `templates/pipeline/qa-report.md` gains `Failing at base` and `Fixed` lines.
- **Tests.** `tests/delivery-generic.test.sh` keeps delivery.md at most 32768 bytes and the Orca lineage command only
  in section 4 "Orca visibility".
- **Doctor.** `/rpg-factory:doctor` reports the Codex subagent setup (dev tool `codex-subagents`, probe
  `codex:subagents`; used by `delivery`, so the routed snapshot does not list it): `codex features list` must show `multi_agent` on, and `agents.default_subagent_model` and
  `agents.subagent.model` of the Codex config (`CODEX_HOME` or `~/.codex/config.toml`) must be inside
  `pipeline.models.scope.codex`. Otherwise it is a WARN line that names the fix (`[agents] default_subagent_model` =
  the `pipeline.subagents` Codex model). Only those two keys are read, a value that is not a model id is never shown,
  and the config is never written.
- **Dispatch.** No Orca dispatch change: `orca worker-start` and `orca agent launch` take no Codex `-c` config
  override, so the subagent model stays a Codex config setting that doctor checks.
- **Agents.** New read-only plugin agent `factory-explorer` (`agents/factory-explorer.md`): a code locator for Factory
  sessions that returns a `path:line` table and a short conclusion (at most 200 words). Tools are limited to Read, Grep,
  Glob and Bash, the model is `sonnet`, and it never edits files, runs git writes, calls Orca or the pipeline dispatch
  and verdict, or spawns agents.
- **Delivery.** New skill `rpg-factory:delivery`, usable in any repository or workspace: the two-level flow (run lead,
  task leads, short sub-sessions), agent routing with model fallback, cross-model review, child worktrees, session
  release, Orca waiting, QA tiers and the plan/verdict/gate pipeline. Its reference
  `skills/delivery/references/delivery.md` is the single copy of the generic policy; factory-core loads it for its
  delivery steps. README gives a one-line pointer for `~/.claude/CLAUDE.md` and Codex `AGENTS.md`.
- **Pipeline.** `factory-pipeline.py` runs without the RPG registry: with `--registry none`, `RPG_FACTORY_PIPELINE_REGISTRY=none`
  (a pipeline-only variable) or a missing registry file it reads `skills/delivery/pipeline-defaults.json`, and every command
  it prints for a next session (task-lead spec, planner spec, `status` next lines) carries `--registry none`.
  The installed plugin always ships `registry.json`, so there the flag or the variable selects the defaults. A plan may set `no_worktree_markers`
  to replace the default markers. `tests/delivery-generic.test.sh` covers tier, validate, dispatch, verdict and gate
  on a throwaway repo outside any workspace.
- **Plugin review.** Point plugin repository reviewers to the plugin-specific checklist.
- **Case selection in the slow suites.** `tests/pipeline.test.sh`, `tests/parallel-policy.test.sh`, `tests/routing.test.sh`
  and `tests/git-guard.test.sh` accept `--case NAMES` (alias `--only`; comma list, repeatable), `--list-cases` and
  `-h|--help`. `--help` prints the usage and exits 0; an unknown argument or case name exits 2 before any fixture or
  run starts. No selector still runs every case.
- **Case maps.** A suite declares which changed files cover which case with `# case-map: <case> <path-or-glob>...`
  header lines. `tests/affected.py cases FILE SUITE...` prints each selected suite with its affected cases, or `ALL`
  when the suite has no (or an invalid) map, the suite itself or a global input changed, or a selecting file is not
  in the map. `tests/run-all.sh --affected` passes `--case A,B` to such a suite and names the cases in the result
  line, so task QA runs only the cases a change can break. An explicit `--only-suites` name still runs all its cases,
  and a case subset never writes a suite PASS record (a full-suite PASS record can still satisfy a subset).
- **Machine-wide test-run slots.** `tests/run-all.sh --affected` and `--only-suites` runs take one of
  `RPG_FACTORY_TEST_SLOTS` slots (default 2, `0` disables the cap, a non-integer exits 2) under the persistent state
  directory (`locks/run-all-slots/<n>`). When every slot is busy the run prints `run-all: waiting for a test slot`
  with the holders and queues, `--no-wait` exits 3 instead, and a slot whose holder died is taken over
  (`run-all: taking over stale test slot`). Parallel sessions now queue instead of slowing every suite 2-4x. Full
  runs keep their own lock.
- **Orca visibility for task worktrees.** A worktree made with `git worktree add --no-track` has no Orca lineage and
  lands in Orca's hidden section. `factory-pipeline.py dispatch --phase lead` (and every place that prints a worktree
  creation) now prints `orca worktree set --worktree path:<dir> --parent-worktree path:<parent> --display-name
  <topic>-<task> --workspace-status in-progress` before `orca agent launch`, with the integration (else main) checkout
  as parent; a child worktree a task lead makes gets the task worktree as parent. Documented in `delivery.md` section 4
  ("Orca visibility"); `tests/pipeline.test.sh` asserts the line and `tests/parallel-policy.test.sh` has a mutation case.
- **Routing scenarios** in `tests/routing.test.sh`: the generic `delivery` skill is never routed as lead or co-lead,
  neither for an unrelated path nor for its own `delivery.md`.
- **Delivery.** The run report (`delivery.md` section 8) gets a "Cost" table, one row per session plus the run lead's
  total, filled from what the runtime shows and `NOT_AVAILABLE` when unmeasured (an estimate is never presented as
  measured). In the integration commit the report's limitations and follow-ups go to the project's backlog, one topic
  each, and every new operating lesson to the file the project's learning-loop rule names.
- **Operating lesson.** `.claude/CLAUDE.md` says never to stop a process by pattern (`pkill -f <name>`): a worker that
  did so to stop its own duplicate skills-lint run may have killed other sessions' runs. Stop only the PID you started.
- **Delivery.** `skills/delivery/references/delivery.md` section 8 has a new subsection "In-session subagents": a
  subagent is a read-only scout, never a writer, a review or a QA verdict. It holds the per-role table (access, when,
  max parallel, limits; the data lives in registry `pipeline.subagents`), the default subagent model (Claude Sonnet 5.5
  through `rpg-factory:factory-explorer`; Codex uses the `pipeline.subagents` codex model) and the general rules. The
  canonical sentence sits under the marker `policy:subagents-read-only`, and `tests/parallel-policy.test.sh` checks
  it (marker deleted, duplicated or changed).
- **Pipeline.** Every session prompt `scripts/factory-pipeline.py` prints now carries one line with its role's subagent
  rule, read from the registry `pipeline.subagents` through `scripts/lib/subagent_policy.py` `rule(reg, role, agent)`:
  the planner, the task lead (a new rule 7; the push rule is now rule 8), implementation sessions (shared and child),
  review (the reviewer's own model, the verdict stays the reviewer's) and task and integration QA (no subagents). The
  rule names the agent that actually runs the session: with `--runner agent` that is Claude, so a Codex review turned
  into a Claude SAME_MODEL review names Claude's Sonnet alias. A registry without `pipeline.subagents` exits 1 with
  nothing dispatched.
- **Registry.** New `pipeline.subagents` policy: per role (run_lead, planner, lead, implement, review, qa) the subagent
  access (`none|read`), `max_parallel` and the one situation that justifies a subagent, plus the forbidden actions and
  the subagent model per agent. The default subagent model is Claude Sonnet 5.5 (`claude-sonnet-5-5`, alias `sonnet`,
  agent `rpg-factory:factory-explorer`); Codex uses `gpt-6.1-terra` at effort `medium`. `scripts/lib/subagent_policy.py`
  `rule(reg, role, agent)` turns one entry into the sentence a dispatch prompt carries.
- **Checks.** `scripts/check-registry.sh` fails when a subagent model or effort is outside `pipeline.models.scope`, or a
  Claude alias is not the `pipeline.models.agent_tool_alias` of its model. New suite `tests/subagent-policy.test.py`
  covers the rule text per role and agent, the missing block and the scope failures. The suite runs `check-registry.sh`
  through the Git Bash resolver (`scripts/lib/shells.py`), so it also runs on Windows.
- **Pipeline.** Tier XS for a tiny prose-only change (registry `pipeline.tiers.XS`: every path prose, at most 3 files
  and 40 changed lines, no contract or generated path). `tier` prints `Tier: XS` when it applies and `above XS:` with
  the reasons otherwise (`tier --plan` counts the changed lines of the checkout). `validate` accepts a one-task XS plan
  and rejects a path that is not prose, a second task or too many paths. `dispatch --phase lead` on an XS task starts
  no task lead: it prints the run lead's own steps (edit and commit on the plan topic branch, one cross-model review,
  the task tier command, the `tier XS: lead ran task suites` QA verdict, gate); `--phase implement` is refused. Its
  review reads the topic checkout and pairs against the run lead's model. The gate accepts the XS review plus the
  lead-run QA and blocks when the committed diff is above the XS thresholds.

### Changed

- **Delivery.** `skills/delivery/references/delivery.md` states each rule once and shrinks from 57813 bytes (main with
  the single verify flow) to 32727 bytes (the Orca lineage lesson lives only in section 4 "Orca visibility"; session
  release, "sub-sessions never commit" and the one-full-run-per-machine rule are stated once). The verdict, verify,
  fallback and model CLI details moved to `docs/pipeline-cli.md`, the tier command details of this repo to
  `tests/README.md`. `skills/delivery/SKILL.md` and `skills/factory-core/SKILL.md` point to delivery.md section 10
  instead of restating the flow steps. delivery.md now states that a plan task carries a `kind` for the "Which model"
  routing, and that the integration checkout itself gets the main checkout as its Orca lineage parent.
- **Policy.** `skills/factory-core/references/parallel-work.md` keeps only the UnityIndie specifics (Unity no-worktree
  repos, the `unity-test` resource, registry repos, human gates and release rules) and points to `delivery.md`.
  Dispatch specs cite `references/delivery.md`.
- **Pipeline prompts.** Direct implementation, review and QA workers to their complete specs and consult delivery policy only when blocked.
- **`tests/pipeline.test.sh` is faster.** The multi-wave fixture repositories are built once per run as templates and
  copied per case, independent cases run as parallel child runs (`PIPELINE_TEST_UNITS`, default 4) whose output is
  printed in case order, and the assertion helpers match in bash instead of forking a subshell and `grep` per check
  (`PIPELINE_TEST_MATCH=check` compares both); `PIPELINE_TEST_TIMES=1` prints each section's wall time. On a loaded
  machine the full run (710 assertions) went from 59m51s to 14m12s, and `--case validate` (12 assertions) takes 17 s.
- **One verify session per task.** A task is reviewed and tested once, after every subtask is committed. New
  `factory-pipeline.py dispatch --phase verify --sha <sha>` starts one fresh session of the reviewing model: it reviews
  the diff first (a blocking finding is a FAIL and no test runs), then runs the task tier command once. After a FAIL and
  a fix, one fresh re-verify session reviews the fix delta and reruns the failed suites plus what the fix touched.
  `verdict --phase verify` records the review and QA verdicts of the SHA. `--phase review` and `--phase qa` stay for a
  lead that needs only one of them, for example integration QA. `status` names `--phase verify` after the last subtask.
- **Implementers run no suites.** An implementation spec asks for a syntax check of the edited files only. `validate`
  warns when a task's `checks` would make an implementer run a suite.
- **No per-subtask review.** The gate no longer blocks on a subtask review. A prose subtask written by the reviewer's
  model is covered by the verify review. A code subtask written by the reviewer's model is printed as an accepted
  `SAME_MODEL (single verify)` note.
- **Leads do not re-run checks.** The task lead and the run lead read the verify report. The run lead keeps only the
  integration QA and CI.
- **Narrower selection.** `tests/run-all.sh` and `tests/affected.py` are no longer global inputs of
  `tests/affected.py`. A runner change selects `tests/run-all-parallel.test.sh` and `tests/affected.test.sh`, and a
  change to `tests/affected.py` selects `tests/affected.test.sh`. CI still runs every suite.
- **Policy.** `delivery.md` sections 1, 6 and 10 and the QA tiers table describe the single verify flow (new
  `policy:single-verify` marker). `parallel-work.md`, `.claude/CLAUDE.md` and the `delivery` skill point to it.
  `tests/parallel-policy.test.sh` checks the new table rows and that the rule has one copy.
- **`dispatch --phase qa` prints the case list.** The QA spec names the exact cases `tests/affected.py` selects for the
  candidate, so task QA runs only the cases a change can break.
- **`dispatch --phase implement` forbids whole slow suites.** An implementer runs only the targeted checks of its spec
  and, in a suite with cases, only the cases its change touches (`--case`).
- **Lead QA for tier S and docs-only tasks.** Those tasks get the task lead's own QA verdict instead of a QA session.
- **QA tiers carry typical times, and the test-run slot rule replaces the "at most 2 full runs" lesson.** `delivery.md`
  section 10 and `.claude/CLAUDE.md` describe the machine-wide test slots (`RPG_FACTORY_TEST_SLOTS`, default 2): a busy
  machine queues targeted runs instead of slowing every suite 2-4x, and a QA worker's background run is stopped before
  the worker is abandoned. `parallel-work.md` keeps only the RPG slot names and case selection.
- **Repository guidance.** Slimmed `.claude/CLAUDE.md` from 23 KB to about 8 KB; moved architecture to `docs/architecture/overview.md`, the release procedure to `docs/releasing.md`, and the full command list to the `Commands` section of `scripts/README.md`. Skill touchpoints now read the Skills paragraph from the architecture overview.

### Fixed

- **Tests.** `tests/delivery-generic.test.sh` expected key set now includes `subagents`, as `pipeline-defaults.json`
  has. The `tests/parallel-policy.test.sh` "rule moved out of section 5" mutation ends its range at the Orca-first
  rule again instead of deleting to the end of the file.
- **Delivery pointers.** The delivery and factory-core skills now state the tier XS exception (no task lead, the run lead edits the files) next to the "every tier gets a task lead" rule. Stale pointers that named `parallel-work.md` for delivery policy now point to `delivery.md` (section 5, section 10 "Model choice") or `docs/pipeline-cli.md`, and the full command list is pointed to `scripts/README.md` "Commands". `tests/orca-commands.test.sh` also checks the Orca commands cited in `docs/pipeline-cli.md`. `tests/affected.py` runs `tests/delivery-generic.test.sh` for a change to `skills/delivery/references/delivery.md`, so its size cap is no longer missed by task QA.
- **Pipeline: gate after a topic sync into a task branch.** A task branch that merged the topic (after the topic took a
  default-branch merge through another task) no longer makes earlier tasks' reviews STALE. Only that sync merge's own
  conflict resolutions count; the merging task's current review covers them when it owns the path and depends on the
  earlier task. A real post-review edit on the topic or in a task branch stays STALE.
- **Pipeline: cleanup.** `cleanup` reports a leftover task directory (empty or not), an Orca record of a removed worktree and a prunable git worktree record as LEFTOVER, never CLEAN, with `git worktree prune` and `orca worktree rm --worktree path:<dir>`; a plain git task worktree is removed with `git worktree remove` (no `--force`). Before a removal it names the Orca terminals still bound to the worktree and asks the task lead to confirm each released worker's CLI exited. A directory Windows reports busy is named to the user (PID, command) and never killed. `delivery.md` section 8 records these cleanup rules; section 4 names `orca worktree set` as the only lineage step, never `orca worktree create`.
- **Pipeline: gate after a default-branch merge.** `gate` no longer marks a review STALE when its owned paths have the same content as at the reviewed commit, or when the changes arrived through a merge of the default branch (only that merge's own conflict resolutions count); a real later change still makes it STALE. The plan file and its `report.md` belong to the run lead and are never listed as changes outside every task's owned paths.
- **Tests: affected.** `tests/affected.py` maps `agents/*` to `tests/skills-lint.sh`, so `run-all --affected` and suite reuse no longer skip the agent lint when only an agent file changes.
- **Docs: README.** The doctor row lists the dev-tool state WARN next to OK / DOWN / MISSING.
- **`tests/parallel-policy.test.sh` and `tests/orca-commands.test.sh` read the single policy copy.** After the generic
  policy moved to `skills/delivery/references/delivery.md` they still read `parallel-work.md` and failed; they now check
  `delivery.md` and keep their mutation and command checks.
- **Moved CLAUDE.md sections.** `skill-author`, `README.md` and `docs/dogfood.md` point to `docs/releasing.md` and
  `docs/architecture/overview.md` instead of sections that moved; `docs/architecture/README.md` lists `overview.md`.
  `tests/affected.py` maps `docs/architecture/overview.md` to the `new-skill` suite and `tests/run-all.sh` reads
  `docs/releasing.md` in the release policy check.
- **Tests.** The marker, which-model, qa-tiers and Orca-first checks in `tests/parallel-policy.test.sh` now read
  `skills/delivery/references/delivery.md`, where the generic policy moved; the lint-driven mutations stay on
  `parallel-work.md`.
- **Tests.** `tests/orca-commands.test.sh` reads the cited Orca commands, the child placements and the "also deletes
  the checked-out local branch" caveat from `skills/delivery/references/delivery.md`, where split commit 9d21098
  moved them, and still checks the commands `parallel-work.md` cites.
- **Delivery.** `delivery.md` is back under its 32 KiB size cap (`tests/delivery-generic.test.sh`).

## [1.7.0] - 2026-11-09

Agent routing between Claude and Codex with availability fallback, QA tiers (full-run lock, suite reuse, narrower --affected), CI as the full-suite gate with run-all --workspace-only, worker stall detection, multi-wave gate attribution and post-merge cleanup.

### Added

- Route pipeline implementation, planning, review and QA by task kind and available models, with per-run MODEL_UNAVAILABLE marks and automatic SAME_MODEL fallback reviews. A subtask needs an implementer or a kind; routing honors the registry routing defaults and candidate agents, and detects Orca account availability with UTF-8 output. `validate` does not probe availability, and the planner reads no per-run MODEL_UNAVAILABLE marks.
- Record the model `dispatch --phase implement` started per task and subtask; review, QA, `verdict` and the gate pair against that record (else the planned routing), never current availability, so a model that returns after a fallback does not review its own work as cross-model.
- `verdict` stamps a SAME_MODEL fallback only when that candidate's `dispatch --phase review` was a fallback for the same reviewer, and refuses `--fallback` for available models, unknown agents and QA verdicts; `verdict --subtask` pairs against the subtask's routing (its record, its review dispatch, or `--subplan`), not the task's.
- Bind subtask review coverage to its reviewed paths: later edits require a fresh paired review; legacy verdicts conservatively cover all task paths.
- The gate does not let a task review launder a subtask: a subtask whose recorded implementer differs from the one the task review paired against, or is the task reviewer's own model, needs its own PASS review by its pair or a dispatch-recorded SAME_MODEL fallback review (noted `SAME_MODEL (fallback: <pair> unavailable)`).
- Warn about unexplained model overrides and plans using only one model; expose model choices and reasons in dispatch and status. `status` reports a plan task without `id` as INVALID, and `check-registry.sh` accepts a registry without `pipeline.qa_prefer`.
- **`tests/run-all.sh --workspace-only`.** Runs only what CI cannot run: the live-workspace suites and checks
  (facts, live pin status, skill citations, routing history replay, `claude plugin validate`), with the suite reuse.
- **`-h` / `--help`.** `tests/run-all.sh` prints its usage header and exits 0. An unknown argument exits 2 with the
  usage header and never starts a run.
- **Pipeline.** Multi-wave plans: the gate accepts an earlier wave's review when a later wave's changes under its paths
  are covered by the later task's own current PASS review (and QA where required), with commits attributed to tasks
  by the topic's merge commits. Unreviewed changes and evil merges still block. `status` judges review currency with
  the same rule, so `status` and the gate agree on shared dependent paths.
- **Pipeline.** `verdict` records the true implementer of a task (the task record, else the unanimous subtask records,
  else the review dispatch or the planned routing) and the subtask implementers; `--implementer` declares it (refused
  when it conflicts with an implementer the dispatch recorded), and the gate pairs the review against the recorded
  implementer.
- **Pipeline.** `status` shows a task's own current QA and reports integration QA staleness as such; a QA recorded a
  moment ago is never STALE.
- **Pipeline.** `verdict --report` requires an existing file; `--note TEXT` takes free text.
- **Pipeline.** `check-registry.sh` ties the kind enum copies (the subplan schema and the registry schema
  `agent_routing`) to `docs/schemas/pipeline-plan.schema.json` and fails when one differs.
- **run-all.** One full run per machine: a full `tests/run-all.sh` (no `--affected` or `--only-suites`) and every
  `--release` run take a lock in the persistent state dir; the shared-config snapshot is taken after the lock. A second full run waits and prints `waiting for full run <pid> in <checkout>`;
  `--no-wait` exits 3 instead, and a lock whose holder is dead is taken over. A holder counts as alive when its PID
  answers `kill -0` or, on Git Bash, when the Windows PID it recorded from `/proc/$$/winpid` is in `tasklist.exe`, so a
  full run started from another MSYS or Cygwin runtime is not taken over. Takeover prints
  `run-all: taking over stale full-run lock (<pid>)`. Only one waiter reclaims a stale lock, and a lock that a new
  holder has not finished writing is not taken over.
- **run-all.** A full run on a clean tree writes a result record for that tree; `--reuse` exits 0 at once on a PASS
  record of the same clean tree with at least the same coverage (a `--no-workspace` or `--no-claude` record does not
  satisfy a run without that flag) and prints `reused full run at <HEAD> (tree <tree>, <date>)`. `--release` never
  reuses the record.
- **run-all.** Suite-level reuse: each suite's PASS is recorded under a hash of its inputs (`tests/affected.py hashes`,
  the conservative rule: the suite file, the paths it names, every file in the tree of each code file the suite
  reaches, such as `scripts/ui/data/*.json`, helpers with a caller edge included, the global inputs and the tool
  versions; only `scripts/lib` stays narrowed to its importers, suites directly in `tests/` are not tree data and the
  index docs `scripts/README.md` and `tests/README.md` count only where a suite names them), and a later run skips that suite and
  prints `PASS  <check> (reused <suite> inputs <hash>)`. Suites graded by a postprocessor, checks that read the live
  workspace (a `run` inside a live block too) and `--no-history` runs are never reused, no record is published when the inputs changed during the run, and a suite that skipped a case for a missing tool
  publishes no PASS record (a later run with the tool runs it).
  `--no-reuse` runs every suite; `--release` never reuses.
- **run-all.** `--only-suites LIST` runs only the named suites (comma-separated paths), unioned with `--affected` when
  both are given; neither takes the full-run lock. A name run-all does not run (a missing file, or a suite without a
  run-all line such as `tests/dogfood.sh`) exits 2. `--list-suites` (read-only) prints the names `--only-suites`
  accepts under the current flags (release-only suites need `--release`). A one-suite `--only-suites` run took 76 s before and 14 s after.
- **run-all.** With `--affected` or `--only-suites`, the live-workspace blocks and the checks that run a script outside
  a suite line (`scripts/checks/skill-citations.py`, `scripts/factory-context.sh`, `scripts/checks/pin-status.py`,
  `pin-plan.py`, `package-ready.py`, `netcode-headless.sh`) are selected like suites by that script path, else they
  count as not affected; `--only-suites` may name such a script.
- **run-all.** `--affected` selects the suites with one `tests/affected.py select-many` call per run instead of one
  call per suite.
- **run-all.** When `python3` resolves to the Windows Store alias, run-all puts the real Python directory first on
  `PATH` for the suites (about 70 ms saved per call); the user's system is not changed.
- **Tests.** `tests/affected.py` no longer treats `scripts/lib/*` as global. Selection (`--affected`, `select`,
  `select-many`) follows the narrow static graph: Python imports (parsed with `ast`, plus a text scan) and the shell
  and jq helpers a script loads or runs by name, through every tracked code file on the way, so a lib module or a
  helper selects only the suites of the scripts that reach it; a module it cannot map still selects every suite. A
  miss there is caught by the integration full run. `affected.py hashes SUITE...` prints each suite's input hash for
  suite reuse (`-` when reuse is unsafe) under the conservative tree rule above, because a false PASS is the risk
  there. `tests/affected.test.sh` covers both rules.
- **Guard.** `scripts/git-guard.py --batch` evaluates JSON-line cases in one process through the same evaluation as
  the hook. `tests/git-guard.test.sh` runs most cases through it and keeps a representative set on the real hook
  process (exit codes, `; exit 0` wiring, crash safety); the case count is unchanged. Suite wall time: 717 s before,
  about 96-128 s after.
- **Pipeline.** QA tiers (registry `pipeline.qa_tiers`): `dispatch --phase qa` prints one tier command. Task QA runs
  `tests/run-all.sh --affected --base <review base> [--only-suites <check suites>] -j 2` (the suites the task's checks
  name that `tests/run-all.sh --list-suites` lists, each once; only a plain standalone suite command or a plain
  scoped `tests/run-all.sh` invocation is folded into it, every other check that mentions run-all is printed
  `DO NOT RUN`, other checks stay whole extra commands)
  and its spec forbids a full run. `verdict --phase qa --state FAIL --failed-suites LIST` records the failed suites;
  the next QA dispatch on a new candidate reruns those that `tests/run-all.sh --list-suites` lists, each once, with
  `--affected --base <that FAIL's candidate>`. The tier commands are read from registry `pipeline.qa_tiers`. A repo
  without `tests/run-all.sh` keeps the previous QA body: its checks and the `run-checks.py` fast tier. Integration
  QA runs `tests/run-all.sh --reuse -j 4` under the lock. `validate` warns when a task's checks contain a full
  `tests/run-all.sh` or its acceptance requires a full run (`full runs belong to integration QA`).
- **Pipeline.** Task QA never prints a runnable full run, and no check is dropped silently. A `tests/run-all.sh`
  check is folded into the tier command only when it is one plain standalone scoped invocation: an optional
  `env -u TMPDIR` and `bash` prefix, plain flag tokens (no quote, backslash, `#`, `$`, backtick, operator,
  redirection or newline) and `--affected` or `--only-suites` among them. Every other check that mentions run-all,
  a plain full run included (`tests/run-all.sh -j 4`, `tests/run-all.sh -j 4 && ...`, `bash -c "tests/run-all.sh -j 4"`,
  `sh tests/run-all.sh`, a quoted, escaped or commented form), is printed in the QA spec as an extra command
  `DO NOT RUN (...; report it NOT_RUN)`; the QA session reports it NOT_RUN. Without a review base the task QA command is
  `tests/run-all.sh --only-suites <check suites> -j 2`; with no check suites either, the spec prints `NONE` and asks
  the task lead for a base. When two extra commands run the same suite, the `env -u TMPDIR` form is kept.
  `verdict --failed-suites` accepts any suite `tests/run-all.sh --list-suites` lists (for example
  `testlab/tests/test_lab.py` and `scripts/check-registry.sh`).
- **Pipeline.** A tier S task (plan or task tier S, or every owned path prose: a `.md` file anywhere, a path under `changelog.d/` or a `skills/` directory path; a non-`.md` file under `skills/`, `docs/*.json` and `docs/schemas/` are not prose) needs no QA session: the task lead runs the task QA command after the review PASS and records
  `verdict --phase qa --state PASS --by <lead> --note 'tier S: lead ran task suites'`. The gate accepts such a
  lead-run QA verdict (note starting `tier S`, no QA session) only for a tier S task. A QA PASS from a fresh QA
  session is accepted as before for every tier, including the one-model fallback where the implementer's model runs
  QA.
- **Pipeline.** The gate judges a subtask review's currency with the multi-wave attribution the task level uses, and
  from the subtask's own paths instead of the task's whole owned paths: a later wave merged with its own current
  PASS review does not make an earlier subtask review STALE, while unreviewed changes still do. A later sibling
  subtask's own current paired PASS review also covers its changes to an earlier subtask's paths (for example a fix
  session that edits files an earlier subtask implemented). That credit covers only the sibling's commits made after
  it started (its recorded implement dispatch); a sibling without a recorded start gets no credit.
- **Pipeline.** `verdict --subtask <id> --fallback '<model> unavailable' --note TEXT` records a SAME_MODEL fallback
  subtask review after the fact, for a review made before dispatch recorded fallbacks (for example during an outage
  of the paired model). The retrospective form is for subtask reviews only: without `--subtask` it is refused, and a
  task review keeps a dispatch-recorded fallback or `gate --allow-same-model`. `--note` is required and the reviewer must be the implementer's model; the gate shows it as an accepted fallback
  with its reason and note, never silently. The bare `verdict --fallback <model>` form also requires `--note`.
- **Pipeline.** A workspace-relative `repos.<key>.path` in a plan is resolved under the workspace wherever the
  pipeline reads a repo path.
- **Tests.** `tests/affected.py` selects the parallel-policy suite for changes to `scripts/orca-wait.sh` and
  `tests/orca-wait.test.sh`.
- **Plans in the repo.** `docs/plans/` holds the plugin's pipeline plans (`docs/plans/<topic>.json`, starting with
  `plugin-flow-2.json`), the backlog (`docs/plans/backlog.md`) and run reports (`docs/plans/<plan>/report.md`), so a
  run can resume from any clone. `docs/plans/README.md` states what stays in the per-machine state dir (verdicts,
  specs, subplans, Orca state: a new machine re-runs review and QA) and the portable `repos.<key>.path` forms.
  `tests/parallel-policy.test.sh` fails on any machine-specific absolute path under `docs/plans/`.
- **Portable plan repo paths.** `scripts/lib/plan_paths.py` (`resolve_repo_path`) resolves a plan-relative path and
  `${RPG_FACTORY_WORKSPACE}/<repo>` against the workspace root; a later task wires it into `factory-pipeline.py`.
- **Run lead waiter.** `scripts/orca-wait.sh --run <id>` waits on a Run for `worker_done`, `escalation` or
  `question`, acks heartbeats, keeps waiting on timeout, prints the first real message and exits; one instance per
  Run by a lock file in the state dir (`tests/orca-wait.test.sh`, fake `orca`).
- **Run report rule.** The run lead writes `docs/plans/<plan>/report.md` at integration (sessions, verdicts, checks,
  limitations) and commits it with the integration.
- **Worker stalls.** The Orca waiter reports stalled workers and exits 5; `pipeline_route.stall_reason` identifies model availability failures in terminal output.

### Changed

- **CI is the full-suite gate.** Integration QA before the PR is `tests/run-all.sh --workspace-only`; after the PR
  opens, CI green (`gh pr checks <pr> --watch`) is the merge gate; no full local run before a PR.
  `dispatch --task integration:<repo> --phase qa` prints `--workspace-only` for the plugin repo, `gate` prints the CI watch with the PR commands, and registry
  `pipeline.qa_tiers` integration is `ci+workspace`. The full
  `tests/run-all.sh --release` and `tests/dogfood.sh --installed` run only for releases. While CI runs, start the next
  task (`.claude/CLAUDE.md`, `parallel-work.md` section 10 "QA tiers").
- **Lead worktree.** `dispatch --phase lead` creates a new task worktree with
  `git worktree add --no-track -b <branch> <path> <base>` and starts the lead with
  `orca agent launch --worktree path:<path>`: `orca worktree create` writes `branch.<name>.base` into the shared
  `.git/config`, which breaks other sessions' full runs (`parallel-work.md` section 4).
- **Cleanup after the PR merges.** `parallel-work.md` section 8 adds the after-merge step: once the integration PR
  is merged into main, the run lead removes the integration checkout or worktree (not the main checkout), deletes
  every merged task branch and the integration branch locally (`git branch -d`) and on origin
  (`git push origin --delete <branch>`, only branches of this plan that main contains), releases every worker and
  starts the next plan from main. The run lead passes `factory-pipeline.py cleanup plan.json --after-merge` once the
  PR is merged: it lists these commands and reports CLEAN only when none is left (a plan `repos` path that no longer
  exists is LEFTOVER; the path must point at the main checkout).
- **Core.** `parallel-work.md` section 10 has a "QA tiers" table (task QA, re-QA, tier S, reviewer, integration QA,
  release) with the lock and reuse rules: a task never runs the whole suite, reviewers run no suites, and the only
  full run of a batch is integration QA. It replaces the "at most two concurrent full runs" rule with one full run
  per machine. `.claude/CLAUDE.md` follows: the PR rule names integration QA's full run (or a reused PASS record of
  the same tree), and Commands lists `--reuse`, `--no-wait`, `--only-suites`, `--list-suites` and `--no-reuse`.
- **Tests.** `tests/parallel-policy.test.sh` builds one minimal throwaway plugin copy, copies only the lint inputs
  per mutation and runs only the lint sections a mutation reaches, concurrently (`PARALLEL_POLICY_JOBS`, default 4).
  It also checks the QA tiers table: one copy under its marker, the required rows, no full run in the task row.
  Suite wall time: 831 s before, about 61-115 s after.
- **Tests.** `tests/routing.test.sh` caches each history replay result in the persistent state dir, keyed by commit
  SHA and a hash of the routing inputs (the suite, the registry, every script, the routing environment and the tool
  versions), and replays only commits without a cached result (`history replay: <n> cached / <n> replayed`); each
  write prunes old cache keys;
  `--no-history` skips the replay.
- **Tests.** `tests/pipeline.test.sh` captures the output of identical commands once and runs independent cases in
  parallel. It does not copy prebuilt fixture repos: per-case setup is a few git commands, and the time is in the
  `factory-pipeline.py` CLI calls. Suite wall time: 459 s before, 242 s after.
- **Pipeline.** Refinements of the agent routing: `dispatch --runner print` is a preview and writes no implementer or
  reviewer model record; `agents --down` without `--reason` prints MODEL_UNAVAILABLE once; `validate` and
  `subplan validate` warn about an unexplained implementer override also for items without `kind`, against the default
  routing; a legacy subtask verdict is suppressed only by the modern record of the same subtask with the current
  fingerprint, not by a subtask id that extends it.
- **Pipeline.** The plan kind list comes from `docs/schemas/pipeline-plan.schema.json` instead of a hard-coded copy; the
  `factory-pipeline.py` docstring documents the `agents` verb and the print preview.
- **Workflow.** `factory-workflow.py dispatch` routes its agent through the pipeline routing helper (default routing,
  availability fallback) instead of reading `pipeline.default_implementer`.
- **run-all.** The shared git config check reports WARN with the `diff -u` when the only change during the run is whole added `[branch "..."]` or `[worktree]` sections (another session adding a branch or worktree). Any other change still fails: a changed or removed key, a key added inside an existing section, a duplicate of an existing section, or an added unrelated section.
- **Parallel work policy.** `parallel-work.md` section 5 names `scripts/orca-wait.sh` as the run lead's single
  waiter; section 8 adds the run report and the lesson that plan edits are atomic (write a copy, validate it, then
  replace the plan).

### Fixed

- `tests/run-all.sh` on Windows with the Python install manager's `python3` alias: the alias runs
  `python3 -B - <file>` as `<file>` through its shebang, so `--only-suites` and `--list-suites` failed ("cannot list
  the suites") and Git Bash forks crashed. When the real Python directory has no `python3.exe`, run-all calls its
  `python.exe` directly (exported `python3` function), also for `--list-suites`.
- **Checks.** `tests/facts.test.sh` grades each registry fact against the committed tree (a temporary `HEAD`
  export per repo) instead of the working tree, and prints a note when uncommitted changes would give a different
  result (untracked files included), so an uncommitted Unity `ProjectSettings` edit no longer fails
  `enter-playmode-options`. Probes run with a disposable index, so a git probe never rewrites a product repo's
  `.git/index`, and each repo is exported once per run.
- **Checks.** A timed-out check's process tree is killed even when the POSIX `ps` listing fails or is missing
  (`scripts/lib/procrun.py`); `tests/run-checks.test.sh` covers it and reaps zombies in the timeout-tree case.
- **UI.** `scripts/ui/ui_catalog.py` checks the `git cat-file --batch` and `ls-tree` return codes and guards
  truncated output: a failing read is NOT_AVAILABLE with its reason instead of a crash or a silently empty catalog.
- **Tests.** `tests/orca-commands.test.sh` checks flag values against the usage choice list and covers
  `orca orchestration worker-start --worktree new-child` and `orca worktree create --parent-worktree`.
- **Tests.** Resolve Git Bash explicitly for pipeline enum-copy registry checks so Windows CI does not launch WSL.
- Resolve pipeline model and effort profiles after agent routing and availability fallback, including task and subtask validation previews.
- `pipeline_route.available` keyed its cache on the marks file mtime, so a mark set and cleared within the
  timer resolution (Windows CI) returned the stale availability. The key is now the file content.
- **run-all.** `tests/run-all.sh -j N` no longer hangs when a suite worker dies without writing its result: the scheduler records each worker's PID and grades the suite FAIL with its buffered output and the line `suite worker died without a result (pid N)`. Later suites still run and the counts stay correct (`tests/run-all-parallel.test.sh` kills a stand-in suite).
- **Tests.** `tests/git-guard.test.sh` retries a case once when it expects an advisory and the guard printed nothing, and prints a `RETRY` line with the first try's return code; empty output twice still fails, and an expected allow is never retried. The root cause of the empty output under load is not proven: the guard fails open (git probes time out after 5 s and return nothing, and internal errors are swallowed), so this is mitigated by a visible retry, not fixed at the root.
- **Tests.** `tests/ui-figma-env.test.sh` fresh-heartbeat fixtures no longer go stale on a loaded machine: they stamp the heartbeat one hour ahead (`figma_env.py` has no clock override and only treats ages over 60 s as stale); the stale case keeps its 2020 timestamp.
- **Tests.** `tests/routing.test.sh` strips the CR from skill names that Windows `jq -r` prints.

## [1.6.0] - 2026-11-09

Model policy for the delivery pipeline (leads pick model and effort per session inside a user-defined scope; Codex workers on gpt-6.1-terra), asset-gen core skills, and the work merged since 1.5.0.

### Added

- **Asset generation engine.** `scripts/assetgen/assetgen.py` (`list`, `show`, `resolve`, `render`, `lint`,
  `review-cmd`, `qa`, `manifest`; stdlib only, Pillow optional) turns a purpose, a game style and a ComfyUI workflow
  template into a reviewed, QA'd and recorded generation run. Core data under `templates/assetgen/`: purposes
  `concept-2d`, `sprite-2d`, `icon`, `ui-element`, `texture-tileable`, `ref-3d-turnaround`, `image-edit`; styles
  `stylized-painterly`, `pixel-art`, `low-poly`, `realistic-pbr`, `anime-cel`, `flat-ui`; API-format templates
  `image-generate` and `image-edit` (`rpg-factory.comfy-template/1`: `{{param}}` placeholders, typed params,
  `output_node`). A game layer `<authoring>/assetgen/{purposes,styles,templates}/` overrides or `extends` core ids.
  `render` is strict, `lint` checks data and workflows offline against a node snapshot and rejects URLs, host
  addresses and credentials (malformed nested data and out-of-range link indices are FAIL rows, never a traceback), `review-cmd` only prints a read-only `codex exec` command, and `qa` checks PNG validity,
  size (exact, min, aspect or any), alpha, transparent corners, tileable seams and blank images. The stdlib PNG
  decoder applies gray, RGB and palette `tRNS` transparency like Pillow. Every parser refuses abbreviated options.
- **Domain `assetgen`.** Module `authoring.assetgen` (`assetgen/`), artifact kind `gen-run`
  (`docs/schemas/kinds/gen-run.schema.json`), quality plugin `scripts/checks/domains/assetgen.py` (the reviewer
  model differs from the prompt author; the review files, not the `run.md` summary, are the evidence and each verdict
  is bound to the prompt and output SHA-256s and a requirements hash (purpose, style and template content hashes,
  resolved params, and for the image review the whole `workflow.json` graph and the reference images kept in `references/`) that `review-cmd` handed the reviewer, so a missing,
  contradicting or stale review fails, also after a purpose is re-resolved with a stricter rubric; `qa.json` must be PASS with a PASS row for every check the purpose requires, `NOT_AVAILABLE` never
  grades PASS, and a QA report graded with an older purpose qa block or requested size is stale; output hashes, provenance, refs), human gate `assetgen-approval`,
  handoffs `assetgen-to-art2d`, `-art3d`, `-ui` and `-vfx`, and the `comfy-mcp` dev tool (MCP server plus a
  ComfyUI service probe, headless or Desktop). A same-model review is allowed only as the explicit fallback
  `"by": "SAME_MODEL:<model>"`, which grades WARN, never PASS.
- **Skills.** Lead `asset-gen`: the generation workflow (route, pick, resolve, prompt, Codex prompt review with at
  most 2 fix rounds, render, comfy-mcp `server_info` -> `validate_workflow` -> `run_workflow` -> `fetch_outputs`, QA
  plus visual and Codex image review with at most 2 regenerations, `manifest`, human approval, handoff, promotion
  into the game layer on request). Tech skill `comfyui` (paths `assetgen/`; used by `asset-gen`, `art-2d`,
  `art-3d`, `ui-ux`, `vfx`): template format, layer precedence, comfy-mcp setup and tool sequence, the 9router
  image node's pitfalls (credentials read by the node, returned size, unsupported model ids, no local models),
  Desktop and headless ports, and adding a purpose, style or template.
- **Commands.** `/rpg-factory:assetgen` (`factory-cmd.py assetgen`) runs the read-only engine verbs `list`, `show`,
  `resolve`, `lint` and `review-cmd`. It defaults `--authoring` to the workspace authoring repo when that repo has
  `assetgen/`, and it refuses `render`, `qa`, `manifest` and `--out` with any abbreviation of it (`--ou=FILE`).
- **Tests.** `tests/assetgen.test.sh` (in run-all, selected by `--affected` for engine, template and quality-plugin
  changes), routing scenarios (`assetgen/` -> lead `asset-gen` with tech `comfyui`; `art2d/` without it), the
  `asset-gen` dogfood scenario and the `asset-gen-icon` eval.
- **ComfyUI-visible runs.** `render` also writes `<run>/workflow.ui.json`, the same graph in ComfyUI frontend
  (LiteGraph) format with node layout, titles, links, `widgets_values` and the run id, which converts back to the API
  graph. The core templates feed the prompt through a `PrimitiveStringMultiline` node titled
  `Prompt (Claude, Codex review <state>)`. New verbs: `assetgen.py embed --run DIR` (mandatory after
  `fetch_outputs`, before `qa`) writes the UI workflow as a `workflow` tEXt chunk into each output PNG, idempotent and
  keeping the `prompt` chunk, so dragging the PNG into ComfyUI restores the graph; `assetgen.py publish --run DIR
  --comfy-url URL` (optional, not exposed through `factory-cmd.py`) uploads `workflow.ui.json` through ComfyUI's
  userdata API to Workflows > assetgen, and reports `NOT_AVAILABLE` without writing anything when ComfyUI is not
  reachable.
- **Claude's visual review is recorded.** The agent writes `<run>/review-image-claude.json` (review schema and the
  image review binding, `"by": "claude"`), `manifest` records it as `spec.claude_image_review` and summarises it in
  `run.md`, and the quality check `gen-run-claude-review` WARNs when it is missing, unbound or stale and FAILs when it
  contradicts `run.md` or is a FAIL verdict on a proposed run; it never replaces the Codex image review.
- **Image review inputs.** `review-cmd --phase image` states the true pixel size of every output, and for purposes
  with a tileable check it passes a 2x2 tiled preview (`<run>/review/tile-2x2.png`) to the reviewer.
- **Skills.** `asset-gen` and `comfyui` document `embed` and `publish`, that comfy-mcp `run_workflow` posts to
  `/prompt` and never opens a canvas tab, Claude's own image review file, and that the generate step reports an
  outdated `comfyui_9router` node pack from `server_info` without updating it.
- **Style lock: project style config.** `<authoring>/assetgen/project.json` (`rpg-factory.assetgen-project/1`:
  default `style` `{id, version}`, `allowed_styles`, `families` mapping an asset family to a game sub-style,
  `art_direction` refs) is the single source of the game's style. `resolve --family F` (else the purpose's
  `default_family`) picks the style, refuses a style outside the project or a deprecated one unless
  `--style-override REASON` (recorded in `spec.style_lock.override` and `run.md`), and keeps today's behaviour with a
  lint `WARN` when the game has no `project.json`. Schemas `docs/schemas/assetgen-{project,anchor,rejection}.schema.json`.
- **Style lock: versioned, structured styles.** Styles carry `version` and `status` (`draft`, `active`,
  `deprecated`) and optional structured fields (`palette` colours, `lighting`, `outline` with `edge_darkness`,
  `shape_language`, `forbidden[]`, `canvas` per family, `tone`); a prose string still works. Purposes gain
  `default_family`, `dimensions`, `max_references` and `qa.outlines`. Every spec, review binding, anchor, rejection
  and gen-run records the style reference `{style_id, version, sha256}`.
- **Style lock: anchors and rejections.** `assetgen.py promote-anchor` writes a `proposed` anchor from a manifested
  run output under `assetgen/styles/<style-id>/anchors/`; only a person activates it, and it is valid only while its
  source gen-run is approved (the quality check `gen-run-style` also checks the signed approval, the image hash and
  that the approver is not an agent or model). `assetgen.py reject` records a rejected asset or direction with a
  fixed reason under `rejections/`; relevant rejections feed the prompt's avoid list and the review rubric, and the requirements hash binds them
  and the family, so a changed rejection set makes earlier reviews stale. Both reviews also show the style's
  `forbidden` list, `outline` and `shape_language`.
- **Style lock: deterministic reference selection.** `resolve` selects valid active anchors of the run's style
  version (family match, dimension overlap, strength, id; capped by `max_references`) with `reason[]` per pick, and
  `render --run` copies them to `<run>/references/anchor-<id>.png` and wires them through `LoadImage` and core
  `ImageBatch` nodes into `NineRouterImage.reference_images` (an image-edit reference stays first).
- **Style lock: consistency QA.** `qa` adds the soft rows `style-palette`, `style-tone`, `style-edges` and
  `style-canvas` (`scripts/assetgen/consistency.py`; `WARN` by default, `FAIL` only when the style says so,
  `NOT_AVAILABLE` without the style field), and the image review attaches the selected anchors, adds an anchor
  rubric item and one `Not repeated:` item per relevant rejection, and binds the style ref and anchor hashes.
- **Style lock: drift.** `assetgen.py drift --authoring DIR` (read-only, `rpg-factory.assetgen-drift/1`) lists
  gen-runs, anchors and rejections recorded on an older style version, a changed style hash or a missing style.
  `/rpg-factory:assetgen drift` forwards it; `factory-cmd.py assetgen` refuses `promote-anchor` and `reject`,
  because they write into the authoring repo.
- **Style lock: quality checks.** The quality plugin adds `gen-run-style` (style reference, recorded anchors exist,
  are active, approved by a person, with matching image bytes and an approved source gen-run; an active anchor
  promoted from an unapproved run fails; image reviews bind the style reference and anchors). The new fast check
  `assetgen-lint` (`assetgen.py lint --authoring .`) lints the game layer, `project.json`, anchors and rejections.
- **Style lock docs and skills.** `docs/architecture/domains/assetgen.md` section "Style lock"; `asset-gen` gains
  the family, override, anchor upload, style-row and rejection steps and a reference
  `references/style-lock.md` (bootstrap a new game style: exploration `concept-2d` runs, a person picks,
  `promote-anchor`, a person approves, then `project.json` and the game style at version 1; style change and drift);
  `comfyui` documents the anchor wiring and uploading every `references/*` file.
- **Edge fringe QA and `defringe`.** `qa` adds the row `png-edge-fringe` for purposes with alpha (the colour of
  low-alpha edge pixels against the adjacent opaque pixels and the output composited on black and white), and
  `assetgen.py defringe --run DIR [--alpha-floor N]` bleeds opaque neighbour colour into low-alpha pixels (stdlib,
  premultiply-safe), runs after `fetch_outputs` and before `embed` and QA, keeps the originals under `outputs-raw/`,
  records the params and the hashes before and after in `defringe.json` (a `- Defringe:` line in `run.md`), starts
  from the originals when run again, and refuses an approved run and outputs `qa.json` or an image review already
  binds (unless `--force`, which names the records to re-run).
- **Composite previews for alpha review.** `review-cmd --phase image` writes and attaches
  `review/composite-dark.png` and `review/composite-light.png` for every output with alpha, and the rubric asks to
  judge the edges on both; Claude's own image review uses the same composites. `--no-write` uses them only when
  they are current, like the tile preview.
- **Approval verb.** `assetgen.py approve-record --run DIR --by NAME [--note TEXT]` writes the approval record and the
  `run.md` status `approved` for a person; it refuses a missing `--by`, an agent or model name and a name the run
  records as an agent or reviewer. The person commits `run.md` and the record in one SSH-signed commit whose signer
  principal is that name. The `asset-gen` skill runs it only on the person's explicit word and quotes it; the
  `gen-run` lifecycle allows `proposed` -> `approved`, and `factory-cmd` does not forward the verb.
- **Cross-family anchors.** `resolve` warns when a selected anchor's family differs from the run's family, and
  `anchor_family_fallback: false` in a purpose or `project.json` forbids such anchors (`resolve` records the
  warnings as `spec.warnings`).
- **Changelog fragments.** Each change adds `changelog.d/<topic>.md` (Keep a Changelog `###` sections) instead of
  editing `CHANGELOG.md`, which conflicted in about 19 of the merges in this repository's history.
  `scripts/changelog.py` validates (`check`), previews (`preview`) and, at release, writes the `## [X.Y.Z]` section and
  removes the fragments (`release X.Y.Z [--summary TEXT]`). run-all fails when `[Unreleased]` gets a direct entry, and
  `scripts/release-check.py` requires `changelog.d/` to hold no fragment (`tests/changelog.test.sh`,
  `tests/release-check.test.sh`).
- **Doctor and SessionStart.** When `python3` on PATH is the Windows Store alias (`\WindowsApps\`), doctor and the
  SessionStart advisory say each hook call starts about 70 ms slower and suggest putting the real interpreter first
  on PATH. Detection only: nothing is changed (`tests/install-status.test.sh`, `tests/hook-perf.test.sh`).
- **Pipeline.** Orca child worktrees at both levels. A subplan subtask takes `placement` (`shared`, the default, or `child`) and a `reason` (required for `child`); `subplan validate` rejects an unknown placement, `child` without a reason and `child` in a no-worktree repo (Unity project). `dispatch --subplan <file> --subtask <id>` (implement, review, qa) defaults `--paths`, the agent (implementer for implement, reviewer for review) and the placement from the subtask; `--placement shared|child` overrides it. A child prints `orca orchestration worker-start ... --worktree new-child --name <task branch>--<subtask or phase> --base-branch <task branch or --sha>`: a child implement session commits on its child branch and the task lead merges it and removes the child at once. `--phase lead` creates a new task worktree as an Orca child of the integration checkout by default (`orca worktree create ... --parent-worktree path:<checkout that has plan.topic checked out>`; Orca lineage only, the git layout is unchanged); without such a checkout it falls back to `--no-parent` with a stderr note, `--placement shared` forces `--no-parent` and `--placement child` is accepted with the same result as the default (an existing task worktree and a no-worktree repo are unchanged), and `--task integration:<repo> --phase qa --placement child` runs the QA in a child at the SHA. Every child command and spec says never to create or remove a child while a full `tests/run-all.sh` runs (shared `.git/config`); a child in a no-worktree repo is a usage error.
- **Pipeline.** `status` lists each task's leftover child worktrees (`children`: path, branch, merged; status schema updated) with a merge-then-`orca worktree rm` note, lists the leftover children of each repo's integration checkout (integration QA or a helper session) once per repo in `integration_children` (repo, path, branch, merged and a merge-then-`orca worktree rm` note), and `cleanup` names each one as "child of <task>" or "child of integration:<repo>" (its `orca worktree rm` command once merged and clean; a child with uncommitted changes or a failing `git status` is kept and named, like a task worktree). A child is found by its name (`<parent branch>--...`) or, for any other name, by Orca's lineage (`parentWorktreeId` / `childWorktreeIds` from the read-only `orca worktree list --json`, read only when a worktree is not already explained); only children of this run's task worktrees and integration checkout count, and without a working `orca` the naming rule alone applies (never an error).
- **Pipeline.** `verdict --subtask <id>` records a subtask's review or QA in its own file; every verdict is also kept per candidate (`<task>__<phase>__<sha12>__<by>.json`). A subtask review or QA of this plan version that is not PASS on the newest applicable candidate blocks `gate` (NOT_READY) and `status` (no gate step; the task lead is started to fix it) until a `verdict --subtask <id>` PASS on that commit or a newer one that contains it. Only records on the commit being graded (the integration HEAD in `gate`, the task candidate in `status`) or an ancestor of it apply, and among those the one no other applicable record contains decides: a late PASS on an older candidate never resolves a newer FAIL, and a PASS on a fix left on an unmerged child branch never resolves a FAIL on the integrated commit.
- **Citations.** `scripts/checks/skill-citations.py --fix` rewrites the line spec of every MOVED citation in place
  (only the digits inside the backticks; encoding and line endings are kept), and `--strict` counts MOVED as a failure.
- **Docs.** `AGENTS.md` at the repo root for Codex: it points at `.claude/CLAUDE.md` as the authoritative guide and
  adds only the Codex-only notes (Git Bash, reinstall after edits, `factory-cmd.py` instead of slash commands, hook
  trust review). `scripts/README.md` indexes every script entrypoint with its purpose and covering test suite.
- **Lint.** `tests/skills-lint.sh` prints a `WARN` line (not a failure) when `factory-core` `SKILL.md` exceeds a
  140-line budget; the 160-line cap is unchanged.
- **Two-level eval.** `evals/pipeline-two-level/` asks for a multi-file plugin change and grades the tool transcript:
  the session acts as the run lead and must run a successful `factory-pipeline.py dispatch --phase lead` with
  `--runner print` (running `tier` or writing a plan alone fails; the match is anchored on the Bash `command`, so an
  `echo` of the dispatch command does not count), and never edits the requested task files itself
  (implementing in the run lead's own session fails, even with a correct final report).
- **Two-level dogfood scenario.** The opt-in `tests/dogfood.sh --two-level` runs a real headless session on a throwaway
  clone of the plugin with a multi-file plugin task and passes only when the session dispatches a task lead
  (`factory-pipeline.py dispatch --phase lead --runner print`) and edits none of the task files. A dispatch counts only
  when its output carries the printed task-lead spec and no error (a pipe such as `| head` hides a failed exit status).
  The grading is offline too: `tests/dogfood.sh --grade-two-level <transcript.jsonl> [<clone dir>]` grades a recorded
  transcript without a model call (the disk check only with a clone dir); `tests/pipeline.test.sh` runs it on
  synthetic transcripts.
- **Cleanup names the dispatch specs.** `factory-pipeline.py cleanup` lists the plan's spec files under
  `<state dir>/pipeline/<plan id>/specs/` (count and directory) as kept state; it never deletes them and they do not
  affect CLEAN.
- **Delivery pipeline.** `scripts/factory-pipeline.py` (and `/rpg-factory:pipeline`) runs the parallel-work policy
  end to end: `tier` (S/M/L from the routing snapshot), `validate` for a `plan.json` (disjoint owned paths,
  cycles, waves, cross-model reviewer, exclusive resources; schema `docs/schemas/pipeline-plan.schema.json`),
  `planner` and `dispatch` (exact `orca orchestration` worker starts or the Agent fallback for implement, review
  and QA), `verdict` (review and QA results keyed by the candidate SHA) and `gate` (READY_FOR_PR only when every
  task is integrated, reviewed PASS by the other model on unchanged paths, QA PASS on the integration HEAD, the
  trees are clean, every change sits in a task's owned paths, each verdict matches the current plan's task and
  the fast checks are PASS and current; `--no-run-checks` gives UNVERIFIED, never a delivery). With the user's `deliver: pr` the lead pushes and
  opens the PR the gate prints; merging stays with the user (`git-safety.md` rule 5). Settings live in registry
  `pipeline`; QA uses `templates/pipeline/qa-report.md` (`tests/pipeline.test.sh`).
- **No worktrees in Unity projects.** `repos.client.worktrees: false` (and any repo with
  `ProjectSettings/ProjectVersion.txt` at its root): every role works in the main checkout, the repo's tasks run
  one after another with review and QA each, and Unity test runs are one shared exclusive resource
  (`pipeline.exclusive_resources`).
- **Cleanup after every task.** `parallel-work.md` section 8 is mandatory: when a task is done the lead removes
  the run's worktrees (`git worktree remove`, never `--force`), deletes task branches already in the integration
  branch (`git branch -d`), and ends every Claude and Codex worker session (`orca orchestration worker-release`,
  background agents stopped). `factory-pipeline.py cleanup` lists what is left and prints the commands; it must
  report CLEAN before the final report.
- **Commands.** `/rpg-factory:domain [<id>] [--json]` (`factory-cmd.py domain`): every registry domain with its lead,
  repos and artifact counts, or one domain with artifact kinds, quality and human gates, handoffs, artifacts by
  status, stale upstreams, FAIL and HUMAN_REQUIRED artifacts and next steps (JSON schema `rpg-factory.domain/1`).
  Read-only and data-driven: a new registry domain needs no code change; an unknown id exits 2 listing the domains.
- **Commands.** `factory-cmd.py help [--json]` lists every verb with its arguments, read-only flag, an example, the
  Claude form (`/rpg-factory:<verb>`) and the Codex form (`python3 -B <plugin root>/scripts/factory-cmd.py <verb>`)
  (JSON schema `rpg-factory.commands/1`); agents and Codex discover the commands there.
- **Commands.** `--json` for `status`, `route` (file and `--domain`/`--kind` forms), `check` (passed to
  `run-checks.py --json`) and `doctor` (`rpg-factory.doctor/1`: install, registry, workspace, repos, tools, hooks,
  dev_tools).
- Show optional authoring domains in Factory status, including artifact lifecycle counts, stale upstreams, quality failures, human gates, and follow-ups owned by domain leads.
- **Operating lessons in the repo.** `.claude/CLAUDE.md` gains an "Operating lessons" section (no worktree or
  branch creation while run-all runs, `git switch --no-track -c`, Git Bash never WSL, citation `--fix` before a
  release gate, at most two concurrent full run-all runs, `git update-index --chmod=+x` on Windows, quoting shell
  examples, the learning loop), pointed to from `AGENTS.md`. New `docs/dogfood.md` (linked from the
  `tests/dogfood.sh` and `tests/dogfood-codex.sh` headers) says how to classify and report nondeterministic dogfood
  failures and lists the known traps. `parallel-work.md` adds the full test run as a shared resource, the
  Codex-else-Claude rule, Orca message traps (escalation from non-workers, heartbeats in `check --wait`, multi-line
  prompts under `cmd.exe`, confirming a Codex worker picked up its prompt), session count under memory pressure and
  which plan edits keep verdicts.
- **Model policy for the delivery pipeline.** Registry `pipeline.models` holds a model scope per agent (Claude, Codex),
  profiles per role (planner, lead, implement by grade, review, QA) and a grade rubric; `scripts/check-registry.sh` and
  `docs/registry.schema.json` reject a profile outside the scope. Plan tasks and subplan subtasks take an optional
  `grade` (`light|standard|heavy`) and `grade_reason`; without one the grade comes from the tier (S light, M standard,
  L, contract and generated paths heavy) and a subtask inherits its task's grade. `validate` and `subplan validate`
  print the resolved model and effort. `planner` and `dispatch` accept `--grade`, `--model` and `--effort` (a value
  outside the scope exits 2) and pass `--model/--effort` to `orca orchestration worker-start`, `orca worktree create`
  and `orca agent launch`; the Agent-tool runner passes a model alias and notes that effort cannot be set; `verdict`
  stores the optional model and effort. A personal override file (`$RPG_FACTORY_MODEL_POLICY` or
  `<persistent state dir>/model-policy.json`) may narrow the scope and replace profiles. The policy is described once, in
  `parallel-work.md` section 10, "Model choice" (`scripts/lib/model_policy.py`, `tests/pipeline.test.sh`). Codex workers
  use `gpt-6.1-sol` at effort `high` for planner, lead, review and `heavy`, and `gpt-6.1-terra` at `high` for `light`,
  `standard` and `qa`.
- **Pipeline status.** `factory-pipeline.py status <plan.json> [--json]` (schema `rpg-factory.pipeline-status/1`,
  `docs/schemas/pipeline-status.schema.json`) shows how far each task got - pending, implementing, candidate, reviewed
  (PASS or FAIL with its SHA), integrated or qa - derived from git and the recorded verdicts, with the next command per
  task, the ready wave and the tasks to dispatch now, and the gate once every task has QA and every repo has its
  integration QA PASS at the integration HEAD (also after the per-task QA of a Unity project; until then the next
  command is that integration QA), so status names the gate only when the gate can pass. A new lead session resumes a
  run from it without the old session's context. Read-only. `/rpg-factory:pipeline status` runs it.
- **Registry fragments.** `registry.json` is now built from `registry/` by `scripts/build-registry.py`: `core.json`
  (shared sections), `engineering/<repo>.json`, `engineering/skills.json`, `engineering/contracts.json` and
  `domains/<domain>.json` (a domain's modules, contracts, skills, kinds and lifecycles). Parallel domain branches
  edit different files; replaying this repository's merges found `registry.json` conflicts in every parallel domain
  merge of 1.3.0. Readers still read the one committed `registry.json`. `--check` (run-all) fails when it is not the
  build or an entry sits in the wrong fragment; `scripts/new-skill.py` writes the fragments. The one-time migration
  reorders `registry.json` (entries grouped by fragment) without changing its content (`tests/registry-fragments.test.sh`).
- **CODEOWNERS by domain.** `.github/CODEOWNERS` maps each domain's fragment, skills, templates, checks, adapters,
  docs and tests to an owner; the registry-fragments suite keeps its paths and domains current.
- **Pipeline.** `factory-pipeline.py cleanup` and `status` list the settled Orca workers of a task lead's Run that are not released, with their `orca orchestration worker-release --dispatch <id>` commands. The Run comes from the new optional plan task field `orca_run` (not part of the verdict fingerprint) or from `--orca-run <id>` (repeatable, `run:<id>` accepted). The check is read-only (`orca orchestration worker-list --run <id> --json`, every page): a released worker and a running worker are no finding; an unreleased settled worker makes cleanup LEFTOVER and puts its release command first in the status `next` list. Without orca, or when the call fails, the Run prints a NOT_AVAILABLE line and nothing fails. `status --json` keeps stdout to the status schema and prints the same `Workers:` lines (NOT_AVAILABLE, UNRELEASED) on stderr.
- **`tests/run-all.sh --affected [--base REF]`.** Runs only the suites a change touches (`tests/affected.py`: files
  changed since the merge-base with `origin/main`/`main` plus untracked files; a suite runs when it is the changed
  file, names it, lists it as an indirect input, or a global input such as the registry or `scripts/lib/` changed).
  Cheap inline checks always run; `--release` ignores it. Every suite line now shows its duration
  (`tests/affected.test.sh`).
- **Parallel run-all.** `tests/run-all.sh -j N` (`--jobs N`) runs up to N independent suites at once. Each suite's
  output is buffered and every line, inline checks included, prints in the `-j 1` order with its time; the count and
  the exit code are those of a serial run. The read-only live-workspace checks (`runl`, `block`) form a lane that runs
  one suite at a time next to the fixture suites; `run1` suites (the shared git config guard suite, the
  installed-plugin safety suite, `claude plugin validate`) wait for every queued suite and run alone. The longest
  suites start first. The default stays `-j 1`; the run ends with its wall time, and CI uses `-j 4`
  (`tests/run-all-parallel.test.sh`).
- **testlab dev tool.** Registry `dev_tools` lists `testlab` for `measure`, probed by the new `plugin-file:<path>`
  kind (a file of this plugin exists, here `testlab/testlab.py`) in `scripts/lib/devtools.py`, `check-registry.sh` and
  the registry schema (`tests/devtools.test.sh`).
- **Line-budget test.** `tests/line-budget.test.sh` fails when `scripts/lib/gitguard.py`, `scripts/lib/context.py` or
  `scripts/run-checks.py` reaches 500 lines, so the split-big-scripts budget cannot regress silently.
- **Parallel work.** `parallel-work.md` section 8 gains "Session lifecycle": one worktree per task for its whole life, and one fresh worker session per dispatch, never reused. The implementer, reviewer, QA worker and any fix run as separate fresh sessions in that task worktree or in an Orca child of it (`child-worktrees.md`; reviewer and QA read-only, after checking that `git rev-parse HEAD` is the candidate SHA); review and QA never get a new task worktree, and integration QA runs in the integration branch's checkout, never in a task worktree. Each session is released in the turn it reports, in every repo, and the task worktree stays (in a no-worktree repo only the task work is serialized: the next task starts after the previous task's QA verdict); a task is integrated when its review PASS is recorded, in wave order, and its worktree is removed only after that PASS and integration. The lead keeps only `plan.json` and integration state and hands off after each wave through `factory-pipeline.py status plan.json`. Sections 1, 4, 6, 8 (cleanup) and 10 (review step) follow the same rule (dispatch placement: `task-lead-in-worktree.md`).
- **Docs.** `.claude/CLAUDE.md` "Developing this plugin": every plugin task runs through `factory-pipeline.py` with a `plan.json` naming the plugin checkout, small disjoint tasks and cross-model review. The skill-author skill plans scaffold, content and routing/dogfood as separate tasks; `AGENTS.md` points Codex at the same flow.
- **Pipeline task lead.** `factory-pipeline.py dispatch <plan.json> --task <id> --phase lead [--report-to <run id>]`
  starts ONE task-lead session per plan task, with the task spec plus the task-lead rules: plan and split the task
  into subtasks with disjoint paths, one fresh Claude or Codex session per subtask in the same worktree, sub-sessions
  that do not commit, the task lead commits per subtask, cross-model review and QA sessions in that worktree, a fresh
  fix session after a FAIL, every session released as it reports, a `status` report to the run lead (branch, HEAD,
  verdicts, checks), never push, merge or remove the worktree. Orca forbids nested workers, so `--runner orca` prints
  a handoff instead of a worker start: `orca worktree create --branch <topic>-<task> --parent-worktree path:<integration
  checkout> --agent ... --prompt ...` for a new task worktree (`--no-parent` only without such a checkout or with
  `--placement shared`, `child-worktrees.md`), `orca agent launch --worktree path:<dir> --prompt ...` to resume in it; the task lead
  creates its own Orca Run and reports with `orca orchestration send --to run:<id> --type status`. In a no-worktree
  repo (Unity project) the task lead runs in the main checkout and dispatch never prints a worktree create or a new
  top-level worker. `status` names `--phase lead` as the next command of a pending task.
- **Pipeline subplan.** `factory-pipeline.py subplan validate <subplan.json> [--plan PATH] [--json]`
  (`docs/schemas/pipeline-subplan.schema.json`) checks a task lead's split of one plan task: subtask paths inside the
  task's owned paths and outside its exclusions, overlapping subtasks ordered by deps, known deps and no cycle, an
  implementer that is a pipeline agent and a reviewer of the other model (registry `pipeline.review_pairing`), and
  well-formed subtasks; it prints the waves (one subtask per wave in a no-worktree repo).

### Changed

- **`--run` takes a run id.** Every `--run` accepts the run id as well as the run directory; an id resolves under
  `<authoring>/assetgen/runs/` (with `--authoring`, else the current repo).
- **Short `resolve` output.** `resolve` prints a short summary (style lock, references, rejections, key params,
  warnings); the source file of every field and param only with `--verbose` or `--json`.
- **`asset-gen` skill: a service FAIL stops regenerating.** After a FAIL the service causes, not the prompt (for
  example a returned size that ignores the request), the agent stops regenerating, runs `manifest` on the last attempt
  with its QA FAIL visible and reports; the earlier attempts stay without `run.md`.
- **`comfyui` skill.** It names the service ignoring `size` as a known issue, and says that `server_info`'s outdated
  flag for a node pack compares the pack hash with ComfyUI's own commit, so it is unreliable for a pack inside the
  ComfyUI checkout: the agent reports it as unverified and never prompts or performs an update on that signal alone.
- **2D Art.** Generated images may become production sources, but only through a human-approved `gen-run` handed
  off by `assetgen-to-art2d`. Any other generated image stays a concept draft. Art 3D, UI/UX and VFX accept
  approved gen-runs through their handoff contracts and name `rpg-factory:comfyui` for inspecting a generation.
- **Registry.** The `codex` dev tool is also used by `asset-gen`, for the independent prompt and image review.
- **Docs.** The skill counts are now 14 specialised skills and 11 tech skills (`.claude/CLAUDE.md`, plugin and
  marketplace manifests, README, factory-core Skills, skill-contract diagram).
- **Tests.** `tests/new-skill.test.sh` reads the lead count from the registry instead of a fixed number.
- **Purpose over style.** A purpose's `constraints` (lighting, background, framing; precedence in
  `scripts/assetgen/data/precedence.json`, the palette stays a style hint) win over the style's hint of the same name.
  `resolve` writes `spec.hints` and marks each overridden style hint, and the review prompts use those hints, so the
  prompt writer never sees both. `ref-3d-turnaround` and `texture-tileable` carry lighting constraints; lint fails a
  constraint on a style-only hint.
- **`ref-3d-turnaround`.** QA checks the aspect of the requested size with a 25% tolerance and a minimum area (90% of
  the requested pixel count, new `qa.size.min_area`) instead of a minimum width and height, and the prompt guidance
  asks for a compact landscape sheet whose views fill most of its height.
- **Failed attempts.** A failed attempt's run directory stays on disk without `run.md`, the next attempt takes the
  next number, and `manifest` lists the earlier attempts of the series without `run.md` in
  `spec.trace.failed_attempts` (the envelope `trace` stays the engineering trace; documented in `asset-gen`).
- **`manifest` keeps an approval.** An `approved` run stays `approved`, and its approval stays bound, when `manifest`
  runs again, nothing the approval binds changed and `run.md` stays byte for byte the same; otherwise it goes back to
  `proposed` and names the changed fields.
- **Style bootstrap.** `asset-gen` `references/style-lock.md`: a new game style id has no anchors until runs under it
  are approved and promoted, so promote again under the game style id or explore under it; step 5 checks the
  structured `palette`, `tone` and `canvas` fields, and `lint` WARNs on an active game style none of whose
  structured fields a style check can grade with: absent, empty (`canvas: {}`, `tone: {}`, `palette.colors: []`,
  `outline.edge_darkness: {}`, a canvas entry with neither `aspect` nor `min_side`) or malformed. The WARN names
  each field's state; the rule is `consistency.field_states`, the same parsing the `style-*` QA rows use, and such
  an empty settings object is now `NOT_AVAILABLE` in QA instead of being graded on defaults.
- **`drift` reports style-id mismatches.** Gen-runs and anchors recorded under another style id than `project.json`
  are listed (`style-id-mismatch`, the text naming the project style), not only older versions of the same style.
- **Hooks.** Cheaper hook calls. The file guard no longer loads the whole git guard (it compiled it on every Read only
  to find the workspace): the shared path helpers (`find_workspace`, `main_checkout`, `linked_worktree`,
  `native_path`, `native_abs`) live once in `scripts/lib/workspace.py`, used by the git guard, the file guard and
  the routing engine. The git guard moved to `scripts/lib/gitguard.py`; `scripts/git-guard.py` is a small hook
  entry that re-exports every guard name. Hook entry points (git guard, file guard, Skill hook, Codex hook,
  SessionStart) cache compiled bytecode under `<state dir>/pycache` (`scripts/lib/hookspeed.py`; the plugin tree stays
  free of `__pycache__`; `RPG_FACTORY_PYCACHE=off` disables it). Write tools cache a repository's submodule paths
  (`git ls-files -s`) in the state dir per work tree and `.git/index` stat, and recompute when the index changes.
  Measured on Windows (median of 10, real interpreter): git guard `git status` 63-95 ms to 55-66 ms, file guard
  Read 71-80 ms to 58-60 ms, Write 87-88 ms to 55-66 ms (`tests/hook-perf.test.sh`).
- **Pipeline.** Shorter dispatch specs: the task-lead rules are seven short lines (commands spelled once), the implement, review and QA specs keep objective, owned paths, checks and report format, and the task spec JSON puts each key on one line. For the plugin-flow child-worktrees task the lead spec went from 55 to 24 lines and the implement spec from 47 to 17.
- **Citations.** A citation whose anchor is no longer within the cited lines +/- 3 but occurs exactly once in the
  file, or exactly once within +/- 40 lines, is now MOVED (reported with the shifted spec, exit 0) instead of FAIL.
  `tests/run-all.sh` prints MOVED citations as warnings with the `--fix` hint; `tests/run-all.sh --release` runs the
  check with `--strict`. A missing file or anchor, several far candidates, an unanchored citation and a line past the
  end still fail.
- **Core.** `factory-core` `SKILL.md` shrinks from 160 to 124 lines: the mode table, the routing details of workflow
  step 4, the validation-state table and the git-safety advisory list now live only in their references
  (`skill-contract.md` "Routing", `validation.md`, `git-safety.md`, `workflows.md`). The 12 workflow steps keep their
  marks and commands.
- **factory-core drives the two-level flow.** `skills/factory-core/SKILL.md` names the main session the run lead
  (plans, dispatches, integrates, reports; never edits task files) and one task lead per task. Step 6 writes a
  `plan.json` for every tier (S is a one-task plan with its own task lead), runs `dispatch --phase lead` per ready
  task and `status` to resume; Unity (no-worktree) repos keep the task lead and every session in the main checkout,
  subtasks in sequence. Step 7 (task lead) runs `subplan validate` and one fresh sub-session per subtask, committing
  each with explicit paths. Step 11 (task lead) dispatches cross-model review (Codex reviews Claude's code and Claude
  reviews Codex's; without Codex a fresh Claude session marked SAME_MODEL) and QA; step 12 (run lead) gates, opens the
  PR, releases every session and runs `cleanup` until CLEAN. `AGENTS.md` and `.claude/CLAUDE.md` point to these steps.
- **Pipeline tier flows.** Registry `pipeline.tiers.S|M|L.flow` describe the two-level flow: the run lead writes the
  plan and dispatches one task lead per task (no-worktree repo: main checkout, in sequence), task leads run
  sub-sessions, cross-model review and QA, the run lead integrates and never implements.
- **Docs.** README, `docs/codex.md` and the factory-core "Commands" section list every verb with its Claude and
  Codex form.
- Share read-only artifact discovery, upstream revision checks, quality grouping, and domain summaries between workflow and status commands without changing workflow output.
- **Guard.** `scripts/lib/gitguard.py` loads the `scripts/lib/guard/` package by path under the unique name
  `rpgf_guard`, so no module named `guard` is imported and no other `guard` module on `sys.path` can shadow it or
  be shadowed by it. Behaviour and public names are unchanged; `tests/hook-perf.test.sh` asserts the package name and
  its cached bytecode.
- **Pipeline.** Orca first inside Orca: in an Orca session (`ORCA_WORKTREE_ID` or `ORCA_AGENT_HOOK_ENDPOINT` set) with the runtime reachable, `factory-pipeline.py planner` and `dispatch` default to `--runner orca` and refuse `--runner agent` (exit 2, naming `--runner orca`) unless `--orca-unavailable <reason>` is given; the reason is written into the session prompt so the report names it. Outside Orca `--runner agent` works as before. Reason: Agent-tool task leads with plain git worktrees are invisible in Orca, where the user works. `parallel-work.md` section 5 states the rule and `tests/parallel-policy.test.sh` checks it.
- **Pipeline.** The task-lead spec printed by `dispatch --phase lead` says to release every implement, review and QA session the moment it reports, its candidate is superseded or it stops, not at task end; to check with `status --orca-run <run id>`; and to name its Orca Run id in the report. `parallel-work.md` section 8 names the check.
- **Pipeline.** The task lead is always a Claude session, whatever the task's implementer: registry `pipeline.lead_agent` (`"claude"`, the default when the key is missing) picks the agent of `dispatch --phase lead`, and `--agent codex` on `--phase lead` prints a warning and keeps Claude. Implementation, review and QA sessions keep the cross-model pairing. `parallel-work.md` states the rule under the new `policy:task-lead-claude` marker, linted by `tests/parallel-policy.test.sh`, and factory-core `SKILL.md` step 6 says it.
- **Faster test cycle.** `tests/parallel-policy.test.sh` builds one minimal plugin copy with a single `tar` pipe
  instead of one `cp` per file and runs its mutation lints concurrently (`PARALLEL_POLICY_JOBS`, default 4; about 11 to
  4 minutes on Windows). `tests/new-skill.test.sh` copies only the tracked and untracked files the scaffolder and
  lints read, no longer the whole checkout including `.git`. Assertions and counts are unchanged.
- **run-all.** Suites read `/dev/null` instead of the caller's stdin, the Codex packaging suite runs through the
  scheduler (so `--affected` can skip it), the live workspace checks sit together after the fixture suites, and the
  git environment isolation suite moved next to `claude plugin validate` at the end.
- **`run-checks.py` grading moved to `scripts/lib/runchecks_grade.py`.** `parser_for()` and `grade()` (which parser a
  registry check uses and how its output grades) now live in the library module; `run-checks.py` imports them back,
  so its `--json` output is unchanged and the script is back under its 500-line budget.
- Split git guard logic, check process execution and snapshot rendering into focused modules while preserving existing behavior and public imports.
- Extend Python syntax and release-policy wording checks to the extracted modules, including advisory wording in snapshot rendering.
- **Pipeline placement.** `dispatch --phase implement|review|qa` joins the task's existing worktree (found by the task
  branch in `git worktree list`, `--worktree path:<it>`) and never creates one: a missing task worktree is an error
  (exit 1, run `--phase lead` first). `--phase implement --paths <subtask paths>` starts a sub-session limited to those
  paths that does not commit (a `child` placement commits on its child branch only, `child-worktrees.md`). Integration QA (`--task integration:<repo> --phase qa`) runs in the existing checkout of
  the integration branch, never in a task worktree; none is an error, no worktree is created.
- **Agent fallback.** `--runner agent` starts Claude sessions only: a session planned for Codex runs as a fresh Claude
  session whose prompt says SAME_MODEL, and its review counts as SAME_MODEL.
- **Parallel work.** `parallel-work.md` describes the two levels (sections 1, 3, 4, 5, 6, 7, 8 and 10): the run lead
  gives each task one worktree and one task-lead session and integrates; the task lead runs subtasks, cross-model
  review, QA and fixes as fresh sessions in that worktree. It records the Orca nesting limit and the Unity rule (task
  lead, subtasks, review and QA in the main checkout, one after another; Unity test runs exclusive). Every session is
  released as it reports, in every repo; a no-worktree repo serializes only its task work. `.claude/CLAUDE.md`,
  `AGENTS.md` and the skill-author skill point to it.

### Fixed

- **Style QA is bound to its style inputs.** `qa.json` now records `style_binding` (`runfiles.qa_style_binding`: the
  style ref with id, version and hash, a hash of the effective style data, the family, and each selected anchor copy
  under `references/` with its SHA-256, the tone references `style-tone` reads). The quality plugin recomputes it from
  `spec.json` and the run's anchor copies, and `gen-run-qa` fails a report graded with other style data, version,
  family or anchors (also one without `style_binding`) as stale: re-run `qa` and `manifest`. Before, a style
  re-resolved with a fail-severity rule kept an old PASS report acceptable.

- **Size QA vs the real image service.** The 9router image node can ignore `size` entirely (live style-lock e2e,
  2026-11-08: 1672x941 returned for 1536x1024 and 1024x1024 requests), so `concept-2d` could never pass and
  `promote-anchor` refused good outputs. No core purpose's size QA grades the exact size any more: it grades
  orientation or aspect with a tolerance, a minimum area and a minimum short side that real outputs meet, per purpose
  in data, with regression tests on the real returned sizes. Every core purpose has a short side and an area floor
  (`icon`, `sprite-2d`, `texture-tileable`, `ui-element` and `image-edit` 512 px and 512x512 pixels), so a 256x256
  output fails each.
- **Review prompt params.** The requested params in the review prompts and `run.md` `spec.params` come from the
  rendered workflow, so a `render --param` value is the one the reviewer and the record see, never the `spec.json`
  value it replaced. Each review is bound to exactly those params: a `render --param` that changes a param after a
  review makes it stale (render title, `review-cmd` and the quality check agree; the same params again keep it
  bound), and the quality check FAILs a `run.md` `spec.params` that differs from the rendered params instead of
  substituting `spec.json`.
- **Size double-counted in the image review.** The image review prompt states QA's verdict as context and tells the
  reviewer not to grade size or the other deterministic checks again; they belong to QA only.
- **`filename_prefix`.** `spec.json`, the review prompts and `run.md` record the same `assetgen/<run-id>` prefix that
  `render` writes into the workflow.
- **`review-cmd`.** The printed command uses absolute paths, so it works from any working directory.
- **`asset-gen` skill.** It documents `show --kind purpose <id>`: a bare `show image-edit` was ambiguous between the
  purpose and the template.
- **`lint`.** A bad game-layer value is blamed on the game file that holds it, not on the unchanged core file it
  extends.
- **Uncommitted approval message.** An approval record that is present but not committed and signed reads
  "approval present but not committed/signed" instead of "missing" in `gen-run-style`, graded `HUMAN_REQUIRED` like
  the trace grades it. `artifact-trace` uses the same phrase (still `HUMAN_REQUIRED`) when the record file is on disk
  but not committed, both with `run.md` uncommitted (it said "missing approval") and with `run.md` committed (it said
  "approval is not immutable"); no record file for the artifact still reads "missing approval".
- **`approve-record` immutability and line endings.** `approve-record` never overwrites an approval record: the same
  approval again is a no-op, another one (by, date or note) for the same `run.md` revision is refused before `run.md`
  is touched, and a changed `run.md` gets a new revision and a new record. A `run.md` with CRLF line endings parses
  and keeps them, and the record's `rev` is what `git hash-object` gives the file in its repository (line-ending
  filters such as `core.autocrlf` applied), so it is the blob the commit binds.
- **Square size tolerance.** `sprite-2d` and `icon` square checks failed on real service outputs (1322x1190); the
  square purposes `icon`, `sprite-2d` and `texture-tileable` now set `square_tolerance` 0.15, and a landscape or portrait purpose can set `qa.size.allow_swap` to accept the
  swapped orientation (1024x1536 returned for 1536x1024; a boolean, default false, checked by `lint`), with these
  real sizes as regression tests.
- **`embed` stale chunk.** `embed` replaces an existing `workflow` chunk that differs from the current
  `workflow.ui.json` (idempotent when equal), so a re-render no longer leaves the old graph in the PNG.
- **Agent and model names as approvers.** The shared approver guard (`approve-record --by`, an active anchor's
  `approved_by`, `gen-run-style`) only knew claude, codex and gpt names, so `approve-record --by gemini-2.5-pro`
  approved a run. It now refuses the common model and agent families as a whole-word name start, also after a vendor
  prefix such as `google/` (gemini, llama, mistral, qwen, deepseek, grok, o1/o3/o4, phi-, copilot and others), the
  registry's `pipeline.agents`, and any name ending in `-bot` or `-agent`; person names such as `Grokowski` are
  accepted.
- **`defringe` dropped colour metadata.** `defringe` rebuilt each output from its pixels and kept only the text
  chunks, so `gAMA`, `cHRM`, `iCCP`, `sRGB` and `pHYs` were lost and the opaque body could look different. It now
  carries `cHRM`, `gAMA`, `iCCP` or `sRGB` (never both; `iCCP` wins), `cICP`, `mDCv`, `cLLI` and `pHYs` from before
  the first `IDAT`, in file order, right after `IHDR`, and still drops chunks bound to the old pixel format (`sBIT`,
  `PLTE`, `tRNS`, `bKGD`, `hIST`, `sPLT`).
- **Review previews dropped colour metadata.** The image review's dark and light composites and the 2x2 tile previews
  were written untagged, so an output with `gAMA`, `cHRM`, `iCCP` or `sRGB` displayed different body colours and
  fringe contrast in its preview than in the output (with `gAMA` 100000, opaque 128 displays as 188 in the output
  and 128 in the preview). Every review preview now carries the output's colour chunks right after `IHDR`, with the
  `defringe` rules minus `pHYs` (a preview is never placed); the blend runs on the stored values, with the backgrounds
  in that same space. An untagged output keeps untagged previews, byte for byte, and `--no-write` compares the tagged
  bytes.
- **Grayscale outputs became RGBA with a GRAY ICC profile.** `defringe` and the review previews rewrote a gray or
  gray+alpha output (colour type 0 with `tRNS`, or 4) as RGB(A) while copying its `iCCP`, so a GRAY profile sat on
  a colour image. A grayscale output now stays grayscale: `defringe` writes it as 8-bit gray+alpha (colour type 4)
  with its profile, its composites are gray and its tile preview gray+alpha. No PNG it writes carries a profile of
  the other colour space than its colour type (a GRAY profile on RGB(A), an RGB one on gray): such an `iCCP` is
  dropped, and the output's `sRGB`, if any, is kept instead. Palette and RGB outputs, and untagged previews, are
  unchanged byte for byte.
- **`defringe` and the review previews handled other bit depths as 8-bit.** Both now read the IHDR bit depth and
  handle only 8-bit PNGs (palette included), which is what the image service produces. Any other depth (16-bit, or
  1/2/4-bit) is refused with the reason `bit depth N not supported`: `defringe` records the output as `skipped` and
  leaves it byte-identical with no `outputs-raw/` copy, and `review-cmd` builds no composite or tile for it, prints
  the reason on stderr and still hands the output itself to the reviewer.
- **The documented fringe repair was refused after QA.** `asset-gen` step 7 said to run `defringe` after a
  `png-edge-fringe` FAIL, but `qa.json` then binds the outputs, so `defringe` refused. Step 7 (and the `comfyui`
  skill and the domain doc) now document `assetgen.py defringe --run <run> --force [--alpha-floor N]`, then `embed`,
  `qa` and both image reviews again (`review-cmd --phase image` and `review-image-claude.json`). The refusal and the
  `next:` hint after a forced run name `embed`, `qa` and both image reviews.
- **Codex role.** `AGENTS.md` no longer lets Codex act as the run lead or a task lead: Codex runs only as a session a
  Claude task lead starts (implementer, cross-model reviewer, QA); the run lead is the main Claude Code session and the
  task lead is always Claude (registry `pipeline.lead_agent`). `AGENTS.md` points to the `.claude/CLAUDE.md` operating
  lessons for Git Bash instead of restating the WSL lesson. `tests/parallel-policy.test.sh` fails when `AGENTS.md`
  names Codex as run lead or task lead.
- **Child implement sessions.** `parallel-work.md` section 10 step 4 states the child exception: a shared-placement
  implement session never commits, a child session commits on its own child branch and the task lead merges and
  removes it. `tests/parallel-policy.test.sh` checks the step under a policy marker.
- **Parallel-work wording.** Section 4 says which placement default applies to which phase (`dispatch --phase lead`
  defaults to `child`, every other session to `shared`) and that a no-worktree (Unity) repo's task branch is the plan
  `topic`; section 8 removes a leftover child with `orca worktree rm --worktree path:<child>`.
- **Changelog.** The task-lead and session-lifecycle fragments name `--parent-worktree` as the task worktree default and
  the child-worktree exception.
- **factory-core allowed-tools.** The `python3 -B ${CLAUDE_PLUGIN_ROOT}/scripts/factory-pipeline.py` form the
  pipeline prints is granted, not only the form without `-B`.
- **Pipeline: Unity aliases.** `status` and `dispatch` serialize no-worktree tasks by checkout, as `validate` does: two
  plan repo keys that name one Unity checkout are never both ready, the second task waits for the first one's QA, and
  per-task QA counts every alias of the checkout (also in the gate). `status` offers a no-worktree checkout's
  integration QA only after every task of the checkout, under any alias, passed per-task QA, and runs the aliases'
  integration QAs one at a time, so no QA session runs beside a task lead in one Unity checkout. The gate counts
  every alias's owned paths on the shared integration branch, so their changes are not stray.
- **Pipeline: dependent tasks with shared paths.** `status` counts only a task's own commits: a task branch cut from the
  integration branch starts at its fork point (no own commits while it is still on the topic's first-parent chain),
  and a no-worktree task starts after its serial predecessor's last verdict (before that verdict it has not started).
  A dependent task that owns an earlier task's paths is no longer a review candidate before its first commit, in a
  worktree repo and in a no-worktree (Unity) repo.
- **Pipeline: child names.** Review and QA children are named `<parent>--[<subtask>--]<phase>-<sha7>`, so the review
  and the QA of one candidate, or a subtask whose implement child still exists, never collide in Orca. A child
  command also says on stderr to run it from the parent worktree (integration QA included).
- **Pipeline: one id rule.** Task and subtask ids follow the schemas' pattern `^[A-Za-z0-9][A-Za-z0-9_.-]*$` in
  `validate`, `subplan validate`, `dispatch` and `verdict`; `subplan validate` rejects unknown subplan and subtask keys,
  and `validate` rejects a task id `integration_<repo>` (it would share the integration QA's verdict file).
- **Pipeline: case on Windows.** The gate's and `status`'s git pathspecs for owned paths are case-insensitive on
  Windows, matching the owned-path check, so a plan path in another case no longer hides a stale review.
- **Pipeline: Agent fallback for a child.** `--runner agent` with child placement uses the Agent tool's
  `isolation: worktree` and never tells the session to run `git worktree add`.
- **Pipeline.** Plans and subplans with a UTF-8 BOM (PowerShell `Out-File`/`Set-Content`) load instead of failing with a JSON error.
- **Pipeline.** A task review recorded by a model other than the task's paired reviewer (a paired review of a Codex subtask without `--subtask`) no longer overwrites the pair's review of the same SHA; it is kept per candidate and named on stderr.
- **One-line Orca prompts.** cmd.exe cut multi-line `orca` arguments at the first newline, so a dispatched session
  received only the first line of its spec. Every `--runner orca` dispatch (planner, task lead, implement, review, QA)
  now stores the full spec under `<state dir>/pipeline/<plan id>/specs/` and passes a one-line prompt pointing to that
  absolute file; the planner's prompt also ends with `Request: <text>`, whitespace collapsed to single spaces.
- **Pending status for unstarted tasks.** `factory-pipeline.py status` keeps a task with no branch, worktree or review
  pending: commits on the integration branch from an earlier task with the same owned paths no longer make it a
  `candidate` at the integration HEAD.
- **Planner specs in a reserved directory.** Planner specs moved from `pipeline/planner/` (which a plan with id
  `planner` would share) to `pipeline/_planner/`; `validate` rejects a plan id whose state directory is `_planner`.
- **Spec path test on short Windows paths.** `tests/pipeline.test.sh` compares spec directories by real, case-folded
  path, so an 8.3 short `TEMP` (Windows CI runners) no longer fails the check.
- **Note for unreviewed integration commits.** `status` keeps an unstarted task pending but notes when its owned paths
  already have commits on the integration branch and no review record exists ("integrated earlier? check before
  dispatching again").
- **Workflow dispatch for Orca.** `factory-workflow.py dispatch --runner orca` printed
  `orca orchestration worker-start --task "<spec>"`, which Orca rejects (`--task` takes a task id and a start needs
  `--agent`); it now prints `--spec ... --agent ... --worktree ...` and never a new worktree for a Unity project.
- Isolate devtools fixtures from inherited Codex runtime markers so real user MCP and plugin names cannot change test expectations.
- **Timeout test no longer depends on machine load.** `tests/run-checks.test.sh` bounded the whole
  `run-checks.py --timeout 1` call at 8 s wall clock, which failed under two concurrent full run-all runs (8.97 s,
  10.83 s). A timed-out check's result now carries a `timeout` record measured by the runner
  (`limit_s`, `timed_out_after_s`, `killed_after_s`, `cleanup_grace_s`, `verified`; `scripts/lib/procrun.py`), and the
  test asserts that the tree was killed after the limit and within the runner's cleanup grace. A negative case keeps a
  never-killed hung child failing the bound.
- **`tests/ui-commands.test.sh` diagnostics.** The `components settings` case prints every asserted value on failure
  and no longer reads a previous case's output.
- **Remaining load-sensitive tests.** The Windows grandchild probe in `tests/run-checks.test.sh` no longer takes a
  reused PID for a survivor: a live process at that PID counts only when it started no later than the check's own
  post-spawn timestamp, and the probe prints the tasklist row and both times on failure (a live grandchild still
  fails). `tests/session-state.test.sh` checks the file-lock retries on a fake clock instead of real elapsed time,
  and `tests/run-all-parallel.test.sh` relies on overlap evidence instead of comparing `-j 3` and `-j 1` wall time.
- **Timeout tree check under load.** When bash needs more than the 1 s limit to reach `echo $!`, the check is killed
  before it writes `child.pid` (seen in 6 of 90 runs under a process-spawn storm). The test now accepts that case when
  the runner's own record verifies the whole tree is gone, and still fails without a verified record. Every
  `t-timeout-tree` failure now prints the result's state, reason, exit, duration, timeout record and output tail
  (or the raw output head when there is no result).
- **`run-checks.py` bash flavor probe.** On Windows, a `uname` probe that fails to start or exits non-zero no longer makes
  the flavor `unknown` at once (that BLOCKs every check of the run). The probe now runs up to 3 times, and a probe that
  ran keeps its answer. The "cannot be resolved" BLOCKED reason now names what is missing (workspace, workspace path,
  checkout path, HEAD), the selected bash, its flavor and each probe answer. A timeout reason no longer repeats
  `cleanup=`.
- **Docs.** The `scripts/README.md` library index lists the current `lib/` modules (guard package, snapshot rendering,
  workspace helpers, process runner, artifacts, Orca commands), and `docs/architecture/ui-skills.md` names
  `scripts/lib/snapshot_render.py` for the snapshot Next line.
- **Guard.** Dropped a duplicate import in `scripts/lib/guard/common.py` and the blank line at the end of six guard
  modules (`git diff --check` is clean).
- **Tests.** `tests/artifact-quality.test.sh` puts `scripts/lib` on `sys.path` before it loads `scripts/lib/tools.py`
  by path, so the suite no longer fails on `codexconfig` when run on its own.
- **Pipeline.** `factory-pipeline.py dispatch --phase lead|implement` branches a later-wave task (one with deps)
  from the plan's `topic` integration branch when it exists, so it carries the earlier waves; `repos.<key>.base`
  stays the comparison base of `status` and the gate.
- **Pipeline tier for unregistered repos.** `factory-pipeline.py tier --plan <plan.json> --repo <key> --paths <files>`
  tiers a `plan.repos` entry the registry does not know (the plugin repo itself) from the paths alone (modules:
  `skills/<name>`, `scripts/lib`, `scripts`, `tests`, `registry`, `docs`, `hooks`, `commands`, and one `other` module for
  anything else; no contracts or generated paths) instead of failing with
  `factory-context: unknown repo`. A registry repo key still goes through `factory-context.sh`.
- **`pipeline subplan` through the command entry point.** `factory-cmd.py pipeline` (and the `/rpg-factory:pipeline`
  slash command) rejected `subplan` with the usage error, so a task lead could not run `pipeline subplan validate`
  that way. `subplan` is now a pipeline verb and the usage text and `help` list it.
- **Pipeline test on Linux.** `tests/pipeline.test.sh` expected the Orca `--worktree path:...` argument quoted; `shlex.quote`
  leaves a POSIX path unquoted, so main CI failed on ubuntu after PR #75. The two dispatch cases accept both forms.
- **Tests.** `tests/install-status.test.sh` isolates the caller's Codex runtime markers (`CODEX_THREAD_ID`, `PLUGIN_ROOT`, `PLUGIN_DATA`): inside a Codex session they made the plugin look like a Codex install and one of 47 cases failed.
- **testlab.** `testlab/tests/test_framegc.py` now runs in run-all next to the other testlab unit tests.
- **domains test.** The base P4 regression proof drops dev tools probed by `plugin-file:`, a kind its frozen checker
  predates.
- **Skill author.** The validate step names a changelog fragment instead of a `CHANGELOG.md` `[Unreleased]` entry.
- **Pipeline paths.** Owned and subtask paths that are absolute or contain a `..` segment are rejected (plan
  `validate`, `subplan validate`, `dispatch --paths`) before any containment, exclusion or overlap comparison.
- **Only the task lead commits.** `status` names `--phase lead` after a review FAIL in every repo (the task lead
  resumes in its task worktree or the main checkout and starts a fresh fix session), and `dispatch --phase implement`
  never prints a committing worker: in a no-worktree repo it is a sub-session in the main checkout that does not
  commit, with or without `--paths`. `dispatch --paths` overlapping a task exclusion is refused (exit 2), with the
  exclusion test of `subplan validate`. `parallel-work.md` drops the S-tier shortcut: an S task is a one-task plan
  with its own task lead; the run lead never implements a task in its own session.
- **Parallel-policy test.** `tests/parallel-policy.test.sh` makes its plugin copy writable (tar kept read-only modes,
  so `echo >> file` mutations silently did nothing and their cases failed) and reports a FAIL when a mutation command
  itself fails; a regression case copies a read-only source file and mutates it.
- **Two-level policy guard.** `parallel-work.md` states its two-level rules as canonical sentences, each under a
  marker comment (`<!-- policy:run-lead-never-implements -->`, `policy:only-task-lead-commits`,
  `policy:no-worktree-repo`). `tests/parallel-policy.test.sh` no longer matches free prose: each marker must appear
  exactly once with its exact canonical sentence on the next non-empty line, and no line may carry a retired
  shortcut phrasing (fixed-string denylist). Mutations (marker deleted or duplicated, sentence changed, old shortcut
  re-added) fail; a rewording outside the markers passes.
- **Task-lead prompt.** `dispatch --phase lead --report-to` accepts `<id>` and `run:<id>` (no more `--to run:run:<id>`);
  in a no-worktree repo rule 9 no longer mentions removing a worktree; a registry `worktrees_reason` ending in a period
  no longer prints a double period.
- **Pipeline: no-worktree dependent tasks.** In a no-worktree (Unity) repo, a task starts only after its serial
  predecessor's current QA PASS on the shared integration branch: until then `status` keeps it pending (it waits for
  the predecessor) instead of offering a review of the predecessor's commits in the paths both tasks own. A pending
  task that both depends on and follows its predecessor names it once in its "waits for" note.
- **Pipeline: STALE QA in dispatch.** `dispatch --task integration:<key> --phase qa` of a no-worktree checkout, and
  `dispatch --phase lead|implement` of the next task in it, read each task's QA as `status` does: a QA PASS recorded
  for an older version of the task is STALE and still counts as open.
- **Pipeline: subtask verdict files.** A subtask's verdicts are named `<task>@<subtask>__<phase>...`, which no task id
  can produce: task `a__sub-b` and subtask `b` of task `a` no longer share `a__sub-b__review.json`. Task verdict file
  names are unchanged; older `<task>__sub-<subtask>__...` records still count for the task and subtask they name unless
  new-style records exist for that subtask and phase, in which case the new-style records take precedence.
- **Pipeline: command hint.** `/rpg-factory:pipeline`'s argument hint lists `subplan`; `status` no longer runs an
  unused git call after the integration QA rows.

## [1.5.0] - 2026-11-05

Feature release: Codex CLI plugin. The same checkout installs into Codex CLI with the same skills, scripts and
advisory guards.

### Added

- **Codex CLI plugin.** The same checkout installs into Codex CLI (`docs/codex.md`, README "Codex CLI"):
  - `.codex-plugin/plugin.json` (same name, version and `./skills/` as the Claude manifest) and a repo-local Codex
    marketplace `.agents/plugins/marketplace.json` (`codex plugin marketplace add <checkout>`,
    `codex plugin add rpg-factory@rpg-factory`).
  - Codex hooks (`hooks/codex-hooks.json`) through the adapter `scripts/codex_hook.py` (`session-start`, and
    `pre-tool-use` for `Bash` and `apply_patch`): the same advisory git and file guards, `rpg-factory advisory
    (high|warn): ...` context only; exit 0 on any input, never a deny or block decision, no `CLAUDE_*` dependency. Hook fixtures with expected levels in `tests/fixtures/codex-hooks/`.
  - `tests/codex-plugin.test.sh` (in run-all): manifest and marketplace validity, version agreement, every Codex
    hook command runs an existing script and ends with `; exit 0`, adapter robustness (empty, malformed, huge, deeply
    nested and binary stdin; unknown or missing event), every fixture replayed in a stand-in workspace with a fresh
    `CODEX_HOME` at the level its README names and in the documented output shape, the same levels with every
    `CLAUDE_*` variable and `PLUGIN_ROOT` unset, the same skill set as the Claude manifest, the hook wiring
    (SessionStart and PreToolUse for both `Bash` and `apply_patch` reach the adapter), PowerShell-only commands
    reported as `Bash` (Windows), and Claude Code with an inherited `CODEX_HOME` staying on the Claude install check.
    A missing Codex file fails.
  - Codex reports every shell as `Bash`, but on Windows runs it with PowerShell: there the adapter parses the
    command as PowerShell (`scripts/git-guard.py` `collect()`), so native `C:\` paths and backtick escapes reach the
    guard and a backtick-escaped `;` is not taken for a separator.
  - Codex runtime detection (`scripts/lib/pluginroot.py` `is_codex()`): `CODEX_THREAD_ID` or `PLUGIN_ROOT`, never
    under Claude Code (`CLAUDECODE`); `CODEX_HOME` alone is configuration, not a runtime. The skill-read advisory is
    dropped for Codex by an argument of `collect()`, not by a payload field.
  - `tests/dogfood-codex.sh` (opt-in, spends tokens): installs the plugin into a throwaway `CODEX_HOME` (only
    `auth.json`, `model` and `[windows]` copied; `~/.codex` is never modified) and grades four real `codex exec`
    sessions (wire.proto routing, the tag policy, a `git push --tags` request that must get the `high` advisory and
    leave origin without tags, the skill list); `--dry-run` self-tests the grader on nine synthetic transcripts.
- **Release gate covers the Codex files.** `scripts/release-check.py` ("versions agree") and the run-all version
  line include `.codex-plugin/plugin.json` when present, and the Codex marketplace when it carries a version;
  `tests/release-check.test.sh` has cases for agreeing, differing, missing and malformed Codex versions.

### Fixed

- Dogfood write grader: after a command that leaves the scratch workspace, the next command starts in the workspace
  again, as Claude Code resets the shell ("Shell cwd was reset"); a relative write such as
  `cd game-authoring && cat > ../wf.json` was flagged as outside the workspace (`tests/dogfood-grader.test.sh`).
- Skills: the unity-client-tech MessagePipe citation follows the client's move of `DotsRegistration.cs` out of
  `Assets/Scripts/DI/Dots/`.

## [1.4.0] - 2026-10-31

Feature release: UI skills and commands. `/rpg-factory:ui`, `ui-figma`, `ui-components`, `ui-screen` and
`ui-review` run a deterministic, read-only UI plan that loads only the UI skills a request needs (five new tech
skills: ui-orchestrator, ui-component-selection, ui-figma-import, ui-toolkit-screen, ui-validation), selects
components from the real com.cuvara.uitoolkit source (reuse, configure, compose, missing), and drives the official
Unity UI Toolkit Figma connector through the package's v0.8.0 tools. Validated with a real Figma-to-Unity import
(`docs/architecture/ui-figma-real-test.md`). Engineering routing is unchanged except that UI files now list the
UI tech skills. Update with `claude plugin marketplace update rpg-factory && claude plugin update
rpg-factory@rpg-factory`, then start a new session.

### Added

- UI request handling for the Unity client, with progressive skill loading (`docs/architecture/ui-skills.md`):
  - `/rpg-factory:ui`, `ui-figma`, `ui-components`, `ui-screen` and `ui-review`: a deterministic, read-only UI plan
    (`scripts/ui/ui_plan.py`, schema `rpg-factory.ui-plan/1`, rules as data in `scripts/ui/data/intents.json`) - intent,
    only the UI skills the request needs (in order; the rest listed as not loaded), the lead route, Figma URL parsing
    (file key, `node-id` 1-2 -> 1:2), the target project, and exactly what is missing (NEEDS_CONTEXT, exit 3; NOT_UI
    for non-UI text).
  - Five UI tech skills (`domain: ui`, used by `client-integration`): `ui-orchestrator` (entry point: runs the plan,
    asks for missing context, loads only the listed skills), `ui-component-selection`, `ui-figma-import` (the official
    UI Toolkit Connector for Figma through the com.cuvara.uitoolkit 0.8 tools: preflight incl. FIG023, environment
    check, headless import, validator triage, profile, token bridge, mapping preset, mode sheets, ScreenCreator
    "Existing UXML"), `ui-toolkit-screen` (ScreenCreator, presenters, registration, navigator, codegen, settings,
    dialogs, theme service) and `ui-validation` (seven review areas graded by artifact, and the `ui-review` checklist).
    Package facts are cited at UIToolkit v0.8.0.
  - `scripts/ui/ui_catalog.py`: the com.cuvara.uitoolkit catalog read from git at the client pin (or `--ref`, or the
    highest tag), each entry with a `path:line@ref` source, plus Unity built-in controls with docs URLs; NOT_AVAILABLE
    without a readable repository; warns when the client pin is behind the ref used.
  - `scripts/ui/ui_select.py`: needs and screen archetypes (settings, inventory, popup, hud, quest-panel, shop,
    confirm) mapped reuse > configure > compose > missing with catalog evidence; nothing is invented.
  - `scripts/ui/figma_env.py --project <p> [--json] [--probe-pipeline]`: read-only Figma connector environment check
    (Unity, package, helper, connector, Pipeline port without the token, Allow Browser Clients, validator CLI, dotnet).
  - Registry: dev tool `figma-mcp` (its `mcp:` probe cannot see claude.ai connector servers; not required),
    `unity-mcp` and `dotnet` used by the UI skills, and fact `uitoolkit-figma-connector-floor`.
  - `docs/architecture/ui-skills.md` and `docs/architecture/ui-figma-real-test.md` (the real "Game Settings"
    Figma-to-Unity procedure and the report of two real runs, with their limitations).
  - Tests: `tests/ui-commands.test.sh`, `tests/ui-catalog.test.sh`, `tests/ui-skill-routing.test.sh` (golden plan
    matrix of 46 cases, selection on a UIToolkit v0.8.0 fixture, path-scoped routing), `tests/ui-figma-env.test.sh`
    and `tests/ui-skills.test.sh` (skill content, docs, snapshot Next line); evals `ui-settings-screen`,
    `ui-figma-import` and `ui-not-ui` with a fired grader per UI skill and must-not-invoke graders.
  - `tests/dogfood.sh`: scenarios `ui-settings`, `ui-figma`, `ui-not-ui` and a `NOTEXPECT` field (skills that must
    not be invoked).

- **testlab: per-frame GC, main-thread and memory columns in the analysis (UCF F-21, step 1).** The client's
  `frames.csv` gains `gc_alloc_b,gc_count,main_ms,used_mb` (client PR "GC, main-thread and memory columns").
  New `lab/framegc.py` reads them by header name and tolerantly. `report.md` gets a "Frame budget" section with
  per-client GC allocation p50/p95/max, gen0 collections and stall frames (>= 250 ms) set against collections,
  `results.json` gets a `frame_gc` key, and `failure-summary.json` gets a `notes` entry ("stall frame coincided
  with gen0 GC") on `frame_time`, `snapshot_cadence` and `snapshot_update_gap` failures when that is true. Runs
  whose `frames.csv` has only the four old columns analyze exactly as before (no section, no key, no note);
  `testlab/tests/test_framegc.py` proves it on a fixture. No threshold or verdict changed.

### Changed

- Tech skills may declare `paths` (registry schema, resolver, `check-registry.sh`): the skill appears in
  `routing.tech` only when a changed file matches. The golden routing gains the UI tech skills only for UI paths.
- The snapshot Next line loads the UI skills through `ui-orchestrator`: "invoke `rpg-factory:ui-orchestrator`
  first; its UI plan names the subset to load", instead of asking for all five.
- `client-integration` names the five UI skills at its UI step.

## [1.3.0] - 2026-10-31

Feature release: production workflows for Game Design, UI/UX, 2D Art, 3D Art and VFX. Each domain has production
artifact kinds with versioned schemas and draft templates, a domain quality plugin (gameplay-number and approval rules,
UI states/bindings/components/handoffs, 2D image integrity, glTF/GLB and optional Blender inspection, VFX timing and
platform budgets with optional Unity prefab inspection) and a lead skill with handoffs. `/rpg-factory:workflow`
plans dependency waves from artifact references (domain contracts order planned nodes; sync contracts such as
`ui-vfx-sync` only trigger revalidation), reports stale upstream revisions, and writes integrated reports. Shared
validation states are PASS, FAIL, WARN, HUMAN_REQUIRED, NOT_AVAILABLE and BLOCKED; lifecycle states are draft,
proposed, reviewed, approved, in-implementation, verified, released, rejected and blocked. Optional tools (Pillow,
Blender, Unity, Figma, image providers) are detected by name or path and degrade to NOT_AVAILABLE. No approver signing
key is registered, so binding approvals stay HUMAN_REQUIRED. The private `game-authoring` repo holds the authoring
layout generated from the registry. `tests/dogfood.sh --write` runs real write sessions graded from the files on disk;
CI runs on Linux and Windows. Engineering routing is unchanged (golden test). Update with `claude plugin marketplace
update rpg-factory && claude plugin update rpg-factory@rpg-factory`, then start a new session.

### Added

- Added production Game Design artifacts, schemas, templates, gameplay-number checks, and design-to-UI, art, VFX, and Engineering contracts.
- Added production UI/UX artifact schemas, draft templates, quality rules, workflow guidance, and registry handoffs.
- Added production 2D art direction, concepts, asset specifications, runtime export records, references, schemas, and image integrity quality rules.
- Added 3D art artifact kinds, per-kind schemas and draft templates for direction, models, materials, rigs, animation, and delivery.
- Added standard-library glTF/GLB production validation and optional Blender scene-statistics inspection for DCC formats.
- Added production VFX direction, specification, and delivery workflows, domain quality rules, and optional Unity prefab inspection.
- Added the `/rpg-factory:workflow` production workflow for planning, status, and integrated reports across domains.
- Added dependency-aware workflow planning, status, dispatch, and integrated reports through the factory entry point.
- Added lifecycle-aware workflow status, signed approval grading, upstream blob invalidation, ordered revalidation, engineering traces, and schemas for every workflow output.
- Workflow readiness now blocks artifacts when artifact-quality cannot produce lifecycle results, and reports the unavailable-check reason.
- Added lifecycle v2 metadata and quality result contracts, per-kind schema registration, review records, adapter tool discovery and domain quality plugin interfaces.
- Added contained registered repo roots and trusted approval-state access to the domain plugin context, plus name-only optional provider discovery.
- Added real write sessions to `tests/dogfood.sh --write` for every production domain and three cross-domain workflows, graded from the files on disk (routed artifact kinds, zero FAIL rows, no approvals, no writes outside the scratch workspace, wave order, stale status), with an offline grader test.
- Added the private `game-authoring` repository layout, generated from the registry authoring modules and contract paths, with CI that runs the artifact checks at a pinned plugin release.
- Added a Windows (Git Bash) CI job beside Linux.

### Changed

- The Bash/PowerShell and file guards warn when a registered skill's `SKILL.md` is read as a file (`cat`, `sed`, `Get-Content`, the Read tool) and point the session at the Skill tool; installed dogfood found a cross-domain session doing this instead of loading its leads.
- Workflow waves follow artifact-level `upstream`/`sources` references when artifacts exist; domain handoff contracts only order planned nodes without references, so a design technical handoff written after a UI screen is no longer a `CYCLE`.
- Factory Core loads every routed domain lead through the Skill tool in multi-domain tasks and never substitutes reading a SKILL.md.
- An asset-spec-2d no longer needs a runtime export while it is a draft; the export is required once implementation is claimed.
- Replaced foundation guidance with production workflows, valid drafts, quality rules, and domain handoff requirements.
- Routed workflow planning from registered artifact kinds and ordered waves from handoff contracts; synchronization contracts trigger revalidation without imposing wave order.
- Documented registry-derived repository roots, safe path resolution, provider discovery, and the shared `Context.approval` contract.
- Artifact reviews bind to git author identities, expose process or signed assurance, and support registry-required signed reviews.
- Unity and Blender availability detection is path-only: Unity is never launched, and only the optional 3D DCC inspection runs the detected Blender in background mode (missing Blender is NOT_AVAILABLE).
- Extended artifact quality checks with structured results while preserving version 1 artifacts and signed approval verification.
- Artifact quality, lint, and trace now fail closed on malformed files; lifecycle requirements and artifact grades follow registry data, and active design kinds validate their structured spec payloads.
- Artifact check grading treats unavailable evidence as human-required, and adapter tool overrides run portable Python fakes consistently on Windows and Linux.

### Fixed

- `tests/dogfood.sh --all` fails when a write scenario fails, and the write grader tracks `cd` (after `&&`, `;` or a newline, across Bash calls) when it resolves relative output paths.
- Skill citations follow the client's DI and input refactors on develop (`ClientRootInstaller`, `MainSceneInstaller`, injected `GameplayInputRouter`, the deleted `DIExtensions` locator, moved `DotsWorldBridge` lines, session installation moved to `EcsSessionInstallation`, input send extracted to `InputEgress`) and the Netcode `KcpTransport` line drift.
- The Bash and PowerShell guard raises a high advisory for host-wide process termination, in any directory: a kill that names targets by image/filter/pattern (`taskkill /IM|/FI`, `Stop-Process -Name`, `pkill`, `killall`, `kill -1`, `wmic process ... delete`), or a process query by name/pattern (`Win32_Process`, `Get-Process <name>`, `pgrep`, `pidof`, `ps | grep`, `tasklist`) combined with any terminator, including `taskkill //PID $(powershell ... Win32_Process ...)`. It reads the parsed command, so quoted `grep`/`echo`/commit-message text no longer triggers it; raw text is only the fallback for unparseable input.
- Binding gameplay numbers pass only with a verified current-revision approval; a missing approval is HUMAN_REQUIRED, an invalid or untrusted one FAILs.
- UI quality validates numeric ordered breakpoints, data bindings against known source artifacts, component specs, and handoff screen ids.
- 2D art parses lossy, lossless and extended WebP headers and rejects truncated images; optional palette validation runs when Pillow is present.
- VFX budgets cover every ParticleSystem in a prefab, and Unity detection never runs the Editor.
- artifact-quality `--domain`/`--kind` select what is reported but still resolve cross-domain sources and upstream artifacts.
- artifact-quality attributes artifact-trace rows to their subject artifact instead of failing every artifact when one is stale.
- Editing an artifact without changing its status is not an illegal lifecycle transition (artifact-lint and artifact-quality).
- On Windows, `/rpg-factory:route` and run-checks launch the Git for Windows bash instead of the System32 WSL launcher.
- Tests: the dir_readonly ACL check reports SKIP when the token has SeRestorePrivilege enabled (hosted Windows runners), and the testlab host-guard CPU budget is printed instead of asserted on hosted CI runners.

## [1.2.0] - 2026-10-30

Feature release: rpg-factory becomes a multi-discipline factory with a discipline-neutral core. A `domains` registry
section adds Game Design (native; no game-ai-workflows dependency) and foundation domains for UI/UX, 2D Art, 3D Art
and VFX next to Engineering. `--domain` / `--kind` route tasks without file paths and `--graph` shows the handoff
order. A shared artifact contract (schema, lifecycle, trace links to implementation, test and release commits,
SSH-signed immutable approvals) is checked by `artifact-lint` and `artifact-trace`; results a human must judge grade
HUMAN_REQUIRED. Handoffs mark downstream work stale when a design changes. Engineering routing is unchanged (golden
test over 59 scenarios). `feature-state-ownership` and `phase-scope` replace `no-feature-registry` and
`phase-plumbing-only`. The English-only documentation check is enforced. Foundation domains have no production
workflows yet; no approver signing key is registered, so design approvals stay HUMAN_REQUIRED, and the optional
`game-authoring` repo is not created. Update with `claude plugin marketplace update rpg-factory && claude plugin
update rpg-factory@rpg-factory`, then start a new session.

### Added

- Added foundation plans and readiness status for UI/UX, 2D Art, 3D Art and VFX.
- Registered foundation domains for UI/UX, 2D Art, 3D Art and VFX with handoffs, lead skills and shared quality checks. Added asset manifest validation for license, provenance and safe registered-repository delivery paths. New lead skill scaffolding now allocates unique orders beyond the legacy lead-order range.
- Added the `feature-spec-to-impl` handoff contract and registry checks for cross-domain path conflicts, artifact-kind uniqueness, and handoff driver ownership.
- Added domain dependency graph routing, cross-domain path ambiguity reporting, and downstream stale-implementation detection.
- Documented routing entry points, dependency graphs, ownership conflicts and downstream invalidation; updated the Game Design handoff workflow.
- Added `docs/architecture/domains.md` with the domain ownership table and Game Design contract.
- Added the native `game-design` lead skill, domain routing touchpoints and a `--domain` option in the skill scaffolder.
- Added the optional authoring repository, Game Design modules, artifact lifecycles, human review gate, and phase-scoped design permissions.
- Added the shared artifact schema, lifecycle registry data, artifact lint and trace checks, and signed approval verification.
- Routing JSON now includes `routing.domain`, derived from the selected lead skill (defaulting to `engineering`).
- `factory-context.sh` and `/rpg-factory:route` accept domain and artifact-kind entry points; optional repos are skipped until present.
- `tests/domains-routing.test.sh` covers domain/kind selection, optional repositories and path-domain warnings.
- `tests/routing-golden.test.sh` freezes the engineering routing contract: every task scenario of
  `tests/routing.test.sh` (59) must keep its lead, co-leads, legs, follow-ups, tech skills, touched modules and
  check ids (`tests/fixtures/routing-golden.json`, recorded before domain metadata). Added fields are ignored.
- `docs/architecture/`: architecture index, accepted multi-discipline factory architecture, and the domains ADR.
- `registry.json` now defines engineering domain ownership; the schema and `check-registry.sh` validate artifact domains, roles, leads, repos, gates and optional repositories. `tests/check-registry.test.sh` covers these rules.
- `scripts/checks/english-only.py`: Unicode language check (report or enforce, with an allowlist); skills-lint and run-all enforce it.

### Changed

- `run-checks.py` now honors `RPG_FACTORY_REGISTRY`, allowing isolated fixture registries to exercise real PASS, FAIL and HUMAN_REQUIRED grading.
- Replaced the blanket feature-registry ban and plumbing-only rule with domain-scoped feature-state ownership and phase-scope policy; non-owning modules cannot claim feature-state paths.
- Made artifact lint validate against the published JSON Schema and bind immutable IDs and lifecycle transitions to each artifact path; added JSON history and schema regressions.
- Made artifact trace and approval gates follow lifecycle requirements, with regression coverage for draft, verified, and binding-value cases.
- Made Factory Core discipline-neutral by moving Engineering reference material into `engineering.md`; English-only policy is now enforced by the skill lint and full test runner.

### Fixed

- Deduplicated equivalent handoff contracts while retaining distinct Art3D source and delivery paths.
- Kept binding gameplay approvals `HUMAN_REQUIRED` until a trusted signing key is registered; verified approvals bind to the artifact revision.
- Enforced UI production quality rules for breakpoints, source-backed data bindings, components, and uniquely resolved handoff screens.
- Validated WebP headers and palette constraints, and made optional 2D art providers report availability without network calls.
- Made tool detection side-effect-free; Windows tool discovery uses Git Bash instead of the System32 WSL launcher.
- Added a Windows CI job for the shared workflow test suites.
- `tests/routing-golden.test.sh` and `tests/registry-nulls.test.sh` are host-independent (Linux CI without a workspace): host path-form scenarios stay out of the golden, and the guard is compared with itself on the real registry.
- Point art and VFX implementation handoffs at the existing client `Assets/` root, document production-plan folder selection, and configure UTF-8 stdio for the executable asset manifest checker.
- Keep the base P4 checker fixture consistent by removing domains, modules, skills and contracts that depend on the removed authoring repository.
- Store the P4 checker snapshot used by the base regression proof so the proof works from an Orca worktree without Git metadata reachable in the Linux test shell.
- Run dependency graph behavior checks on fixed fixtures and assert the live graph remains acyclic with the required domain order.
- `factory-status.py` and `git-guard.py` accept a registry repo without a `remote` (absent or null); `check-registry.sh` tolerates modules without `docs` and fails when its path query errors instead of silently checking fewer paths.

## [1.1.1] - 2026-10-30

Patch release. Hardens testlab host guards, native server mode, failure summaries and soak analysis; targets run-checks at the invoking worktree with bytecode and canonical-checkout safeguards; isolates git environment state, accepts a Windows-form TMPDIR in netcode-headless and refreshes citations. No breaking changes or user action beyond the usual update command.

### Added

- testlab `failure-summary.json`: every run that is not a clean PASS writes a machine-readable triage next to
  `report.md` at the end of `analyze` (`lab/failsum.py`): verdict, earliest event (scenario time and wall-clock UTC),
  per failing/invalid check the earliest event, evidence files with line pointers, suspected layer
  (environment / harness / server / netcode / client / unknown) by documented rules, confidence, host guard events within
  +-10 s, and a next action. Derived output only: it never changes the verdict or a check result, and a build error is
  recorded in the file. `check_render_jumps` leaves its counted jumps in `ev["_failsum"]` for it (not part of the result).
  Rules and tables: `testlab/docs/FAILURE-SUMMARY.md`; tests on scrubbed excerpts of runs k4n5, ibz3, 9tgw, 3ng5:
  `testlab/tests/test_failsum.py`.
- testlab host guard: optional 1 s per-process CPU sampler (`hostprocs.ps1`, top 10) for S09-class runs, written to
  `host/procs.ndjson` with its own measured cost in `host/procs-summary.json` (about 0.2 % of the host). Evidence only:
  the `host_guard` detail gains a `proc_sampler` summary (INFO); it is not a guard. A scenario can turn it off with
  `proc_sampler: false`. Added so the 40-140 ms client stalls of run ibz3 (F28) can be attributed to a process.
- testlab: `--server-mode native` runs the game server as a Windows process built with the Windows dotnet, so its
  `Stopwatch` is the QueryPerformanceCounter the players use and not the WSL VM's clock (F23 finding B, F24B, soak
  `3ng5`). The server is built from the configured checkout (`aot` when the MSVC linker exists, else self-contained
  ReadyToRun `r2r`; recorded as `server.native` with SDK, source sha and exe/dll hashes), takes the environment of the
  scratch compose service (`docker compose config`, with only the container-network addresses rewritten to the
  published localhost ports) and registers `127.0.0.1:<game port>` in the scratch Redis. The scratch stack runs
  without its `gameserver-dotnet` service (a leftover container and its registry entry are removed), the status
  endpoints are addressed as `localhost` (a Windows `HttpListener` answers 400 to `Host: 127.0.0.1`), CPU/memory come
  from a process sampler and the server console is kept as `server/gameserver.log`. Provenance gains
  `server.runtime` (`docker` or `windows-native`) and `image_id = native:<exe sha256>`; the report and
  `results.json` state the runtime. S18 (netem) is refused in native mode. Docker mode is unchanged.
- testlab: host guard G6 detects sustained server clock-rate steps against the harness monotonic clock and marks
  the run INVALID while preserving any FAIL evidence. The policy thresholds are documented as unvalidated and
  cite the F23 9mre soak evidence. The rate is measured over sliding windows of at least 2 s and needs three
  consecutive same-sign windows, so polling jitter and a single late poll do not fire it. Stalls are excluded with
  a 3 s margin (the achieved-rate meter lags by its 2 s window) and a 35 % plausibility cap. The five 9mre
  episodes are documented: two attributed, one start-up, two unexplained.
- **testlab host guard** marks contaminated soaks INVALID (`feat(testlab)`): `lab/hostguard.py` + `hostguard.ps1` sample the host every 5 s
  (AnyDesk processes with role, host CPU/DPC/interrupt, build-tool and Defender load, the guard's own CPU) and tail AnyDesk's log for
  session events, all passive and read-only; AnyDesk is never stopped. Guards G1-G5 (session start or active session, new AnyDesk process,
  AnyDesk CPU burst, foreign build load, blind guard) inside `start_scheduled - 30 s .. end + finish_grace_s` make the new always-on
  `host_guard` assertion, and the run, **INVALID**: ordered before FAIL, never PASS, exit code 2, FAIL evidence kept and named. New
  `testlab.py preflight-soak` (P1-P7) and an automatic P1-P6 preflight for scenarios with `requires_clean_host` (S09 v5, which refuses to
  start on a FAIL; `--require-clean-host` for others). The rule becomes "no `AnyDesk.exe --backend` and no session event from T-2 min to
  the end; resident processes allowed". `host_quiet` names the nearest guard event for every single-process frame of 1 s or more.
  Limits are policy, unvalidated (`testlab/docs/THRESHOLDS.md`); no scenario threshold or pass rule changed. Tests: `HostGuardTests`
  (real scrubbed `ad.trace` fixture).

### Changed

- testlab `host_guard` G3 is relative to the preflight-measured resident AnyDesk baseline: it fires above
  min(1.0 %, max(0.5 %, baseline max x 2 + 0.3 %)) for 2 consecutive samples (policy, unvalidated). The 1.0 % cap keeps a
  session-like burst (>= 1.36 % seen in F28) firing however noisy the preflight was; a preflight resident max at or above
  the cap fails P2 and the run does not start (RV-F29 B2). After the reboot the idle resident
  `front` process runs 0.18 % mean / 0.33 % max (0.03 % in F19), which the fixed 0.5 % limit flagged. The baseline is recorded
  in `host/preflight.json` (`anydesk_baseline`) and in the guard stats. G1 and G2 are unchanged and still detect sessions;
  ibz3 stays INVALID on G1 (three real outgoing sessions).
- skills: refresh TickLoop citations after the server TickSleeper pacing change, and describe
  the Windows high-resolution timer path accurately.
- `testlab` AnyDesk trace tailing now detects replacement by file identity and a prefix fingerprint, rereads rotations from byte zero even when the replacement is equal to or larger than the previous offset, and records unavailable log identity as G5 blind evidence.

### Fixed

- `server-realtime` gameserver reference: `SimulationPhaseFactory` citation follows `Program.cs` on server `origin/develop` (1136 -> 1143).
- `netcode-headless.sh` now recognizes usable `C:/...` and `C:\\...` `TMPDIR` paths on Windows Git Bash,
  keeping temporary build and TRX data outside the Netcode source tree; candidate checks repeat every TRX
  parser case with a Windows-form temporary directory.
- testlab `graceful_leave` (RV-P5-1): the legacy "no C3 events, no judgement" waiver is removed, so missing client
  evidence can no longer make the check PASS. Only a viewer whose own latest `entity_added`/`entity_removed` event
  for the leaver before the quit is an add is judged: it must receive the removal within the bound or the check
  FAILs. If no viewer is evidenced as holding the leaver at the quit (all removed it earlier, or none logged any
  lifecycle event, or there is no other client), the result is INCONCLUSIVE. This supersedes the sentence below
  that said an already-dropped viewer alone is INCONCLUSIVE beside judged ones: a judged viewer that got the
  removal now gives PASS and lists the others as `not_in_view_at_quit` / `no_lifecycle_events`.
- testlab S08G (P5-S08G-LEAVE): the graceful-leave scenario failed on `rpg-mmo-server` `00ef906` (runs ccle, 4lz1)
  with `others_removed_after_s[1]=null` although the server and client 0 removed the leaver in 0.03/0.05 s. Root
  cause was scenario geometry, not a missed removal: the leaver walked 10 s to x~49.6 while the stationary viewer
  stood at x~-1.6, 51.2 units away against the 50-unit area of interest, so that viewer had already received the
  `removed` event at 11.9 s and held nothing at the 15 s quit (the pass on `ee80bb8` ended at 50.1 with the
  viewer 0.8 closer, a coin flip). S08G v2 walks 6 s (about 30 units), inside every viewer's interest.
  `graceful_leave` now reports a viewer that had dropped the leaver before it quit as `not_in_view_at_quit` and
  leaves the check INCONCLUSIVE instead of FAIL; a viewer that held the leaver and never saw it removed still
  FAILs, and the thresholds are unchanged.
- run-checks: checks no longer write into the user's protected main checkout when invoked from an agent's linked
  worktree (incidents 2026-10-25 and 2026-10-29: `.github/scripts/__pycache__/*.pyc` appeared in the canonical
  `rpg-mmo-server`). Root causes: `python3 -m py_compile` (registry `server.*` check) writes `.pyc` even with
  `PYTHONDONTWRITEBYTECODE=1`, and nothing verified which checkout a run touched. Now: (1) `run-checks.py` and
  `factory-context.sh` take `--repo-path <dir>` and otherwise resolve the target from the cwd's git toplevel (path
  comparison is case/slash/symlink-insensitive via `same_path`); the registry canonical path is used only when the cwd is
  outside every worktree of the repo, and the output (`Target checkout:` line, `NOTE:`, JSON `resolution`) says so;
  (2) every check runs with `PYTHONDONTWRITEBYTECODE=1` and `PYTHONPYCACHEPREFIX=<scratch>/pycache` (forwarded through
  `WSLENV`), and the registry's `python3` check commands use `-B`; (3) when a run targets a worktree, the canonical
  checkout's `git status --ignored` is snapshotted (with size/mtime) before and after, and any difference adds a FAIL
  row `runner/canonical-checkout-guard` (exit 1). `tests/worktree-target.test.sh` covers all three and fails on the
  previous runner (a `.pyc` appeared in the checkout, no guard row).
- tests: no test can rewrite the shared git config of the repository it runs in. Root cause (reproduced): a git
  process that runs a command (`git rebase --exec tests/run-all.sh`, `git bisect run`, a hook) exports `GIT_DIR`; the
  fixtures' `git init <tmpdir>` then re-initialised the CALLER's repository, and from a linked worktree that wrote
  `core.worktree = <worktree path>` (or `core.bare = true`) into the main checkout's `.git/config`, so every git command
  in the main checkout failed (`Invalid path '/mnt/c/Users'`; seen on `rpg-factory` pointing at `f27-cite`).
  `scripts/lib/compat.sh`, which every test sources, now unsets the `GIT_*` state variables. `tests/run-all.sh` hashes
  the shared config before and after the run and fails with `shared git config changed during the run` (diff and a
  copy of the old file in the message); `tests/git-env-isolation.test.sh` fails without the fix.
- testlab H1-H7 (M1 failure matrix, section 7c; no recorded verdict changed, no threshold weakened):
  - H1: viewer (outgoing, `front` process) AnyDesk sessions now have an end and a duration, from the
    `ad_app.control - Session count: (total, incoming)` lines (new event type `session_count`, not a guard input). The
    `host_guard` detail lists them under `anydesk_outgoing_sessions` with the share of the window; a session with no end
    line is reported open with an unknown duration. (F28 assumed 20 s sessions; they were 15:00 each.)
  - H2: `cross_client_convergence` leaves out the samples of a client that is not a valid observer: a net_state other
    than InWorld (`RECONNECT`), a 1 s gap in its sample stream or a frame of 1 s or more (`CLIENT`), from 0.5 s before to 2 s
    after. `detail.skipped_client_gaps` lists the spans and `measured.skipped_client_gap_samples` counts the samples. A
    divergence outside those spans still FAILs. (k4n5: the freeze and the reconnect of the affected clients are skipped; the 4.6 s in between,
    where client 0 drew an entity up to 8 u off before it noticed the dead link, is NOT excluded and still FAILs - no causal link between a
    freeze and a later reconnect is assumed.)
  - H3: `host_quiet` INFO tiers, never graded and never PRODUCT: host-wide stalls of >= 30 ms ending within 50 ms in
    >= 2 client processes (`host_stalls_info_30ms`, `detail.info_stalls_30ms`) and single-process freezes of >= 1 s
    outside a graded stall (`single_process_freezes_1s`, `detail.single_process_freezes`). The 250 ms rule is unchanged.
  - H5: `render_jumps` reports `detail.hop_sizes_by_boundary`: counted jump sizes per scripted step boundary (time modulo
    `repeat_cycle_s`, within 3 s). Reported only; grading is unchanged. A size-based rule is proposed in
    `M4-HARNESS-H1H7.md`, not implemented.
  - H6: a `requires_clean_host` scenario refuses to start (exit 3, before a run directory or the stack exists) unless
    `--player` and `--server-repo` are named, and, with `--expect-player-sha` / `--expect-server-sha`, unless the player
    (`testlab-build.json` `client_head`) and the server checkout are those commits. `run.json` records `soak_inputs`. Other
    scenarios keep their defaults. (`lab/soakinputs.py`.)
  - H7: at guard stop the session-relevant `ad.trace` lines (from one hour before the guard started; peer text of
    accept/authenticate lines redacted) are copied to `host/ad-trace-excerpt.txt`; `guard-summary.json` records the outcome.
  - Tests: `testlab/tests/test_m4_harness.py` (30 tests, 28 fail on the previous harness). The frozen-reference comparison in
    `test_lab.py` ignores exactly the additive reporting keys above; verdicts and every other field still have to equal it.
- testlab `analyze` now isolates the full failure-summary build/write step: non-`OSError` exceptions no longer escape,
  and a minimal summary records the exception type/message and preserves the original verdict and exit code when possible.
- testlab `render_jumps`: a LOCAL snap at a server-confirmed respawn of the same player is explained by the respawn and
  counted as `local_respawn`, bound tightly (RV-F29 B1): the snapshot carrying the new position has a world tick inside
  [HP 0 probe tick, max-HP probe tick + 2], the received step is >= half the rendered step and points where the rendered
  snap went (cos >= 0.7), and one respawn explains one snap. Run ibz3 st 911.107 (rendered 1.088, received 0.8407, 3.4 %
  short of the old 0.8 x rule) failed a real respawn. A later unrelated snap, a second snap, another player's respawn
  and a local major without that evidence still FAIL.
- testlab `entity_lifecycle`: the id-reuse tolerance is per entity type. A projectile uses its content (or measured)
  speed x 0.15 s + 0.2 instead of the player `max_speed`, so a first draw one snapshot ahead after a client stall no longer
  fails (ibz3 proj-17, 1.33 u from spawn vs 1.1). The stale-buffer detection is kept: a first draw at or near the previous
  incarnation's last position still FAILs.
- testlab: S01 no longer FAILs `kcp` (3 `dead_link` closes) and `redis` (6-9 session keys for 3 users) because the WSL
  distro stopped under the run (runs 6qgq, ii3h, jmag, hj3f, imed; native and docker alike). WSL terminates a distro with no
  open `wsl.exe` session; dockerd and the scratch stack died with it mid-run (gateway "shutting down gateway", Redis
  reloading its AOF) and every harness call into WSL stalled for the reboot. The run loop then overran the scenario end:
  `metrics-end` was scraped after the clients quit (their teardown `dead_link` closes counted inside the window), and
  the sessions of the killed gateway stayed in Redis for SessionTTL (1 h). No product bug: the server, Netcode and client
  behaved the same in the passing runs. `run`/`suite`/`sweep` now hold one `wsl.exe` keep-alive session from the first
  stack action to after the teardown (`stack.WslKeepAlive`, recorded in run.json as `wsl_keepalive`); a fresh world starts
  with no `session:*` keys in the scratch Redis (`stack.clear_session_keys`, count in `stale_session_keys_cleared`); and
  a `kcp` or `redis` check whose evidence was taken after the window (timeline `metrics_end_late` / `redis_late`) is
  INCONCLUSIVE, not a FAIL or a false PASS. No threshold or assertion was changed.
- testlab host guard: G1 no longer reports false historical sessions ("active at window start") after the AnyDesk
  log rotates. The tailer re-read the file from 0 and re-emitted its Accepts; each duplicate queued a phantom
  session that a later close ended, shifting every pairing (run 9tgw: sessions 'ended' 13:16:14Z hours late). Events
  are now de-duplicated in the tailer and in `sessions_from_events`, and every open-ended session counts as active at
  the start only with a live backend process sample at or after the window start (matching PID when known). A real
  session in the window still fires G1, G2 and G3.
- testlab: a native game server that cannot be stopped at teardown no longer leaves a green exit and a running
  stack: `stack.down` still brings the scratch backing stack down, then raises, and `_with_stack_teardown` turns an
  exit of 0 or 4 into 3 (a run's own 1 or 2 is kept) and keeps the error in `<runs>/stack/teardown-failure.json`.
- testlab: native `--build-server` builds the Nakama plugin for the version of the resolved scratch compose Nakama
  image (what `.env.scratch` decides) and not for the scenario env or a fixed 3.40.0, so the plugin ABI matches the
  running Nakama; an unreadable image fails the build instead of guessing.
- testlab: native mode with `--build-server` no longer runs `stack.sh --scratch up` (its `up` ends in `dc up -d`
  for the whole project and started the container `gameserver-dotnet` before the native server replaced it).
  The Nakama plugin and the gateway image are built directly (the two builds of `stack.sh do_up`; the game server
  image is not built), then only the backing services are started. Regression tests prove no native path, with
  `build` true or false, runs the full-stack `up`. A native server that is still alive after `kill_tree` and the
  15 s wait now keeps its state and fails the stop with an error (the next run is refused until the process is
  gone) instead of dropping its pid record.
- testlab: the host guard kept sampling only until the players exited, not until the measurement window end
  (scenario end + `finish_grace_s`), so every full-length soak ended with a 20 s blind gap and G5 INVALID. The runner
  now holds the guard until a sample at or after the window end exists (`HostGuard.hold_until`); a sampler that does
  not deliver is still reported by G5, and the window is unchanged.
- AnyDesk session pairing keys service fibers by (service pid, fiber): after a reboot the service restarts its fiber numbering, and the new session's auth/close lines bound to an old, closed session, so preflight P1 reported a closed session as still open (2026-10-30, sessions 02:31Z and 03:00Z). A still-open session stays open.
- P3 now lists every Orca Run and every worker page per Run, verifies each page's explicit Run scope, fails closed with the query error when coverage is incomplete, and records per-run worker counts and scope evidence.
- Follow-up P7F: P3 only coalesces same-workspace worker rows when their allow status matches, so a dispatch exemption cannot authorize a sibling worker; run.json coverage again asserts both agent and dispatch allow entries.
- Follow-up P7E: P3 fails closed on missing, malformed or unknown worker liveness; rejects malformed dispatch identities and dispatch exemptions that do not resolve to exactly one non-empty ID; keeps dispatch exemptions scoped to their worker row; records full matched worker identity; and prevents empty paths or worktree IDs from matching. README documents the supported Windows path normalization and that other path forms remain uncovered.
- Follow-up P7D: P3 treats settled supervised workers with live liveness, and abandoned workers with liveness other than exited, as ACTIVE-UNVERIFIED when their normalized workspace is absent from worktree ps. Wrongly typed worker fields fail closed; `--allow-dispatch` allows exact repeatable dispatch ids and records matches; settled detail is counted by task and terminal state while complete evidence remains measured. Shared settled-state constants drive implementation and threshold documentation.
- testlab soak preflight P3 now classifies supervised workers from settled `workerState` (`succeeded`, `failed`, `cancelled`, `stopped`, `abandoned`) and `dispatchStatus` (`completed`, `failed`, `cancelled`), independent of retained terminal accounting. Settled dispatches are reported without blocking, while missing or unsettled task states remain ACTIVE; live worktree agents still block. P3 continues to read every worker-list page, fail closed when worker-list is unavailable, deduplicate active worktree/worker evidence, and store allow-list resolution in run.json.
- testlab P3 regressions now assert that repeated worker cursors, `hasMore` without `nextCursor`, and repeated run-list cursors make the worker inventory unavailable and P3 FAIL with the pagination reason.

## [1.1.0] - 2026-10-24

Feature release. Adds `testlab/`, autonomous multiplayer gameplay tests with real rendered Unity clients (scenarios
S01-S18 on an isolated scratch stack, delivery analysis, malformed input, churn and packet impairment), and one
parallel-work policy (`skills/factory-core/references/parallel-work.md`: the main session is Lead/Integrator, one
worktree per task, QA and review on stable candidate commits, Orca as the preferred coordinator). The check runner
now fails closed: pollution is attributed per check, a timeout kills the check's whole process tree and FAILs when
that cannot be confirmed, wire-parity and Netcode headless test the candidate checkout and print its SHA, TRX results
need a Completed/Passed outcome with executed tests and no failures, and checks receive the workspace and checkout
as Git Bash or WSL paths. The snapshot routes only the files a task writes (`--paths`); uncommitted changes are
shown as the user's baseline. Also: truthful evidence scope, skill `allowed-tools` lint, guards for linked worktrees
outside the workspace, a Windows lock retry budget for state files and refreshed skill citations. Update the plugin
(`claude plugin marketplace update rpg-factory && claude plugin update rpg-factory@rpg-factory`) and start a new
session. Evidence recorded by 1.0.5 re-grades once as STALE (`check scope changed`).

### Changed

- Refreshed Netcode client guidance for v0.49.0: KcpCrypto reuses per-session crypto state, subscribers are isolated, and snapshot speed distinguishes absent (`NaN`) from present zero; documented the server unknown-type counter, kick-reason drain, and readiness/release runbooks.
- Clarified that `factory-status` derives client and package-CI pin versions from repository state instead of storing moving pin versions in registry prose.
- Updated drifted client, server, and Netcode skill citations to match their integration branches, including client `origin/develop` at `45634b1`.
- `testlab analyze --delivery` now fits server/client clock mapping independently in 10 second windows using one minimum-delay sample per 1 second bin. It reports relative excess above each window's minimum envelope and the empirical p95 fit error bound; absolute one-way delay remains explicitly unavailable, and poor fits yield no delay values or PATH attribution.

### Added

- **testlab S16 judges the undefined-message-type case** on `gameserver_messages_rejected_total{reason="unknown_type"}`
  (rpg-mmo-server #490, `76aa973`): the `malformed_input` rule gains `rejections_counter` (default `gameserver_inputs_rejected_total`), the
  `unknown_type` case asserts the counter rises by 1 and the session stays open, and a server without the series leaves the case
  INCONCLUSIVE (not FAIL). S16 version 2; S16 can now PASS (two live runs against server `7c412e4`, see `testlab/docs/COVERAGE.md`).

- **testlab scenario S18 (packet impairment)**: loss, delay, jitter and reordering on the game server's UDP path, with two rendered clients
  moving, a 30 s clean baseline, a 60 s impaired phase and a 30 s recovery.
  - `testlab/lab/netem.py` shapes with `nsenter` + `tc netem` inside the scratch game server container's own network namespace (UDP port 9000
    only, both directions: `prio` + netem on `eth0` egress, `ingress` redirect to a per-container `ifb0` carrying the same netem). No compose
    override, no capability added to the server, no host-wide qdisc, `/status` and every TCP connection unshaped. Removal is guaranteed and verified:
    `finally` in the step, the runner's own `finally`, a detached watchdog process that deletes the qdiscs after the planned time + 45 s, and a leftover sweep
    in the preflight. Needs passwordless `sudo` for `nsenter`/`tc` in WSL (the preflight says so before any player starts).
  - New checks in `testlab/lab/analyze_netem.py`: `netem_applied` (tc loss counters within 3 sigma of the configured loss, clients' round-trip
    time up), `netem_cleanup`, `netem_retransmits` (server KCP resends rise only while impaired), `netem_snapshots` (per-phase gap and rate limits),
    `netem_prediction` (hard snaps, corrections, keyframes per phase) and `netem_convergence` (clients draw the same positions again within 10 s of the removal).
  - `kcp_health` accepts `"max_dropped": null` (inbound drops reported, not judged); `cross_client_convergence` accepts `until_s`.
  - Thresholds, each with its derivation or marked "policy, unvalidated", and the impairment profile with its source (CORE-BASELINE-V1.md) are in
    `testlab/docs/THRESHOLDS.md`; the `robustness` suite includes S18; 63 unit tests in `testlab/tests/test_netem.py` (run by `tests/run-all.sh`).

- **testlab scenarios S16 (malformed input) and S17 (churn)** with a raw-client harness step.
  - `testlab/lab/rawclient.py` joins the scratch stack like a client (gateway auth, enter world, KCP join, JSON envelopes) and can send
    frames a real client never would; `testlab/lab/rawprobe.py` runs it from a scenario disruption (`raw_malformed`, `raw_churn`) on its
    own thread and records `rawprobe.ndjson` (part of the provenance manifest). The step records; the analyzer decides.
  - S16 sends 11 malformed cases (length prefixes over the 1 MiB limit, zero length, truncated frame, undefined and out-of-range type, garbage
    protobuf, out-of-range movement, attack out of range, cast inside the cooldown) while two rendered clients play. New checks:
    `malformed_input` (each case refused or closes only its own session, with the server counters that moved), `server_alive`,
    `client_sessions`. A `stays_open` case without a `rejections` rule grades INCONCLUSIVE (the session surviving does not show the
    input was refused). The undefined-type case was that case until rpg-mmo-server #490 added the counter (see the S16 entry below).
  - S17 runs 10 cycles of silent drop plus rejoin and graceful leave plus rejoin, then waits out the server's longest hold. New checks:
    `churn_cycles`, `churn_ghosts`, `player_count_baseline`, `redis_leak` (Redis session, registry and map-member key names before and after).
  - Thresholds and their derivations are in `testlab/docs/THRESHOLDS.md`; a new `robustness` suite runs both.
  - 43 unit tests in `testlab/tests/test_lab.py` (raw client against a UDP peer, step helpers, every check's pass and failure modes,
    scenario timelines); `testlab/README.md` and `testlab/docs/COVERAGE.md` document them.

- **`testlab/`: autonomous multiplayer gameplay tests with real, rendered Unity clients.**
  `python3 testlab/testlab.py run|suite|sweep|analyze|build-client|build-loadtest|stack|clean`.
  - It starts the isolated scratch stack (`stack.sh --scratch` + `STACK_SCRATCH_EXTRA_ENV`) and
    launches N players with distinct devices.
  - It drives them through scenario files (S01-S10: bootstrap, idle stability, movement and
    collision, combat, crowding, replication, load sweep, reconnect, soak, regression replay)
    through the client's `IGameplayInputSource` seam. No focus or keyboard is needed.
  - It records client traces and server-authoritative positions (`/debug/entities`) and grades
    every assertion PASS / FAIL / INCONCLUSIVE / INFO with source, sampling, threshold and
    artifacts. Missing evidence is never a PASS.
  - Exit codes: 0 PASS, 1 FAIL, 2 INCONCLUSIVE, 3 harness error.
  - Design, commands, artifacts and triage: `testlab/README.md`.
  - `tests/run-all.sh` runs its unit tests (`testlab/tests/test_lab.py`) and loads every scenario.
  - Crowd checks for rpg-mmo-server#469: `spawn_overlap` (no fresh or respawned player starts
    within 0.5 units of another), `enemy_pursuit` (an enemy far from every player heads for the
    nearest one; settled-crowd speed relative to its target). `enemy_crowding` overlap is a failure
    where the scenario declares separation (S02, S05, S10). Concentration on one player is INFO
    unless a scenario sets `share_is_failure`, because it follows the nearest-player rule.
  - `render_jumps` classifies a jump as a server teleport when the client's own received stream
    shows the same step, and gives host stalls a 1 s tail window, so a respawn the server probe
    aliased is not counted against interpolation or prediction. A received step counts only when
    no entity could walk it in the server ticks between the two samples.
  - `enemy_pursuit` is judged on isolated enemies; crowd steps (separation, queueing) are reported.
    `inputs_consumed` leaves server respawns out of a move segment. Evidence minimums make sparse
    pursuit or spawn evidence INCONCLUSIVE.
  - `--player` accepts a build directory; sweep files are named by scenario id; the atomic JSON
    write retries while a player holds the file (Windows).
  - **Run provenance.** `run.json` records factory, server and client commits, the scratch server
    image id, the embedded Netcode commit (`VERIFY-PROVENANCE.txt`), player exe and managed-code
    hashes, scenario id, version and file hash, host load at start and end, start and end, and a
    sha256 manifest of the evidence files. Every evaluation appends a `provenance` assertion: a
    missing record, a missing field, a run id that is not the directory's, or evidence changed
    after the run is INCONCLUSIVE. Runs recorded before this change therefore re-grade
    INCONCLUSIVE instead of PASS. `results.json` names the run it analyses (`analysis` block);
    `analyze --out DIR` leaves the run directory untouched.
  - **Missing evidence is never PASS, for every check** (tested per check with absent and empty
    inputs). Fixed: `client_log_clean` passed with no player log, `snapshot_cadence` with no
    clients, `render_jumps` with a client's events missing, `players_online` and `redis` with
    zero clients.
  - **Cleanup.** `run`, `suite` and `sweep` stop the scratch stack when they finish, also on
    failure and Ctrl-C (`--keep-stack` keeps it). Ctrl-C stops the players, writes the run record
    and re-raises. Every docker action refuses a container outside `rpgs-*`, and a misconfigured
    `container_prefix` cannot widen the container filter to `rpg-*`.
  - **`leak-check <player>`** reports whether a built player contains TestLab code
    (`NDC.TestLab*` assembly, `CUVARA_TESTLAB`, TestLab type names) without building or running it.
  - **`analyze --delivery <run>`** (rpg-mmo-server#473): joins the server snapshot trace (C1,
    `--snapshot-trace` / `snapshot_trace: true` sets `GAMESERVER_SNAPSHOT_TRACE` and copies the
    file into `server/`) with the client trace (C2 `delivery.csv`, `render.csv`). It reports per
    client and 5-minute bucket the send and receive gaps, relative one-way delay, queue, drops,
    KCP retransmissions and send queue, and classifies every receive gap over 250 ms as
    SERVER_LATE, QUEUE, CLIENT, KCP, PATH or UNKNOWN and ALL-CLIENTS or SINGLE-CLIENT. It is
    diagnostic only.
  - `testlab/docs/COVERAGE.md`: readiness areas mapped to scenarios and checks, with the gaps.
  - **Factory-only coverage gaps closed (COVERAGE F1-F6).** New checks: `snapshot_order` (no
    backward or repeated world tick within a session), `enemy_bounds` (enemies inside the map
    file's bounds at the run's server commit), `enemy_budget` (live enemies within the budget
    the server reports), `render_freshness` (C2 snapshot age p99 within TargetDelay +
    MaxExtrapolation, 150 ms), `prediction_bound` (at most 6 hard snaps per client-minute,
    derived from the 2026-10-22 runs) and `server_config` (the scenario's `SIM_*` rates were in
    force). Each is INCONCLUSIVE on missing evidence. New scenarios S11 (resync after a
    game-server restart) and S12 (30/15 Hz tick rate). `snapshot_cadence` and
    `render_freshness` take `exclude_s` windows; `clients_in_world` takes `reentered_after_s`.
    S01-S10 gain `snapshot_order`, and `prediction_bound`/`enemy_budget` where they apply
    (versions bumped).
  - `build-client` writes a `netcode` block (embedded git HEAD or packages-lock hash) into
    `testlab-build.json`, so a build-client player's provenance names its Netcode commit.
  - **Client trace schema v2 and the client coverage hooks C1-C6** (client 299b6c8,
    `docs/TESTLAB.md`). `render_freshness` now grades the render clock that drew each frame
    (v2 `render_tick` / `clock_newest_tick`): p99 overrun past the newest consumed tick <=
    MaxExtrapolation (50 ms); v1 render.csv (empty `render_tick`) is INCONCLUSIVE. New checks
    `tick_adoption` (C1), `entity_lifecycle` (C3: no ghost after removal, reused ids drawn at
    their own spawn), `cross_client_convergence` (C4: same entity, same render tick, same place),
    `stall_recovery` (C2) and `graceful_leave` (C6); each INCONCLUSIVE without its hook's
    evidence. New scenarios S13 (client stall 500 ms and 2000 ms) and S08G (graceful leave);
    suite `readiness` (S11 S12 S13 S08G). Plan actions `stall`, `quit`, `reconnect`,
    `cast_at_point`, `cast_spam` are accepted; `clients_completed` takes `expected_outcomes`.
  - **`prediction_bound` grades only unexplained snaps.** Every snap is matched by world tick to
    a server respawn or teleport of the same player (/debug/entities); explained snaps are
    reported, the rest are graded at 4 per client-minute (fixed builds at most 2.0, pre-fix runs
    7.5 or more, derived from every stored run). It was 6 total snaps per client-minute, which
    counted correct respawn snaps as errors.
  - **Server hooks S1/S2/S4 (rpg-mmo-server #475).** Disruption `debug_kill` (POST /debug/kill,
    recorded with HTTP status and server tick in `disruptions.ndjson`; `requires_debug_kill`
    assertions are INCONCLUSIVE unless the kill was confirmed). Checks `debug_kill_respawn`,
    `input_rejections` (per-reason rejection deltas) and `cast_damage_bound` (refused casts do no
    damage; no hit beyond the projectile's reach; numbers read from content/abilities.json).
    `enemy_bounds` reads /status `map_bounds` first. Scenarios S14 (deterministic death and
    respawn) and S15 (combat negative path) join the `readiness` suite.
  - **Server image revision.** `--build-server` passes the server HEAD as `STACK_GIT_REVISION`
    (stack.sh stamps it into `org.opencontainers.image.revision`); provenance records the running
    image's label and is INCONCLUSIVE when it is missing or differs from the recorded server SHA.
    Server trees whose stack.sh predates the variable are recorded as `label unsupported`.
  - **Independent review R3 fixes.** Provenance hashes every evidence file (now including
    `disruptions.ndjson`) and checks each scenario's expected inventory: an omitted, unrecorded
    or changed file is INCONCLUSIVE. `analyze --delivery` fits each client's clock rate against
    the server's (the WSL VM clock runs about 7 % slow) and reports one-way delay as unavailable
    when the fit is poor. A run whose informational assertion would fail (S07/S07P memory) is
    PASS_WITH_WARNINGS (exit 4), never PASS; the report shows that and host load under
    "Qualified by". `testlab/docs/THRESHOLDS.md` (generated, kept current by a test) lists every
    limit with its source or "policy, unvalidated".
  - **Soak plan and classifier fixes (T06 findings).** S09 v4 repeats its 300 s movement and combat
    cycle for the whole `--duration` (`repeat_cycle_s`; earlier 1 h soaks were 5 min active, 55 min
    idle). `analyze --delivery`: a gap is ALL-CLIENTS when the other clients' gaps overlap in time
    on the server clock or in touching tick ranges; the KCP class also reads the 4 server rows after
    the late snapshot. On the 1 h soaks the clock fit stays poor (the WSL clock rate wanders
    1.073-1.090), so one-way delay is reported unavailable. Preflight fails fast when a server
    worktree has no `modules/nakama.so` and `--build-server` is not set.
  - **S08G analysis fixes (T34).** A client that left with `quit` writes `summary.json` after
    `Disconnect()`, with an empty user id; client user ids now fall back to the `in_world` event and
    run.json, so `graceful_leave` is judged instead of INCONCLUSIVE. `entity_lifecycle` no longer counts
    the sample of an entity's re-add frame (AOI re-entry) as a ghost of its earlier removal.
    `graceful_leave` names a dead_link session close (the polite disconnect frame never arrived).
  - `cross_client_convergence` skips pairs within 0.5 s of a server-side respawn or teleport of the
    compared entity (`teleport_window_s`): next to one, one client may already draw the new position.
    The final soak's maximum (18.56) was such a pair.
  - **Analysis memory bounded (T41).** A 1 h soak's analysis needed about 13 GB. Samples, events,
    inputs and server entity rows are now streamed from their files (`util.LazyNdjson`) instead of
    held as Python objects; trajectories and frames are float arrays; large value sets use
    `util.Distribution` (exact up to 1 M values, then 1e-6 bins); `cross_client_convergence` forms
    pairs per 60 s render-tick window; `entity_lifecycle` merges its windows with the sample stream
    (its quadratic next-event scan is gone). On a synthetic soak the peak drops from about 7x to
    2x the evidence size; results equal the pre-change analysis (frozen reference test).
  - **S13 stall catch-up rule (Lead decision).** On a client with a scripted stall, remote render
    jumps and remote divergence from the stall start through the frame after the frame whose dt
    contains the stall are not judged (the world moved while the process was frozen; one-frame
    binder drain lag); one local major correction per stall is allowed within 5 s, a second FAILs.
    Other clients and later frames are never excluded. COVERAGE.md statuses refreshed (T31 runs,
    hooks S1-S4 and the delivery trace done, graceful-leave fix upstream).
  - **Reverse scans stay bounded (review R5-1).** `reversed()` on a `util.LazyNdjson` read the whole
    file into a list; it now reads the file backwards in 64 KiB blocks (`util.iter_ndjson_reversed`,
    same rows and skips as the forward reader), so a last-match search (`_user_ids` on events,
    `_status_map_bounds`) holds one block and stops at the match. Server `status.ndjson` (~30 MB in a
    1 h soak) is streamed as well instead of held as a list.
  - **Session-aware delivery classes (T58).** `analyze --delivery` classifies a receive gap that spans
    a session change as RECONNECT (with the cause from player.log when known): a C1 `conn_id` change
    between its two snapshots, or a client `net_state` Ended / `reconnected` inside it. Joined by user id
    alone, the e26z post-reconnect gaps read as SERVER_LATE with retransmission deltas of -700..-1295.
    Bucket counter deltas (retransmissions, dropped) are summed per connection. entity_lifecycle and
    cross_client_convergence are unchanged: every e26z failure lies between a client's frame freeze and
    its reconnect (the backlog frame, and client 0's 31 s on a dead session), none after a session
    change, and the backlog-frame reuse is a real Netcode view defect (T57, Netcode 4520ccf). A test pins
    that an id added after `entities_reset` is not judged as a reuse.
  - **Predictor call trace (T56).** A scenario can turn on the client's Netcode predictor call trace per
    client (`"predictor_trace": true` in `client_defaults` or a `per_client` entry; plan `predictor_trace`;
    client d6c8839, Netcode >= 8986908). S13 (version 2) records it on client 0, the stalled client; the
    expected provenance inventory then requires `client-0/trace.ndjson`. New `testlab.py replay-trace <run>
    [--client N] [--out DIR]` (`lab/predtrace.py`) validates the trace (header and settings, frame markers in
    order, each `Reconcile` followed by its `ReconcileResult`, steering begin/end nesting, steering times) and
    lists the corrections the live predictor recorded per scripted stall. The exact replay stays with Netcode's
    `PredictorTraceReplayer`; the recipe is in testlab/README.md "Predictor call trace".
- `scripts/checks/netcode-headless.sh` finds the rpg-mmo-server holding the pinned Shared.GameLogic
  tag from a Netcode worktree too: `--server DIR`, else the Netcode dir's sibling, else
  `$RPG_FACTORY_WORKSPACE/rpg-mmo-server`; `--resolve-server` prints the choice
  (`tests/netcode-headless.test.sh`, in run-all).
- `netcode-headless.sh` fails when `dotnet test` fails or times out, whatever TRX it left
  (`NETCODE_HEADLESS_TIMEOUT`, default 900 s).
  - Paths given to the CLI in Git Bash form (`/c/...`) work with Windows Python. The README states
    which commands run in Git Bash and which also run in WSL, and that `build-client` regenerates
    the scene only with `--rebuild-scene`.
- `skills/measure/references/legs.md`: the testlab as the multi-client verification leg.
- **Parallel-work policy.** New `skills/factory-core/references/parallel-work.md` is the single policy for
  delegated work: the main session is the lead and integrator; one worktree per implementation task (Orca-managed
  or `isolation: "worktree"`, never a second clone); one Unity writer per client project; shared exclusive
  resources go to one task at a time and a task without one reports `NOT_RUN`; QA and review run in parallel on
  a recorded candidate commit; the lead re-verifies, integrates in dependency order and cleans up only its own
  worktrees, keeping task branches (`orca worktree rm` also deletes a merged checked-out branch, so it is only for
  disposable branches). Orca is the preferred coordinator (load `orca skills get orchestration`; never a decision gate for
  routine work) with Claude Code worktree agents as the fallback. Tags, releases, deploys and `human_gates` keep
  their rules; nothing new asks or blocks. factory-core `SKILL.md`, `git-safety.md` (rule 10 now points here,
  rule 5 names the lead's integration-branch merges), `report.md` (optional parallel-work ledger) and
  `.claude/CLAUDE.md` point to it without copying it.
- `tests/skills-lint.sh` checks the policy is linked, exists in one copy (by its signature phrases), contains no
  blocking wording (ask/prompt the user, wait for / get / require approval or confirmation, until the user,
  `permissionDecision`) and keeps the release and `human_gates` rules; `tests/parallel-policy.test.sh` proves those
  checks fail on a mutated plugin copy; `tests/orca-commands.test.sh` verifies every cited `orca` command against
  `orca --help` and every `--flag` cited with it against that command's `--help` (skipped when Orca is not
  installed, and in `--no-workspace` runs), including that `orca worktree rm` still deletes branches as the
  policy warns.
- `tests/skills-lint.sh` checks that a skill's `allowed-tools` covers every plugin script its `SKILL.md` or
  `references/` tell the agent to run (`${CLAUDE_PLUGIN_ROOT}/scripts/...` uses, and backticked bare script names in
  non-core skills; entry paths match as fnmatch patterns, a named interpreter must match the entry's);
  `tests/parallel-policy.test.sh` proves it fails on a mutated copy.

### Fixed

- Updated .NET game server skill citations to current `EcsWorld` definitions on server `origin/develop`.

- Enforced section citations for Markdown documentation in skills; line citations now fail the skill citation checker.
- **Task-scoped routing in the snapshot.** Without `--paths`, uncommitted changes are the user's baseline: the
  snapshot lists them with their modules but prints no Routing, `Next:`, gates or checks for them and says to route
  the task with `--paths <files the task will write>` (commits on a feature branch are still routed; JSON keeps the
  full resolution and adds `task_scope`). A module without skills prints an explicit `**Routing** no specialised
  lead - factory-core only; follow <CLAUDE.md>` line. An absolute `--paths` entry in a linked worktree of the repo
  maps to its repo-relative path; one in another repo or outside every repo gets a warning and is not routed as
  `<repo>.root` (exit 2 when no path is left). `--mode=plan`, `--lead=x` (any `--flag`) after `--paths` end the
  path list instead of being read as paths. `tests/routing.test.sh` covers each case on a throwaway workspace.
- **Runner timeout isolation.** Checks run in a Windows Job Object or process group with bounded cleanup verification; taskkill fallback verifies the captured process tree, and Git Bash is preferred on Windows while WSL bash receives validated workspace and repository environment values.

- Run wire parity and Netcode headless checks against the candidate checkout, report tested tree SHAs, and fail closed on unresolved trees or unsuccessful test hosts.
- Grade Netcode TRX results as successful only with a present Completed/Passed outcome, valid counters, executed tests, and zero failed, error, timeout, or aborted tests.
- Windows runner cleanup now treats inaccessible or otherwise unqueryable child processes as unknown and fails closed; TRX parser regression cases explicitly target their fixture checkout and assert the parser's diagnostic.
- Candidate check targets must be Git work-tree roots, preventing nested plain directories from inheriting a parent repository's SHA.
- Fingerprint dirty and untracked check outputs using a single stat's size, nanosecond mtime and mode (plus symlink target), avoiding reads of large untracked assets; pass Git Bash Windows paths as `C:/...` without requiring `cygpath` on Windows Python's PATH.
- Isolate each executed validation check's working-tree pollution, terminate its child process tree on timeout, and pass the resolved workspace and checkout through the check environment.
- The `unity-client-tech` `MainSessionDriver.Endpoint` citation now spans the whole adapter class (`MainSessionDriver.cs:237-364`); the old range began in `RunFlowAsync` and ended inside the class.
- **Windows lock retry budget for state files.** `fstate.read_json` and `write_text` retry a Windows sharing
  violation (`PermissionError`) for up to 2 s (backoff capped at 50 ms) instead of a fixed 8 / 5 attempts
  (~0.36 s / ~0.3 s), so a record held open under machine load no longer reads as missing (NOT_RUN) and a
  replace no longer fails; other platforms keep the short attempt count (`tests/session-state.test.sh`).
- Git and file guards: a linked worktree outside the workspace root (Orca worktrees, sibling dirs) whose main
  checkout lies in the workspace now gets that checkout's rules (tags, pushes, protected branches, secrets,
  generated paths), from its cwd or through `git -C`; before, every command there was silent. The worktree is
  found from its `.git` file (no extra git process); a main checkout outside the workspace stays silent.
- Git guard: `merge --ff-only` on a protected branch no longer warns (a fast-forward creates no commit), and
  `pull --rebase=false|no|off|0` (any case) is no longer treated as a rebase.
- `tests/skills-lint.sh`: the dev-tools and allowed-tools blocks fail closed - a crash of their Python check is a
  FAIL (it passed silently before), and skill files are read as UTF-8 (a non-ASCII reference crashed the check
  under a cp1252 locale). `tests/parallel-policy.test.sh` covers both. parallel-work.md says an
  `isolation: "worktree"` QA/review worker starts from the lead's HEAD and checks the candidate SHA first;
  the report template's dotnet row no longer asserts "0 failed".
- Skill `allowed-tools` now grant the scripts the skills run (netcode-client, pin-bump, server-ops, server-realtime,
  unity-package, wire-contract), so unattended runs no longer hit permission prompts.
- `git-safety.md` rule 5: PRs target the repo's default branch from `registry.json`, not always `develop`.
  `repos.md` and dotnet-gameserver describe the gameplay transport as KCP/UDP only (ADR-32). `report.md`'s template
  uses placeholders instead of asserting a `--status` result and example test counts. `parallel-work.md` section 6
  runs each QA and review worker in its own worktree at the candidate SHA. pin-chain.md and packages.md point to
  `pin-status.py` / `package-ready.py` instead of stale pin versions.
- **Truthful check evidence.** A check's identity scope now includes its own module's paths, so editing
  `backend/content/` makes a `content-loader-tests` PASS (run in `backend/gameserver-dotnet`) STALE; a record
  made under another scope is STALE (`check scope changed`), so pre-upgrade records re-grade once. `factory-status`
  grades evidence against the current registry definition (a changed `run` is STALE there too, like
  `run-checks --status`) and a record of a check no longer declared is STALE. Two modules sharing one command each
  get a record graded with their own definition and identity (both PASS right after the run). A check whose
  `needs` prerequisite did not PASS in this run (failed, skipped by `--only`, listed after it) is BLOCKED.
  `run-checks` exits 2 on an unknown `--tier`/`--only` name, a bad `--timeout`, a `--paths` entry outside the
  repo checkout and its linked worktrees (also `../` escapes and paths `factory-context.sh` rejects) and a path in
  another linked worktree of the repo (checks run in, and evidence describes, the checkout `run-checks` runs in:
  run it from that worktree), and prints `none registered` when no check is declared for the paths.
  `validation.md`, factory-core `SKILL.md` and the README describe the new `BLOCKED` meaning.

## [1.0.5] - 2026-10-22

Stability release after a full audit of 1.0.4 (hooks, session state, routing, install, release workflow). Hooks stay
advisory-only and never block; nothing asks for approval. Fixes: tag/push/destructive commands the guard missed
(git-bash `/c/` paths, shell blocks and functions, heredocs read by a shell, `gh --repo`), a missing or failing hook
script can no longer return Claude Code's blocking exit code, atomic and lossless session state and evidence under
concurrency, absolute `--paths` routing on Windows, stale-install detection, workspace worktrees in file-guard, and a
pre-tag `scripts/release-check.py`. Update the plugin (`claude plugin marketplace update rpg-factory && claude plugin
update rpg-factory@rpg-factory`) and start a new session. Evidence stored by 1.0.4 shows as NOT_RUN once (new
workspace key). No command-line or registry changes for users.

### Changed
- **Release policy wording matches practice.** The docs, skills, registry rule `no-tags`, snapshot header and guard
  advisories said agents never tag, while 1.0.4 was tagged and released by an agent on the user's explicit
  authorization. They now say: without explicit release authorization from the user in the current task, stop at
  READY_TO_TAG and the lead tags; with it, perform exactly the authorized merge, version, tag and release steps after
  the release checks pass on the tagged commit (never move, delete or reuse a tag). No behaviour change: the guard
  flags the same commands at the same advisory level, nothing blocks or asks. `run-all.sh` fails if the absolute
  "agents never tag" wording returns or a policy file drops the authorization rule.

### Fixed
- **Guard classification gaps.** `git-guard.py` stays advisory only (no permission decision, exit 0); these
  commands were missed or misread and now get the advisory they should:
  - Windows git-bash paths: `cd /c/...`, `git -C /c/...`, `/mnt/c/...` and such paths in the human-gate scan
    resolved to `C:\c\...` (no workspace, no advisory); they are mapped to drive paths first (`native_path`).
  - Shell reserved words hid git: `{ git tag v1; }`, `! git tag`, `if/then/else/elif`, `for/while/until ... do`,
    `f() { ...; }`, `function f { ... }`, PowerShell `if (...) { git tag v1 }` / `foreach (...) { ... }` (braces end
    a PowerShell command).
  - A heredoc read by a shell (`bash <<EOF`, `bash -s <<EOF`, `cat <<EOF | sh`) is analysed as commands; read by an
    interpreter (`python3 - <<PY`) and mentioning git/gh it is warn (opaque). Other heredocs (commit messages,
    `cat > file <<EOF`) stay data.
  - `gh --repo/-R/--hostname <x>` before the group or verb hid `release create`, `pr merge` and the `publish` gate.
  - Interpreter one-liners invoking `gh` (`python3 -c "...gh release create..."`, `node -e`) are warn like git.
  - Non-object JSON payloads (`[]`, `null`, `42`) crashed with a traceback (exit 1); stdin is read as UTF-8, so a
    non-ASCII cwd no longer breaks the workspace match on Windows.
  - `git tag --merged`, `--no-merged <c>`, `--no-contains <c>` and `--sort <full key>` / `--format '%(...)'` as
    separate words are listings (allow); a name after them, and the abbreviated `--sort -v:refname`, stay high.
  - Speed: read-only git subcommands (status, log, diff, ...) skip the per-repo git calls and the others are
    memoised per directory (30 x `git -C backend status`: ~1.36 s -> ~0.18 s on Windows); commands over 200 KB
    get one warn ("command too large to check") instead of minutes of parsing.
  - `factory-context.sh --mode <m>` run outside the workspace now records the mode (a stale read-only mode stayed),
    and the mode is only recorded when the script is actually run - `grep factory-context.sh --mode review` or
    `echo ... --mode plan` no longer switch it.
  - Wording: the module and `classify_gh` docstrings describe advisory levels high/warn, not deny/ask decisions.
- **Session state and evidence robustness.** Hooks stay advisory-only and never block; tests in
  `session-state.test.sh`, `run-checks.test.sh` and `factory-status.test.sh` cover each fix.
  - Evidence records and run records are written atomically (`fstate.write_json`, readers retry the Windows
    replace window); log and run-record names carry a pid + random suffix, so parallel or same-second runs never
    share or truncate a file. Only the newest 20 logs per check are kept (never the one the latest record names).
  - Valid JSON of the wrong shape in the evidence dir (`{"identity":"x"}`, `[1]`, no `state`) is treated as no
    evidence (NOT_RUN) instead of crashing `run-checks.py --status` and `factory-status.py`.
  - `run-checks.py --dry-run` writes nothing (no run record).
  - The auto-correction of an early tech skill to factory-core happens once per session even under parallel Skill
    calls (claimed by an exclusive `CORRECTED` file; the other calls get the lead-missing advisory).
  - The Skill hook's logs are one file per event (`SKILLS.d/`, `ADVISORIES.d/`): parallel appends lost lines on
    Windows. Legacy `SKILLS` / `ADVISORIES` files are still read. Read them with
    `factory_session.py --skills <session-id>` / `--advisories <session-id>` (used by git-guard.test.sh and dogfood.sh).
  - `MODE` is replaced atomically (no torn reads). A mode is recorded only when the command really runs
    `factory-context.sh` / `context.py` (`grep factory-context.sh --mode review` or `echo ...` no longer set it), and
    "do not implement" alone in Skill arguments is no longer a plan-mode declaration.
  - The hook prints its advisory / correction before logging; an unwritable log loses nothing the session sees,
    and with no usable session dir it advises without correcting.
  - Session ids go through one helper, `fstate.session_key()`: plain ids are unchanged, anything else (`..`, `.`,
    over 100 characters, characters a substitution would collide) becomes `s-<sha1>`.
  - A bare registry skill name (`go-backend` without `rpg-factory:`) is recorded and gated like the prefixed name.
  - `fstate.scratch()` skips a candidate whose `rpg-factory/` cannot be created; `persistent()` falls back to the
    platform temp dir (absolute on Windows too).
  - The evidence workspace key is the case-folded real path, and `run-checks.py` and `factory-status.py` resolve
    `RPG_FACTORY_WORKSPACE` the same way. Evidence stored under the old key shows as NOT_RUN once; rerun the checks.
- **Routing, install and docs.**
  - `factory-context.sh --paths` with an absolute (`C:\`, `C:/`, git-bash `/c/`, WSL `/mnt/c/`) or glob path
    routed nowhere on Windows (`relpath` returned backslashes, lead null). Paths are normalised to repo-relative
    forward slashes; another drive no longer raises. New routing scenarios (absolute forms, glob).
  - A missing hook script made python exit 2, Claude Code's blocking code. Every `hooks.json` command now ends
    with `; exit 0` (bash and PowerShell); stdout still passes through. run-all checks the wiring and runs each
    command against a missing and an exit-2 script.
  - `install-status.py` reported CURRENT for an old cache copy on Windows (backslash `CLAUDE_PLUGIN_ROOT` missed
    the `/.claude/plugins/cache/` test) and whenever the runtime version differed from the source; both are now
    RESTART_REQUIRED. `--session` never tracebacks on malformed `installed_plugins.json` /
    `known_marketplaces.json` and always exits 0. New informational note (doctor, `--json` `notes`) when the
    source HEAD is not the commit of tag `v<VERSION>` (`source 1.0.4 + N commits past v1.0.4`); no state change.
  - `file-guard.py`: linked worktrees of a workspace repo (`.wt-client-cleanup/`) get that repo's rules (via the
    git common dir); paths outside the workspace get no advisory even with `RPG_FACTORY_WORKSPACE` set; the mode
    advisory command is quoted with forward slashes; secret names match case-insensitively (`.ENV`).
  - `tests/dogfood.sh` looks for the session's `ADVISORIES` / `MODE` under both `fstate.scratch()` and
    `persistent()/tmp` (headless hooks on Windows Python 3.14 fall back to the latter).
  - Agent-facing wording said the hooks enforce or deny (snapshot mode line, `tag (deny)` in Human gates, pin-bump
    "denied by the guard", `.claude/CLAUDE.md`); it now says advisory (`tag (high)`), pin-bump names the explicit
    release authorization, README marks the pre-1.0.3 "denied" note historical and states the Windows scratch
    root, and the `--mode` / path forms are documented in the usage headers. run-all fails if
    `denied by the guard`, `hooks enforce` or `(deny)` returns in agent-facing text.
  - New `scripts/release-check.py` (read-only) gates a release before the tag (versions agree, CHANGELOG section,
    empty `[Unreleased]`, tag absent locally and on origin, HEAD == origin/main, clean tree; `--notes` prints the
    release notes) and verifies it afterwards (`--verify-tag`: annotated, `rpg-factory X.Y.Z`, at HEAD, VERSION).
    `tests/release-check.test.sh` (throwaway repo, local bare origin) runs in run-all; the order is in
    `.claude/CLAUDE.md` "Releases".

## [1.0.4] - 2026-10-22

Fix: tech skills stay behind their lead skills under the advisory-only hooks of 1.0.3, still without blocking or
asking. A tech skill requested before factory-core loads factory-core instead (auto-corrected); one requested
before its lead runs with an advisory. Update the plugin (`claude plugin marketplace update rpg-factory && claude
plugin update rpg-factory@rpg-factory`) and start a new session. No command-line or registry changes.

### Fixed
- **Skill order under advisory-only hooks (1.0.3 dogfood regression, `tech-go` and `tech-dots`).** With the
  Skill hook advisory-only, a model could load a tech skill before its lead; dogfood reported it as a failure
  and nothing showed whether the session corrected itself. The hook still never blocks or asks:
  - a tech skill requested **before factory-core** is auto-corrected: the call loads `rpg-factory:factory-core`
    instead (`updatedInput`; Claude Code honours it for the Skill tool - verified in a headless session, not
    documented for Skill), with an advisory naming the route command and the leads. Once per session (factory-core
    is then recorded), so it cannot repeat or loop. If a Claude Code version ignores `updatedInput`, the tech skill
    loads and the advisory still applies;
  - requested **after factory-core but before its lead**, it runs with an actionable advisory ("this call
    continues", the route command, the leads). No auto-correction there: two to four leads use each tech skill and
    only routing knows which applies.
  - every advisory is logged to the session's `ADVISORIES` file, and `SKILLS` records what actually loaded.
  - `tests/dogfood.sh` now grades what loaded (the "Launching skill" results, so an auto-corrected call counts as
    factory-core) and passes a tech-first session only with evidence: the hook's advisory for it, one of its leads
    loading afterwards, and a finished session. New scenario `tech-first` forces the auto-correction. The mode check
    reads the real session state path (`fstate.scratch()`, not `/tmp/rpg-factory`).
  - regression cases in `git-guard.test.sh` (early go-backend, early unity-dots, normal order, no second
    auto-correction, never a permission decision, the hook always exits 0) and `session-state.test.sh`.
- The README "Version" line still said 1.0.0 through 1.0.1-1.0.3; `run-all.sh`'s version check now covers it
  (VERSION == plugin.json == marketplace == CHANGELOG section == README).

## [1.0.3] - 2026-10-22

Hotfix: the hooks never ask for confirmation and never block; every former ask/deny rule reaches the agent
as an advisory. Update the plugin (`claude plugin marketplace update rpg-factory && claude plugin update
rpg-factory@rpg-factory`) and start a new session. Also ships the citation drift guard (PR #6, new optional
registry field `skills.<s>.cite_roots`) and the skill authoring workflow (PR #9). No command-line changes.

### Added
- **Skill authoring workflow.** Adding a skill meant about 25 hand edits across the registry, skills,
  tests, docs and evals, and several lists had already gone stale (unity-dots and netcode-client were missing
  from the factory-core tech list, the README diagram and tech table, and dogfood; go-backend and
  dotnet-gameserver had no eval grader).
  - `scripts/new-skill.py` scaffolds a lead or tech skill: `SKILL.md` with every section skills-lint
    requires and `SCAFFOLD:` markers, plus the registry entry (order after the existing skills of its kind,
    so it never outranks one in routing ties; module ownership or contract driver; `dev_tools.used_by`;
    `cite_roots`). It refuses anything it cannot validate and rewrites `registry.json` only when a JSON
    round trip reproduces it byte for byte.
  - `scripts/skill-touchpoints.py` (read-only, run by `skills-lint.sh --all`) checks that every skill is
    in the factory-core Skills section, the skill-contract diagram, the README diagram and tables,
    `.claude/CLAUDE.md` (names and counts), the plugin manifests' lead count, a routing scenario, a
    dogfood scenario and an eval grader - and that no `SCAFFOLD:` marker is left.
  - Repo-local skill `.claude/skills/skill-author/` (not a plugin skill): the order of work from the
    learning-loop gate to a green run-all.
  - The stale places were fixed; new dogfood scenarios `tech-dots`, `tech-netcode` and evals
    `go-single-test`, `dotnet-single-test`. The routing test's tech list and the Skill-hook test now come
    from the registry, so a new tech skill needs no edit there. `tests/new-skill.test.sh` (22 cases).
- **Citation drift guard (`scripts/checks/skill-citations.py`).** Skills cite product code by
  `path:line`; nothing checked those lines, and a smoke test after 1.0.0 found 9 of 12 sampled server
  citations pointing at the wrong code (e.g. `WriteLoopAsync` cited at `Connection.cs:841`, now 1019). The
  checker reads every line citation in `SKILL.md` and `references/*.md` (full paths, ranges, lists, bare
  `:N` continuations, bare basenames, `dots:`/`client:` and repo-name prefixes) and resolves it at each
  repo's integration branch (`origin/<default_branch>`, `--ref repo=REF` to override) - never the working
  tree. Each line citation needs an **anchor**, the symbol it shows written in backticks before it; the
  anchor must occur within the cited lines +/- 3, else `drift` (with `--suggest`, the corrected line).
  Lines past the end, missing or ambiguous files and line citations outside backticks fail too; a missing
  repo is SKIP. New registry field `skills.<s>.cite_roots` (schema + `check-registry.sh`) says where a
  skill's paths resolve. `skills-lint.sh` runs the repo-free part (`--offline`: backticked and anchored),
  `run-all.sh` the fixture suite `tests/skill-citations.test.sh` and the live check against the workspace.
  The rule is in `skill-contract.md` ("Line citations are checked against the code").

- `check-registry.sh` rejects duplicate keys in `registry.json`: they are valid JSON and jq and Python
  silently keep the last one (a duplicated `cite_roots` hid that another skill had none).

### Changed
- **Hooks are advisory only: they never ask the user and never block the agent.** Agents using the plugin
  still stopped for a human Yes/No: every guard rule returned a `permissionDecision` - `ask` (destructive git,
  any push, rebase, stash, human gates, file-guard rules) shows a confirmation prompt only a person can answer,
  and `deny` (tags and GitHub Releases, `gh repo delete/archive`, read-only execution modes, a tech skill before
  its lead) blocked the call. Now `git-guard.py`, `file-guard.py` and `factory_session.py --skill` never emit a
  `permissionDecision`. A match is returned as `additionalContext`
  `rpg-factory advisory (high|warn): <rule>` - `high` for the former deny class, `warn` for the former ask
  class - and the tool call proceeds through Claude Code's normal permission flow (the user's own settings
  are untouched). The classifiers and rule texts are unchanged; the policy in `git-safety.md` stays as
  guidance for the agent.
- Tests read the advisory level (`high` / `warn` / `allow`) instead of a decision, and every test command
  fails if any hook output contains `permissionDecision`. `tests/session-state.test.sh` adds direct probes
  (rebase, force push, tag, `gh repo delete`, `reset --hard`, multi-client, `kubectl`, a tech skill before its
  lead). `installed-safety.sh` still executes only commands with no advisory.
- `skill-contract.md` "New skill" names every required registry field (`order`, `used_by`, `cite_roots`).

### Fixed
- The skills' line citations, refreshed against the integration branches: drifted lines moved, every
  citation anchored, claims that no longer hold corrected.

## [1.0.2] - 2026-10-21

Fix: read-only inspection of a gated script (`sed -n`, `cat`, `grep`, `head`) no longer asks for a human
gate. Update the plugin (`claude plugin marketplace update rpg-factory && claude plugin update
rpg-factory@rpg-factory`) and start a new session. No command-line changes; the registry gains the optional
`human_gates[].read_only_exempt` field.

### Fixed
- **Human gates no longer ask for read-only inspection of a gated script.** The gate regexes match script
  names anywhere in a command, so `sed -n 300,340p Tools/verify-multiclient.sh` asked under `multi-client`
  exactly like running the script (same for `cat bench.sh`, `grep x backup.sh`, `head toggle-packages.sh`).
  New registry field `human_gates[].read_only_exempt` (schema): the git guard skips such a gate when the
  whole command is read-only (`factory_session.is_read_only`, the classifier the execution modes use). Set
  on every gate with a `match` except `secrets`, whose point is reading. Running, editing (`sed -i`),
  redirecting, or piping a gated script into a shell still asks.
- `is_read_only` accepts print-only `sed` (`N,Mp`, `/re/p`, `Nq`, with `-n`/`-e`/`-E`); `-i`, `-f`, the
  `e` and `w` commands, `s///` and multi-command scripts stay non-read-only. A read-only mode therefore
  allows `sed -n 10,40p file`.

## [1.0.1] - 2026-10-21

Hotfix: the tripwire and its workspace latch are removed. Update the plugin (`claude plugin marketplace
update rpg-factory && claude plugin update rpg-factory@rpg-factory`) and start a new session: hooks bind at
session start, so a running session keeps the old hooks until it is restarted. No registry schema or
command-line changes.

### Changed
- The execution-mode and tech-skill-order logic moved from `scripts/tripwire.py` to
  `scripts/factory_session.py` (Skill hook: `factory_session.py --skill`). Behaviour is unchanged.

### Removed
- **The tripwire and its latch, on purpose.** `tripwire.py` snapshotted every workspace repo around each
  non-read-only Bash/PowerShell call. Any ref or baseline-file change in that window, whoever made it,
  raised a STOP and latched the whole workspace for every session until the user ran `tripwire.py --ack`.
  In practice the Unity Editor saving `ProjectSettings/ProjectSettings.asset` latched it within minutes,
  during read-only commands, and blocked autonomous work in every session. Removed with it:
  - the SessionStart baseline scan, the `--pre` PreToolUse hook and the PostToolUse /
    PostToolUseFailure `--post` hooks;
  - the latch deny in `git-guard.py` (`latch_hits`) and `file-guard.py`, and the guard rule that denied
    `tripwire.py --ack` to the agent (`ack_hits`);
  - the file guard's "already dirty when the session started" ask, which read the tripwire baseline;
  - `fstate` latch, audit and activity paths and `ack_command()`; the doctor "Tripwire latches" section;
  - the STOP, ack and recovery instructions in `factory-core`, `git-safety.md`, `report.md` and the
    doctor command;
  - `tests/tripwire.test.sh`.

  State files left by older versions (`latch/`, `audit/`, `activity/` under the persistent state root, a
  session `LATCH`) are no longer read and can be deleted. `tests/session-state.test.sh` (new) checks that
  stale latch files block nothing (`git fetch --tags`, commits, writes), that no hook or script reads them,
  and keeps the state-path checks from the old suite. The git guard (tag deny, destructive-git asks, human
  gates), the file guard's other rules and the execution modes are unchanged.

## [1.0.0] - 2026-10-20

First stable release. Supported environments: Linux, WSL and Windows (Git for Windows bash with native
Windows Python). No registry schema, hook or command-line changes are required of users:
update the plugin (`claude plugin marketplace update rpg-factory && claude plugin update
rpg-factory@rpg-factory`) and restart the session. Legacy single-file latches from 0.5.0 and earlier are
still read and migrated on `--ack`.

### Added
- **Game rules live only in Shared.GameLogic (ADR-10).** Until now the rule existed only in the
  client's stale `unity-netcode` agent. Factory said nothing when a client or package change
  reimplemented movement, combat or validation logic that the server must agree with. New module rules
  cover `client.scripts`, `netcode.runtime` and `unitydots.runtime`: never copy a game rule. Stop the leg
  and hand the rule to `server-realtime`, then to `pin-bump`. A new rule on `server.gameserver-dotnet`
  says that logic the client must reproduce goes into `Shared.GameLogic`, not only into `GameServer/`.
  `client-integration` has a new workflow step and a new hand-off row, and `server-realtime` step 2 names
  the placement. `tests/routing.test.sh` asserts that each of the four snapshots carries the rule.
- **Tech skill `unity-dots`** (Entities/Burst/Jobs in UnityDots and the client): the ECS-vs-classic
  decision (ECS for many homogeneous per-frame entities; services, UI and request/response state stay
  VContainer + UI Toolkit), the group tree and bootstrap install, `SystemOrderVerifier`, the package ECB
  singleton, the measured `ParallelScheduling` thresholds, archetype-stable spawning, sync points,
  allocators, change filters and ECS tests, every claim cited. References `dots-patterns.md` and
  `ecs-review.md` (the review checklist). Used by unity-package, client-integration and measure.
- **Tech skill `netcode-client`** (com.cuvara.netcode on the client): TCP gateway hop vs KCP-only
  gameplay and its PlayerLoop pump, KcpCrypto (CRC, no integrity) vs the sealed session, codecs,
  snapshot interning and merge, the interpolation clock, movement prediction and reconciliation with
  clock steering, reconnect policy, per-packet allocations, the headless suite. Replaces the client's
  stale `unity-netcode` agent. Used by unity-package, wire-contract, client-integration and measure.
- `unity-client-tech` reference `ui-toolkit.md`: View/ViewModel/Presenter, one-way binding, the
  package list adapters and virtualization, screen flow and subscription lifecycle, the two ways game
  state reaches UI, VContainer scopes and lifetimes. ECS idioms moved to `unity-dots`.
- `measure` reference `client-profiling.md` (markers, Performance Testing, MCP `profiler-*` as point
  samples, no budget without a baseline) and `legs.md` sections for server profiling, the seeded
  network-adversity suites and soak (NOT_AVAILABLE until a harness exists).
- `server-realtime` reference `gameplay-systems.md`: where combat, abilities, statuses, inventory,
  loot and content live, the authority checklist for a new input or command, SGL determinism, and the
  known structural debt.
- **Fast check `sgl-determinism`** (`scripts/checks/sgl-determinism.py`, module
  `server.shared-gamelogic`): fails on any `Math`/`MathF` transcendental in Shared.GameLogic (ADR-10),
  ignoring comments and strings. Fixture tests in `run-all.sh`.
- Registry facts `entities-version`, `burst-version`, `collections-version`, `unity-physics-version`,
  `vcontainer-version`, `unitask-version`, `perf-testing-version`; dev tool `dotnet-diagnostics`
  (`dotnet-counters` / `dotnet-trace`, optional, fallback the server's OTel metrics).
- Evals `dots-spawn-system`, `prediction-reconcile-bug`, `claim-faster-frame`, `inventory-list-screen`,
  `new-command-authority`, `ecs-or-service`; routing scenarios for the new tech skills.
- **CI.** `.github/workflows/tests.yml` runs `tests/run-all.sh --no-workspace --no-claude` on every pull
  request and push to `main` (read-only token, pinned actions, log artifact, FAIL/SKIP summary). The
  runner has no RPG MMO workspace, so workspace checks show as SKIP there; `tests/run-all.sh` with the
  workspace is still required locally before a release.
- **Stash audit.** A visible `git stash` (the approved path) is appended to `audit/<workspace>.jsonl`
  with session, tool call id, command and the stash SHA before and after. It does not latch.

### Changed
- **A tech skill waits for its lead (Skill hook).** The release-gate dogfood `tech-go` failed 4/4 runs: asked
  how to run one gateway test, the model invoked `go-backend` right after `factory-core`, before routing and
  before `server-services`, so the answer skipped the lead's rules and gates. `tripwire.py --skill` now records
  each Factory skill a session runs and denies a `kind: tech` skill until one of its registry `used_by` skills
  ran, with a message naming the route command and those leads; it fails open without a registry. The
  `go-backend` description now has the same "how it works / not for scope" form as the other tech skills.
  `tests/dogfood.sh` counts only Skill calls that ran (a denied call is not an invocation); 12 cases in
  `git-guard.test.sh`.
- **`routing.tech` lists a tech skill only when the snapshot's repo is in its `repos`.** A measure run
  on the server no longer suggests `unity-dots`/`netcode-client`, and a client `Tools/` change no longer
  suggests `dotnet-gameserver` (`scripts/lib/resolve.jq`, skill-contract "Tech skills").
- factory-core step 11 (Review) applies the lead's checklist and the review file of every
  `routing.tech` skill after `/code-review`; the report template gains **Review** and **Lessons**.
- Skill contract: a **learning loop** (a verified failure lands in exactly one of: regression test,
  cited Pitfall, `known_issues`, `facts[]`), version-specific API advice names its fact, and every tech
  skill Pitfall cites a file or issue (`skills-lint.sh` enforces it).
- `known_issues` for the stale client/server CLAUDE.md text and the `unity-netcode` agent name the
  product-repo branches that fix them; remove each entry when its branch reaches the default branch.
- **Tripwire events instead of one latch file.** Each incident is `latch/<workspace>/<event-id>.json` with
  the command, session, tool call id, ref values before and after, and recovery hints (for a dropped
  stash: its SHA and `git stash apply <sha>`). A second incident no longer overwrites the first. `--ack`
  archives events to `acked/` (kept 30 days) instead of deleting them; `--ack <event-id>` acknowledges one,
  and an event created while an ack runs stays open. The latch stays global per workspace. A legacy
  `latch/<workspace>.json` still blocks and is migrated into `acked/` on ack.
- `--status` lists open events with ref values, recovery hints, recent audited stash operations and the
  exact ack command.
- While latched, read-only investigation is allowed: `git reflog` (not `expire`/`delete`/`drop`/`write`,
  which rewrite the history the recovery hints point at), `git stash show` and `git branch --list <pattern>`.
- Snapshots of calls without a `tool_use_id` are keyed by the command, so parallel calls do not share one.
  A second legacy latch is archived next to the first instead of overwriting it.
- git-safety: never stash/reset/clean to get a clean tree (export HEAD instead), never assume a stash is
  yours, one mutating command per worktree, and the recovery procedure after a STOP.

### Fixed
- **Windows (git-bash + native Windows Python) is a supported environment.** On Windows `tests/run-all.sh`
  failed 12 checks before any Factory change. Causes and fixes:
  - `jq -r` writes CRLF there, so `$(jq -r ...)` loops kept a carriage return (`skills/foo<CR>/SKILL.md` does
    not exist): 10 skills-lint failures. New `scripts/lib/compat.sh` (sourced by every test suite and
    `check-registry.sh`) strips it on MSYS/MINGW/CYGWIN only, and adds `mktemp_win`, `is_abs`, `fwd`,
    `path_entry` and `dir_readonly`/`dir_writable` (an ACL, since `chmod 555` does nothing on NTFS).
  - Test scripts passed MSYS paths (`/c/...`, `/tmp/...`) to native Python, which cannot resolve them
    (`No module named 'fstate'`, fixture workspaces never found). `ROOT` now comes from `pwd -W` and temp dirs
    from `mktemp_win` (`C:/...`). `install-status.test.sh` also sets `USERPROFILE`: Windows Python ignores `HOME`.
  - Tests compared native Python paths (`C:\x`) as strings with bash paths (`C:/x`); they now normalise.
  - **Output encoding.** Python entry points wrote cp1252 into pipes (the snapshot showed `?` for `·`,
    `pin-plan.py` crashed on `→`), and 16 `subprocess` calls decoded git and jq output as cp1252. Every
    entry point now writes UTF-8 and every `text=True` call decodes UTF-8 (`errors="replace"`).
  - **Tool lookup ignored `PATHEXT`.** `context.which` and `devtools.which` looked for `python3`, not
    `python3.exe`, so the snapshot said `python3 MISSING` and listed every Python-based fast check as MISSING
    (not run) on Windows. Both now try the `PATHEXT` extensions.
  - **Every check that calls a Factory script failed on Windows.** `{plugin_root}` was substituted as
    `C:\...\rpg-factory`, and `run-checks.py` runs each check through `bash -c`, which drops the backslashes
    (`can't open file '...WorkspacesUnityIndierpg-factory\scripts\checks\sgl-determinism.py'`). It is
    substituted with forward slashes; `run-checks.test.sh` runs a `{plugin_root}` check with a backslash root.
    The guard's mode denial printed the same broken form (`bash C:/x\scripts\factory-context.sh`); it now
    prints a quoted forward-slash path (`git-guard.test.sh` checks it with a backslash root).
  - Registry fact `netcode-vendored-protobuf` probed with `strings`, which git-bash lacks; the probe is
    Python now (same value, 3.29.3). `ci-integration-on-pull-request` opens `ci.yml` as UTF-8.
- **`netcode-headless.sh` compiled nothing since Netcode's prediction tests need Shared.GameLogic.** The temp
  copy had no sibling `rpg-mmo-server`, so `Vec2`/`MapBounds` were missing and no `.trx` was produced. The check
  now does what Netcode CI does: Shared.GameLogic at the tag `package.json` pins (`x-manualDependencies`), taken
  with `git archive` from the workspace server repo into the temp dir, passed as `-p:SglDir` (352/352 run).
  The path is converted for Windows `dotnet.exe`: `cygpath -m` in git-bash, `wslpath -m` in WSL.
- **`package-ready.py` crashed in WSL and read a failed `git status` as a clean tree.** Over `/mnt/c` a cold
  index made `git status` exceed the 30 s timeout (traceback, no verdict). git calls now allow 120 s; a git
  timeout or a failing `git status` exits 2 with "readiness unknown" instead of continuing as if the tree were
  clean (`run-all.sh` covers the non-repo case).
- **Per-project MCP servers were never found on Windows.** `~/.claude.json` keys projects as `C:/x/y`; the
  probe looked up `C:\x\y`, so a project-scoped server such as `ai-game-developer` showed as not configured.
  Keys are compared normalised.
- `run-all.sh`: when live `pin-status` fails and the client's pin files hold uncommitted user changes (the
  local `file:` toggle), the committed HEAD is verified through a read-only export and the live check is
  reported as SKIP with that result, never as PASS. New `tests/compat.test.sh` covers the helpers, UTF-8
  output under a cp1252 stdout, the `PATHEXT` lookup and (by AST) that every `text=True` call decodes UTF-8.
  README has a Windows section with requirements and troubleshooting. A clean tree that fails still fails. `py_compile` now
  covers `scripts/lib/*.py`, reads UTF-8 and treats `SyntaxWarning` as an error.
- `unity-client-tech` cited the client `CLAUDE.md` by line numbers, which had drifted by about 15 lines.
  The citations now use section names.
- **Tripwire false STOPs across sessions.** The pre-command snapshot was one `pre.json` per session,
  consumed by whichever PostToolUse came next. A call denied by the guard (PreToolUse ran, PostToolUse
  never does) left its snapshot behind, and the next read-only command (`tripwire.py --status`) compared
  against it and was blamed for every ref another session had changed in between. Parallel calls of one
  session overwrote each other's snapshot. Snapshots are now per tool call (`pre-<tool_use_id>.json`),
  read only by the same call, written atomically, and pruned after 2 h when a call never completes.
  Without a `tool_use_id`, a snapshot of a different command is discarded.
- **Concurrent sessions.** A ref change is explained when another session's (or a parallel call's)
  completed command saw that same ref reach that same value while its own visible git ran in that repo,
  and its subcommands could make that change: `commit`/`merge`/`reset`/... move only the branch it had
  checked out, `branch`/`switch`/`checkout -b` create branches, `fetch`/`push` move remote-tracking refs,
  `stash` moves `refs/stash`. A read-only `git log`, a different ref, a tag or an unfinished call never
  explains anything, so a hidden reset of `develop` still trips while another session commits elsewhere.
- **Failing commands were never checked.** A Bash call that exits non-zero fires `PostToolUseFailure`,
  not `PostToolUse`; the tripwire now runs `--post` on both (`hooks.json`).
- **A worktree ref change was reported twice** (once per checkout sharing the refs); it is now reported
  once, under the worktree the command ran in.
- Cache writes that fail (Windows: `os.replace` onto a file another hook has open) are retried, never
  leave temp files, and never cost the comparison.
- **The printed ack command did not work.** `os.path.join` produced `C:/.../rpg-factory\scripts\tripwire.py`;
  bash dropped the backslashes and the user's ack silently failed. Every message (STOP, guard denials,
  file guard, SessionStart, doctor) now prints `fstate.ack_command()`: quoted, forward slashes.
- **`--ack` reported success it had not checked** and always exited 0. It now re-reads the state and
  prints `latch is now CLEAR` (exit 0) or `still LATCHED: <ids>` / `NOT cleared: <reason>` (exit 1;
  2 = invalid id). Repeating it is safe; unknown ids are reported.

### Security
- The guard now denies `tripwire.py --ack` to the agent at all times, not only while latched, so an agent
  cannot dismiss an incident another session raised a moment earlier. It matches any Python invocation of
  the script (options before it, `py -3`, `python -c ... run_path`, the path behind a variable) and no
  longer denies `grep -- --ack tripwire.py`.
- **The git guard ignored a workspace when `RPG_FACTORY_WORKSPACE` named another one.** The env root was tried
  before the cwd, so a second checkout of the workspace (or a `cd` into it) counted as "outside the workspace"
  and `git tag`, `push --tags` and `reset --hard` there passed without a decision. The nearest workspace above
  the cwd now wins and the env root is the fallback; after a `cd` the new directory's workspace applies.
- **`git -C <workspace repo> ...` from outside the workspace was not checked** when `RPG_FACTORY_WORKSPACE`
  was unset (`git -C .../rpg-mmo-server tag v1` from another directory was allowed). The workspace is now
  resolved from the directory git works in. Cases in `git-guard.test.sh` and `installed-safety.sh`.
- **The guard went silent on Windows path and encoding differences.** It compared paths as strings, so a
  payload cwd `C:/ws/x` did not match the workspace found as `C:\ws` and every command there was skipped; and a
  non-ASCII branch name (a UTF-8 byte cp1252 cannot decode) raised inside the guard, which counts as "no
  opinion". Paths are compared normalised and git output is decoded as UTF-8. New `git-guard.test.sh` cases
  cover both, the env-root case and `cd` between workspaces.

## [0.5.0] - 2026-10-01

### Security
- **Unity batch-mode test runs were ungated.** Factory treats Unity tests as external
  (HUMAN_REQUIRED), but the new tech skill and the client's Unity MCP reference offered a batchmode
  `-runTests` run as the agent's fallback when the Editor is closed. Nothing gated it, and the run opens
  the user's project, which can rewrite `packages-lock.json` and settings and triggers a reimport. The
  `unity-batch` human gate now also matches `-runTests` and the `_SampleBuild` build entries
  (`PlayClientBuilder`, `SampleBuilder`), which the remap had brought under that gate without its
  regex. The skills now hand the user the batchmode command instead of running it.

### Added
- **Dev tools per skill.** New registry `dev_tools[]` records the MCP servers, plugins and binaries
  the skills use: `unity-mcp`, `lsp-go`, `lsp-csharp`, `pg-aiguide`, `context-mode`, `codex`,
  `dotnet`, `go`, `protoc` and `docker`. Each entry has `probes`, `used_by` skills, `required` and a
  `fallback`. `scripts/lib/devtools.py` probes them: PATH, registry tools, TCP services, MCP server
  names (from workspace/repo `.mcp.json` and `~/.claude.json`) and enabled plugins. Config files are
  parsed in memory, but only server and plugin names leave the module. Env, headers and URLs are
  never returned, printed or stored.
- The snapshot prints a **Services** line and, per repo, **Tools for this change** (OK / DOWN /
  MISSING, with the fallback) for the routed skills. `/rpg-factory:doctor` has a **Dev tools**
  section that also lists skills missing a required tool.
- `check-registry.sh` and the schema validate `dev_tools`: fields, probe syntax, known tools,
  services and skills, and a fallback for every tool. They also accept the new skill kind
  `tech`, which needs `used_by` (repo or cross-repo skills) and must not own a module or contract.
  Known issues `no-csharp-lsp`,
  `golangci-lint-missing` and `gameserver-claude-stale` were added, and `client-claude-stale` was
  extended.
- Tests:
  - `tests/devtools.test.sh` adds scenarios over the real registry in a controlled environment: all
    tools OK; Unity Editor closed (`unity-mcp` DOWN, not MISSING or OK); no C# LSP (`lsp-csharp`
    MISSING with its fallback, doctor still exits 0); a malformed config with a planted secret
    surfaces no content or traceback.
  - `tests/facts.test.sh` proves a stale registry value is caught by re-probing the repo.
  - `tests/routing.test.sh` checks that `--lead <tech skill>` is rejected.
  - `tests/dogfood.sh` adds `tech-dotnet`, `tech-go` and `tech-unity`: real sessions must invoke the
    repo skill and its tech skill, and apply the reported tool fallback.
- `tests/devtools.test.sh` covers the probes, the snapshot, doctor, planted secrets that must never
  be printed, and malformed registry entries.
- **Tech skills** (new skill kind `tech`) explain how a technology works in this workspace. Repo
  skills keep where a change goes and which rules apply. Tech skills own no module, so they are never
  lead, leg or follow-up. `resolve.jq` emits `routing.tech`: the tech skills used by a working skill
  (lead, co-lead or leg). The snapshot prints it in the routing line and the Next hint.
  - `dotnet-gameserver` (used by server-realtime, wire-contract and measure): tick order (the tick
    gathers and connection write tasks encode/send), rates, ECS world locking, zero-alloc idioms and
    what each guard covers, SGL compiler limits, the Net layer, xUnit idioms and filters, NativeAOT.
  - `go-backend` (used by server-services and wire-contract): six modules that `replace` shared
    without go.work, gateway entry points, storage seams, test doubles (`miniredis.RunT`, httptest,
    embedded `runtime.NakamaModule`), single-test commands, and when the dotnet interop tests skip.
  - `unity-client-tech` (used by client-integration, unity-package and pin-bump): Entities system
    install and world lifecycle, Task vs UniTask boundaries, main-thread rules, VContainer, asmdef and
    test-assembly rules, domain reload, WebGL limits, single tests through Unity MCP `tests-run`
    filters (with the Editor closed, the batchmode command is handed to the user).
- Every repo, cross-repo and tech skill has a `## Tools` section that names its `dev_tools` and the
  step each one is for. `tests/skills-lint.sh` enforces it in both directions: each `used_by` skill
  names the tool, and each tool a bullet leads with is registered for that skill. Tech skills need
  the sections Architecture / Idioms / Pitfalls / Testing / Tools, and every `used_by` skill names
  `rpg-factory:<tech>`.
- Routing properties P7 (a tech skill is never routed) and P8 (`routing.tech` only lists skills
  whose `used_by` is a working skill), plus 7 task scenarios in `tests/routing.test.sh`.
- Registry facts with probes: `sgl-langversion`, `sgl-target-frameworks`, `tick-rates-default`,
  `aoi-parallel-gather-min-viewers`, `nakama-version`, `enter-playmode-options`.

### Changed
- `server-realtime`, `server-services` and `client-integration` were deepened and point to their tech
  skill.
  - server-realtime names `SnapshotAllocationTests` (snapshot path only) and the single-test filter,
    and cites ADR-7/8/13/22/25.
  - server-services cites ADR-1/4/6 and adds an evidence rule: skipped interop tests are NOT_RUN,
    never PASS.
  - client-integration is trimmed to 149 lines, covers `_SampleBuild`, adds CI `01-ci-docs.yml`
    (its green result is not evidence) and `02-package-pins.yml`, and its Unity MCP reference gains
    the `tests-run` filters.
- `server-ops` is trimmed to about 150 lines and gains ADR-17 (one replica; `Recreate` on the
  `hostPort` workloads).
- Registry modules:
  - `Assets/_SampleBuild/` maps to `client.buildscripts`, which brings its build gates (it used to
    fall through to `client.unity-assets`).
  - `client.ui` now describes what it actually holds (the theme). The HUD UXML/USS live in
    `client.scripts`, which gains `docs/UI-ARCHITECTURE.md` and the `ci-uxml-drift` external check.
- Known issue `dotnet-wsl` is corrected: a Linux SDK may exist off PATH at `~/.dotnet/dotnet`, and the
  Go interop tests use it.

### Fixed
- **Tech skills were not loaded for "how does it work / how do I test it" questions.** A real session
  routed to `server-realtime` but never invoked `dotnet-gameserver`: the pointer sat only in the
  "place the code" step and said "read", not "invoke". The repo skill, `factory-core` and the
  snapshot's Next line now give one rule: the lead invokes the tech skill (Skill tool) before
  implementing, debugging or reviewing code, or answering how it works or how to test it, in every
  mode. A tech skill is supporting context, not a follow-up.
- **A session could use a tech skill as the owner.** In one of three real Go sessions the model
  invoked `go-backend` and `dotnet-gameserver` but never the routed lead or co-lead, so no rules, gates
  or validation were loaded. Every tech skill now opens with a "Supporting skill, never the owner:
  invoke the lead first" guard (lint-enforced). `tests/dogfood.sh` fails any session that invokes a
  tech skill before an owning skill.
- `/rpg-factory:status` answers dropped each Pending item's owning skill (`[unity-package]`), which is
  the point of the report. On this branch the installed and A/B sessions failed 3/3, against 2/2 on 0.4.0,
  although the status output was byte-identical. The command now says to keep the brackets as printed
  (3/3 after the fix).
- The `factory-core` Skills table let a session name the lead by lookup and stop. It is now marked
  orientation-only: run Route and invoke the lead before answering, with tech skills after the lead.
  Known residual: `netcode-change` still sometimes names the lead without invoking it, at the 0.4.0
  rate (0.4.0 passed 5 of 6 sessions, this release 6 of 7).
- `--explain` said a tech skill was "not selected - no touched path maps to its modules ()". It now
  reports `tech (supporting)` with the skill that uses it, or names its users when none works on the
  change.
- The git guard denied `git tag --sort=...` / `--format=...` (a read) as tag creation. Listing
  options in their `=` form are now a listing. A tag name after them, or a separated `--sort <value>`,
  is still denied.
- `go-backend`: only the `*_test.go` files of `integration_test` carry the build tag; the
  `mock_client.go` helper does not.
- `server-ops` reference: the Nakama plugin is built by `deploy/nakama-plugin.Dockerfile`.
  `docker/Dockerfile.nakama-plugin` is not referenced by anything.
- **The `services.unity-mcp` probe never ran.** Skills branch on "the snapshot shows `unity-mcp`
  reachable", but no script read `services`. The snapshot now probes each service over TCP
  (0.3 s timeout) and reports it in markdown and `--json`.

### Documentation
- README: plugin hooks bind at session start. A session running before rpg-factory was installed or
  enabled has no Factory hooks at all (compaction does not load them); start or resume a session, and
  check with `/rpg-factory:doctor`. Found in the post-release audit of the v0.4.0 tagging session;
  fresh, resumed and `--plugin-dir` sessions were verified to deny tag creation and enforce modes.

## [0.4.0] - 2026-09-30

### Security
- **GitHub mutations were unguarded.** `gh api graphql` could create tags (`createRef refs/tags/*`,
  `createRelease`), `gh repo delete` and branch-protection writes were allowed. The guard now applies a
  structural gh policy: the API method is derived the way gh does (`-X`, else POST when fields or
  `--input` are given); reads pass; tag/release creation (REST and GraphQL) and repository
  deletion/archival are denied; every other remote mutation (branch protection, rulesets, repo
  settings, secrets, variables, workflows, runs, PR/issue changes, GraphQL mutations or queries from a
  file) asks. `gh` commands naming a workspace repo are checked even outside the workspace. These
  changes are remote-only, so the tripwire cannot see them - the guard is the only control.
- Protected refs and remotes: `git pull` without `--ff-only` on a protected branch, renaming or
  deleting a protected branch, `fetch <src>:<dst>` into local branches (forced or not; into tag refs =
  deny), `remote add/set-url/remove/rename`, `config` writes to aliases / remote URLs / `insteadOf` /
  `hooksPath` / credential helpers, `symbolic-ref` writes, `submodule add/set-url` now ask.
- **File tools were unguarded.** New `scripts/file-guard.py` (PreToolUse
  `Write|Edit|MultiEdit|NotebookEdit|Read`): writes into embedded package clones, submodule content,
  registry generated paths, the user's baseline files or secrets ask; secret reads ask; writes while the
  tripwire is latched or while a read-only mode is declared are denied. MCP tools are not inspected
  (documented; the `unity-asset-edit` gate remains the control).
- **A tripwire STOP vanished with its session.** The latch is now also written per workspace in the
  persistent state root: a crashed or closed session leaves the next one latched, SessionStart says
  why, and only the user's `--ack` clears it (the ack now rebuilds the baseline immediately).

### Fixed
- **State paths could be relative.** With `TMPDIR` empty (as in some shells), relative or invalid, the
  tripwire and runner wrote `rpg-factory/<session>/` into the current directory. All state now resolves
  through `scripts/lib/fstate.py` (always absolute; scratch under a usable `$TMPDIR` or `/tmp`,
  persistent state under `$XDG_STATE_HOME/rpg-factory` / `~/.local/state/rpg-factory`);
  `netcode-headless.sh` rejects a relative/invalid `TMPDIR`. Read paths no longer create directories.
- **The first dirty file of each repo was not protected.** The tripwire baseline stripped the first
  porcelain line and lost the first character of its path (and mangled quoted paths); it now parses
  NUL-separated porcelain.
- `is_read_only` treated `2>/dev/null` / `2>&1` as writes.
- Command `!` lines must match their own `allowed-tools` pattern or Claude Code refuses them (found by
  installed dogfood; now linted). factory-core asks for Factory script paths exactly as printed
  (absolute): relative paths hit permission prompts, and allow-listing relative paths would auto-approve
  any repo's own `rpg-factory/scripts/`.
- CHANGELOG 0.3.0 said 16 human gates; the registry has 15.

### Added
- **Execution modes** `analyze`, `plan`, `implement`, `validate`, `review`, `resume`: declared with
  `factory-context.sh --mode <m>` (printed in the snapshot), recorded per session by the guard and
  enforced by both guards (analyze/plan/review read-only; validate only `run-checks.py`). factory-core
  owns the mode table; every skill honours it. A PreToolUse(Skill) hook also records an explicit mode
  from Factory skill arguments ("plan only", "mode: validate") - installed dogfood showed sessions that
  never ran the Route command. Evidence: in v0.3.0 dogfood every missed lead invocation came from a
  plan-only prompt.
- **Commands** `/rpg-factory:status`, `/rpg-factory:route`, `/rpg-factory:check`, `/rpg-factory:doctor`
  (one validating dispatcher, `scripts/factory-cmd.py`). No `ack` command: clearing a latch stays a
  user action.
- **Tree-bound evidence.** `run-checks.py` stores each executed check with the identity of the tree it
  ran on (HEAD + diff and untracked files in the check's directory and its module's same-repo
  dependencies + the check definition) and its full log; `--status` grades the declared checks against
  the current tree without running anything: **STALE** after any relevant change, **NOT_RUN** when never
  executed.
- `factory-status.py`: package-CI pins from contract watchers (the real UnityDots CI -> Netcode v0.41.0
  vs the client's v0.45.0 drift is now pending), remote-knowledge **freshness** per repo (never fetches;
  prints the `git fetch` when older than 24 h), uncommitted work per repo, embedded clones, and stored
  evidence graded against the current tree. Status scans run in parallel.
- Workspace model: registry `repos.<key>.embedded_clones` (the client's gitignored
  `Packages/com.cuvara.*`): tripwire fingerprints them and samples their dirty files before/after each
  command (the user's own concurrent edits are not flagged); a snapshot run inside one says so
  instead of silently showing the canonical repos.
- Registry: contract `transport-security` (driver server-ops; TLS / `GAMESERVER_SEALED` switches vs the
  server, Netcode, client-pin and smoketest/verify capabilities - history `ed090ab`, `437a3db`);
  `package-pins` watchers; modules `server.bench` (measure leads benchmark harnesses) and
  `netcode.measurement` (measure co-leads).
- Skills: server-ops rollout order for security switches; unity-package package-CI pins;
  client-integration Unity-MCP hand-off (`references/unity-mcp.md`); measure ownership; factory-core
  game-ai-workflows hand-off.
- Tests: guard 252 (GitHub, refs/remotes/config, modes), tripwire 40, file guard 29, commands 30,
  run-checks 35 (evidence), factory-status 22, worktree 13 (clones), routing 52 (transport-security,
  bench, follow-up noise), installed-safety 83; dogfood gains analyze/plan/validate-only and command
  scenarios (13 real sessions against the installed plugin).

### Changed
- Performance (same harness, /mnt/c): SessionStart baseline ~12 s (was ~14 s; repos and clones now scanned in
  parallel), read-only command hooks ~0.19 s (was ~0.18 s), state-changing ~0.8 s (was ~0.9 s; signatures and
  clone samples in parallel), factory-status ~4.3 s (was ~4.8 s; parallel scans, one git grep), file guard
  ~0.09 s per file-tool call (new). Plugin scripts append (not prepend) their paths to sys.path so stdlib
  imports never stat /mnt/c first.
- `git pull` on a protected branch now asks unless `--ff-only`.
- Routing: a cross-repo dependent adds only its module's primary owner as a follow-up (a secondary owner
  such as `measure` on `netcode.measurement` is not downstream work of a wire change). Replay of all 358
  post-split commits against v0.3.0: 0 lead changes; co-leads/follow-ups differ only where intended
  (measure on 26 Netcode measurement commits, transport-security on 5 TLS commits).

## [0.3.0] - 2026-09-30

### Fixed
- **Install state was invisible.** `claude plugin list` still reported 0.1.0 while the source was
  0.2.0, and nothing checked what sessions load. `scripts/install-status.py` reports the load mode
  and state (CURRENT / STALE / CONTENT_MISMATCH / RESTART_REQUIRED / NOT_INSTALLED); a SessionStart
  hook warns when not CURRENT and the snapshot header shows the runtime version and load path.
  Observed with Claude Code 2.1.280: a **directory** marketplace (this workspace) loads the plugin
  in place from the marketplace directory - the version-keyed cache copy is only used by other
  marketplace types, where `claude plugin update` is a no-op until the version changes. README
  "Updating" documents both; the v0.3 roadmap's premise that v0.2.0 sessions ran v0.1.0 content is
  not supported by this evidence (only the install record was stale).
- **Guard: `xargs` tag creation** (`echo v9 | xargs git tag`) was allowed because the peeled command
  looked like a tag listing; xargs input is now modelled as an extra argument (deny). Found by
  `tests/installed-safety.sh`; the tripwire had caught it after the fact.
- **Guard bypasses.** The guard now covers the PowerShell tool (matcher `Bash|PowerShell`,
  PowerShell tokenizer with backtick escapes and the `&` call operator) and expands commands before
  classifying: wrappers (`env`, `sudo`, `timeout`, `nohup`, `nice`, `command`, `exec`, `xargs`,
  `find -exec`), nested shells (`bash/sh -c`, `eval`, `cmd /c`, `powershell -c`), repo git aliases;
  `$VAR` / `$(...)` as the program and interpreter one-liners running git ask.
- Guard: `gh api .../git/refs|tags` and `gh release create` are denied; `merge`, `cherry-pick`,
  `revert`, `am`, `pull --rebase`, `reset <commit>` on protected branches ask; `checkout -B`,
  `switch -C`, `branch -f`, `update-ref`, `gc --prune`, `reflog expire`, `prune` ask. Worktrees use
  their main checkout's protected branches.
- Routing: `backend/content/` was mapped by two modules (winner depended on registry order).

### Added
- **Tripwire** (`scripts/tripwire.py`, SessionStart/PreToolUse/PostToolUse): detects git state
  changes the guard could not see (tags, pushes, branch/HEAD/stash moves without a visible git
  command in that repo, modified or deleted baseline files, moved user submodules, changed dirty
  files inside submodules). Emits "STOP - rpg-factory tripwire" and latches the session (the guard
  denies non-read-only commands) until `tripwire.py --ack`.
- **Deterministic routing**: one primary lead (cross-repo driver > repo-kind driver on a touched
  source > primary owner > secondary owner > `skills.<name>.order`), ordered co-leads, AMBIGUOUS,
  `--lead` override (validated) and `--explain`. `.meta` paths route like their asset; unmapped
  files route to per-repo fallback modules `<repo>.root`.
- **Worktree-aware context**: the snapshot resolves the repo or worktree from the current directory.
- **Check runner** `scripts/run-checks.py`: runs the registry checks for the touched modules and
  grades them PASS / FAIL / BLOCKED / NOT_AVAILABLE / HUMAN_REQUIRED / SKIPPED with per-check
  parsers (`go-test`, `dotnet-test`, `exit`, `regex:`), `needs` dependencies, extended-tier approval
  (`--approve`), pollution detection (before/after `git status`) and an evidence JSON.
- **Derived cross-repo status** `scripts/factory-status.py`: contract consistency, the wire rollout
  chain (server bindings → Netcode copy → Netcode release → client pin), package release state
  (released / unreleased changes / READY_TO_TAG), pins vs latest tags, CI SGL watchers,
  unity-build-workflows refs and gitlink (`--remote`), in-flight `<type>/<area>/<topic>` branches
  linked across repos, and pending items with their owning skill. No stored state.
- Registry schema v3: `skills.order`, fallback modules, check `parser` / `needs`, `facts[]` with
  read-only probe commands (re-verified by `tests/facts.test.sh`), 15 human gates (incl. `sgl-release`; this entry originally said 16).
- `VERSION` file; run-all checks VERSION == plugin.json == marketplace == CHANGELOG section.
- Tests: guard bypass matrix (145 cases incl. PowerShell and wrappers), tripwire simulations,
  routing properties over real history, worktree, check runner, factory-status rollout fixtures,
  install-status (both load modes), facts; `tests/installed-safety.sh` drives the installed hooks
  against a disposable workspace (63 cases incl. tripwire STOP and latch; part of
  `run-all --release`); `tests/dogfood.sh --installed` runs headless sessions against the installed
  plugin and asserts the loaded source/version/path and the invoked skills.
- `--paths` normalisation: repo-prefixed (`rpg-mmo-server/backend/...`), absolute, comma-joined and
  glob paths resolve to repo-relative files (they used to fall to the repo fallback and lose routing).
  factory-core routes by the files the task writes (a benchmark writes the harness/BENCHMARK.md).
- Cross-repo tasks have one lead: a downstream contract end (e.g. the client's `PartyService.cs` for
  `nakama-rpc`) prints a **Cross-repo** line naming the upstream driver; factory-core says so.
- Snapshot routing prints an explicit "Next: invoke the Skill tool with the lead" line (installed
  dogfood showed sessions naming the lead without invoking it).

### Changed
- Snapshot diet: compact output filtered to the touched repos, toolchain probed lazily
  (all repos 16.1 KB / 15.3 s → 3.3 KB / 4.9 s; one repo with `--paths` 13.9 KB → 2.4 KB).
- `factory-core`: Resume step (factory-status), routing with lead/co-leads, validation through the
  runner, tripwire STOP rule, same branch topic across repos, plugin boundary clause
  (game-ai-workflows, web-game-factory).
- `pin-bump`: also moves the unity-build-workflows toolkit (submodule gitlink and reusable-workflow
  `@vN` refs); submodule bumps route to it.
- `wire-contract`: resumes at the first incomplete rollout stage; compatibility, rollout order and
  rollback table; `--min-protocol-version` on gateway and game server.
- `client-integration`: package-version awareness (codes against the pinned tag) and hand-off table.
- `server-realtime` trimmed; volatile values in skills replaced by registry facts;
  `skills-lint` flags rule sentences copied from the registry and missing plugin boundaries.

## [0.2.0] - 2026-09-30

### Added
- Eight specialised skills on top of Factory Core: cross-repo drivers `wire-contract`, `pin-bump`,
  `measure`; repo skills `server-realtime`, `server-services`, `server-ops`, `unity-package`,
  `client-integration`. Each follows `references/skill-contract.md` (Core first, registry facts,
  validation delta, generated paths, human gates, review checklist, report additions).
- Registry schema v2: repos `netcode`, `unitydots`, `uitoolkit`; 52 modules (deploy split into
  k8s/compose/monitoring/db, plus persistence, content, measurement-docs, wire-conformance, and 17
  package modules); `skills`; 9 `contracts` (wire-generated, protocol-version, join-token,
  redis-server-registry, nakama-rpc, sgl-pin, package-pins, gamestate-migrations, server-knobs with a
  `co_edit` clause); 15 `human_gates`; module `skills`/`gates`; 26 verified `known_issues`.
- `factory-context.sh`: cross-repo dependents (advisory), suggested skills with roles
  (lead / leg / follow-up), touched contracts with other ends / upstream / watchers, human gates,
  known issues; all five repos in the default snapshot.
- Check scripts: `pin-status.py`, `pin-plan.py` (incl. `--client-ref` historical replay),
  `wire-parity.sh`, `netcode-headless.sh` (temp-copy test run), `package-ready.py`.
- Tests: `tests/routing.test.sh` (25 task scenarios + 13 real historical commits replayed
  read-only), `tests/skills-lint.sh` (skill contract), JSON Schema validation in
  `check-registry.sh`; `tests/dogfood.sh` (opt-in headless sessions asserting the invoked skills -
  8 scenarios verified with sonnet).
- Evals: routing cases for server-realtime, server-ops, unity-package, server-services, plus
  wire-contract / pin-bump graders.

### Changed
- Contributor instructions moved from `CLAUDE.md` to `.claude/CLAUDE.md` (a root CLAUDE.md is not
  plugin context and fails `claude plugin validate --strict`).
- Plugin/marketplace descriptions describe the full workflow set.
- Git guard hardened: one invalid `human_gates` regex no longer disables the whole guard (each gate
  and the git evaluation fail independently).
- Git guard: creating, deleting or pushing tags is now **denied** (agents never tag); commands
  matching registry `human_gates[].match` (kubectl/helm/ssh, workflow dispatch, secrets,
  toggle-packages.sh, local stack) now ask. Protected branches come from each repo's registry entry.
- `factory-core`: new Route step (invoke the suggested lead skill), skill map, updated references.
- `server.gameserver-dotnet` knob rule corrected: passthrough is enforced against compose and fleet
  manifests (ComposeEnvPassthroughTests / FleetEnvPassthroughTests), not `20-configmaps.yaml`.

## [0.1.0] - 2026-09-30

### Added
- Factory Core v1 plugin (`rpg-factory`) with single-plugin marketplace.
- `factory-core` skill: workflow (scope, baseline, branch, plan, implement, obligations,
  validate, verify, review, report), live snapshot injection, global rules from the registry,
  and references for repos, validation, git safety, report template and skill contract.
- `registry.json` (27 modules across rpg-mmo-server and IndieRPGMMOAdventure) with
  `docs/registry.schema.json`.
- `scripts/factory-context.sh`: read-only live snapshot (branch, working tree, branch diff,
  submodules, touched modules and dependents, checks by tier, obligations, toolchain with
  `dotnet` -> `dotnet.exe` fallback, Unity MCP reachability); `--paths` and `--json` modes.
- `scripts/git-guard.py` PreToolUse(Bash) hook asking before destructive or high-impact git.
- `scripts/check-registry.sh`, `scripts/checks/unity-package-pins.py`.
- `tests/run-all.sh`, `tests/git-guard.test.sh`, and three `claude plugin eval` smoke cases.
