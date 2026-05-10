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
    """Match a full UUID or an unambiguous UUID prefix."""
    clients = list_clients(conn)
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
    all_ids = [c["id"] for c in list_clients(_db())]
    rows = _cache().get_connected_client_ids(all_ids)
    print()
    print_connected_table(rows)
    print()


def cmd_server_ping(_args: list[str]) -> None:
    """/server ping"""
    ok = MgmtClient(config.mgmt_socket, timeout_ms=3000).ping()
    status = "reachable ✓" if ok else "NOT reachable ✗"
    print(f"  Server {status}  ({config.mgmt_socket})")


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
