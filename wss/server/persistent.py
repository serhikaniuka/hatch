import asyncio
import base64
import json
import logging
import sqlite3
from pathlib import Path

import websockets

from .cache import CacheClient
from .config import ServerConfig
from .db import assign_client_num, update_client_hostname
from . import registry

logger = logging.getLogger(__name__)

_VALID_KEY_TYPES = {
    "ssh-rsa", "ssh-ed25519",
    "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521",
}


def _authorized_keys_path(config: ServerConfig) -> Path:
    return Path(config.db_path).parent / "ssh" / "authorized_keys"


def _validate_public_key(key: str) -> bool:
    parts = key.strip().split()
    if len(parts) < 2:
        return False
    if parts[0] not in _VALID_KEY_TYPES:
        return False
    try:
        base64.b64decode(parts[1])
    except Exception:
        return False
    if len(parts) > 2:
        if any(c in parts[2] for c in '\n\r;|&`$\\'):
            return False
    return True


def _install_client_key(config: ServerConfig, client_id: str, public_key: str) -> None:
    ak = _authorized_keys_path(config)
    marker = f"wss-client-{client_id}"
    line = f"restrict,port-forwarding {public_key.strip()} {marker}\n"
    try:
        existing = ak.read_text()
    except FileNotFoundError:
        existing = ""
    lines = [l for l in existing.splitlines(keepends=True)
             if not l.rstrip().endswith(marker)]
    lines.append(line)
    ak.write_text("".join(lines))


def _remove_client_key(config: ServerConfig, client_id: str) -> None:
    ak = _authorized_keys_path(config)
    marker = f"wss-client-{client_id}"
    try:
        existing = ak.read_text()
    except FileNotFoundError:
        return
    lines = [l for l in existing.splitlines(keepends=True)
             if not l.rstrip().endswith(marker)]
    ak.write_text("".join(lines))


async def handle_persistent(
    websocket,
    client_id: str,
    client_ip: str,
    cache: CacheClient,
    config: ServerConfig,
    conn: sqlite3.Connection,
    db_lock: asyncio.Lock,
) -> None:
    await cache.set_client_state(client_id, "connected", client_ip)
    await cache.append_recent_connection(client_id, "connected")

    loop = asyncio.get_event_loop()
    async with db_lock:
        client_num = await loop.run_in_executor(None, assign_client_num, conn, client_id)

    logger.info("Client #%d %s connected from %s", client_num, client_id, client_ip)

    registry.register(client_id, websocket)
    await websocket.send(json.dumps({"type": "CONNECTED", "client_id": client_id}))

    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")

            if msg_type == "SSH_KEY_REGISTER":
                pub_key = msg.get("public_key", "")
                hostname = msg.get("hostname", "").strip()
                if _validate_public_key(pub_key):
                    _install_client_key(config, client_id, pub_key)
                    if hostname:
                        async with db_lock:
                            await loop.run_in_executor(
                                None, update_client_hostname, conn, client_id, hostname
                            )
                    logger.info(
                        "Client #%d registered SSH key (host: %s)",
                        client_num, hostname or "-",
                    )
                else:
                    logger.warning("Client #%d sent invalid SSH public key", client_num)

            elif msg_type == "PING":
                await websocket.send(json.dumps({"type": "PONG"}))
                await cache.set_client_state(client_id, "connected", client_ip)

            elif msg_type == "TUNNEL_ESTABLISHED":
                logger.info(
                    "Client #%d: tunnel established server_port=%s → client_port=%s",
                    client_num, msg.get("server_port"), msg.get("client_port"),
                )
            elif msg_type == "TUNNEL_FAILED":
                logger.warning(
                    "Client #%d: tunnel failed server_port=%s error=%s",
                    client_num, msg.get("server_port"), msg.get("error"),
                )
            elif msg_type == "MESSAGE":
                logger.info("Message from #%d: %s", client_num, msg.get("payload"))
            else:
                logger.debug("Unknown message type '%s' from #%d", msg_type, client_num)

    except websockets.exceptions.ConnectionClosed:
        logger.info("Client #%d %s disconnected", client_num, client_id)
    finally:
        registry.unregister(client_id)
        _remove_client_key(config, client_id)
        await cache.set_client_state(client_id, "disconnected", client_ip)
        await cache.append_recent_connection(client_id, "disconnected")
