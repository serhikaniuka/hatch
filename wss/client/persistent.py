import asyncio
import json
import logging
from datetime import datetime, timezone

import websockets

from . import state
from .config import config
from .ssl_context import build_persistent_ssl_context

logger = logging.getLogger(__name__)

PING_INTERVAL = 30


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def run_persistent(client_id: str) -> None:
    uri = f"wss://{config.server_host}:{config.server_port}"
    attempt = 0

    state.update(client_id=client_id, server_uri=uri)

    while True:
        ssl_ctx = build_persistent_ssl_context()
        state.update(connection="connecting", reconnect_attempts=attempt)
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
                state.update(connection="connected", connected_at=_now(), reconnect_attempts=0)

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
            state.update(connection="disconnected")
            attempt += 1
            await asyncio.sleep(wait)
        except asyncio.CancelledError:
            logger.info("Persistent connection cancelled.")
            state.update(connection="disconnected")
            return


async def _heartbeat(ws) -> None:
    while True:
        await asyncio.sleep(PING_INTERVAL)
        try:
            await ws.send(json.dumps({"type": "PING"}))
            state.update(last_ping_sent=_now())
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
            state.update(last_pong_received=_now())
            logger.debug("PONG received")
        elif msg_type == "MESSAGE":
            logger.info("Message from server: %s", msg.get("payload"))
        else:
            logger.debug("Unknown message type: %s", msg_type)
