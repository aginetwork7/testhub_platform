#!/bin/sh
set -eu

CHROMIUM_VERSION="151.0.7922.173"
DEBIAN_REVISION="1~deb13u1"
HEVC_DEBIAN_REVISION="${DEBIAN_REVISION}+hevc1"
PATCH_COMMIT="027325135a14413f54cbd8bdbfcfbc2ce3ba3eb2"
LLVM_PACKAGE_VERSION="1:22.1.8~++20260714015211+ca7933e47d3a-1~exp1~20260714135221.79"
LLVM_SIGNING_FINGERPRINT="6084F3CF814B57C1CF12EFD515CF4D18AF4F7421"
SOURCE_DIR="chromium-${CHROMIUM_VERSION}"
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

configure_sources() {
    cat > /etc/apt/sources.list.d/debian.sources <<'EOF'
Types: deb deb-src
URIs: http://deb.debian.org/debian
Suites: trixie trixie-updates
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

Types: deb deb-src
URIs: http://deb.debian.org/debian-security
Suites: trixie-security
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
EOF
}

configure_llvm_repository() {
    curl --retry 3 -fsSL https://apt.llvm.org/llvm-snapshot.gpg.key -o /tmp/llvm.asc
    actual_fingerprint="$(gpg --show-keys --with-colons /tmp/llvm.asc | sed -n 's/^fpr:::::::::\([^:]*\):$/\1/p' | head -n 1)"
    if [ "$actual_fingerprint" != "$LLVM_SIGNING_FINGERPRINT" ]; then
        echo "Unexpected LLVM repository signing key: $actual_fingerprint" >&2
        exit 1
    fi
    install -m 0644 /tmp/llvm.asc /usr/share/keyrings/apt.llvm.org.asc
    cat > /etc/apt/sources.list.d/llvm.sources <<'EOF'
Types: deb
URIs: https://apt.llvm.org/trixie/
Suites: llvm-toolchain-trixie-22
Components: main
Signed-By: /usr/share/keyrings/apt.llvm.org.asc
EOF
    apt-get update
    apt-get install -y --no-install-recommends \
        "llvm-22=${LLVM_PACKAGE_VERSION}" \
        "lld-22=${LLVM_PACKAGE_VERSION}" \
        "clang-22=${LLVM_PACKAGE_VERSION}" \
        "clang-format-22=${LLVM_PACKAGE_VERSION}" \
        "libclang-rt-22-dev=${LLVM_PACKAGE_VERSION}" \
        "libc++-22-dev=${LLVM_PACKAGE_VERSION}"
}

verify_sources() {
    sha256sum -c <<EOF
9ed2e1d02d10a0eaa7d5f08c513ce0ac459b0dfa10ef14dfe98dede89bff2fc6  chromium_${CHROMIUM_VERSION}-${DEBIAN_REVISION}.dsc
4655486724e0f2765949d439d8e8caee4801ce47ed9f2bd52bcb8236fbecdeb6  chromium_${CHROMIUM_VERSION}.orig-pre-gen.tar.xz
d0330f43015f2538a69bdb66a13a9f955f44c8dbc1bcaed4452d54858ee0709c  chromium_${CHROMIUM_VERSION}.orig.tar.xz
2eb1314335e5761d1930e6e029931dd2b398fd755ba9e02ffc16a1eee1b4cf3a  chromium_${CHROMIUM_VERSION}-${DEBIAN_REVISION}.debian.tar.xz
EOF
}

fetch_sources() {
    if [ ! -f "chromium_${CHROMIUM_VERSION}-${DEBIAN_REVISION}.dsc" ]; then
        apt-get source --download-only "chromium=${CHROMIUM_VERSION}-${DEBIAN_REVISION}"
    fi
    verify_sources
}

