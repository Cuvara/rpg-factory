---
name: server-ops
description: Use when a change in rpg-mmo-server touches how the backend is packaged, deployed, observed or recovered - Dockerfiles, compose files and stack.sh, k8s/k3s/Agones manifests (fleets, autoscaler, allocation), deploy verification, Prometheus/Grafana config, DB migrations' ops copies and backup/restore scripts, environments.tsv, or the cd.yml / publish-images workflows. Not for game server or gateway code (server-realtime / server-services), not for wire changes (wire-contract), not for benchmarks (measure), and never for applying anything to a cluster or host on its own.
argument-hint: "[deploy/infra task]"
allowed-tools: Bash(bash ${CLAUDE_PLUGIN_ROOT}/scripts/factory-context.sh:*)
---

# Server ops - deploy, infra, CI/CD

> **Prerequisite:** follow `rpg-factory:factory-core` for this task. If it has not run in this task yet, invoke it first.

Task: $ARGUMENTS

## Applies when / Not when

- **Applies:** edits under `backend/deploy/` (docker, compose, `stack.sh`, `Makefile`, `k8s/`,
  `k3s/`, `agones/`, `monitoring/`, `db/`, `environments.tsv`, `preflight-isolation.sh`),
  `.github/workflows/cd.yml` / `publish-images.yml`, deploy docs, the verify probe, post-deploy smoke.
- **Not when:** the change is in `backend/gateway`, `backend/gameserver-dotnet` code, `backend/shared`,
  Nakama plugin code, or a benchmark. Hand those off (see Scope). This skill **authors and validates
  offline**; it never deploys.

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
`co_edit`); this skill owns the values (`.env.example`, `20-configmaps.yaml` keys) and everything else; migration SQL, both canonical (`GameServer/Persistence/Migrations/`) and the
`db/migrations/gamestate/*.sql` + `db/init-gamestate.sql` copies -> `server-services`. In `server.db`
this skill owns only `db/{backup,restore,redis-backup,redis-restore}.sh` and the `cd.yml` backup/migrate steps; `scripts/` at repo root (`build-all.sh`, `deploy-local.sh`,
`bootstrap-vps.sh`) -> `server.scripts`; load/bench numbers -> `measure`.
Order when combined with a code change: code skill first, then this skill for its deployment.

## Workflow delta

1. **Classify the target** of every edit: local compose (dev box), k3d dev cluster `k3d-rpg-dev`
   (shared: CD `DEPLOY_MODE=k8s` applies to it), staging/production (compose/host on the runner host).
   Anything past "edit a file and validate offline" is a human gate.
2. **Read the doc that governs the file** before editing (map in `references/manifests-and-checks.md`).
   The docs carry the incident history behind each invariant; `backend/deploy/CLAUDE.md` "File Structure
   Target" is aspirational, the tree is the truth.
3. **Env edits are two-sided.** Adding/removing an `env:` entry in a fleet or a compose gameserver service
   is checked against the gameserver's declared knobs by `GameServer.Tests/Deploy/*PassthroughTests`.
   Changing a port/deploy dir/compose project for an environment = GitHub Environment variable **and**
   its `environments.tsv` row in the same change (`docs/CICD.md` "reserved-identity registry").
4. **Validate offline** (Validation delta), comparing against the base commit where a check is
   already red at HEAD. Never "fix" a pre-existing failure silently; report it.
5. **Stop before any live action** and hand the user the exact command (Human gates).
6. Obligations: `backend/deploy/CHANGELOG.md` `[Unreleased]`; the matching `backend/deploy/docs/*.md`.

## Rules

- ADR-2: a map-pinned fleet (fixed `GAMESERVER_MAP_ID`) runs `replicas: 1` and **never** gets a
  FleetAutoscaler; the only autoscaler targets the dungeon fleet (`k8s/app/70-...`), policy `Buffer`
  only (ADR-14 decision 5). Source: `docs/K3S.md` "Why there is no autoscaler on a MAP fleet".
- Apply order in `k8s/app/`: autoscaler last, after the dungeon fleet image is pinned
  (`k8s/app/README.md` "Apply"). `dev-up.sh` encodes the order; do not reorder by hand.
- Fleets: port named `game`, `portPolicy: Dynamic`, `POD_NAME` from `metadata.name`, no `GAMESERVER_ID`,
  no `GAMESERVER_PUBLIC_ADDR`, no literal secret values (`docs/K3S.md` "Offline validation").
- Secrets never in git: `k8s/app/30-secret-template.yaml` and `agones/secret-example.yaml` stay templates;
  `.env`, `.env.scratch`, `kubeconfig.local*` are gitignored (`backend/deploy/.gitignore`).
- WSL: `docker` is Docker Desktop's shim. Bind-mount sources must be literal relative paths
  (`./monitoring`), never `$PWD`/absolute (`docs/CICD.md` "path-translation rule").
