#!/bin/sh
set -eu

CHROMIUM_VERSION="151.0.7922.173-1~deb13u1+hevc1"
PLAYWRIGHT_VERSION="1.58.0"
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ARTIFACT_DIR="${ARTIFACT_DIR:-$SCRIPT_DIR/artifacts}"

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    echo "Usage: $0 MEDIA_PATH [EVIDENCE_PATH]" >&2
    exit 2
fi

MEDIA_PATH="$(readlink -f "$1")"
EVIDENCE_PATH="$(readlink -f "${2:-$ARTIFACT_DIR/hevc-playback-evidence.json}")"
EVIDENCE_DIR="$(dirname -- "$EVIDENCE_PATH")"
mkdir -p "$EVIDENCE_DIR"

for package_name in chromium chromium-common chromium-sandbox; do
    test -f "$ARTIFACT_DIR/${package_name}_${CHROMIUM_VERSION}_arm64.deb"
done

(
    cd "$ARTIFACT_DIR"
    sha256sum -c SHA256SUMS
)

docker run --rm --shm-size=1g \
    -e "CHROMIUM_VERSION=$CHROMIUM_VERSION" \
    -e "PLAYWRIGHT_VERSION=$PLAYWRIGHT_VERSION" \
    -v "$ARTIFACT_DIR:/artifacts:ro" \
    -v "$SCRIPT_DIR:/probe:ro" \
    -v "$MEDIA_PATH:/fixture/input.mp4:ro" \
    -v "$EVIDENCE_DIR:/evidence" \
    python:3.12-slim sh -eu -c '
        apt-get update
        apt-get install -y --no-install-recommends \
            "/artifacts/chromium-common_${CHROMIUM_VERSION}_arm64.deb" \
            "/artifacts/chromium-sandbox_${CHROMIUM_VERSION}_arm64.deb" \
            "/artifacts/chromium_${CHROMIUM_VERSION}_arm64.deb"
        pip install --no-cache-dir "playwright==${PLAYWRIGHT_VERSION}"
        python /probe/probe.py \
            --browser /usr/lib/chromium/chromium \
            --media /fixture/input.mp4 \
            --evidence "/evidence/'"$(basename -- "$EVIDENCE_PATH")"'"
    '