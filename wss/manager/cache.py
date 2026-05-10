import json
from typing import Optional

from pymemcache.client.base import Client
from pymemcache.exceptions import MemcacheError


class CacheReader:
    def __init__(self, host: str, port: int):
        self._client = Client(
            (host, port),
            connect_timeout=2,
            timeout=2,
            ignore_exc=True,
        )

    def get_client_state(self, client_id: str) -> Optional[dict]:
        try:
            raw = self._client.get(f"client:state:{client_id}")
            return json.loads(raw) if raw else None
        except (MemcacheError, json.JSONDecodeError):
            return None

    def get_connected_client_ids(self, all_client_ids: list[str]) -> list[dict]:
        """Return state dicts for clients whose Memcached state is 'connected'."""
        results = []
        for cid in all_client_ids:
            state = self.get_client_state(cid)
            if state and state.get("status") == "connected":
                results.append({"client_id": cid, **state})
        return results
