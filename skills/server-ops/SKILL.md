---
name: server-ops
description: Use when a change in rpg-mmo-server touches how the backend is packaged, deployed, observed or recovered - Dockerfiles, compose files and stack.sh, k8s/k3s/Agones manifests (fleets, autoscaler, allocation), deploy verification, Prometheus/Grafana config, DB migrations' ops copies and backup/restore scripts, environments.tsv, or the cd.yml / publish-images workflows. Not for game server or gateway code (server-realtime / server-services), not for wire changes (wire-contract), not for benchmarks (measure), and never for applying anything to a cluster or host on its own.
argument-hint: "[deploy/infra task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*)
---

# Server ops - deploy, infra, CI/CD

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first. Honour the declared Factory mode: in `analyze`, `plan` and `review` apply this skill's workflow, rules and checklist to produce the analysis, plan or findings - change nothing; in `validate` only run and grade checks.

Task: $ARGUMENTS

## Applies when / Not when

- **Applies:** `backend/deploy/` (docker, compose, `stack.sh`, `Makefile`, `k8s/`, `k3s/`, `agones/`,
  `monitoring/`, `db/`, `environments.tsv`, `preflight-isolation.sh`), `cd.yml` / `publish-images.yml`,
  deploy docs, the verify probe, post-deploy smoke.
- **Not when:** gateway, game server, `shared` or Nakama plugin code, or a benchmark (hand off, see
  Scope). This skill **authors and validates offline**; it never deploys.

## Scope

Repo `server` only. Modules: `server.deploy-k8s`, `server.deploy-compose`, `server.monitoring`,
`server.db`, `server.deploy`, `server.verify-probe`, `server.smoketest`, `server.ci`.
Resolve paths, rules, docs and checks from the registry, never from memory:

```bash
bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh --repo server --paths <files you changed>
jq '.modules[] | select(.id|startswith("server.deploy") or .=="server.monitoring" or .=="server.db")' ${CLAUDE_PLUGIN_ROOT}/registry.json
```

Hand-offs: new gameserver knob or env var -> `server-realtime`, which also adds the `env:` passthrough
lines of the five `server-knobs` copies plus the deploy CHANGELOG entry in the knob commit (contract
`co_edit`); this skill owns the values (`.env.example`, `20-configmaps.yaml` keys) and everything else.
Migration SQL (canonical and the `db/` copies) -> `server-services`; in `server.db` this skill owns only
`db/{backup,restore,redis-backup,redis-restore}.sh` and the `cd.yml` backup/migrate steps. Repo-root
`scripts/` -> `server.scripts`; load/bench numbers -> `measure`.
Order when combined with a code change: code skill first, then this skill for its deployment.

## Workflow delta

1. **Classify the target** of every edit: local compose, k3d dev cluster `k3d-rpg-dev` (shared: CD
   `DEPLOY_MODE=k8s` applies to it), staging/production (runner host). Past offline = human gate.
2. **Read the governing doc** first (map in `references/manifests-and-checks.md`); it carries the
   incident history. `backend/deploy/CLAUDE.md` "File Structure Target" is aspirational; the tree is truth.
3. **Env edits are two-sided.** Adding/removing an `env:` entry in a fleet or a compose gameserver service
   is checked against the gameserver's declared knobs by `GameServer.Tests/Deploy/*PassthroughTests`.
   Changing a port/deploy dir/compose project for an environment = GitHub Environment variable **and**
   its `environments.tsv` row in the same change (`docs/CICD.md` "reserved-identity registry").
4. **Validate offline** (Validation delta) against the base commit where a check is already red;
   never "fix" a pre-existing failure silently; report it.
5. **Stop before any live action** and hand the user the exact command (Human gates).
6. Obligations: `backend/deploy/CHANGELOG.md` `[Unreleased]`; the matching `backend/deploy/docs/*.md`.

## Transport security switches (contract `transport-security`, this skill drives)

Gateway / Nakama TLS and `GAMESERVER_SEALED=require` live in the deploy manifests
(`k8s/app/40-gateway.yaml` is the contract source; fleets, compose, `k8s/data/nakama.yaml` follow).
A switch only goes **on** after every capability it needs exists; it goes **off** in reverse:

1. Server code supports it (gateway TLS flags, `NakamaTlsPin.cs`, sealed sessions) - `server-services` / `server-realtime`.
2. The Netcode tag the client pins supports it (`SealedHandshakeClient`, `factory-status.py` pins) - `unity-package` → `pin-bump`.
3. The client loads a pin for that backend (`TransportSecurityReport.cs`, `BackendCommandLine.cs`) - `client-integration`.
4. Smoketest / verify pin the **target** cluster's certificate (`smoke/`, `k8s/verify/`).
5. Then flip the manifest, and validate end to end (killprobe / dungeonprobe / verify) - external, human-gated.

History: `ed090ab` (meta-hop TLS broke dungeon entry), `437a3db` (verify pinned another cluster's
certificate). Report which of 1-4 are done, with evidence, before flipping.

## Rules

- ADR-2: a map-pinned fleet (fixed `GAMESERVER_MAP_ID`) runs `replicas: 1` and **never** gets a
  FleetAutoscaler; the only autoscaler targets the dungeon fleet (`k8s/app/70-...`), policy `Buffer`
  only (ADR-14 decision 5). Source: `docs/K3S.md` "Why there is no autoscaler on a MAP fleet".
- Apply order in `k8s/app/`: autoscaler last, after the dungeon fleet image is pinned
  (`k8s/app/README.md` "Apply"). `dev-up.sh` encodes the order; do not reorder by hand.
- ADR-17: on k8s every component is one replica and every gateway rollout is a join outage (accepted
  for dev only). The `hostPort` workloads (gateway 7000, Nakama 7001) keep `strategy: Recreate`; a
  second replica or RollingUpdate there is a new ADR decision, not a manifest tweak.
