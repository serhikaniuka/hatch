import json

import pynng


class ClientMgmtClient:
    """Synchronous NNG Req0 client for the WSS client management socket."""

    def __init__(self, socket_url: str, timeout_ms: int = 5000):
        self._url = socket_url
        self._timeout = timeout_ms

    def _call(self, cmd: dict) -> dict:
        with pynng.Req0(
            dial=self._url,
            recv_timeout=self._timeout,
            send_timeout=self._timeout,
        ) as sock:
            sock.send(json.dumps(cmd).encode())
            return json.loads(sock.recv())

    def ping(self) -> bool:
        try:
            resp = self._call({"cmd": "ping"})
            return resp.get("ok") is True
        except Exception:
            return False

    def status(self) -> dict:
        return self._call({"cmd": "status"})

    def cert(self) -> dict:
        return self._call({"cmd": "cert"})
