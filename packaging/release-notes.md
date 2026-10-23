## Install

New to vpngo? Follow the [step-by-step guide](https://github.com/@REPOSITORY@/blob/v@VERSION@/docs/HOWTO.md) ([Português](https://github.com/@REPOSITORY@/blob/v@VERSION@/docs/HOWTO.pt-BR.md)) first; it lists what each system needs before installing.

**Linux**

```sh
curl -fLO https://github.com/@REPOSITORY@/releases/download/v@VERSION@/install-linux.sh
sh install-linux.sh
```

**macOS**

```sh
curl -fLO https://github.com/@REPOSITORY@/releases/download/v@VERSION@/install-macos.sh
sh install-macos.sh
```

**Windows**: download and run `vpngo-@VERSION@-windows-setup.exe` below. It asks whether to install the VPNGo app with its graphical interface or only the `vpngo` command, and needs no administrator rights. Silent install: `vpngo-@VERSION@-windows-setup.exe --silent` (add `--cli-only` for the command only).

**Windows** (PowerShell, command only)

```powershell
Invoke-WebRequest https://github.com/@REPOSITORY@/releases/download/v@VERSION@/install-windows.ps1 -OutFile install-windows.ps1
powershell -ExecutionPolicy Bypass -File .\install-windows.ps1
```

**Package managers** (stable releases only)

| System | Command |
| --- | --- |
| Arch Linux, CachyOS, Manjaro | Download `PKGBUILD` below into an empty folder, then `makepkg -si` there (install `vopono-bin` from the AUR first) |
| Ubuntu, Debian | `sudo apt install ./vpngo_*_all.deb` (download the `.deb` below; needs [vopono](https://github.com/jamesmcm/vopono/releases)) |
| Fedora | `sudo dnf install ./vpngo-*.noarch.rpm` (download the `.rpm` below; needs [vopono](https://github.com/jamesmcm/vopono/releases)) |
| macOS (Homebrew) | `brew tap @OWNER@/vpngo && brew trust @OWNER@/vpngo && brew install vpngo` (also installs Mihomo) |
| Windows (Scoop) | `scoop bucket add vpngo https://github.com/@OWNER@/scoop-vpngo` then `scoop install vpngo` (also installs Python and Mihomo) |

The installers download the archive for your system, check it against `SHA256SUMS`, install it in `~/.local/share/vpngo` (`%LOCALAPPDATA%\vpngo` on Windows) and create the `vpngo` command. Running a newer installer upgrades in place and keeps your profiles and settings.

## Files

| File | Contents |
| --- | --- |
| `vpngo-@VERSION@-linux.*` | Linux launcher, installer and test probe |
| `vpngo-@VERSION@-macos.*` | macOS launcher and installer |
| `vpngo-@VERSION@-windows.*` | Windows launcher and installer |
| `vpngo-@VERSION@-windows-setup.exe` | Windows setup (app with graphical interface, or command only) |
| `vpngo_*_all.deb`, `vpngo-*.noarch.rpm` | Linux packages for Ubuntu/Debian and Fedora |
| `PKGBUILD` | Arch Linux package recipe (stable releases) |
| `install-*.sh`, `install-windows.ps1` | Download-and-install scripts |
| `SHA256SUMS` | SHA-256 checksum of every file above |

Linux and macOS archives are `.tar.gz`; the Windows archive is `.zip`. To check a manual download, run `sha256sum -c SHA256SUMS --ignore-missing` (Linux), `shasum -a 256 -c SHA256SUMS --ignore-missing` (macOS) or compare `Get-FileHash <file>` with its line in `SHA256SUMS` (Windows).

vpngo is licensed under the Apache License 2.0. Redistributions must keep the `LICENSE` and `NOTICE` files.
