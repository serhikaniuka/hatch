"""Shared mutable state for the client process.

Updated by persistent.py; read by mgmt.py to answer management queries.
"""
import time
from typing import Any

_start = time.monotonic()

_state: dict[str, Any] = {
    "connection": "starting",   # starting | enrolling | connecting | connected | disconnected
    "client_id": None,
    "server_uri": None,
    "connected_at": None,
    "last_ping_sent": None,
    "last_pong_received": None,
    "reconnect_attempts": 0,
}


def update(**kwargs: Any) -> None:
    _state.update(kwargs)


def snapshot() -> dict[str, Any]:
    return dict(_state)


def uptime_seconds() -> int:
    return int(time.monotonic() - _start)
