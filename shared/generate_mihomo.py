#!/usr/bin/env python3
"""Convert one standard WireGuard peer to a private vpngo Mihomo profile."""

import argparse
import base64
import binascii
import configparser
import hashlib
import ipaddress
import json
import os
import re
import secrets
import sys
from pathlib import Path

from i18n import tr
from apps import AppError, mihomo_dir


STATE = mihomo_dir()
DEFAULT_PORT = 9097


def scalar(value):
    """JSON strings are valid YAML strings and quote IPv6, keys and hostnames safely."""
    return json.dumps(str(value), ensure_ascii=True)


def group_name(application):
    return "vpngo-" + hashlib.sha256(application.encode("utf-8")).hexdigest()[:12]


def profile_proxy(name):
    return "vpngo-wireguard" if name == "default" else f"vpngo-wireguard-{name}"


def wg_key(value, label):
    try:
        if len(base64.b64decode(value, validate=True)) != 32:
            raise ValueError()
    except (ValueError, binascii.Error) as error:
        raise ValueError(f"Invalid WireGuard {label}.") from error
    return value


def parse_endpoint(value):
    match = re.fullmatch(r"(?:\[([^]]+)\]|([^:]+)):(\d+)", value.strip())
    if not match:
        raise ValueError("Endpoint must be host:port or [IPv6]:port.")
    host = match.group(1) or match.group(2)
    port = int(match.group(3))
    if not 1 <= port <= 65535:
        raise ValueError("Endpoint port must be 1-65535.")
    if not host or any(character.isspace() for character in host):
        raise ValueError("Invalid Endpoint host.")
    return host, port


def parse_wireguard(path):
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.read(path, encoding="utf-8")
    if "Interface" not in parser or "Peer" not in parser:
        raise ValueError("WireGuard file must have [Interface] and one [Peer].")
    interface, peer = parser["Interface"], parser["Peer"]
    private_key = wg_key(interface["PrivateKey"].strip(), "private key")
    public_key = wg_key(peer["PublicKey"].strip(), "public key")
    addresses = [ipaddress.ip_interface(item.strip()) for item in interface["Address"].split(",")]
    ipv4_address = next((address for address in addresses if address.version == 4), None)
    ipv6_address = next((address for address in addresses if address.version == 6), None)
    ipv4 = str(ipv4_address.ip) if ipv4_address else None
    ipv6 = str(ipv6_address.ip) if ipv6_address else None
    dns = []
    for raw in interface.get("DNS", "").split(","):
        value = raw.strip()
        if value:
            try:
                dns.append(str(ipaddress.ip_address(value)))
            except ValueError:
                # wg-quick also permits search domains in DNS; they are not
                # nameservers and cannot be passed to vopono's --dns option.
                continue
    if not ipv4:
        raise ValueError("An IPv4 Interface Address is required.")
    allowed = [str(ipaddress.ip_network(item.strip(), strict=False)) for item in peer["AllowedIPs"].split(",")]
    if "0.0.0.0/0" not in allowed:
        raise ValueError("AllowedIPs must include 0.0.0.0/0 for application VPN routes.")
    host, port = parse_endpoint(peer["Endpoint"])
    psk = peer.get("PresharedKey", "").strip()
    if psk:
        wg_key(psk, "preshared key")
    keepalive = int(peer.get("PersistentKeepalive", "0"))
    mtu = int(interface.get("MTU", "1420"))
    if not 0 <= keepalive <= 65535 or not 576 <= mtu <= 9000:
        raise ValueError("Invalid PersistentKeepalive or MTU.")
    return dict(private_key=private_key, public_key=public_key, ipv4=ipv4,
                ipv4_cidr=str(ipv4_address) if ipv4_address else None, dns=dns,
                ipv6=ipv6, ipv6_cidr=str(ipv6_address) if ipv6_address else None,
                allowed=allowed, host=host, port=port, psk=psk,
                keepalive=keepalive, mtu=mtu)


