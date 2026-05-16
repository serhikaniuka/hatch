import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime, timezone

import websockets

from . import state
from .config import config
from .ssl_context import build_persistent_ssl_context

logger = logging.getLogger(__name__)

PING_INTERVAL = 30

# active SSH tunnel subprocesses: server_port → (process, known_hosts_path)
_tunnels: dict[int, tuple] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _ensure_ssh_key() -> str:
    """Generate a persistent ed25519 key pair if absent. Returns public key text."""
    key_path = config.tunnel_key_file
    pub_path = config.tunnel_pub_file

    if not key_path.exists():
        config.data_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Generating tunnel SSH key at %s", key_path)
        proc = await asyncio.create_subprocess_exec(
            "ssh-keygen", "-q", "-t", "ed25519", "-f", str(key_path), "-N", "",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"ssh-keygen failed: {stderr.decode().strip()}")
        os.chmod(key_path, 0o600)

    return pub_path.read_text().strip()


async def run_persistent(client_id: str) -> None:
    uri = f"wss://{config.server_host}:{config.server_port}"
    attempt = 0

    pub_key = await _ensure_ssh_key()

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

                await ws.send(json.dumps({
                    "type": "SSH_KEY_REGISTER",
                    "public_key": pub_key,
                }))

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
                    await _teardown_all_tunnels()

        except (websockets.exceptions.ConnectionClosed, OSError) as exc:
            wait = min(2 ** attempt, 60)
            logger.warning("Disconnected (%s). Retrying in %ds ...", exc, wait)
            state.update(connection="disconnected")
            attempt += 1
            await asyncio.sleep(wait)
        except asyncio.CancelledError:
            logger.info("Persistent connection cancelled.")
            state.update(connection="disconnected")
            await _teardown_all_tunnels()
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
        elif msg_type == "TUNNEL_REQUEST":
            asyncio.create_task(_handle_tunnel_request(ws, msg))
        elif msg_type == "MESSAGE":
            logger.info("Message from server: %s", msg.get("payload"))
        else:
            logger.debug("Unknown message type: %s", msg_type)


async def _handle_tunnel_request(ws, msg: dict) -> None:
    server_port: int = msg["server_port"]
    client_port: int = msg["client_port"]
    logger.info("Tunnel request: server_port=%d ← client_port=%d", server_port, client_port)

    try:
        proc, kh_path = await _start_ssh_tunnel(msg)
        _tunnels[server_port] = (proc, kh_path)
        await ws.send(json.dumps({
            "type": "TUNNEL_ESTABLISHED",
            "server_port": server_port,
            "client_port": client_port,
        }))
        logger.info("SSH tunnel established on server port %d", server_port)
        asyncio.create_task(_monitor_tunnel(server_port, proc, kh_path))
    except Exception as exc:
        logger.error("Failed to establish tunnel on port %d: %s", server_port, exc)
        try:
            await ws.send(json.dumps({
                "type": "TUNNEL_FAILED",
                "server_port": server_port,
                "error": str(exc),
            }))
        except Exception:
            pass


async def _start_ssh_tunnel(msg: dict) -> tuple:
    """Start SSH reverse tunnel. Returns (process, known_hosts_path)."""
    server_port: int = msg["server_port"]
    client_port: int = msg["client_port"]
    ssh_host: str = msg["ssh_host"]
    ssh_port: int = msg["ssh_port"]
    ssh_user: str = msg["ssh_user"]
    ssh_known_hosts: str = msg.get("ssh_known_hosts", "")

    fd, kh_path = tempfile.mkstemp(prefix="wss_tunnel_", suffix=".known_hosts")
    os.write(fd, ssh_known_hosts.encode())
    os.close(fd)

    cmd = [
        "ssh", "-N",
        "-R", f"{server_port}:127.0.0.1:{client_port}",
        "-p", str(ssh_port),
        "-i", str(config.tunnel_key_file),
        "-o", f"UserKnownHostsFile={kh_path}",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "BatchMode=yes",
        f"{ssh_user}@{ssh_host}",
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )

    await asyncio.sleep(1.5)
    if proc.returncode is not None:
        stderr = await proc.stderr.read()
        _cleanup_temp_files(kh_path)
        raise RuntimeError(f"SSH exited immediately: {stderr.decode().strip()}")

    return proc, kh_path


async def _monitor_tunnel(server_port: int, proc, kh_path: str) -> None:
    await proc.wait()
    _tunnels.pop(server_port, None)
    _cleanup_temp_files(kh_path)
    if proc.returncode != 0:
        stderr = b""
        if proc.stderr:
            try:
                stderr = await asyncio.wait_for(proc.stderr.read(), timeout=1)
            except asyncio.TimeoutError:
                pass
        logger.warning(
            "SSH tunnel on server port %d exited (rc=%d): %s",
            server_port, proc.returncode, stderr.decode().strip(),
        )
    else:
        logger.info("SSH tunnel on server port %d closed cleanly.", server_port)


def _cleanup_temp_files(*paths: str) -> None:
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass


async def _teardown_all_tunnels() -> None:
    for server_port, (proc, kh_path) in list(_tunnels.items()):
        try:
            proc.terminate()
        except ProcessLookupError:
            pass
        _cleanup_temp_files(kh_path)
    _tunnels.clear()