- Fleets: port named `game`, `portPolicy: Dynamic`, `POD_NAME` from `metadata.name`, no `GAMESERVER_ID`,
  no `GAMESERVER_PUBLIC_ADDR`, no literal secret values (`docs/K3S.md` "Offline validation").
- Secrets never in git: `k8s/app/30-secret-template.yaml`, `agones/secret-example.yaml` stay templates.
- WSL `docker` is Docker Desktop's shim: bind-mount sources literal relative (`./monitoring`), never
  `$PWD`/absolute (`docs/CICD.md` "path-translation rule").
- `monitoring/prometheus.yaml`: keep the copied `otlp:`/`storage:` blocks on `OTEL_LGTM_VERSION` bumps and
  `metric_name_escaping_scheme: underscores` on gameserver jobs (`docs/MONITORING.md`).
- DB: never edit a shipped migration; `db/migrations/gamestate/*.sql` are verbatim ops copies of
  `GameServer/Persistence/Migrations/`; `db/init-gamestate.sql` mirrors `001_init.sql` only
  (`docs/DATABASE.md` section 1).
- A merge to `develop` **is** a deploy to dev (`cd.yml` on push). CI does not run any of the offline
  deploy checks below, so they are the only gate before that deploy.
- Never quote a player-count ceiling or tier CCU as measured (`backend/deploy/CLAUDE.md` section 8, ADR-7).

## Generated & protected paths

- Protected (gitignored; never read, never commit): `backend/deploy/.env`, `.env.scratch`,
  `kubeconfig.local*`, `agones/secret-*.local.yaml`. Use `.env.example` when a command needs an env file.
- `modules/*.so` built by `make plugin` (gitignored). `k8s/app/proof/`, `k8s/verify/tests/` fixtures are
  captured evidence: change only with a new capture. No generator-owned files.

## Validation delta

Core runs the registry checks; how to read them (baselines in `references/manifests-and-checks.md`):

| Tier | Check | When | Evidence |
|---|---|---|---|
| fast | `k3s/validate-manifests.py` (no args) | any `agones/` or `k3s/` yaml | `N document(s) validated, 0 failure(s)`, exit 0 |
| extended | `k3s/validate-manifests.py k8s/app/*.yaml` | any `k8s/app/` yaml | `[FAIL]` set identical to base commit (pre-existing namespace FAILs: fact `k8s-app-baseline-validation-failures`); new FAIL = failed |
| fast | `bash verify/tests/autoscaler_rule_test.sh` (cwd `k8s`) | fleet/autoscaler/verify lib edits | `RESULT=PASS`, 3 cases OK |
| fast | `docker compose --env-file .env.example ... config -q` | compose edits | exit 0, no output, for base + override + agones |
| extended | Deploy passthrough tests (`FullyQualifiedName~GameServer.Tests.Deploy`) | `env:` in fleet or compose | dotnet counts, Total > 0, 0 failed |
| fast (server-services leg) | `MigratorTests` (`EmbeddedMigrations_MatchDeployCopies`, `InitGamestateSql_MatchesFirstMigration`) | `db/*.sql` (server-services leg) | passed counts |
| fast | monitoring yaml/json parse | `monitoring/` | exit 0; **no promtool locally** - rule semantics NOT_AVAILABLE |

External (never self-run, report HUMAN_REQUIRED with the command): `kubectl apply --dry-run=server`,
`k8s/verify/verify.sh --target ...`, `make flow-up && make flow-check`, `cd.yml` `post-deploy-smoke`.

## Human gates

Ask before, and never run unasked:
- `kubectl`, `helm`, `k3d`, `k3s`, `ssh`, `scp` and their wrappers: `k8s/{dev-up,rollback-to-compose}.sh`,
  `k3s/{setup,teardown}-dev.sh`, `k8s/data/apply.sh`, `k8s/registry/push.sh`, `k8s/verify/verify.sh`
  (live cluster; `--allow-allocation` costs a GameServer).
- Stacks: `stack.sh up|down|check`, `make flow-*|up|down|reset|monitoring-*`, `docker compose up|down|restart`.
- `db/backup.sh`, `db/restore.sh` (destructive with `--yes`), `db/redis-*.sh`.
- `gh workflow run cd.yml|publish-images.yml`, re-running CD runs, merging to develop/staging/release-*.
- Reading or committing `.env`, `kubeconfig.local*`, secrets; editing GitHub Environment variables.
- Any action against staging or production.

## Tools

- `docker`: compose `config -q` and image builds, offline only (missing: compose check NOT_AVAILABLE).
- `context-mode`: validator / CD logs through it, only `[FAIL]`/`[warn]` lines enter context (else grep).

## Review checklist

- [ ] No literal secret, no new tracked file matching `.gitignore` secret patterns.
- [ ] Map fleet still `replicas: 1`, no autoscaler targets it; dungeon autoscaler `Buffer`.
- [ ] Env added to fleet/compose is a declared gameserver knob (passthrough tests) and documented.
- [ ] Port/identity changes mirrored in `environments.tsv` and called out for the GitHub Environment.
- [ ] Bind mounts relative and bundled by `cd.yml` `bundle` if hosts need them; validator `[FAIL]` set
  not larger than base, `[warn]` lines reviewed.
- [ ] CHANGELOG + governing doc updated; stale doc claims touched by the change corrected.

## Report additions

- Target environments affected and pending gates, each with the exact command for the user.
- Validator output delta vs base commit (FAIL/warn lines), autoscaler `RESULT=` line, passthrough test
  counts for compose/fleet env edits.
- "Deploys on merge to develop: yes/no" for the change.
