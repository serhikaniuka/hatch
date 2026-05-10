"""NNG Rep0 management socket for the WSS client process.

Mirrors the pattern used by wss/server/mgmt.py but exposes client-side state.

Protocol
--------
All messages are UTF-8 JSON.  Request: {"cmd": "<name>", ...extra}
Response: {"ok": true, "result": ...} or {"ok": false, "error": "..."}

Commands
--------
ping    → {"ok": true, "result": "pong"}
status  → uptime, connection state, server URI, last ping/pong timestamps
cert    → certificate subject, validity window, SHA-256 fingerprint
"""
import asyncio
import binascii
import json
import logging

import pynng

from . import state
from .config import config

logger = logging.getLogger(__name__)


async def serve_mgmt() -> None:
    logger.info("Client management socket on %s", config.mgmt_socket)
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
                await sock.asend(json.dumps({"ok": False, "error": "invalid JSON"}).encode())
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
        snap = state.snapshot()
        return {
            "ok": True,
            "result": {
                "uptime_seconds": state.uptime_seconds(),
                "connection": snap["connection"],
                "client_id": snap["client_id"],
                "server_uri": snap["server_uri"],
                "connected_at": snap["connected_at"],
                "last_ping_sent": snap["last_ping_sent"],
                "last_pong_received": snap["last_pong_received"],
                "reconnect_attempts": snap["reconnect_attempts"],
                "mgmt_socket": config.mgmt_socket,
            },
        }

    if cmd == "cert":
        return _cmd_cert()

    return {"ok": False, "error": f"unknown command: {cmd!r}"}


def _cmd_cert() -> dict:
    if not config.is_enrolled():
        return {"ok": False, "error": "not enrolled — no certificate on disk"}

    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.x509 import load_pem_x509_certificate

        pem = config.client_cert_file.read_bytes()
        cert = load_pem_x509_certificate(pem)
        fp = binascii.hexlify(cert.fingerprint(hashes.SHA256())).decode()

        return {
            "ok": True,
            "result": {
                "client_id": config.client_id_file.read_text().strip(),
                "subject": cert.subject.rfc4514_string(),
                "not_before": cert.not_valid_before_utc.isoformat(),
                "not_after": cert.not_valid_after_utc.isoformat(),
                "fingerprint": f"sha256:{fp}",
            },
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
