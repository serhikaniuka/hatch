import asyncio
import json
import logging

import websockets

from .cache import CacheClient
from .config import ServerConfig

logger = logging.getLogger(__name__)


async def handle_persistent(
    websocket,
    client_id: str,
    client_ip: str,
    cache: CacheClient,
    config: ServerConfig,
) -> None:
    await cache.set_client_state(client_id, "connected", client_ip)
    await cache.append_recent_connection(client_id, "connected")
    logger.info("Client %s connected from %s", client_id, client_ip)

    await websocket.send(json.dumps({"type": "CONNECTED", "client_id": client_id}))

    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")

            if msg_type == "PING":
                await websocket.send(json.dumps({"type": "PONG"}))
                await cache.set_client_state(client_id, "connected", client_ip)
            elif msg_type == "MESSAGE":
                logger.info("Message from %s: %s", client_id, msg.get("payload"))
            else:
                logger.debug("Unknown message type '%s' from %s", msg_type, client_id)

    except websockets.exceptions.ConnectionClosed:
        logger.info("Client %s disconnected", client_id)
    finally:
        await cache.set_client_state(client_id, "disconnected", client_ip)
        await cache.append_recent_connection(client_id, "disconnected")
