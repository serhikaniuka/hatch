import os


class ClientManagerConfig:
    mgmt_socket: str = os.environ.get("WSS_CLIENT_MGMT_SOCKET", "tcp://127.0.0.1:8767")


config = ClientManagerConfig()
