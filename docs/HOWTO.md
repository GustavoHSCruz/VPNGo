# vpngo step-by-step guide

vpngo opens an application of your choice, such as Firefox or Discord, through a VPN. Only that application uses the VPN; everything else on the computer keeps using your normal connection.

You need:

- a computer with Linux, Windows or macOS;
- a VPN file in WireGuard format (`.conf`). Part 1 shows how to get one for free from Proton VPN;
- about 15 minutes.

Commands go in a terminal: **Terminal** on Linux and macOS, **PowerShell** on Windows. Copy each command, paste it into the terminal and press Enter. When the terminal asks for your password, type it and press Enter; nothing appears on screen while you type, which is normal.

> **Status by system.** Linux is tested. The Windows and macOS launchers are implemented but have not been tested on real computers yet. If you try them, a report helps a lot (see the README's [Contributing](../README.md#contributing) section).

## Contents

1. [Get your VPN file](#1-get-your-vpn-file) (all systems)
2. [Linux](#2-linux)
3. [Windows](#3-windows)
4. [macOS](#4-macos)
5. [Everyday use](#5-everyday-use) (all systems)
6. [Advanced options](#6-advanced-options)
7. [Problems and checks](#7-problems-and-checks)
8. [Where vpngo keeps its files](#8-where-vpngo-keeps-its-files)

## 1. Get your VPN file

vpngo does not create VPN accounts. It uses the WireGuard file your VPN provider gives you. Each file is one **profile**: one VPN exit, usually one country.

### Free Proton VPN file

vpngo was built and tested with these files.

1. Create a free account at [protonvpn.com](https://protonvpn.com) if you don't have one.
2. Sign in at [account.protonvpn.com](https://account.protonvpn.com).
3. Open **Downloads** and scroll to **WireGuard configuration**.
4. Type a name for the file, such as `vpngo-nl`. Proton lists your files by this name, so you can revoke one later.
5. Choose your platform (**GNU/Linux**, **Windows** or **macOS**). Leave the options as they are; free accounts can only toggle **VPN Accelerator**.
6. Pick a server from the free list and click **Create**. When it is ready, download the file. It lands in your **Downloads** folder with a `.conf` ending.

Create one file for each country you want. Keep in mind:

- The free plan allows very few simultaneous connections (one at the time of writing). Two apps on two free profiles at the same time may fail. Check Proton's current terms.
- Free files only work with free servers, and the country is fixed when you create the file.
- If a profile stops connecting, its key may have expired or been revoked on the same page. Create a new file and register it again under the same name.

Proton's own guide: [How to download WireGuard configuration files](https://protonvpn.com/support/wireguard-configurations/).

### Paid plans and other providers

Paid Proton plans use the same page and offer more servers and connections. Other providers and WireGuard servers you host yourself also work if the file passes these checks, which `vpngo profile add` runs for you:

- `[Interface]` has a valid `PrivateKey` and an `Address` that includes an IPv4 address.
- There is exactly one `[Peer]`, with a valid `PublicKey`, an `Endpoint` (`host:port` or `[IPv6]:port`) and `AllowedIPs` that include `0.0.0.0/0`.
- `DNS` is optional. Linux DNS isolation needs an IP address there.

OpenVPN, IKEv2 and VPN apps that cannot export a WireGuard file are not supported. The README has the [full field table](../README.md#profile-requirements).

## 2. Linux

**How it works on Linux:** vpngo uses [vopono](https://github.com/jamesmcm/vopono) to give each app its own isolated network with its own VPN tunnel. The kill switch is on by default: if the VPN drops, the app loses internet instead of falling back to your normal connection. vpngo asks for your password with `sudo` because creating that isolated network needs administrator rights.

### Step 1: Install what vpngo needs

Use the commands for your system.

**Arch Linux, CachyOS, Manjaro:**

```sh
sudo pacman -S --needed git python wireguard-tools iproute2 procps-ng iputils nftables
yay -S vopono-bin
```

If you use `paru` instead of `yay`, run `paru -S vopono-bin`.

**Ubuntu, Debian, Linux Mint, Pop!_OS** (64-bit Intel/AMD):

```sh
sudo apt update
sudo apt install git python3 wireguard-tools iproute2 procps iputils-ping nftables curl
curl -fLO https://github.com/jamesmcm/vopono/releases/download/1.0.2/vopono_1.0.2_amd64.deb
sudo apt install ./vopono_1.0.2_amd64.deb
```

**Fedora:**

```sh
sudo dnf install git python3 wireguard-tools iproute procps-ng iputils nftables
sudo dnf install https://github.com/jamesmcm/vopono/releases/download/1.0.2/vopono_1.0.2_amd64_fedora.rpm
```

Other systems and ARM computers: install the same tools from your package manager and vopono from [its releases page](https://github.com/jamesmcm/vopono/releases).

Optional: to use [DNS isolation](#linux-kill-switch-and-dns-isolation) later, also install `bubblewrap` (`sudo pacman -S bubblewrap`, `sudo apt install bubblewrap` or `sudo dnf install bubblewrap`).

### Step 2: Download and install vpngo

```sh
git clone https://github.com/GustavoHSCruz/VPNGo.git ~/VPNGo
~/VPNGo/linux/install.sh
```

The first command downloads vpngo into the `VPNGo` folder in your home directory. The second one is the **Linux installer**, `linux/install.sh`. It checks that step 1 worked and creates the `vpngo` command in `~/.local/bin`. It changes nothing else on your system. Keep the `~/VPNGo` folder: the command runs from there.

Close the terminal, open a new one and run `vpngo profile list`. If it answers `No VPN profiles configured.`, the installation worked. If it says `command not found`, `~/.local/bin` is not on your PATH yet. Log out and back in, or add it with:

```sh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc   # use ~/.zshrc if your terminal uses zsh
```

### Step 3: Register your VPN file

Move the file to a private folder and give it a short name, here `myvpn`. Replace `vpngo-nl.conf` with your file's name:

```sh
mkdir -p ~/.config/wireguard && chmod 700 ~/.config/wireguard
mv ~/Downloads/vpngo-nl.conf ~/.config/wireguard/
chmod 600 ~/.config/wireguard/*.conf
vpngo profile add myvpn ~/.config/wireguard/vpngo-nl.conf
```

vpngo remembers where the file is; it does not copy it. Don't move or delete it afterwards.

### Step 4: Open an app through the VPN

```sh
vpngo start firefox myvpn
```

vpngo asks for your password, closes Firefox if it is open and opens it again through the VPN. The command returns right away and Firefox stays open; you may close the terminal. vpngo remembers that Firefox uses `myvpn`, so next time `vpngo start firefox` is enough.

Use the program's command name: `firefox`, `chromium`, `discord`, `telegram-desktop`, and so on. If vpngo cannot find the program, see [App not found](#app-not-found).

### Step 5: Check that it works

Open [api.ipify.org](https://api.ipify.org) in Firefox and in another browser. The two numbers must be different. Firefox shows the VPN's address; the other browser shows yours.

### Turn it off

- `vpngo off firefox`: Firefox stays open and goes back to your normal connection. `vpngo on firefox` returns it to the VPN.
- `vpngo stop firefox`: closes Firefox and removes its VPN network. If you open Firefox normally afterwards, it uses your normal connection.

## 3. Windows

**How it works on Windows:** vpngo uses [Mihomo](https://github.com/MetaCubeX/mihomo), a free routing program. Mihomo creates one virtual network adapter and sends only the programs you choose through the VPN. Windows asks for permission (the "Do you want to allow this app to make changes to your device?" window) when Mihomo starts, because creating that adapter needs administrator rights.

Two limits to know: there is no kill switch, so if Mihomo stops, the apps go back to your normal connection. And an app that starts separate helper programs may need [extra setup](#helper-programs-windows-and-macos).

### Step 1: Install what vpngo needs

Open **PowerShell**: press the Windows key, type `PowerShell` and press Enter. Run these commands one at a time:

```powershell
winget install -e --id Git.Git
winget install 9NQ7512CXL7T
```

The first command installs Git, which downloads vpngo. The second installs the [Python install manager](https://www.python.org/downloads/latest/pymanager/) from the Microsoft Store; vpngo is written in Python. Accept the terms if winget asks.

Close PowerShell, open it again and run `python --version`. If it offers to install a Python version, accept. It must end up showing `Python 3.` followed by a number. If it opens the Microsoft Store instead, install **Python install manager** from the Store and try again.

Next, install Mihomo. These commands download the official build for your computer from the [Mihomo releases page](https://github.com/MetaCubeX/mihomo/releases) and save it as `mihomo.exe` in the `bin` folder of your user folder:

```powershell
$arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'amd64-compatible' }
New-Item -ItemType Directory -Force "$HOME\bin" | Out-Null
Invoke-WebRequest "https://github.com/MetaCubeX/mihomo/releases/download/v1.19.32/mihomo-windows-$arch-v1.19.32.zip" -OutFile "$env:TEMP\mihomo.zip"
Expand-Archive "$env:TEMP\mihomo.zip" "$env:TEMP\mihomo" -Force
Move-Item "$env:TEMP\mihomo\mihomo-windows-$arch.exe" "$HOME\bin\mihomo.exe" -Force
```

Mihomo already includes the Windows virtual adapter driver (Wintun); nothing else is needed. vpngo was checked against Mihomo v1.19.32. If you keep `mihomo.exe` somewhere else, set the `VPNGO_MIHOMO` variable to its full path.

### Step 2: Download and install vpngo

```powershell
git clone https://github.com/GustavoHSCruz/VPNGo.git "$HOME\VPNGo"
powershell -ExecutionPolicy Bypass -File "$HOME\VPNGo\windows\install.ps1"
```

The first command downloads vpngo into the `VPNGo` folder of your user folder (for example `C:\Users\you\VPNGo`). The second one runs the **Windows installer**, `windows\install.ps1`. Windows blocks scripts by default; `-ExecutionPolicy Bypass` allows only this run and does not change the setting for other scripts. The installer:

- creates the `vpngo` command as `vpngo.cmd` in `C:\Users\you\bin`;
- adds that folder to your user PATH, so PowerShell and Command Prompt find `vpngo` and `mihomo.exe`.

It needs no administrator rights and changes nothing else. Keep the `VPNGo` folder: the command runs from there.

Close PowerShell, open it again and run `vpngo profile list`. If it answers `No VPN profiles configured.`, the installation worked.

### Step 3: Register your VPN file

Move the file to a folder inside your user folder and give it a short name, here `myvpn`. Replace `vpngo-nl.conf` with your file's name:

```powershell
New-Item -ItemType Directory -Force "$HOME\vpn" | Out-Null
Move-Item "$HOME\Downloads\vpngo-nl.conf" "$HOME\vpn\"
vpngo profile add myvpn "$HOME\vpn\vpngo-nl.conf"
```

vpngo remembers where the file is and prepares Mihomo's configuration. Don't move or delete the file afterwards.

### Step 4: Open an app through the VPN

```powershell
vpngo start firefox myvpn
```

The first time, Windows asks for permission to run Mihomo: click **Yes**. A Mihomo window opens; **leave it open**, because closing it takes every app off the VPN. vpngo then closes Firefox if it is open and opens it again through the VPN. vpngo remembers that Firefox uses `myvpn`, so next time `vpngo start firefox` is enough.

Use the program's name without `.exe`: `firefox`, `chrome`, `discord`, and so on. vpngo searches `Program Files`, `Program Files (x86)` and `AppData\Local`. If it cannot find the program, see [App not found](#app-not-found).

### Step 5: Check that it works

Open [api.ipify.org](https://api.ipify.org) in Firefox and in Edge. The two numbers must be different. Firefox shows the VPN's address.

### Turn it off

- `vpngo off firefox`: Firefox stays open and goes back to your normal connection. `vpngo on firefox` returns it to the VPN.
- `vpngo stop firefox`: closes Firefox and **blocks** its internet while Mihomo is running. To open it with the VPN again, use `vpngo start firefox`; to use it without the VPN, run `vpngo off firefox` first.
- To turn everything off, close the Mihomo window. All apps go back to your normal connection.

## 4. macOS

**How it works on macOS:** vpngo uses [Mihomo](https://github.com/MetaCubeX/mihomo), a free routing program. Mihomo creates one virtual network interface and sends only the programs you choose through the VPN. vpngo asks for your Mac password with `sudo` when it starts Mihomo, because creating that interface needs administrator rights.

Two limits to know: there is no kill switch, so if Mihomo stops, the apps go back to your normal connection. And an app that starts separate helper programs may need [extra setup](#helper-programs-windows-and-macos).

### Step 1: Install what vpngo needs

Open **Terminal** (Applications → Utilities → Terminal) and run:

```sh
xcode-select --install
```

A window offers to install Apple's command line tools, which include Git and Python 3. Click **Install** and wait until it finishes. If the terminal says they are already installed, move on.

Next, install Mihomo. These commands download the official build for your Mac (Apple Silicon or Intel) from the [Mihomo releases page](https://github.com/MetaCubeX/mihomo/releases) and save it as `mihomo` in `~/.local/bin`:

```sh
arch=$(uname -m | sed 's/x86_64/amd64-compatible/')
mkdir -p ~/.local/bin
curl -fL -o /tmp/mihomo.gz "https://github.com/MetaCubeX/mihomo/releases/download/v1.19.32/mihomo-darwin-$arch-v1.19.32.gz"
gunzip -c /tmp/mihomo.gz > ~/.local/bin/mihomo && chmod +x ~/.local/bin/mihomo
```

vpngo was checked against Mihomo v1.19.32. If you already use [Homebrew](https://brew.sh), `brew install mihomo` also works; check that `brew info mihomo` shows a recent version.

Finally, make sure Terminal finds commands in `~/.local/bin`:

```sh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zprofile
```

### Step 2: Download and install vpngo

```sh
git clone https://github.com/GustavoHSCruz/VPNGo.git ~/VPNGo
~/VPNGo/macos/install.sh
```

The first command downloads vpngo into the `VPNGo` folder in your home folder. The second one is the **macOS installer**, `macos/install.sh`. It creates the `vpngo` command in `~/.local/bin` and changes nothing else. Keep the `~/VPNGo` folder: the command runs from there.

Close Terminal, open it again and run `vpngo profile list`. If it answers `No VPN profiles configured.`, the installation worked.

### Step 3: Register your VPN file

Move the file to a private folder and give it a short name, here `myvpn`. Replace `vpngo-nl.conf` with your file's name:

```sh
mkdir -p ~/.config/wireguard && chmod 700 ~/.config/wireguard
mv ~/Downloads/vpngo-nl.conf ~/.config/wireguard/
chmod 600 ~/.config/wireguard/*.conf
vpngo profile add myvpn ~/.config/wireguard/vpngo-nl.conf
```

vpngo remembers where the file is and prepares Mihomo's configuration. Don't move or delete the file afterwards.

### Step 4: Open an app through the VPN

```sh
vpngo start firefox myvpn
```

The first time, vpngo asks for your Mac password to start Mihomo, which keeps running in the background. vpngo then closes Firefox if it is open and opens it again through the VPN. vpngo remembers that Firefox uses `myvpn`, so next time `vpngo start firefox` is enough.

Use the app's name as it appears in the Applications folder, without `.app`: `firefox`, `discord`, `telegram`, and so on. Names with spaces go in quotes: `vpngo start "google chrome" myvpn`. If vpngo cannot find the app, see [App not found](#app-not-found).

### Step 5: Check that it works

Open [api.ipify.org](https://api.ipify.org) in Firefox and in Safari. The two numbers must be different. Firefox shows the VPN's address.

### Turn it off

- `vpngo off firefox`: Firefox stays open and goes back to your normal connection. `vpngo on firefox` returns it to the VPN.
- `vpngo stop firefox`: closes Firefox and **blocks** its internet while Mihomo is running. To open it with the VPN again, use `vpngo start firefox`; to use it without the VPN, run `vpngo off firefox` first.
- To turn everything off, stop Mihomo with `sudo pkill -x mihomo`. All apps go back to your normal connection.

## 5. Everyday use

The commands are the same on every system. Replace `app` with the program's name and `profile` with a name you chose in `profile add`.

| Command | What it does |
| --- | --- |
| `vpngo profile add <profile> <file.conf>` | Registers a VPN file under a name, or updates it. |
| `vpngo profile list` | Lists your profiles. |
| `vpngo start <app> [profile]` | Closes the app and opens it through its VPN. With a profile, also remembers that choice. |
| `vpngo assign <app> <profile>` | Changes which profile the app uses next time, without opening it. |
| `vpngo status <app>` | Shows whether the app is on the VPN and which profile it uses. |
| `vpngo switch <app> <profile>` | Moves an open app to another profile without closing it. |
| `vpngo off <app>` / `vpngo on <app>` | Moves an open app to your normal connection, or back to the VPN. |
| `vpngo stop <app>` | Closes the app and ends its VPN session. |

You can run several apps at the same time, each on its own profile:

```sh
vpngo profile add germany /path/to/de.conf
vpngo profile add brazil /path/to/br.conf
vpngo start firefox germany
vpngo start discord brazil
vpngo switch firefox brazil
```

**About `switch`.** Only the chosen app changes. Connections it already had are closed, and the app has to reconnect by itself. Most apps do it within seconds; if one stays offline, reload the page or use the app's own reconnect option. `switch` is refused while the app is on `off`; run `on` first.

- **Linux:** vpngo keeps the app's isolated network, swaps the VPN tunnel and checks that the new tunnel answers before confirming. If the check fails, it restores the previous tunnel, addresses, MTU, DNS and route. In a real test with two tunnels, the same app kept running while its public address changed. One DNS lookup failed during the change and the next request recovered without any action.
- **Windows and macOS:** vpngo changes Mihomo's choice for that app only and closes the connections Mihomo assigns to it.

## 6. Advanced options

### Linux kill switch and DNS isolation

On Linux, every app starts with the kill switch on. You can change this per app; the change applies at the next `start`:

```sh
vpngo policy example-app killswitch on
vpngo policy example-app dns on
vpngo start example-app
```

DNS isolation (`dns on`) needs `bubblewrap`, the kill switch, and an IP address in the `DNS =` line of the profile; Proton files have one. It makes the app look up website names through the VPN's DNS server instead of your computer's. Apps with their own DNS (DNS over HTTPS, for example), or that hand work to programs outside their isolated network, can still bypass it. Test the app before relying on it. To turn both off, turn DNS off first, then the kill switch.

On Windows and macOS, `policy ... killswitch on` and `policy ... dns on` are refused: Mihomo cannot guarantee them per app. If Mihomo stops, fails to identify a process, or a helper program has no rule, traffic can go through your normal connection.

### Helper programs (Windows and macOS)

On Linux, everything the app starts stays in its isolated network. On Windows and macOS, Mihomo recognizes programs by name, so a separate helper program that the app starts (an updater, a renderer, a separate network process) may use your normal connection. Register known helpers:

```sh
vpngo helper add example-app /full/path/to/helper
vpngo start example-app
```

The rule applies at the next `start`. It improves recognition but does not cover every possible process; check the address from inside the app when it matters.

## 7. Problems and checks

### App not found

vpngo looks for the program in your PATH, in folders you registered and in the usual installation folders. If it says `Application 'x' was not found`, tell it where the program is and try again:

```sh
vpngo config /opt/example-app/bin                      # Linux: the folder or the program file
vpngo config /Applications/Example.app                 # macOS: the .app
vpngo config "C:\Program Files\Example\example.exe"    # Windows: the .exe
```

### `vpngo` is not recognized

Close the terminal and open a new one. On Linux and macOS, repeat the PATH step of your system's installation. On Windows, check that `C:\Users\you\bin\vpngo.cmd` exists; if it doesn't, run the installer again.

### Linux

- `vpngo start` returns to the terminal and the app keeps running. If the app does not open, read the log: `tail -n 30 ~/.local/state/vpngo/start.log`.
- To compare addresses from the terminal, find the isolated network's name with `vopono status --json`, then compare `curl -4 https://api.ipify.org` with `sudo ip netns exec <name> curl -4 https://api.ipify.org`. The second must show the VPN's address.
- After a `switch`, vopono's own status still shows the server from when the app started. Trust `vpngo status <app>` and the observed address.
- If `switch` reports that the rollback needs repair, do not assume the route is safe. Inspect the WireGuard snapshot it names and restart the app.

**Test without closing your apps.** vpngo includes a test program, the probe, that writes its public address to the log about every ten seconds. Replace `myvpn` and `other` with two profiles you registered:

```sh
vpngo config ~/VPNGo/tests/manual/vpngo-probe
vpngo start vpngo-probe myvpn
vpngo switch vpngo-probe other
tail -n 12 ~/.local/state/vpngo/start.log
vpngo stop vpngo-probe
```

After `switch`, the address in the log must change to the new exit's. The probe makes fresh connections each time, so it does not prove that every app reconnects the same way. To test two apps at once, copy the probe to another name, for example `cp ~/VPNGo/tests/manual/vpngo-probe ~/.local/state/vpngo/vpngo-probe-b`, register the copy with `vpngo config`, and start it with another profile. Each copy writes its own name before the address.

### Windows

- Run vpngo from PowerShell or Command Prompt.
- If Mihomo does not start, read the messages in its window and check `state\config.yaml` in the `VPNGo` folder.
- If you closed the Mihomo window by accident, run `vpngo start <app>` again.

### macOS

- Mihomo keeps running after the command ends. Its log is `~/VPNGo/state/mihomo.log`.
- If vpngo says `mihomo executable not found`, repeat step 1 of the macOS section or set `VPNGO_MIHOMO` to the full path of the `mihomo` file.

On every system, `vpngo status <app>` shows the current route. Checking the address from inside the app is the final proof; on Windows and macOS, a Mihomo rule alone does not guarantee that every connection of the app uses the VPN.

## 8. Where vpngo keeps its files

| What | Linux and macOS | Windows |
| --- | --- | --- |
| Profiles, app paths, choices and policies (`profiles.json`, `apps.json`, `assignments.json`) | `~/.config/vpngo/` | `%APPDATA%\vpngo\` |
| Linux logs and session data | `~/.local/state/vpngo/` | — |
| Mihomo configuration and log | `state/` in the `VPNGo` folder | `state\` in the `VPNGo` folder |

Your `.conf` files, `state/config.yaml` and `state/controller.json` contain private keys and passwords. Never share them or attach them to bug reports.

Messages are in English by default. For Portuguese, set `VPNGO_LANG=pt-BR` (`$env:VPNGO_LANG = 'pt-BR'` in PowerShell).
