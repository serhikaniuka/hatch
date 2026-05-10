import asyncio
import base64
import json
import logging
import os
from pathlib import Path
from typing import Optional

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import websockets

from .config import config
from .ssl_context import build_enrollment_ssl_context

logger = logging.getLogger(__name__)


async def run_enrollment(client_id: str) -> None:
    uri = f"wss://{config.server_host}:{config.server_port}"
    ssl_ctx = build_enrollment_ssl_context()

    logger.info("Connecting to %s for enrollment ...", uri)
    async with websockets.connect(uri, ssl=ssl_ctx) as ws:
        # Send HELLO
        await ws.send(json.dumps({"type": "HELLO", "client_id": client_id}))

        # Expect CERT_REQUEST or ERROR
        msg = await _recv(ws)
        if msg is None:
            raise RuntimeError("Server closed connection unexpectedly")
        if msg.get("type") == "ERROR":
            raise RuntimeError(f"Server error: {msg.get('code')} — {msg.get('detail')}")
        if msg.get("type") != "CERT_REQUEST":
            raise RuntimeError(f"Unexpected message: {msg}")

        logger.info("Received CERT_REQUEST, generating key and CSR ...")
        private_key, csr = _generate_key_and_csr(client_id)

        csr_der = csr.public_bytes(serialization.Encoding.DER)
        await ws.send(json.dumps({
            "type": "CSR",
            "data": base64.b64encode(csr_der).decode(),
        }))

        # Expect CERT_ISSUED or ERROR
        msg = await _recv(ws, timeout=60)
        if msg is None:
            raise RuntimeError("Server closed connection before issuing cert")
        if msg.get("type") == "ERROR":
            raise RuntimeError(f"Server error: {msg.get('code')} — {msg.get('detail')}")
        if msg.get("type") != "CERT_ISSUED":
            raise RuntimeError(f"Unexpected message: {msg}")

        cert_pem = base64.b64decode(msg["certificate"])
        ca_pem = base64.b64decode(msg["ca_certificate"])

    _save_artifacts(client_id, private_key, cert_pem, ca_pem, config.data_dir)
    logger.info("Enrollment complete. Certificate stored in %s", config.data_dir)


def _generate_key_and_csr(client_id: str):
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, client_id),
        ]))
        .sign(private_key, hashes.SHA256(), default_backend())
    )
    return private_key, csr


def _save_artifacts(
    client_id: str,
    private_key,
    cert_pem: bytes,
    ca_pem: bytes,
    data_dir: Path,
) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)

    key_path = data_dir / "client.key"
    key_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)

    (data_dir / "client.crt").write_bytes(cert_pem)
    (data_dir / "ca.crt").write_bytes(ca_pem)
    (data_dir / "client_id").write_text(client_id)

    logger.info("Saved key, cert, CA cert, and client_id to %s", data_dir)


async def _recv(ws, timeout: int = 30) -> Optional[dict]:
    try:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        return json.loads(raw)
    except (asyncio.TimeoutError, json.JSONDecodeError, websockets.exceptions.ConnectionClosed):
        return None
