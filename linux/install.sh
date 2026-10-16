#!/bin/sh
set -eu

project=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
target="$HOME/.local/bin/vpngo"
mkdir -p "$HOME/.local/bin"
for command in python3 vopono wg ip ss pgrep nohup; do
    command -v "$command" >/dev/null 2>&1 || { printf 'Required command not found: %s\n' "$command" >&2; exit 1; }
done
if [ -e "$target" ] || [ -L "$target" ]; then
    if [ "$(readlink -f "$target")" = "$project/linux/vpngo" ]; then
        printf 'Already installed: %s\n' "$target"
        exit 0
    fi
    backup="$target.backup.$(date +%Y%m%d%H%M%S)"
    mv "$target" "$backup"
    printf 'Previous command saved as %s\n' "$backup"
fi
ln -sfn "$project/linux/vpngo" "$target"
printf 'Installed %s\n' "$target"
printf '%s\n' 'Make sure ~/.local/bin is on PATH.'