def build_config(profiles, secret, port, managed=None, platform=None):
    managed = managed or {}
    windows = (platform or sys.platform) == "win32"
    if "private_key" in profiles:  # Existing callers used a single WireGuard profile.
        profiles = {"default": profiles}
    lines = [
        "mode: rule", "log-level: warning", "allow-lan: false", "ipv6: true",
        "find-process-mode: always", "profile:", "  store-selected: false",
        f"external-controller: {scalar(f'127.0.0.1:{port}')}",
        f"secret: {scalar(secret)}",
    ]
    if windows:
        # ProxiFyre redirects only selected processes into local SOCKS sockets.
        # Explicitly disable every global listener and all TUN routing.
        lines += ["port: 0", "socks-port: 0", "mixed-port: 0", "redir-port: 0",
                  "tproxy-port: 0", "tun:", "  enable: false", "  auto-route: false",
                  "  strict-route: false"]
    else:
        lines += ["tun:", "  enable: true", "  stack: mips",
                  "  auto-route: true", "  auto-detect-interface: true", "  strict-route: true", "  dns-hijack:",
                  "    - 'any:53'", "    - 'tcp://any:53'"]
    lines += ["dns:", "  enable: true",
        "  ipv6: true", "  enhanced-mode: redir-host", "  nameserver:",
        "    - '1.1.1.1'", "    - '9.9.9.9'", "proxies:",
    ]
    for name, wg in sorted(profiles.items()):
        lines += [f"  - name: {profile_proxy(name)}", "    type: wireguard",
                  f"    ip: {scalar(wg['ipv4'])}"]
        if wg["ipv6"]:
            lines.append(f"    ipv6: {scalar(wg['ipv6'])}")
        lines += [f"    private-key: {scalar(wg['private_key'])}", "    peers:",
                  f"      - server: {scalar(wg['host'])}", f"        port: {wg['port']}",
                  f"        public-key: {scalar(wg['public_key'])}",
                  "        allowed-ips:"]
        lines += [f"          - {scalar(network)}" for network in wg["allowed"]]
        if wg["psk"]:
            lines.append(f"        pre-shared-key: {scalar(wg['psk'])}")
        if wg["keepalive"]:
            lines.append(f"        persistent-keepalive: {wg['keepalive']}")
        lines += ["    udp: true", f"    mtu: {wg['mtu']}"]
    if managed:
        lines.append("proxy-groups:")
        for application, data in sorted(managed.items()):
            profile = data.get("profile", "default")
            if profile not in profiles:
                raise ValueError(f"Profile '{profile}' for '{application}' is unavailable.")
            proxy = profile_proxy(profile)
            lines += [f"  - name: {group_name(application)}", "    type: select",
                      "    proxies:", "      - REJECT", "      - DIRECT"]
            lines += [f"      - {profile_proxy(name)}" for name in sorted(profiles)]
            selected = "REJECT" if data.get("blocked") else proxy if data["enabled"] else "DIRECT"
            lines.append(f"    default-selected: {selected}")
    if windows:
        from windows_backend import build_proxifyre_config, credentials, listener_ports
        build_proxifyre_config(managed, secret, port)  # Validate before emitting any rules.
        if managed:
            lines.append("listeners:")
        for application, listener_port in listener_ports(managed, port).items():
            username, password = credentials(application, secret)
            lines += [f"  - name: {group_name(application)}-in", "    type: socks",
                      "    listen: 127.0.0.1", f"    port: {listener_port}", "    udp: true",
                      f"    proxy: {group_name(application)}", "    users:",
                      f"      - username: {scalar(username)}", f"        password: {scalar(password)}"]
        lines += ["rules:", "  - 'MATCH,REJECT'"]
        return "\n".join(lines) + "\n"
    lines.append("rules:")
    for application, data in sorted(managed.items()):
        group = group_name(application)
        paths = [data.get("executable", ""), *data.get("helpers", [])]
        for path in paths:
            if path:
                if "," in path or "\n" in path:
                    raise ValueError(f"Unsupported process path for Mihomo routing: {path}")
                lines.append(f"  - {scalar(f'PROCESS-PATH,{path},{group}')}")
    for application, data in sorted(managed.items()):
        process = data["process"]
        if not re.fullmatch(r"[A-Za-z0-9_. ()-]{1,100}", process):
            raise ValueError(f"Unsupported process name for Mihomo routing: {process}")
        group = group_name(application)
        lines.append(f"  - {scalar(f'PROCESS-NAME,{process},{group}')}")
        if data.get("bundle"):
            stem = Path(process).stem
            lines.append(f"  - {scalar(f'PROCESS-NAME-WILDCARD,{stem} Helper*,{group}')}")
    lines.append("  - 'MATCH,DIRECT'")
    return "\n".join(lines) + "\n"


def private_write(path, content):
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    try:
        if os.name == "posix":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(content)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def controller(port=None):
    """Load the local controller settings, creating them with a new secret if missing."""
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "posix":
        STATE.chmod(0o700)
    path = STATE / "controller.json"
    previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    current = {"port": port or int(previous.get("port", DEFAULT_PORT)),
               "secret": previous.get("secret") or secrets.token_urlsafe(32)}
    if current != previous:
        private_write(path, json.dumps(current))
    if not (STATE / "managed.json").exists():
        private_write(STATE / "managed.json", "{}")
    return current


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("wireguard", type=Path, help="standard WireGuard .conf file")
    cli.add_argument("profile", nargs="?", default="default", help="profile name (default: default)")
    cli.add_argument("--port", type=int, default=DEFAULT_PORT, help="local Mihomo API port")
    args = cli.parse_args()
    if not 1024 <= args.port <= 65535:
        cli.error("--port must be between 1024 and 65535")
    from profiles import register, parsed_profiles
    register(args.wireguard, args.profile)
    profiles = parsed_profiles()
    settings = controller(args.port)
    managed = json.loads((STATE / "managed.json").read_text(encoding="utf-8"))
    if sys.platform == "win32":
        from windows_backend import assign_ports
        if assign_ports(managed, settings["port"]):
            private_write(STATE / "managed.json", json.dumps(managed, indent=2))
    private_write(STATE / "config.yaml", build_config(profiles, settings["secret"], settings["port"], managed))
    if sys.platform == "win32":
        from windows_backend import write_config
        write_config(STATE, managed, settings)
    print(tr("config_created", path=STATE / "config.yaml"))
    print(tr("config_private"))


if __name__ == "__main__":
    try:
        main()
    except (AppError, OSError, ValueError, KeyError, configparser.Error) as error:
        print(f"vpngo: {error}", file=sys.stderr)
        sys.exit(1)
