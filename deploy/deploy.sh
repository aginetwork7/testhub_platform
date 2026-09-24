#!/usr/bin/env bash

set -euo pipefail
umask 077

# The Chromium HEVC packages installed by Dockerfile.backend are excluded from
# Git, so each checkout must be provisioned with them by hand. Check them here
# so a missing or corrupt set fails before the backup and the image build.
verify_chromium_artifacts() {
    local artifact_dir="deploy/chromium-hevc/artifacts"
    local version package_name package_file
    version="$(sed -n 's/^ARG HEVC_CHROMIUM_VERSION="\([^"]*\)"$/\1/p' Dockerfile.backend)"
    [[ -n "$version" ]] || {
        printf 'Cannot read HEVC_CHROMIUM_VERSION from Dockerfile.backend.\n' >&2
        return 1
    }
    for package_name in chromium chromium-common chromium-sandbox; do
        package_file="${package_name}_${version}_arm64.deb"
        [[ -f "$artifact_dir/$package_file" ]] || {
            printf 'Missing %s/%s.\n' "$artifact_dir" "$package_file" >&2
            return 1
        }
    done
    [[ -f "$artifact_dir/SHA256SUMS" ]] || {
        printf 'Missing %s/SHA256SUMS.\n' "$artifact_dir" >&2
        return 1
    }
    (cd "$artifact_dir" && sha256sum --quiet -c SHA256SUMS)
}

# The nginx config is mounted as a directory. A bind mount binds the directory's inode, not its path, so
# any git operation that rebuilds that directory — a merge, a branch switch, a clean — leaves the container
# holding an orphaned inode and seeing an empty conf.d. That failure is silent in the worst way: `nginx -t`
# still passes because an empty conf.d is valid, and the site keeps serving from the config already in
# memory, so nothing looks wrong until nginx is next reloaded and comes up serving nothing.
#
# Rather than trying to predict when git rebuilds the directory, check the outcome: the container must be
# able to see its own config after the deploy. Recreating the container re-resolves the mount.
verify_nginx_config() {
    local environment_file="$1"
    docker compose --env-file "$environment_file" exec -T nginx \
        sh -c '[ -n "$(ls -A /etc/nginx/conf.d 2>/dev/null)" ]' 2>/dev/null || return 1
    docker compose --env-file "$environment_file" exec -T nginx nginx -t >/dev/null 2>&1
}

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

verify_chromium_artifacts || {
    printf 'Chromium HEVC packages are not tracked by Git; copy the validated *.deb files and SHA256SUMS into deploy/chromium-hevc/artifacts before deploying (see deploy/chromium-hevc/README.md).\n' >&2
    exit 1
}

mkdir -p "$backup_directory"
backup_file="$backup_directory/testhub-before-base-$(date +%Y%m%d-%H%M%S).sql"

docker compose --env-file "$environment_file" exec -T db \
    mysqldump -uroot -prootpassword --single-transaction --routines --triggers testhub > "$backup_file"

docker compose --env-file "$environment_file" up -d --build

# `up -d` leaves a container alone when its service definition has not changed, which is exactly how the
# nginx container ends up still bound to a directory git has since replaced. Only force a recreate when the
# check below says the mount really did go stale, so an ordinary deploy still avoids the needless restart.
if ! verify_nginx_config "$environment_file"; then
    printf 'nginx cannot see its config after deployment; recreating the container to re-resolve the mount.\n' >&2
    docker compose --env-file "$environment_file" up -d --force-recreate nginx
    verify_nginx_config "$environment_file" || {
        printf 'nginx still cannot see /etc/nginx/conf.d after a forced recreate; deployment left it broken.\n' >&2
        exit 1
    }
fi

docker compose --env-file "$environment_file" ps

printf 'Deployed base revision %s. Database backup: %s\n' "$deployment_commit" "$backup_file"