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
shim="$HOME/.local/bin/vpngo"

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
trap 'rm -rf "$work"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

rollback() {
    status=$?
    trap - EXIT INT TERM
    if [ "$status" -ne 0 ] && [ "${swapped:-0}" -eq 1 ]; then
        if [ -d "$prefix/app.old" ]; then
            rm -rf "$prefix/app"
            mv "$prefix/app.old" "$prefix/app"
        elif [ "${had_app:-0}" -eq 0 ]; then
            rm -rf "$prefix/app"
        fi
        rm -f "$shim"
        if [ -e "$work/previous-command" ] || [ -L "$work/previous-command" ]; then
            mv "$work/previous-command" "$shim"
        fi
        printf '%s\n' 'vpngo installer: previous installation restored.' >&2
    fi
    rm -rf "$work"
    exit "$status"
}

printf 'Downloading vpngo %s for Linux...\n' "$version"
download "$base/$asset" "$work/$asset"
download "$base/SHA256SUMS" "$work/SHA256SUMS"
expected=$(awk -v name="$asset" '$2 == name || $2 == "*" name { print $1; exit }' "$work/SHA256SUMS")
[ -n "$expected" ] || fail "$asset is not listed in SHA256SUMS."
[ "$(sha256 "$work/$asset")" = "$expected" ] || fail "checksum mismatch for $asset; the download is corrupt or was altered."
printf 'Checksum verified.\n'

tar -xzf "$work/$asset" -C "$work"
mkdir -p "$prefix"
[ ! -e "$prefix/app.old" ] || fail 'app.old exists; resolve the previous interrupted upgrade before retrying.'
if [ -e "$shim" ] || [ -L "$shim" ]; then
    cp -pP "$shim" "$work/previous-command"
fi
rm -rf "$prefix/app.new"
mv "$work/vpngo-$version-$system" "$prefix/app.new"
had_app=0
if [ -d "$prefix/app" ]; then
    had_app=1
fi
swapped=1
trap rollback EXIT
if [ "$had_app" -eq 1 ]; then
    mv "$prefix/app" "$prefix/app.old"
fi
mv "$prefix/app.new" "$prefix/app"

"$prefix/app/linux/install.sh" ||
    fail 'install the missing tools (step 1 of the Linux guide), then run this installer again.'
[ "$("$prefix/app/linux/vpngo" version)" = "vpngo $version" ] ||
    fail 'the installed vpngo version did not validate.'
swapped=0
rm -rf "$prefix/app.old" || printf '%s\n' 'vpngo installer: could not remove app.old; remove it before the next upgrade.' >&2
printf 'vpngo %s installed in %s\n' "$version" "$prefix/app"
