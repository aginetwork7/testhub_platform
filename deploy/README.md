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

## Chromium HEVC Packages

`Dockerfile.backend` installs the pinned Chromium HEVC build from
`deploy/chromium-hevc/artifacts/`. The `.deb` files and `SHA256SUMS` there are
ignored by Git, so a fresh clone or `git pull` never brings them along. Every
checkout that builds the backend image, including the production checkout,
needs its own copy. Copy the validated set from the build checkout before the
first deployment and again after every Chromium version bump:

```bash
cp deploy/chromium-hevc/artifacts/*.deb deploy/chromium-hevc/artifacts/SHA256SUMS \
   /home/agi7/testhub_platform/deploy/chromium-hevc/artifacts/
```

`deploy/deploy.sh` checks for the files and verifies their checksums before it
backs up the database or builds; without them the Docker build fails inside
the `sha256sum -c SHA256SUMS` step.

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

## One-Command Production Deployment

After changes are merged into `base`, deploy the latest `origin/base` revision
on the production host as the `agi7` user:

```bash
sudo -n -u agi7 /home/agi7/testhub_platform/deploy/deploy.sh
```

The deployment script requires the checkout to already be on a clean `base`
branch, validates the Compose configuration, creates a MySQL backup under
`$HOME/testhub-backups`, fast-forwards to `origin/base`, and rebuilds the
existing Compose stack. It does not delete Docker volumes or ignored production
configuration files.