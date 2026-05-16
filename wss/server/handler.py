import asyncio
import hashlib
import json
import logging
import sqlite3

import websockets

from .cache import CacheClient
from .config import ServerConfig
from .db import get_cert_by_fingerprint
from .enrollment import handle_enrollment
from .persistent import handle_persistent

logger = logging.getLogger(__name__)


async def connection_handler(
    websocket,
    conn: sqlite3.Connection,
    db_lock: asyncio.Lock,
    cache: CacheClient,
    config: ServerConfig,
) -> None:
    client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
    cert_der = _get_peer_cert_der(websocket)

    if cert_der is None:
        logger.info("Enrollment connection from %s", client_ip)
        await handle_enrollment(websocket, conn, db_lock, config.ca_cert, config.ca_key)
        return

    fingerprint = _compute_fingerprint(cert_der)
    loop = asyncio.get_event_loop()
    cert_row = await loop.run_in_executor(None, get_cert_by_fingerprint, conn, fingerprint)

    if cert_row is None:
        logger.warning("Rejected unknown cert fingerprint %s from %s", fingerprint, client_ip)
        await websocket.send(json.dumps({
            "type": "ERROR",
            "code": "CERT_NOT_FOUND",
            "detail": "Certificate not registered",
        }))
        await websocket.close()
        return

    client_id = cert_row["client_id"]
    logger.info("Persistent connection from client %s (%s)", client_id, client_ip)
    await handle_persistent(websocket, client_id, client_ip, cache, config, conn, db_lock)


def _get_peer_cert_der(websocket) -> bytes | None:
    try:
        ssl_object = websocket.transport.get_extra_info("ssl_object")
        if ssl_object is None:
            return None
        return ssl_object.getpeercert(binary_form=True)
    except Exception:
        return None


def _compute_fingerprint(der: bytes) -> str:
    return hashlib.sha256(der).hexdigest()