patch_sources() {
    curl -fsSL \
        "https://raw.githubusercontent.com/StaZhu/enable-chromium-hevc-hardware-decoding/${PATCH_COMMIT}/add-hevc-ffmpeg-decoder-parser.cjs" \
        -o /tmp/add-hevc-ffmpeg-decoder-parser.cjs
    curl -fsSL \
        "https://raw.githubusercontent.com/StaZhu/enable-chromium-hevc-hardware-decoding/${PATCH_COMMIT}/enable-hevc-ffmpeg-decoding.patch" \
        -o /tmp/enable-hevc-ffmpeg-decoding.patch
    echo "af5a41105c79c1fc75516214b8ff6076a945abe453db1f7455088abf43c52a7d  /tmp/add-hevc-ffmpeg-decoder-parser.cjs" | sha256sum -c -
    echo "fe9249ff725bc63a054c0910beaa7f35a1fc4e7a189eaa54442788e4010e5a21  /tmp/enable-hevc-ffmpeg-decoding.patch" | sha256sum -c -

    node /tmp/add-hevc-ffmpeg-decoder-parser.cjs -r third_party/ffmpeg
    patch --batch --fuzz=0 -p1 < "$SCRIPT_DIR/chromium-151-ffmpeg-hevc-dependencies.patch"
    patch --batch --fuzz=0 -p1 < "$SCRIPT_DIR/chromium-151-ffmpeg-include.patch"
    patch --batch -p1 < /tmp/enable-hevc-ffmpeg-decoding.patch

    grep -q 'CONFIG_HEVC_DECODER 1' third_party/ffmpeg/chromium/config/Chrome/linux/arm64/config_components.h
    grep -q 'CONFIG_HEVC_PARSER 1' third_party/ffmpeg/chromium/config/Chrome/linux/arm64/config_components.h
    grep -q '&ff_hevc_decoder' third_party/ffmpeg/chromium/config/Chrome/linux/arm64/libavcodec/codec_list.c
    grep -q '&ff_hevc_parser' third_party/ffmpeg/chromium/config/Chrome/linux/arm64/libavcodec/parser_list.c
    grep -q 'libavcodec/aarch64/hevcdsp_init_aarch64.c' third_party/ffmpeg/ffmpeg_generated.gni
    grep -q 'libavcodec/aom_film_grain.c' third_party/ffmpeg/ffmpeg_generated.gni
    grep -q 'libavcodec/dovi_rpudec.c' third_party/ffmpeg/ffmpeg_generated.gni
    grep -q 'libavcodec/dovi_rpu.c' third_party/ffmpeg/ffmpeg_generated.gni
    grep -q 'libavcodec/dynamic_hdr_vivid.c' third_party/ffmpeg/ffmpeg_generated.gni
    grep -q '    "libavcodec",' third_party/ffmpeg/BUILD.gn
    grep -q 'return "h264,hevc"' media/ffmpeg/ffmpeg_common.cc
}

set_package_revision() {
    DEBEMAIL="testhub-build@localhost" DEBFULLNAME="TestHub Build" \
        dch --newversion "${CHROMIUM_VERSION}-${HEVC_DEBIAN_REVISION}" \
        --distribution trixie-security \
        'Enable bundled FFmpeg HEVC software decoding.'
}

build_packages() {
    export DEB_BUILD_OPTIONS="nocheck terse parallel=${CHROMIUM_BUILD_JOBS:-2}"
    dpkg-buildpackage --build=binary --no-sign
}

if [ "$(dpkg --print-architecture)" != "arm64" ]; then
    echo "This build is pinned to Debian ARM64." >&2
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive
configure_sources
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl dpkg-dev gpg nodejs patch
configure_llvm_repository
fetch_sources
rm -rf "$SOURCE_DIR"
dpkg-source -x "chromium_${CHROMIUM_VERSION}-${DEBIAN_REVISION}.dsc"
cd "$SOURCE_DIR"
patch_sources
set_package_revision
apt-get build-dep -y "chromium=${CHROMIUM_VERSION}-${DEBIAN_REVISION}"
build_packages