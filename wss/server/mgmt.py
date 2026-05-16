import json
import logging
import time
from pathlib import Path

import pynng

from . import registry
from .cache import CacheClient
from .config import config

logger = logging.getLogger(__name__)

_start_time = time.monotonic()


async def serve_mgmt(cache: CacheClient) -> None:
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

            resp = await _dispatch(req, cache)
            try:
                await sock.asend(json.dumps(resp).encode())
            except Exception as exc:
                logger.warning("mgmt send error: %s", exc)


async def _dispatch(req: dict, cache: CacheClient) -> dict:
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

    if cmd == "tunnel":
        return await _cmd_tunnel(req, cache)

    if cmd == "tunnel_list":
        return await _cmd_tunnel_list(cache)

    return {"ok": False, "error": f"unknown command: {cmd!r}"}


async def _cmd_tunnel(req: dict, cache: CacheClient) -> dict:
    client_id = req.get("client_id")
    client_port = req.get("client_port")

    if not client_id:
        return {"ok": False, "error": "missing: client_id"}
    if not isinstance(client_port, int) or not (1 <= client_port <= 65535):
        return {"ok": False, "error": "missing or invalid: client_port (1-65535)"}
    if client_id not in registry.connected_ids():
        return {"ok": False, "error": f"client {client_id!r} is not connected"}

    server_port = await cache.reserve_tunnel_port(client_id, client_port)
    if server_port is None:
        return {"ok": False, "error": "no free ports available in range 9000-9999"}

    ssh_dir = Path(config.db_path).parent / "ssh"
    try:
        host_pub = (ssh_dir / "ssh_host_ed25519_key.pub").read_text().strip()
        ssh_known_hosts = f"{config.ssh_host} {host_pub}"
    except Exception as exc:
        await cache.release_tunnel_port(server_port)
        return {"ok": False, "error": f"SSH host key read error: {exc}"}

    sent = await registry.send_to(client_id, {
        "type": "TUNNEL_REQUEST",
        "server_port": server_port,
        "client_port": client_port,
        "ssh_host": config.ssh_host,
        "ssh_port": config.ssh_port,
        "ssh_user": "tunnel",
        "ssh_known_hosts": ssh_known_hosts,
    })
    if not sent:
        await cache.release_tunnel_port(server_port)
        return {"ok": False, "error": "failed to send TUNNEL_REQUEST to client"}

    logger.info(
        "Tunnel requested: client=%s client_port=%d → server_port=%d",
        client_id, client_port, server_port,
    )
    return {
        "ok": True,
        "result": {
            "server_port": server_port,
            "client_id": client_id,
            "client_port": client_port,
            "ssh_host": config.ssh_host,
            "ssh_port": config.ssh_port,
        },
    }


async def _cmd_tunnel_list(cache: CacheClient) -> dict:
    ports = await cache.get_tunnel_ports()
    return {"ok": True, "result": ports}
