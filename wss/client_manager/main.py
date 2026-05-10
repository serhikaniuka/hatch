#!/usr/bin/env python3
"""
WSS client interactive management shell.

    python -m client_manager.main

Type /help inside the shell for available commands.
"""
import shlex
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import NestedCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style

from .commands import cmd_client_cert, cmd_client_ping, cmd_client_status
from .config import config
from .nng_client import ClientMgmtClient

# ── command registry ───────────────────────────────────────────────────────────

REGISTRY: list[tuple[str, str, str, object]] = [
    ("/help",          "",   "Show this help",                  None),
    ("/client ping",   "",   "Check NNG management socket",     cmd_client_ping),
    ("/client status", "",   "Show client connection state",    cmd_client_status),
    ("/client cert",   "",   "Show certificate details",        cmd_client_cert),
    ("/exit",          "",   "Quit",                            None),
]

DISPATCH: dict[str, object] = {cmd: fn for cmd, _, _, fn in REGISTRY if fn is not None}

# ── tab-completion tree ────────────────────────────────────────────────────────

_COMPLETER = NestedCompleter.from_nested_dict({
    "/help": None,
    "/client": {
        "ping":   None,
        "status": None,
        "cert":   None,
    },
    "/exit": None,
})

_STYLE = Style.from_dict({
    "prompt.tool":  "bold ansiyellow",
    "prompt.arrow": "bold",
})

_HISTORY_FILE = Path.home() / ".wss-client-mgr-history"

# ── startup banner ─────────────────────────────────────────────────────────────

def _banner() -> None:
    nng_ok = ClientMgmtClient(config.mgmt_socket, timeout_ms=1500).ping()
    nng_mark = "✓" if nng_ok else "✗ (client not running or NNG not reachable)"
    print()
    print("  ┌─ WSS Client Manager ─────────────────────────────┐")
    print(f"  │  NNG  : {config.mgmt_socket}  {nng_mark}")
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
    """Parse and run one command. Returns False when the user wants to exit."""
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
                HTML("<prompt.tool>wss-client-mgr</prompt.tool> <prompt.arrow>❯</prompt.arrow> ")
            )
        except KeyboardInterrupt:
            continue
        except EOFError:
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
