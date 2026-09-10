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
docker compose --env-file "$environment_file" ps

printf 'Deployed base revision %s. Database backup: %s\n' "$deployment_commit" "$backup_file"