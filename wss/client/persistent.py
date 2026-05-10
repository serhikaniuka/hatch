import asyncio
import json
import logging

import websockets

from .config import config
from .ssl_context import build_persistent_ssl_context

logger = logging.getLogger(__name__)

PING_INTERVAL = 30


async def run_persistent(client_id: str) -> None:
    uri = f"wss://{config.server_host}:{config.server_port}"
    attempt = 0

    while True:
        ssl_ctx = build_persistent_ssl_context()
        try:
            logger.info("Connecting to %s (attempt %d) ...", uri, attempt + 1)
            async with websockets.connect(uri, ssl=ssl_ctx) as ws:
                msg = await asyncio.wait_for(ws.recv(), timeout=15)
                data = json.loads(msg)
                if data.get("type") != "CONNECTED":
                    logger.error("Expected CONNECTED, got: %s", data)
                    return
                logger.info("Persistent connection established as %s", client_id)
                attempt = 0

                ping_task = asyncio.create_task(_heartbeat(ws))
                try:
                    await _receive_loop(ws, client_id)
                finally:
                    ping_task.cancel()
                    try:
                        await ping_task
                    except asyncio.CancelledError:
                        pass

        except (websockets.exceptions.ConnectionClosed, OSError) as exc:
            wait = min(2 ** attempt, 60)
            logger.warning("Disconnected (%s). Retrying in %ds ...", exc, wait)
            attempt += 1
            await asyncio.sleep(wait)
        except asyncio.CancelledError:
            logger.info("Persistent connection cancelled.")
            return


async def _heartbeat(ws) -> None:
    while True:
        await asyncio.sleep(PING_INTERVAL)
        try:
            await ws.send(json.dumps({"type": "PING"}))
        except websockets.exceptions.ConnectionClosed:
            break


async def _receive_loop(ws, client_id: str) -> None:
    async for raw in ws:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue

        msg_type = msg.get("type")
        if msg_type == "PONG":
            logger.debug("PONG received")
        elif msg_type == "MESSAGE":
            logger.info("Message from server: %s", msg.get("payload"))
        else:
            logger.debug("Unknown message type: %s", msg_type)
