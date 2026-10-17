# Windows application routing

Windows uses this path for each explicitly selected executable:

```text
Discord.exe -> ProxiFyre TCP/UDP process rule -> 127.0.0.1 SOCKS listener -> WireGuard profile
other apps -> existing Windows connection
```

Mihomo's TUN, automatic routes and DNS hijacking are disabled. No system proxy is set. ProxiFyre never receives an empty-string/catch-all application rule. Each app has its own authenticated SOCKS listener and selector, so apps can use different VPN profiles. Local IPv4 LAN traffic is bypassed.

## Install the Windows backend

Install Python, Mihomo and VPNGo as in the main guide. Then, from the source checkout:

```powershell
powershell -ExecutionPolicy Bypass -File .\windows\install-backend.ps1
```

For a release install, run `windows\install-backend.ps1` from the installed VPNGo folder instead. It downloads the official ProxiFyre 2.6.4 setup for the native Windows architecture and verifies a pinned SHA-256 before elevation. Add `-DownloadOnly` to prepare and verify it without installing anything.

The separate setup installs ProxiFyre, Windows Packet Filter and required Visual C++ runtime packages. It requires administrator permission and may require a reboot; it never forces a reboot. .NET Framework 4.7.2+ is required on x86/x64, or 4.8.1+ on ARM64. The ProxiFyre service is registered with manual startup and remains stopped until routing is configured.

VPNGo supports the protected official installation in Program Files. It refuses to overwrite an existing unrelated `app-config.json`, or a configuration owned by another VPNGo user. It writes an ownership/digest sidecar and restores the previous owned configuration if a service restart fails. Keep ProxiFyre's GUI from independently editing VPNGo's generated rules.

Sources: [ProxiFyre setup and dependencies](https://github.com/wiresock/proxifyre/blob/v2.6.4/docs/installer.md), [process matching, TCP/UDP and limitations](https://github.com/wiresock/proxifyre/blob/v2.6.4/docs/configuration.md), [Mihomo listener routing](https://wiki.metacubex.one/en/config/inbound/listeners/).

## Start and stop

```powershell
vpngo start discord
vpngo status discord
vpngo off discord
vpngo on discord
vpngo stop discord
vpngo shutdown
```

`start` checks dependencies before preparing the app or closing it. Mihomo starts unelevated with logs in `%LOCALAPPDATA%\vpngo\mihomo`. Administrator permission is requested only to apply process filters through ProxiFyre. The app is restarted only after its proxy and process filters are ready. Missing dependencies, refused elevation, or failed service startup cannot fall back to the old global TUN.

`off` selects a direct route for that app while keeping the local forwarding path. `stop` closes the app and leaves its selector blocked, as on the existing macOS backend. `shutdown` stops VPNGo's ProxiFyre service and its recorded Mihomo process; apps remain open and can reconnect through their usual connection. It does not uninstall the shared driver or stop unrelated Mihomo instances.

Temporary runs remove their process rules when their worker exits. Adding/removing rules restarts the shared ProxiFyre service if necessary and can briefly interrupt other managed apps. Profile switching and `on`/`off` change only the selected app's Mihomo selector.

## Scope and validation

This is process-based forwarding, not a Windows network compartment. All copies with the same executable name use the same route. Register separate helpers with `vpngo helper add`. Shared system processes and the routing engine itself cannot be selected. Windows system DNS remains unchanged, and there is no strict per-app DNS isolation or kill switch. Unresolved process ownership and fragmented IPv6 UDP can bypass attribution; see the ProxiFyre limitations above.

The tests run a real unelevated Mihomo instance with authenticated local TCP/UDP echo requests. They compare default IPv4/IPv6 routes, adapters and system-proxy settings before, during and after that instance. Driver/service operations are simulated for failure and rollback tests. These do not establish end-to-end VPN operation through ProxiFyre or Discord voice/video; those require the driver and a device check.

After installing the backend, check the public IP from a selected test app and an unselected app, confirm both TCP and UDP traffic, and exercise `shutdown`. Do not infer isolation from a successful launch message alone.
