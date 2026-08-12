#!/usr/bin/env bash

set -euo pipefail
umask 077

usage() {
    printf 'Usage: %s <tag>\nExample: %s v1.2.0\n' "$0" "$0" >&2
    exit 2
}

tag="${1:-}"
[[ "$#" -eq 1 && "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([-.][0-9A-Za-z.-]+)?$ ]] || usage

repository_root="$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel)"
cd "$repository_root"

environment_file="deploy/env/agi7.testhub.env"
backup_directory="${TESTHUB_BACKUP_DIR:-$HOME/testhub-backups}"

[[ -f "$environment_file" ]] || {
    printf 'Missing production environment file: %s\n' "$environment_file" >&2
    exit 1
}

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    printf 'Production worktree has tracked changes; commit or stash them before deployment.\n' >&2
    exit 1
fi

git fetch origin base --tags --prune

release_commit="$(git rev-parse --verify --quiet "refs/tags/$tag^{commit}")" || {
    printf 'Unknown release tag: %s\n' "$tag" >&2
    exit 1
}

if ! git merge-base --is-ancestor "$release_commit" origin/base; then
    printf 'Tag %s is not reachable from origin/base.\n' "$tag" >&2
    exit 1
fi

mkdir -p "$backup_directory"
backup_file="$backup_directory/testhub-before-$tag-$(date +%Y%m%d-%H%M%S).sql"

docker compose --env-file "$environment_file" config -q
docker compose --env-file "$environment_file" exec -T db \
    mysqldump -uroot -prootpassword --single-transaction --routines --triggers testhub > "$backup_file"

git checkout --detach "$release_commit"
docker compose --env-file "$environment_file" up -d --build
docker compose --env-file "$environment_file" ps

printf 'Deployed %s (%s). Database backup: %s\n' "$tag" "$release_commit" "$backup_file"