"""How long an app has been on its current route, and how long on each route in total.

The record lives with the app's session (the Linux session file, or the Mihomo
managed entry) and changes only when the route does:

    {"state": "vpn", "since": 1792621195.0, "vpn_seconds": 0.0, "direct_seconds": 0.0,
     "rx_base": 0, "tx_base": 0}

rx_base and tx_base are the app's byte counters when the current route began, so
traffic "since this route" is the counter minus its base. None means the counters
restart with each route (Mihomo closes every connection when it switches).
"""

import time


ROUTES = ("vpn", "direct")


def begin(state, since=None, counters=None):
    counters = counters or {}
    return {"state": state, "since": time.time() if since is None else since,
            "vpn_seconds": 0.0, "direct_seconds": 0.0,
            "rx_base": counters.get("rx_bytes"), "tx_base": counters.get("tx_bytes")}


def switch(record, state, counters=None, now=None):
    """The record after the route changed to state; unchanged when it already was."""
    now = time.time() if now is None else now
    if not record:
        return begin(state, now, counters)
    if record.get("state") == state:
        return record
    record = dict(record)
    previous = record.get("state")
    if previous in ROUTES:
        record[f"{previous}_seconds"] = float(record.get(f"{previous}_seconds") or 0) + max(
            0.0, now - float(record.get("since") or now))
    counters = counters or {}
    record.update(state=state, since=now, rx_base=counters.get("rx_bytes"), tx_base=counters.get("tx_bytes"))
    return record


def view(record, counters=None, now=None):
    """Fields for `status --json`: when the current route began, seconds on each route so far,
    and the bytes moved since the current route began."""
    if not record:
        return {}
    now = time.time() if now is None else now
    counters = counters or {}
    since = record.get("since")
    totals = {route: float(record.get(f"{route}_seconds") or 0) for route in ROUTES}
    if record.get("state") in ROUTES and since:
        totals[record["state"]] += max(0.0, now - float(since))
    result = {"route_since": since, "vpn_seconds": round(totals["vpn"]),
              "direct_seconds": round(totals["direct"])}
    for name, base in (("rx_bytes", record.get("rx_base")), ("tx_bytes", record.get("tx_base"))):
        current = counters.get(name)
        if current is not None:
            # A counter below its base means the interface was recreated: count from zero.
            result[f"route_{name}"] = current - base if base is not None and current >= base else current
    return result
