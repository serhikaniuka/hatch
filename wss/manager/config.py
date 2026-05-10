import os
from pathlib import Path

_BASE = Path(__file__).parent.parent


class ManagerConfig:
    db_path: str = os.environ.get("WSS_DB_PATH", str(_BASE / "server" / "wss.db"))
    memcached_host: str = os.environ.get("WSS_MEMCACHED_HOST", "127.0.0.1")
    memcached_port: int = int(os.environ.get("WSS_MEMCACHED_PORT", "11211"))
    mgmt_socket: str = os.environ.get("WSS_MGMT_SOCKET", "tcp://127.0.0.1:8766")


config = ManagerConfig()
