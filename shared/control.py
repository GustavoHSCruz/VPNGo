#!/usr/bin/env python3
"""Switch one application's Mihomo selector through the local API."""

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from apps import AppError, key
from generate_mihomo import STATE, group_name, profile_proxy
from i18n import tr
from managed import load_managed, save_managed
from profiles import profile_key, resolve
import route_clock


CONTROLLER = STATE / "controller.json"


def request(port, secret, method, path, payload=None):
    url = f"http://127.0.0.1:{port}{path}"
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers={
        "Authorization": f"Bearer {secret}", "Content-Type": "application/json",
    })
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=5) as response:
        data = response.read()
    return json.loads(data) if data else None


def app_connections(port, secret, process_name, helper_paths=(), group=None):
    result = request(port, secret, "GET", "/connections")
    if not isinstance(result, dict) or "connections" not in result:
        raise ValueError(tr("controller_bad"))
    connections = result["connections"]
    # Mihomo serializes an empty connection snapshot as null.
    if connections is None:
        connections = []
    if not isinstance(connections, list):
        raise ValueError(tr("controller_bad"))
    for connection in connections:
        metadata = connection.get("metadata") or {}
        process = str(metadata.get("process") or "")
        process_path = str(metadata.get("processPath") or "")
        rule = str(connection.get("rule") or "")
        payload = str(connection.get("rulePayload") or "")
        chains = connection.get("chains") or []
        name = process_name.casefold()
        helper = Path(process_name).stem.casefold() + " helper"
        helper_match = process_path.casefold() in {path.casefold() for path in helper_paths}
        if ((group is not None and (group in chains or metadata.get("inboundName") == group + "-in")) or
                process.casefold() == name or
                Path(process_path).name.casefold() == name or
                process.casefold().startswith(helper) or
                helper_match or
                (rule == "PROCESS-NAME" and payload.casefold() == name)):
            identifier = str(connection.get("id") or "")
            if re.fullmatch(r"[A-Za-z0-9-]{8,64}", identifier):
                yield identifier


def main():
    if (len(sys.argv) not in {3, 4} or sys.argv[2] not in {"on", "off", "status", "switch", "reconnect", "block"}
            or (sys.argv[2] == "switch") != (len(sys.argv) == 4)):
        print(tr("usage"), file=sys.stderr)
        return 2
    if not CONTROLLER.is_file():
        raise ValueError(tr("not_configured"))
    controller = json.loads(CONTROLLER.read_text(encoding="utf-8"))
    port, secret = int(controller["port"]), controller["secret"]
    app_name, action = sys.argv[1], sys.argv[2]
    managed = load_managed()
    app_key = key(app_name)
    if app_key not in managed:
        raise ValueError(tr("app_not_started", app=app_name))
    group = group_name(app_key)
    assigned_profile = managed[app_key].get("profile", "default")
    proxy = profile_proxy(assigned_profile)
    current = request(port, secret, "GET", "/proxies/" + group)
    if not isinstance(current, dict) or not isinstance(current.get("now"), str):
        raise ValueError(tr("controller_bad"))
    filters_active = True
    if sys.platform == "win32" and action in {"status", "on", "switch", "reconnect"}:
        from windows_backend import routing_active
        filters_active = routing_active()
        if not filters_active and action != "status":
            raise AppError("Windows process filters are not active. Run 'vpngo start <app>' first.")
    if action == "status":
        if managed[app_key].get("blocked"):
            state = tr("status_stopped") if current["now"] == "REJECT" else tr("status_partial")
        else:
            state = (tr("status_on") if current["now"] == proxy else
                     tr("status_off") if current["now"] == "DIRECT" else
                     tr("status_partial"))
        if not filters_active:
            state = tr("status_partial")
        routing = ("ProxiFyre process filters + loopback SOCKS (best effort)" if sys.platform == "win32"
                   else "Mihomo process rules (best effort)")
        print(tr("controller_status", app=app_name, state=state) +
              f"; profile: {assigned_profile}; routing: {routing}" +
              (f"; temporary session orphaned: run 'vpngo stop {app_name}'"
               if managed[app_key].get("orphaned") else ""))
        return 0
    if action == "block":
        if current["now"] != "REJECT":
            request(port, secret, "PUT", "/proxies/" + group, {"name": "REJECT"})
        managed[app_key]["blocked"] = True
        managed[app_key]["enabled"] = False
        save_managed(managed)
        try:
            identifiers = set(app_connections(port, secret, managed[app_key]["process"],
                                              managed[app_key].get("helpers", []), group))
            for identifier in identifiers:
                try:
                    request(port, secret, "DELETE", "/connections/" + urllib.parse.quote(identifier))
                except urllib.error.HTTPError as error:
                    if error.code != 404:
                        raise
        except (ValueError, urllib.error.URLError) as error:
            print(f"vpngo: route blocked; could not close every existing connection: {error}", file=sys.stderr)
        print(f"{app_name}: VPN route blocked and existing connections closed where possible.")
        return 0
    if action == "switch":
        if current["now"] in {"DIRECT", "REJECT"}:
            raise ValueError("Turn the VPN on before switching profiles.")
        assigned_profile = profile_key(sys.argv[3])
        resolve(assigned_profile)
        proxy = profile_proxy(assigned_profile)
        target = proxy
    else:
        target = proxy if action == "on" else "DIRECT"
    if action == "reconnect":
        target = current["now"]
    changed = current["now"] != target
    selector_changed = False
    try:
        if changed or action == "reconnect":
            ids = set(app_connections(port, secret, managed[app_key]["process"],
                                      managed[app_key].get("helpers", []), group))
            if changed:
                request(port, secret, "PUT", "/proxies/" + group, {"name": target})
                selector_changed = True
                ids.update(app_connections(port, secret, managed[app_key]["process"],
                                           managed[app_key].get("helpers", []), group))
        else:
            ids = set()
        for identifier in ids:
            try:
                request(port, secret, "DELETE", "/connections/" + urllib.parse.quote(identifier))
            except urllib.error.HTTPError as error:
                if error.code != 404:  # It may have closed after the selector changed.
                    raise
        if action != "reconnect":
            managed[app_key]["enabled"] = target != "DIRECT"
            managed[app_key]["blocked"] = False
            managed[app_key]["profile"] = assigned_profile
            item = managed[app_key]
            # Entries from before v0.7.0 have no clock: the old route began when the app started.
            record = item.get("route") or route_clock.begin(
                "direct" if current["now"] == "DIRECT" else "vpn", item.get("started_at") or item.get("created_at"))
            item["route"] = route_clock.switch(record, "direct" if target == "DIRECT" else "vpn")
            save_managed(managed)
    except Exception:
        if selector_changed:
            request(port, secret, "PUT", "/proxies/" + group, {"name": current["now"]})
        raise
    if action == "switch":
        print(f"{app_name}: selected profile '{assigned_profile}'. Existing connections were closed for reconnection.")
    elif action == "reconnect":
        print(f"{app_name}: existing connections were closed for reconnection.")
    else:
        print(tr("controller_on" if action == "on" else "controller_off", app=app_name))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AppError, OSError, ValueError, KeyError, json.JSONDecodeError, urllib.error.URLError) as error:
        if isinstance(error, urllib.error.URLError) and not isinstance(error, urllib.error.HTTPError):
            error = tr("controller_unavailable")
        print(f"vpngo: {error}", file=sys.stderr)
        sys.exit(1)
