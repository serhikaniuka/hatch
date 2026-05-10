import asyncio
import json
import logging
import time

import pynng

from .config import config

logger = logging.getLogger(__name__)

_start_time = time.monotonic()


async def serve_mgmt() -> None:
    logger.info("Management socket listening on %s", config.mgmt_socket)
    with pynng.Rep0(listen=config.mgmt_socket) as sock:
        while True:
            try:
                raw = await sock.arecv()
            except pynng.exceptions.Closed:
                break
            except Exception as exc:
                logger.warning("mgmt recv error: %s", exc)
                continue

            try:
                req = json.loads(raw)
            except json.JSONDecodeError:
                resp = {"ok": False, "error": "invalid JSON"}
                await sock.asend(json.dumps(resp).encode())
                continue

            resp = _dispatch(req)
            try:
                await sock.asend(json.dumps(resp).encode())
            except Exception as exc:
                logger.warning("mgmt send error: %s", exc)


def _dispatch(req: dict) -> dict:
    cmd = req.get("cmd")

    if cmd == "ping":
        return {"ok": True, "result": "pong"}

    if cmd == "status":
        uptime = int(time.monotonic() - _start_time)
        return {
            "ok": True,
            "result": {
                "uptime_seconds": uptime,
                "mgmt_socket": config.mgmt_socket,
            },
        }

    return {"ok": False, "error": f"unknown command: {cmd!r}"}
