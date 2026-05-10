import os
from pathlib import Path

_BASE = Path(__file__).parent.parent


class ClientConfig:
    server_host: str = os.environ.get("WSS_SERVER_HOST", "localhost")
    server_port: int = int(os.environ.get("WSS_SERVER_PORT", "8765"))
    data_dir: Path = Path(
        os.environ.get("WSS_CLIENT_DATA_DIR", str(_BASE / "client" / "data"))
    )
    mgmt_socket: str = os.environ.get("WSS_CLIENT_MGMT_SOCKET", "tcp://127.0.0.1:8767")

    @property
    def client_id_file(self) -> Path:
        return self.data_dir / "client_id"

    @property
    def client_cert_file(self) -> Path:
        return self.data_dir / "client.crt"

    @property
    def client_key_file(self) -> Path:
        return self.data_dir / "client.key"

    @property
    def ca_cert_file(self) -> Path:
        return self.data_dir / "ca.crt"

    def is_enrolled(self) -> bool:
        return (
            self.client_id_file.exists()
            and self.client_cert_file.exists()
            and self.client_key_file.exists()
            and self.ca_cert_file.exists()
        )


config = ClientConfig()
