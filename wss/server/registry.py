"""In-process registry of active persistent WebSocket connections.

Updated by persistent.py on connect/disconnect; read by mgmt.py to push
messages (e.g. TUNNEL_REQUEST) to specific clients.
"""
from typing import Any

_connections: dict[str, Any] = {}  # client_id → websocket


def register(client_id: str, ws: Any) -> None:
    _connections[client_id] = ws


def unregister(client_id: str) -> None:
    _connections.pop(client_id, None)


def connected_ids() -> list[str]:
    return list(_connections.keys())


async def send_to(client_id: str, msg: dict) -> bool:
    import json
    ws = _connections.get(client_id)
    if ws is None:
        return False
    try:
        await ws.send(json.dumps(msg))
        return True
    except Exception:
        return False
