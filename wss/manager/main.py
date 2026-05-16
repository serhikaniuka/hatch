#!/usr/bin/env python3
"""
WSS interactive management shell.

    python -m manager.main

Type /help inside the shell for available commands.
"""
import shlex
import sys
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import NestedCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style

from .commands import (
    cmd_client_add,
    cmd_client_list,
    cmd_client_renew,
    cmd_client_revoke,
    cmd_client_show,
    cmd_connected,
    cmd_server_ping,
    cmd_server_status,
    cmd_tunnel_open,
    cmd_tunnel_list,
)
from .config import config
from .nng_client import MgmtClient

# ── command registry ───────────────────────────────────────────────────────────

# Keys are the command words typed by the user (one or two tokens joined by space).
# Values are (handler, synopsis, description).
REGISTRY: list[tuple[str, str, str, object]] = [
    ("/help",           "",                   "Show this help",                          None),
    ("/client add",     "[--days N]",          "Register a new client",                   cmd_client_add),
    ("/client list",    "",                    "List all registered clients",             cmd_client_list),
    ("/client show",    "<#|id>",                "Show details, certificate, live state",   cmd_client_show),
    ("/client renew",   "<#|id> [--days N]",     "Extend enrollment window (now + N days)", cmd_client_renew),
    ("/client revoke",  "<#|id>",                "Revoke certificate — allows re-enroll",   cmd_client_revoke),
    ("/connected",      "",                      "Show currently connected clients",        cmd_connected),
    ("/server ping",    "",                      "Check NNG management socket",             cmd_server_ping),
    ("/server status",  "",                      "Show server uptime via NNG",              cmd_server_status),
    ("/tunnel open",    "<#|id> <port|ssh|vnc>", "Open reverse SSH tunnel from client",     cmd_tunnel_open),
    ("/tunnel list",    "",                    "List reserved tunnel ports",              cmd_tunnel_list),
    ("/exit",           "",                    "Quit",                                    None),
]

DISPATCH: dict[str, object] = {cmd: fn for cmd, _, _, fn in REGISTRY if fn is not None}

# ── tab-completion tree ────────────────────────────────────────────────────────

_COMPLETER = NestedCompleter.from_nested_dict({
    "/help":    None,
    "/client": {
        "add":    None,
        "list":   None,
        "show":   None,
        "renew":  None,
        "revoke": None,
    },
    "/connected":  None,
    "/server": {
        "ping":   None,
        "status": None,
    },
    "/tunnel": {
        "open": None,
        "list": None,
    },
    "/exit": None,
})

_STYLE = Style.from_dict({
    "prompt.tool":   "bold ansicyan",
    "prompt.arrow":  "bold",
})

_HISTORY_FILE = Path.home() / ".wss-mgr-history"

# ── startup banner ─────────────────────────────────────────────────────────────

def _banner() -> None:
    nng_ok = MgmtClient(config.mgmt_socket, timeout_ms=1500).ping()
    nng_mark = "✓" if nng_ok else "✗ (server not running or NNG not reachable)"
    print()
    print("  ┌─ WSS Manager ────────────────────────────────────┐")
    print(f"  │  DB        : {config.db_path}")
    print(f"  │  Memcached : {config.memcached_host}:{config.memcached_port}")
    print(f"  │  NNG       : {config.mgmt_socket}  {nng_mark}")
    print("  │")
    print("  │  Type /help for available commands.")
    print("  └──────────────────────────────────────────────────┘")
    print()

# ── help ───────────────────────────────────────────────────────────────────────

def _cmd_help() -> None:
    w_cmd  = max(len(cmd)  for cmd, _, _, _ in REGISTRY)
    w_args = max(len(args) for _, args, _, _ in REGISTRY)
    print()
    for cmd, args, desc, _ in REGISTRY:
        print(f"  {cmd:<{w_cmd}}  {args:<{w_args}}  {desc}")
    print()

# ── dispatch ───────────────────────────────────────────────────────────────────

def _dispatch(line: str) -> bool:
    """Parse and run one command line. Returns False when the user wants to exit."""
    try:
        tokens = shlex.split(line)
    except ValueError as exc:
        print(f"  Parse error: {exc}")
        return True

    if not tokens:
        return True

    first = tokens[0].lower()
    if first in ("/exit", "/quit", "/q"):
        return False
    if first == "/help":
        _cmd_help()
        return True

    # Try two-word key first, then one-word
    for width in (2, 1):
        key = " ".join(tokens[:width])
        if key in DISPATCH:
            try:
                DISPATCH[key](tokens[width:])
            except KeyboardInterrupt:
                print()
            except Exception as exc:
                print(f"  Error: {exc}")
            return True

    print(f"  Unknown command: {tokens[0]}  (type /help)")
    return True

# ── main loop ──────────────────────────────────────────────────────────────────

def main() -> None:
    _banner()

    session: PromptSession = PromptSession(
        history=FileHistory(str(_HISTORY_FILE)),
        completer=_COMPLETER,
        complete_while_typing=True,
        style=_STYLE,
    )

    while True:
        try:
            line = session.prompt(
                HTML("<prompt.tool>wss-mgr</prompt.tool> <prompt.arrow>❯</prompt.arrow> ")
            )
        except KeyboardInterrupt:
            # Ctrl-C cancels the current line, like a normal shell
            continue
        except EOFError:
            # Ctrl-D exits
            break

        line = line.strip()
        if not line:
            continue
        if not line.startswith("/"):
            print("  Commands start with /  (type /help)")
            continue
        if not _dispatch(line):
            break

    print("\n  Goodbye.\n")


if __name__ == "__main__":
    main()
