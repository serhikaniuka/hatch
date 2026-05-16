import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from pymemcache.client.base import Client
from pymemcache.exceptions import MemcacheError

logger = logging.getLogger(__name__)


class CacheClient:
    def __init__(self, host: str, port: int, ttl: int = 3600, max_recent: int = 100):
        self._client = Client(
            (host, port),
            connect_timeout=2,
            timeout=2,
            ignore_exc=True,  # degrade gracefully if memcached is unavailable
        )
        self._ttl = ttl
        self._max_recent = max_recent

    async def set_client_state(self, client_id: str, status: str, ip: str) -> None:
        state = {
            "status": status,
            "last_seen": datetime.now(timezone.utc).isoformat(),
            "ip": ip,
        }
        await self._run(
            self._client.set,
            f"client:state:{client_id}",
            json.dumps(state).encode(),
            self._ttl,
        )

    async def get_client_state(self, client_id: str) -> Optional[dict]:
        raw = await self._run(self._client.get, f"client:state:{client_id}")
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    async def append_recent_connection(self, client_id: str, event: str) -> None:
        entry = {
            "client_id": client_id,
            "event": event,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        raw = await self._run(self._client.get, "connections:recent")
        try:
            entries = json.loads(raw) if raw else []
        except (json.JSONDecodeError, TypeError):
            entries = []

        entries.insert(0, entry)
        entries = entries[: self._max_recent]
        await self._run(
            self._client.set,
            "connections:recent",
            json.dumps(entries).encode(),
        )

    # ── tunnel port reservation ────────────────────────────────────────────────

    _TUNNEL_TTL = 43200  # 12 hours
    _PORT_START = 9000
    _PORT_END   = 9999

    async def reserve_tunnel_port(self, client_id: str, client_port: int) -> int | None:
        """Atomically reserve the first free port in 9000-9999. Returns the port or None."""
        all_keys = [f"tunnel:port:{p}" for p in range(self._PORT_START, self._PORT_END + 1)]
        taken: dict = await self._run(self._client.get_many, all_keys) or {}
        for port in range(self._PORT_START, self._PORT_END + 1):
            key = f"tunnel:port:{port}"
            if taken.get(key) is not None:
                continue
            payload = json.dumps({
                "client_id": client_id,
                "client_port": client_port,
                "reserved_at": datetime.now(timezone.utc).isoformat(),
            }).encode()
            added = await self._run(self._client.add, key, payload, self._TUNNEL_TTL)
            if added:
                return port
        return None

    async def get_tunnel_ports(self) -> list[dict]:
        """Return all currently reserved tunnel ports."""
        all_keys = [f"tunnel:port:{p}" for p in range(self._PORT_START, self._PORT_END + 1)]
        results: dict = await self._run(self._client.get_many, all_keys) or {}
        ports = []
        for key, raw in results.items():
            if raw is None:
                continue
            try:
                data = json.loads(raw)
                data["port"] = int(key.split(":")[-1])
                ports.append(data)
            except (json.JSONDecodeError, ValueError):
                pass
        return sorted(ports, key=lambda d: d["port"])

    async def release_tunnel_port(self, port: int) -> None:
        await self._run(self._client.delete, f"tunnel:port:{port}")

    async def _run(self, fn, *args):
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, fn, *args)
        except MemcacheError as exc:
            logger.warning("Memcached error: %s", exc)
            return None
