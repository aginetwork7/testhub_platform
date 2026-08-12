# Dual-Environment Docker Deployment

Each environment has its own Compose project, containers, network, volumes,
host directories, secrets, database, Redis instance, and Hermes state.

## Required Host Layout

The debug stack runs from `/home/lijun/testhub_platform`. The production stack
runs from `/home/agi7/testhub_platform` and must be owned by `agi7`. Create the
production secret file at `/home/agi7/.secrets/hermes_api_key`; do not copy or
mount the debug user's secret directory.

Copy each template to the same path without `.example`, for example
`deploy/env/agi7.testhub.env` and `deploy/env/agi7.hermes.env`. These populated
files are ignored by Git. Fill the runner tokens, Swagger token, host names, and
Hermes API key paths before use.

## Cutover Order

1. Create the `agi7` working copy and its separate runtime directories.
2. Start `agi7` TestHub with `docker compose --env-file deploy/env/agi7.testhub.env up -d --build`. This creates `agi7_testhub_default`.
3. Start the matching Hermes stack with `docker compose -f deploy/hermes/docker-compose.yml --env-file deploy/env/agi7.hermes.env up -d`.
4. Migrate the debug stack to the equivalent `lijun` environment files, then start its Hermes stack.
5. Start the shared edge proxy with `docker compose -f docker-compose.edge.yml --env-file deploy/env/edge.env up -d`.

The application Nginx containers are private. The edge proxy is the only
container that publishes port `80`; it routes `DEBUG_SERVER_NAME` and
`PRODUCTION_SERVER_NAME` to the corresponding application Nginx containers.
Create DNS records for those two names before the final cutover.

## Verification

Run `docker compose --env-file <environment-file> config` before each startup.
Then verify that `docker ps --format '{{.Names}}'` contains the expected
`lijun_` and `agi7_` prefixes, and that `docker network inspect
<instance>_testhub_default` lists only that environment's application services
and its matching Hermes services.

## Tag-Based Production Releases

After changes are merged into `base`, open the repository's **Actions** tab and
run **Create Release Tag**. The workflow always checks out the latest `base`
commit, creates an annotated tag, and increments the highest existing stable
`vX.Y.Z` tag by one patch version. For example, after `v0.1.2`, it creates
`v0.1.3`.

GitHub exposes manually dispatched workflows only when their workflow file is
present on the repository default branch. This repository currently uses
`main` as its default branch, so merge `.github/workflows/create-release-tag.yml`
into `main` once, or change the repository default branch to `base`. The
workflow itself always tags `base` in either case.

On the production host, deploy that exact release as the `agi7` user:

```bash
sudo -n -u agi7 /home/agi7/testhub_platform/deploy/deploy.sh v1.2.0
```

For the first release containing this script, fetch and check out that tag once
before running the command above:

```bash
sudo -n -u agi7 sh -c '
cd /home/agi7/testhub_platform
git fetch origin --tags
git checkout --detach v1.2.0
./deploy/deploy.sh v1.2.0
'
```

The deployment script refuses tracked source changes, verifies that the tag is
reachable from `origin/base`, creates a MySQL backup under
`$HOME/testhub-backups`, checks out the release in detached-HEAD mode, and
rebuilds the existing Compose stack. It does not delete Docker volumes or
ignored production configuration files.