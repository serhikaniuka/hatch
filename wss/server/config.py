import os
from pathlib import Path

_BASE = Path(__file__).parent.parent


class ServerConfig:
    host: str = os.environ.get("WSS_SERVER_HOST", "0.0.0.0")
    port: int = int(os.environ.get("WSS_SERVER_PORT", "8765"))
    db_path: str = os.environ.get("WSS_DB_PATH", str(_BASE / "server" / "wss.db"))
    ca_cert: str = os.environ.get("WSS_CA_CERT", str(_BASE / "certs" / "ca.crt"))
    server_cert: str = os.environ.get("WSS_SERVER_CERT", str(_BASE / "certs" / "server.crt"))
    server_key: str = os.environ.get("WSS_SERVER_KEY", str(_BASE / "certs" / "server.key"))
    ca_key: str = os.environ.get("WSS_CA_KEY", str(_BASE / "certs" / "ca.key"))
    memcached_host: str = os.environ.get("WSS_MEMCACHED_HOST", "127.0.0.1")
    memcached_port: int = int(os.environ.get("WSS_MEMCACHED_PORT", "11211"))
    client_state_ttl: int = int(os.environ.get("WSS_CLIENT_STATE_TTL", "3600"))
    recent_connections_max: int = 100
    mgmt_socket: str = os.environ.get("WSS_MGMT_SOCKET", "tcp://127.0.0.1:8766")


config = ServerConfig()
