#!/usr/bin/env python3
"""
WSS management CLI.

Run from the wss/ directory:
    python -m manager.main [OPTIONS] COMMAND [ARGS]...
"""
import sys

import click

from .cache import CacheReader
from .config import config
from .db import (
    create_client,
    get_cert,
    get_client,
    get_connection,
    list_clients,
    revoke_cert,
    update_allow_to,
)
from .display import (
    print_client_detail,
    print_client_table,
    print_connected_table,
)
from .nng_client import MgmtClient


def _db():
    return get_connection(config.db_path)


def _cache():
    return CacheReader(config.memcached_host, config.memcached_port)


# ── top-level group ────────────────────────────────────────────────────────────

@click.group()
def cli():
    """WSS server management tool."""


# ── client commands ────────────────────────────────────────────────────────────

@cli.group()
def client():
    """Manage WSS clients."""


@client.command("add")
@click.option("--days", default=1, show_default=True,
              help="Enrollment window in days.")
def client_add(days: int) -> None:
    """Register a new client and print its UUID."""
    conn = _db()
    client_id = create_client(conn, days=days)
    click.echo(client_id)


@client.command("list")
def client_list() -> None:
    """List all registered clients."""
    conn = _db()
    print_client_table(list_clients(conn))


@client.command("show")
@click.argument("client_id")
def client_show(client_id: str) -> None:
    """Show full details and certificate info for CLIENT_ID."""
    conn = _db()
    c = get_client(conn, client_id)
    if c is None:
        click.echo(f"Client not found: {client_id}", err=True)
        sys.exit(1)
    cert = get_cert(conn, client_id)
    state = _cache().get_client_state(client_id)
    print_client_detail(c, cert, state)


@client.command("renew")
@click.argument("client_id")
@click.option("--days", default=1, show_default=True,
              help="Days from now for the new allow_to.")
def client_renew(client_id: str, days: int) -> None:
    """Extend the enrollment window: allow_to = now + N days."""
    conn = _db()
    if not update_allow_to(conn, client_id, days=days):
        click.echo(f"Client not found: {client_id}", err=True)
        sys.exit(1)
    click.echo(f"Enrollment window extended by {days} day(s).")


@client.command("revoke")
@click.argument("client_id")
@click.confirmation_option(prompt="Revoke certificate and allow re-enrollment?")
def client_revoke(client_id: str) -> None:
    """Delete a client's certificate so it can re-enroll."""
    conn = _db()
    if revoke_cert(conn, client_id):
        click.echo("Certificate revoked. Client may now re-enroll.")
    else:
        click.echo("No certificate on record for that client.")


# ── connected ─────────────────────────────────────────────────────────────────

@cli.command("connected")
def connected() -> None:
    """Show clients currently connected (from Memcached)."""
    conn = _db()
    all_ids = [c["id"] for c in list_clients(conn)]
    rows = _cache().get_connected_client_ids(all_ids)
    print_connected_table(rows)


# ── server commands ────────────────────────────────────────────────────────────

@cli.group()
def server():
    """Talk to the running server via NNG."""


@server.command("ping")
def server_ping() -> None:
    """Check if the server management socket is reachable."""
    mgmt = MgmtClient(config.mgmt_socket)
    if mgmt.ping():
        click.echo(f"Server is reachable  ({config.mgmt_socket})")
    else:
        click.echo(f"Server is NOT reachable  ({config.mgmt_socket})", err=True)
        sys.exit(1)


@server.command("status")
def server_status() -> None:
    """Get server uptime and config via NNG."""
    mgmt = MgmtClient(config.mgmt_socket)
    try:
        resp = mgmt.status()
    except Exception as exc:
        click.echo(f"Failed to connect: {exc}", err=True)
        sys.exit(1)

    if not resp.get("ok"):
        click.echo(f"Server error: {resp.get('error')}", err=True)
        sys.exit(1)

    r = resp["result"]
    uptime = r.get("uptime_seconds", 0)
    h, rem = divmod(uptime, 3600)
    m, s = divmod(rem, 60)
    click.echo(f"Uptime        : {h:02d}:{m:02d}:{s:02d}")
    click.echo(f"Mgmt socket   : {r.get('mgmt_socket', '-')}")


# ── entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
