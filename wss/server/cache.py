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

    async def _run(self, fn, *args):
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, fn, *args)
        except MemcacheError as exc:
            logger.warning("Memcached error: %s", exc)
            return None