- `monitoring/prometheus.yaml` replaces the otel-lgtm default: keep the copied `otlp:`/`storage:` blocks
  when bumping `OTEL_LGTM_VERSION`; keep `metric_name_escaping_scheme: underscores` on gameserver jobs
  (`docs/MONITORING.md`).
- DB: never edit a shipped migration; `db/migrations/gamestate/*.sql` are verbatim ops copies of
  `GameServer/Persistence/Migrations/`; `db/init-gamestate.sql` mirrors `001_init.sql` only
  (`docs/DATABASE.md` section 1).
- A merge to `develop` **is** a deploy to dev (`cd.yml` on push). CI does not run any of the offline
  deploy checks below, so they are the only gate before that deploy.
- Never quote a player-count ceiling or tier CCU as measured (`backend/deploy/CLAUDE.md` section 8, ADR-7).

## Generated & protected paths

- Protected (never read, never commit): `backend/deploy/.env`, `.env.scratch`, `kubeconfig.local*`,
  `agones/secret-*.local.yaml`. Use `.env.example` when a command needs an env file.
- `modules/*.so`: built by `make plugin` (gitignored).
- `k8s/app/proof/`, `k8s/verify/tests/` fixtures: captured evidence; change only with a new capture.
- No generator-owned files in these modules.

## Validation delta

Core's fast tier runs the registry checks. Domain reading of them (details and baseline results
in `references/manifests-and-checks.md`):

| Tier | Check | When | Evidence |
|---|---|---|---|
| fast | `k3s/validate-manifests.py` (no args) | any `agones/` or `k3s/` yaml | `6 document(s) validated, 0 failure(s)` at `5023a3d`, exit 0 |
| extended | `k3s/validate-manifests.py k8s/app/*.yaml` | any `k8s/app/` yaml | `[FAIL]` set identical to base commit (2 known namespace FAILs at `5023a3d`); new FAIL = failed |
| fast | `bash verify/tests/autoscaler_rule_test.sh` (cwd `k8s`) | fleet/autoscaler/verify lib edits | `RESULT=PASS`, 3 cases OK |
| fast | `docker compose --env-file .env.example ... config -q` | compose edits | exit 0, no output, for base + override + agones |
| extended | Deploy passthrough tests (`FullyQualifiedName~GameServer.Tests.Deploy`) | `env:` in fleet or compose | dotnet counts, Total > 0, 0 failed |
| fast (server-services leg) | `MigratorTests` (`EmbeddedMigrations_MatchDeployCopies`, `InitGamestateSql_MatchesFirstMigration`) | `db/*.sql` (server-services leg) | passed counts |
| fast | monitoring yaml/json parse | `monitoring/` | exit 0; **no promtool locally** - rule semantics `not-run:tool-missing` |

External (never self-run): `kubectl apply --dry-run=server`, `k8s/verify/verify.sh --target ...`,
`make flow-up && make flow-check`, `cd.yml` `post-deploy-smoke`. Report `not-run:external` with the
command the user should run.

## Human gates

Ask before, and never run unasked:
- `kubectl`, `helm`, `k3d`, `k3s`, `ssh`, `scp`, and scripts that wrap them: `k8s/dev-up.sh`,
  `k8s/rollback-to-compose.sh`, `k3s/setup-dev.sh`, `k3s/teardown-dev.sh`, `k8s/data/apply.sh`,
  `k8s/registry/push.sh`, `k8s/verify/verify.sh` (read-only, but hits a live cluster;
  `--allow-allocation` costs a GameServer).
- Starting/stopping stacks: `stack.sh up|down|check`, `make flow-*|up|down|reset|monitoring-*`,
  `docker compose up|down|restart`.
- `db/backup.sh`, `db/restore.sh` (destructive with `--yes`), `db/redis-*.sh`.
- `gh workflow run cd.yml|publish-images.yml`, re-running CD runs, merging to develop/staging/release-*.
- Reading or committing `.env`, `kubeconfig.local*`, secrets; editing GitHub Environment variables.
- Any action against staging or production.

## Review checklist

- [ ] No literal secret, no new tracked file matching `.gitignore` secret patterns.
- [ ] Map fleet still `replicas: 1`, no autoscaler targets it; dungeon autoscaler `Buffer`.
- [ ] Env added to fleet/compose is a declared gameserver knob (passthrough tests) and documented.
- [ ] Port/identity changes mirrored in `environments.tsv` and called out for the GitHub Environment.
- [ ] Bind mounts relative; new mount source is bundled by `cd.yml` `bundle` if compose needs it on hosts.
- [ ] Validator `[FAIL]` set not larger than base; `[warn]` lines reviewed.
- [ ] CHANGELOG + governing doc updated; stale doc claims touched by the change corrected.

## Report additions

- Target environments affected and which gates are pending, each with the exact command for the user.
- Validator output delta vs base commit (FAIL/warn lines), autoscaler test `RESULT=` line.
- For compose/fleet env edits: passthrough test counts or `not-run` state.
- "Deploys on merge to develop: yes/no" for the change.
