# Deploy tree map and offline checks

Verified against `rpg-mmo-server` `develop` @ `5023a3d` on 2026-09-30. Paths are relative to
`backend/deploy/` unless stated.

## Where things live and which doc governs them

| Area | Files | Governing doc |
|---|---|---|
| Images | `docker/Dockerfile.{gameserver-dotnet,gateway,nakama,nakama-plugin}` (build context `backend/`) | `docs/CICD.md` "Container images (GHCR)" |
| Local stack | `docker-compose.yml`, `docker-compose.override.yml` (second map server `gameserver-dotnet-map02`), `docker-compose.agones.yml` (kubeconfig mount + k3d network), `stack.sh up\|check\|health\|logs\|ps\|down [--scratch] [--no-build]`, `Makefile` (`flow-*` wrap `stack.sh`) | `docs/RUNBOOK-local-dev.md` |
| Dev cluster, k8s-native | `k8s/data/` (kustomize: postgres x2, redis, nakama in `rpg-k8s-data`), `k8s/app/00..70-*.yaml` (gateway, map fleet, dungeon fleet, dungeon FleetAutoscaler in `rpg-k8s-realtime`), `k8s/dev-up.sh` (same script CD runs in `DEPLOY_MODE=k8s`), `k8s/rollback-to-compose.sh` | `k8s/README.md`, `k8s/app/README.md` |
| Legacy Agones dev | `agones/fleet-map-dotnet-dev.yaml`, `agones/allocation-dev.yaml`, `agones/secret-example.yaml`, `k3s/{setup-dev,teardown-dev,lib}.sh`, `k3s/namespaces.yaml` (`rpg-realtime`, `rpg-meta`, `rpg-data`) | `docs/K3S.md` |
| Deploy verification | `k8s/verify/verify.sh --target dev-agones\|k8s-dev\|k8s-stg [--layer N] [--list]` (layers: 1 cluster, 2 data, 3 registry, 4 flow, 5 client, 6 refusal), `k8s/verify/targets/*.env`, `k8s/verify/probe/` (Go, no tests) | `k8s/verify/README.md` |
| Monitoring | `monitoring/prometheus.yaml`, `monitoring/alerts.yaml` (loaded via `rule_files`), `monitoring/grafana-dashboards.yaml`, `monitoring/dashboards/rpg-gameplay.json`; mounted into `grafana/otel-lgtm:${OTEL_LGTM_VERSION:-0.11.15}` in `docker-compose.yml` | `docs/MONITORING.md` |
| Databases | `db/init-gamestate.sql`, `db/migrations/gamestate/001_init.sql`, `db/backup.sh`, `db/restore.sh`, `db/redis-backup.sh`, `db/redis-restore.sh` | `docs/DATABASE.md`, `docs/DISASTER-RECOVERY.md` |
| Environment isolation | `environments.tsv` (dev / staging / production rows: deploy dir, compose project, name prefix, ports), `preflight-isolation.sh` | `docs/CICD.md` "Two environments on one runner" |

Namespaces in use: `rpg-k8s-data`, `rpg-k8s-realtime` (current dev), `rpg-realtime` (pre-cutover
fleet, scaled to 0, rollback target). Source: `k8s/README.md`.

`MONITORING.md` "What we own" lists three files; `alerts.yaml` (added 2026-09-13) is the fourth.

**Host bundle.** `cd.yml` job `bundle` copies `docker-compose.yml`, `docker-compose.agones.yml`,
`Makefile`, `.env.example`, `monitoring/` and `db/` (not `docker-compose.override.yml`), then asserts
a fixed list of files exists (`cd.yml` ~lines 360-370; `monitoring/alerts.yaml` is not in that list).
A new bind-mount source or script the hosts need must be added to both the copy and the assert list,
or a missing file becomes an empty directory on the host (`docs/MONITORING.md` "How it ships").

## `k3s/validate-manifests.py`

