#!/bin/sh
set -eu

project=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
target="$HOME/.local/bin/vpngo"
mkdir -p "$HOME/.local/bin"
if [ -e "$target" ] || [ -L "$target" ]; then
    if [ "$(readlink "$target" 2>/dev/null || true)" = "$project/macos/vpngo" ]; then
        printf 'Already installed: %s\n' "$target"
        exit 0
    fi
    backup="$target.backup.$(date +%Y%m%d%H%M%S)"
    mv "$target" "$backup"
    printf 'Previous command saved as %s\n' "$backup"
fi
ln -s "$project/macos/vpngo" "$target"
printf 'Installed %s\n' "$target"
printf '%s\n' 'Make sure ~/.local/bin is on PATH.'
