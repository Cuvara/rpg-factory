# CD pipeline, image publishing, environments

Verified against `rpg-mmo-server` `develop` @ `5023a3d` on 2026-09-30. Sources:
`.github/workflows/cd.yml`, `.github/workflows/publish-images.yml`, `backend/deploy/docs/CICD.md`,
`backend/deploy/environments.tsv`.

## What deploys, and when

| Trigger | Workflow | Effect |
|---|---|---|
| push to `develop` | `cd.yml` | deploys **dev** (self-hosted runner labels `self-hosted, dev`) |
| push to `staging` | `cd.yml` | deploys **staging** |
| push to `release-*` | `cd.yml` | deploys **production**, pushes GHCR images (`build-images`) |
| `workflow_dispatch` (`environment`, `skip_tests`, `build_images`) | `cd.yml` | deploys any ref to the chosen environment; also the rollback path |
| push to `develop` touching gateway/shared/gameserver-dotnet/`deploy/docker/**`; push of `core-baseline-*` tags; dispatch (`ref`, `tag`) | `publish-images.yml` | builds + pushes gateway and gameserver-dotnet to GHCR, deploys nothing; never writes `:latest` |

So **merging a PR into develop is a dev deploy.** `ci.yml` / `ci-dotnet.yml` gate PRs; neither runs
`validate-manifests.py`, `autoscaler_rule_test.sh`, `docker compose config`, promtool or kubeconform.

`cd.yml` jobs: `resolve`, `test-shared`, `test-gateway`, `test-nakama`, `test-smoketest`,
`test-integration`, `build-gateway`, `build-smoketest`, `build-verify-probe`, `build-plugin`,
`build-images`, `bundle`, `db-migrate`, `deploy`, `post-deploy-smoke`, `alert`, `summary`.
One deploy per environment at a time (`concurrency: cd-<env>`, cancel-in-progress).

Deploy-relevant steps, by line in `cd.yml`:

| Line | Step | Uses |
|---|---|---|
| 451 | pre-deploy Postgres backup (`db-migrate` job) | `backend/deploy/db/backup.sh --skip-missing` |
| 463 | pre-deploy Redis backup | `backend/deploy/db/redis-backup.sh --skip-missing` |
| 589 | Isolation preflight (first step of `deploy`, before the bundle sync) | `backend/deploy/preflight-isolation.sh` against `environments.tsv` |
| 1342 | Deploy to Kubernetes (`DEPLOY_MODE=k8s`, dev only) | `backend/deploy/k8s/dev-up.sh` |
| 1424 | k8s post-deploy verification | `./verify/verify.sh --target "${K8S_VERIFY_TARGET}"` |
| 1562 | `post-deploy-smoke` job | smoketest binary from the bundle |

Schema migrations run inside `deploy`, between the data tier and the realtime profile, not in
`db-migrate` (comment at top of `cd.yml`).

## Deploy modes (`vars.DEPLOY_MODE`, per GitHub Environment)

- `host` (default): bundle binaries supervised by `scripts/deploy-local.sh`.
- `containers`: images built on the runner from `backend/deploy/docker/Dockerfile.*`, brought up by
  the compose `realtime` profile.
- `k8s`: whole stack as k3s workloads via `k8s/dev-up.sh`; **dev only**.

The CICD.md "Deploy modes" table covers `host` / `containers`; `k8s` is documented in the `cd.yml`
header and `backend/deploy/k8s/README.md`.

## Environments on one host

All three environments are stacks on one runner host. `environments.tsv` reserves, per environment,
`deploy_dir`, `compose_project`, `name_prefix` and published ports:

| env | compose_project | prefix | gateway / gameserver ports (subset) |
|---|---|---|---|
| dev | `rpg-mmo-meta` | `rpg` | 8000, 9200 |
| staging | `rpg-mmo-staging` | `rpg-stg` | 8020, 9220 |
| production | `rpg-mmo-prod` | `rpg-prod` | 8010, 9210 |

`preflight-isolation.sh` fails the deploy when a resolved value belongs to another row or
contradicts its own row. The file is an assertion over the GitHub Environment variables, not the
source: change both in one change (`CICD.md` "The reserved-identity registry and the preflight guard").

## Rollback (`CICD.md` section 7)

1. Re-run the last good `cd.yml` run (artifact kept 14 days), or dispatch an older ref.
2. On the runner: `*.prev` binaries (host mode) or `rpg-mmo/<svc>:<sha>` re-tag (containers mode).
3. k8s dev: `k8s/rollback-to-compose.sh` (scales to zero, deletes GameServers, keeps PVCs/volumes).

All of these are human-gated. The skill writes the command into the report; the user runs it.

## WSL runner specifics

The dev runner is WSL; `docker` there is Docker Desktop's shim and `docker.exe` resolves absolute
`/mnt/...` paths against the Windows drive, silently mounting an empty directory for bind mounts
(`CICD.md` "4a" and "The path-translation rule"). `db/*.sh` and `scripts/build-all.sh` carry
`detect_docker()` for this.
