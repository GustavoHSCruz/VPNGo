#!/bin/sh
# Download, verify and install vpngo @VERSION@ for Linux.
#
#   sh install-linux.sh
#
# VPNGO_VERSION installs another release. VPNGO_PREFIX changes the install folder
# (default: ~/.local/share/vpngo). VPNGO_RELEASE_URL downloads from another
# location, such as a local mirror.
set -eu

version=${VPNGO_VERSION:-@VERSION@}
repository=@REPOSITORY@
system=linux
asset="vpngo-$version-$system.tar.gz"
base=${VPNGO_RELEASE_URL:-https://github.com/$repository/releases/download/v$version}
prefix=${VPNGO_PREFIX:-${XDG_DATA_HOME:-$HOME/.local/share}/vpngo}

fail() {
    printf 'vpngo installer: %s\n' "$*" >&2
    exit 1
}

download() {
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL -o "$2" "$1" || fail "could not download $1"
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "$2" "$1" || fail "could not download $1"
    else
        fail 'curl or wget is required.'
    fi
}

sha256() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d ' ' -f 1
    else
        shasum -a 256 "$1" | cut -d ' ' -f 1
    fi
}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT INT TERM

printf 'Downloading vpngo %s for Linux...\n' "$version"
download "$base/$asset" "$work/$asset"
download "$base/SHA256SUMS" "$work/SHA256SUMS"
expected=$(awk -v name="$asset" '$2 == name || $2 == "*" name { print $1; exit }' "$work/SHA256SUMS")
[ -n "$expected" ] || fail "$asset is not listed in SHA256SUMS."
[ "$(sha256 "$work/$asset")" = "$expected" ] || fail "checksum mismatch for $asset; the download is corrupt or was altered."
printf 'Checksum verified.\n'

tar -xzf "$work/$asset" -C "$work"
mkdir -p "$prefix"
rm -rf "$prefix/app.new" "$prefix/app.old"
mv "$work/vpngo-$version-$system" "$prefix/app.new"
if [ -d "$prefix/app" ]; then
    mv "$prefix/app" "$prefix/app.old"
fi
mv "$prefix/app.new" "$prefix/app"
rm -rf "$prefix/app.old"

"$prefix/app/linux/install.sh" ||
    fail 'install the missing tools (step 1 of the Linux guide), then run this installer again.'
printf 'vpngo %s installed in %s\n' "$version" "$prefix/app"