Offline: pulls Agones `install.yaml` for `--agones-version` (default: fact `agones-default-version`), validates CRs against
the CRD `openAPIV3Schema`, then runs project contract checks (`check_fleet`, `check_autoscaler`,
`check_allocation`, `check_gateway_constants`). Needs `pyyaml` + `jsonschema`; first run needs network
(cache `$XDG_CACHE_HOME/rpg-mmo/agones-<ver>.yaml`, default `~/.cache/rpg-mmo/`). Use `python3 -B`
so nothing is written into the repo.

- **No arguments** = `agones/*.yaml` + `k3s/*.yaml` only; expected `N document(s) validated, 0 failure(s)`, exit 0.
- **`k8s/app/` must be passed explicitly**: `python3 -B k3s/validate-manifests.py k8s/app/*.yaml`.
  Pre-existing failures (count = fact `k8s-app-baseline-validation-failures`), exit 1. They are `check_fleet`'s
  namespace rule (`rpg-k8s-realtime` vs gateway `DefaultNamespace` `rpg-realtime`), which
  `40-gateway.yaml` overrides with `ALLOCATOR_NAMESPACE`. Plus one `[warn]` for `DefaultFleetMap`.
  Judge a change by the **delta** of `[FAIL]` lines against the base commit.
- Pass fleets and their autoscaler/allocation **together**: fleet-name cross-checks only see fleets
  in the same invocation.
- Native kinds other than Namespace/Secret/ConfigMap (Deployment, Service, RBAC) are listed as
  `skipped (no schema available)`: they are **not** validated. Say so in the report.
- Schema-valid is not webhook-valid (bogus enum values pass). The stronger check is
  `kubectl apply --dry-run=server -f <file>` on the target cluster: human gate (`docs/K3S.md`
  "Stronger: server-side dry run").
- `--check-image IMAGE --expect-revision SHA` asserts a local image's revision label (needs docker).

## Other offline checks (verified exit 0 on 2026-09-30)

```bash
# cwd backend/deploy/k8s - canned kubectl JSON, no cluster; proves the ADR-2 autoscaler rule
bash verify/tests/autoscaler_rule_test.sh           # last line: RESULT=PASS (...)

# cwd backend/deploy - compose files resolve; .env.example avoids reading the real .env
for c in "" "-f docker-compose.override.yml" "-f docker-compose.agones.yml"; do
  docker compose --env-file .env.example -f docker-compose.yml $c config -q || exit 1; done

# cwd backend/deploy - monitoring files parse (no promtool/kubeconform installed on this box)
python3 -c "import yaml,json; [list(yaml.safe_load_all(open(f))) for f in ('monitoring/alerts.yaml','monitoring/prometheus.yaml','monitoring/grafana-dashboards.yaml')]; json.load(open('monitoring/dashboards/rpg-gameplay.json'))"

# cwd backend/deploy - 23 tracked scripts
for f in $(git ls-files '*.sh'); do bash -n "$f" || exit 1; done
```

## Tests in other modules that read deploy files

Run with Core's `{dotnet}` in `backend/gameserver-dotnet` (not run while authoring this skill):

| Test | Reads | Run when |
|---|---|---|
| `GameServer.Tests.Deploy.ComposeEnvPassthroughTests` | `docker-compose.yml` service `gameserver-dotnet`, `docker-compose.override.yml` service `gameserver-dotnet-map02` | compose gameserver `environment:` edits |
| `GameServer.Tests.Deploy.FleetEnvPassthroughTests` | `agones/fleet-map-dotnet-dev.yaml`, `k8s/app/50-fleet-map.yaml`, `k8s/app/60-fleet-dungeon.yaml` | fleet `env:` edits |
| `GameServer.Tests.Persistence.MigratorTests.EmbeddedMigrations_MatchDeployCopies` | `db/migrations/gamestate/*.sql` | migration copies |

Filter: `--filter "FullyQualifiedName~GameServer.Tests.Deploy"` (namespace verified). These run in
`ci-dotnet.yml` on every PR; the offline checks above run in **no** workflow.
