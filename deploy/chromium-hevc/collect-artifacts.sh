#!/bin/sh
set -eu

CHROMIUM_VERSION="151.0.7922.173-1~deb13u1+hevc1"
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ARTIFACT_DIR="$SCRIPT_DIR/artifacts"

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 BUILD_DIR" >&2
    exit 2
fi

BUILD_DIR="$(readlink -f "$1")"
mkdir -p "$ARTIFACT_DIR"
STAGING_DIR="$(mktemp -d "$ARTIFACT_DIR/.staging.XXXXXX")"

cleanup() {
    rm -rf "$STAGING_DIR"
}
trap cleanup EXIT INT TERM

for package_name in chromium chromium-common chromium-sandbox; do
    source_path="$BUILD_DIR/${package_name}_${CHROMIUM_VERSION}_arm64.deb"
    actual_package="$(dpkg-deb -f "$source_path" Package)"
    actual_version="$(dpkg-deb -f "$source_path" Version)"
    actual_architecture="$(dpkg-deb -f "$source_path" Architecture)"
    if [ "$actual_package" != "$package_name" ] || \
       [ "$actual_version" != "$CHROMIUM_VERSION" ] || \
       [ "$actual_architecture" != "arm64" ]; then
        echo "Unexpected package metadata in $source_path" >&2
        exit 1
    fi
    install -m 0644 "$source_path" "$STAGING_DIR/"
done

(
    cd "$STAGING_DIR"
    sha256sum ./*.deb > SHA256SUMS
    sha256sum -c SHA256SUMS
)

find "$ARTIFACT_DIR" -maxdepth 1 -type f ! -name '.gitkeep' -delete
find "$STAGING_DIR" -maxdepth 1 -type f -exec mv -t "$ARTIFACT_DIR" -- {} +