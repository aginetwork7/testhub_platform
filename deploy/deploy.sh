#!/usr/bin/env bash

set -euo pipefail
umask 077

[[ "$#" -eq 0 ]] || {
    printf 'Usage: %s\nDeploys the latest origin/base revision.\n' "$0" >&2
    exit 2
}

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

current_branch="$(git branch --show-current)"
if [[ "$current_branch" != "base" ]]; then
    printf 'Production checkout must already be on base; current branch: %s\n' "${current_branch:-detached HEAD}" >&2
    exit 1
fi

docker compose --env-file "$environment_file" config -q

git fetch origin base --prune
git merge --ff-only origin/base

deployment_commit="$(git rev-parse HEAD)"

mkdir -p "$backup_directory"
backup_file="$backup_directory/testhub-before-base-$(date +%Y%m%d-%H%M%S).sql"

docker compose --env-file "$environment_file" exec -T db \
    mysqldump -uroot -prootpassword --single-transaction --routines --triggers testhub > "$backup_file"

docker compose --env-file "$environment_file" up -d --build
docker compose --env-file "$environment_file" ps

printf 'Deployed base revision %s. Database backup: %s\n' "$deployment_commit" "$backup_file"