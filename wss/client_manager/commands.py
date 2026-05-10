"""
Command implementations for the WSS client management REPL.

Each cmd_* function receives a list of string tokens (everything after the
command keyword) and prints its own output.
"""
from .config import config
from .nng_client import ClientMgmtClient


def _client(timeout_ms: int = 3000) -> ClientMgmtClient:
    return ClientMgmtClient(config.mgmt_socket, timeout_ms=timeout_ms)


def cmd_client_ping(_args: list[str]) -> None:
    """/client ping"""
    ok = _client(timeout_ms=3000).ping()
    mark = "reachable ✓" if ok else "NOT reachable ✗"
    print(f"  Client {mark}  ({config.mgmt_socket})")


def cmd_client_status(_args: list[str]) -> None:
    """/client status"""
    try:
        resp = _client().status()
    except Exception as exc:
        print(f"  Connection failed: {exc}")
        return
    if not resp.get("ok"):
        print(f"  Error: {resp.get('error')}")
        return
    r = resp["result"]
    s = r.get("uptime_seconds", 0)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    print()
    print(f"  Connection  : {r.get('connection', '-')}")
    print(f"  Client ID   : {r.get('client_id') or '-'}")
    print(f"  Server URI  : {r.get('server_uri') or '-'}")
    print(f"  Connected at: {r.get('connected_at') or '-'}")
    print(f"  Last ping   : {r.get('last_ping_sent') or '-'}")
    print(f"  Last pong   : {r.get('last_pong_received') or '-'}")
    print(f"  Reconnects  : {r.get('reconnect_attempts', 0)}")
    print(f"  Uptime      : {h:02d}:{m:02d}:{sec:02d}")
    print(f"  Mgmt socket : {r.get('mgmt_socket', '-')}")
    print()


def cmd_client_cert(_args: list[str]) -> None:
    """/client cert"""
    try:
        resp = _client().cert()
    except Exception as exc:
        print(f"  Connection failed: {exc}")
        return
    if not resp.get("ok"):
        print(f"  Error: {resp.get('error')}")
        return
    r = resp["result"]
    print()
    print(f"  Client ID   : {r.get('client_id', '-')}")
    print(f"  Subject     : {r.get('subject', '-')}")
    print(f"  Not before  : {r.get('not_before', '-')}")
    print(f"  Not after   : {r.get('not_after', '-')}")
    print(f"  Fingerprint : {r.get('fingerprint', '-')}")
    print()
