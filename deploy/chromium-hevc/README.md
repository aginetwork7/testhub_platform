# Chromium HEVC build

This directory contains the pinned ARM64 build and validation workflow for
Chromium `151.0.7922.173-1~deb13u1+hevc1`. The browser decodes the original HEVC
media; the workflow does not transcode test fixtures.

## Build

Run `build.sh` as root in an ARM64 Debian 13 environment. Use a dedicated,
writable working directory because the Chromium source tree and packages are
large:

```sh
cd /path/to/chromium-build
CHROMIUM_BUILD_JOBS=6 /path/to/testhub/deploy/chromium-hevc/build.sh
```

The build downloads pinned Debian sources and upstream patches, verifies their
hashes, applies the local Chromium 151 compatibility patches, and produces
Debian packages in the parent build directory.

## Collect and validate

Collect the three runtime packages from the build directory:

```sh
deploy/chromium-hevc/collect-artifacts.sh /path/to/chromium-build
```

Validate package checksums and browser playback against an unchanged HEVC file:

```sh
deploy/chromium-hevc/validate-artifacts.sh /path/to/input.mp4
```

The validation requires Docker and writes JSON evidence under `artifacts/` by
default. A successful probe requires decoded dimensions, no media error, and
at least 0.5 seconds of playback progress.

## Artifact policy

The `.deb` packages, checksum manifest, and playback evidence are local build
artifacts and are intentionally excluded from Git. Run the collection step
before building `Dockerfile.backend`; its package metadata and checksum gates
reject missing or unexpected artifacts.