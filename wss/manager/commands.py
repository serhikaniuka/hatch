"""
Command implementations for the WSS management REPL.

Each cmd_* function receives a list of string tokens (everything after the
command keyword) and prints its own output.
"""
from .cache import CacheReader
from .config import config
from .db import (
    create_client,
    get_cert,
    get_connection,
    list_clients,
    revoke_cert,
    update_allow_to,
)
from .display import print_client_detail, print_client_table, print_connected_table
from .nng_client import MgmtClient


# ── helpers ────────────────────────────────────────────────────────────────────

def _db():
    return get_connection(config.db_path)


def _cache():
    return CacheReader(config.memcached_host, config.memcached_port)


def _resolve(conn, token: str) -> dict | None:
    """Match by client number (#N or N), full UUID, or unambiguous UUID prefix."""
    clients = list_clients(conn)

    # #N or bare integer → match client_num
    num_str = token.lstrip("#")
    if num_str.isdigit():
        num = int(num_str)
        hits = [c for c in clients if c.get("client_num") == num]
        if len(hits) == 1:
            return hits[0]
        if not hits:
            print(f"  No client with number #{num}.")
        else:
            print(f"  Ambiguous: multiple clients with number #{num}.")
        return None

    # UUID prefix
    hits = [c for c in clients if c["id"].startswith(token)]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        print(f"  Ambiguous prefix '{token}' — {len(hits)} matches. Use more characters.")
        return None
    print(f"  Client not found: {token}")
    return None


def _parse_days(tokens: list[str], default: int = 1) -> int | None:
    """Extract --days N from token list; return None on bad input."""
    it = iter(tokens)
    for tok in it:
        if tok == "--days":
            try:
                return int(next(it))
            except (StopIteration, ValueError):
                print("  --days requires an integer, e.g.  --days 3")
                return None
    return default


# ── commands ───────────────────────────────────────────────────────────────────

def cmd_client_add(args: list[str]) -> None:
    """/client add [--days N]"""
    days = _parse_days(args)
    if days is None:
        return
    client_id = create_client(_db(), days=days)
    print(f"  Registered  : {client_id}")
    print(f"  Enrollment  : {days} day(s) from now")


def cmd_client_list(_args: list[str]) -> None:
    """/client list"""
    print()
    print_client_table(list_clients(_db()))
    print()


def cmd_client_show(args: list[str]) -> None:
    """/client show <id>"""
    if not args:
        print("  Usage: /client show <id>")
        return
    conn = _db()
    c = _resolve(conn, args[0])
    if c is None:
        return
    cert = get_cert(conn, c["id"])
    state = _cache().get_client_state(c["id"])
    print()
    print_client_detail(c, cert, state)
    print()


def cmd_client_renew(args: list[str]) -> None:
    """/client renew <id> [--days N]"""
    if not args:
        print("  Usage: /client renew <id> [--days N]")
        return
    conn = _db()
    c = _resolve(conn, args[0])
    if c is None:
        return
    days = _parse_days(args[1:])
    if days is None:
        return
    update_allow_to(conn, c["id"], days=days)
    print(f"  Enrollment window extended by {days} day(s).")
    print(f"  Client: {c['id']}")


def cmd_client_revoke(args: list[str]) -> None:
    """/client revoke <id>"""
    if not args:
        print("  Usage: /client revoke <id>")
        return
    conn = _db()
    c = _resolve(conn, args[0])
    if c is None:
        return
    answer = input(f"  Revoke cert for {c['id'][:16]}…? [y/N] ").strip().lower()
    if answer != "y":
        print("  Cancelled.")
        return
    if revoke_cert(conn, c["id"]):
        print("  Certificate revoked. Client may re-enroll.")
    else:
        print("  No certificate on record for that client.")


def cmd_connected(_args: list[str]) -> None:
    """/connected"""
    clients = list_clients(_db())
    client_map = {c["id"]: c for c in clients}
    rows = _cache().get_connected_client_ids(list(client_map))
    print()
    print_connected_table(rows, client_map)
    print()


def cmd_server_ping(_args: list[str]) -> None:
    """/server ping"""
    ok = MgmtClient(config.mgmt_socket, timeout_ms=3000).ping()
    status = "reachable ✓" if ok else "NOT reachable ✗"
    print(f"  Server {status}  ({config.mgmt_socket})")


_PORT_NAMES: dict[str, int] = {
    "ssh": 22,
    "vnc": 5901,
}


def cmd_tunnel_open(args: list[str]) -> None:
    """/tunnel open <client-id> <port|ssh|vnc>"""
    if len(args) < 2:
        print("  Usage: /tunnel open <client-id> <port|ssh|vnc>")
        return
    client_id_prefix, port_str = args[0], args[1]
    port_str_lower = port_str.lower()
    if port_str_lower in _PORT_NAMES:
        client_port = _PORT_NAMES[port_str_lower]
    else:
        try:
            client_port = int(port_str)
        except ValueError:
            names = ", ".join(f"{k}={v}" for k, v in _PORT_NAMES.items())
            print(f"  Invalid port: {port_str!r}  (named ports: {names})")
            return

    conn = _db()
    c = _resolve(conn, client_id_prefix)
    if c is None:
        return

    try:
        resp = MgmtClient(config.mgmt_socket, timeout_ms=5000).tunnel(c["id"], client_port)
    except Exception as exc:
        print(f"  Connection failed: {exc}")
        return

    if not resp.get("ok"):
        print(f"  Error: {resp.get('error')}")
        return

    r = resp["result"]
    print(f"  Tunnel requested ✓")
    print(f"  Server port : {r['server_port']}")
    print(f"  Client port : {r['client_port']}")
    print(f"  SSH target  : {r['ssh_host']}:{r['ssh_port']}")
    print(f"  Reserved for 12 hours.")


def cmd_tunnel_list(_args: list[str]) -> None:
    """/tunnel list"""
    try:
        resp = MgmtClient(config.mgmt_socket, timeout_ms=5000).tunnel_list()
    except Exception as exc:
        print(f"  Connection failed: {exc}")
        return

    if not resp.get("ok"):
        print(f"  Error: {resp.get('error')}")
        return

    ports = resp["result"]
    print()
    if not ports:
        print("  No tunnel ports currently reserved.")
    else:
        from tabulate import tabulate
        rows = [[
            p["port"],
            p.get("client_id", "-"),
            p.get("client_port", "-"),
            p.get("reserved_at", "-"),
        ] for p in ports]
        print(tabulate(rows,
                       headers=["Server port", "Client ID", "Client port", "Reserved at"],
                       tablefmt="simple"))
    print()


def cmd_server_status(_args: list[str]) -> None:
    """/server status"""
    try:
        resp = MgmtClient(config.mgmt_socket, timeout_ms=3000).status()
    except Exception as exc:
        print(f"  Connection failed: {exc}")
        return
    if not resp.get("ok"):
        print(f"  Server error: {resp.get('error')}")
        return
    r = resp["result"]
    s = r.get("uptime_seconds", 0)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    print(f"  Uptime      : {h:02d}:{m:02d}:{sec:02d}")
    print(f"  Mgmt socket : {r.get('mgmt_socket', '-')}")
