import asyncio
import base64
import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.x509.oid import NameOID
from cryptography.hazmat.backends import default_backend
import websockets

from .db import get_client, get_cert_by_client_id, store_certificate

logger = logging.getLogger(__name__)


async def handle_enrollment(
    websocket,
    conn: sqlite3.Connection,
    lock: asyncio.Lock,
    ca_cert_path: str,
    ca_key_path: str,
) -> None:
    async def send(msg: dict) -> None:
        await websocket.send(json.dumps(msg))

    async def recv_json() -> Optional[dict]:
        try:
            raw = await asyncio.wait_for(websocket.recv(), timeout=30)
            return json.loads(raw)
        except (asyncio.TimeoutError, json.JSONDecodeError):
            return None

    # Step 1: receive HELLO
    msg = await recv_json()
    if not msg or msg.get("type") != "HELLO" or not msg.get("client_id"):
        await send({"type": "ERROR", "code": "INVALID_CSR", "detail": "Expected HELLO message"})
        return

    client_id = str(msg["client_id"]).strip()

    # Step 2: validate client in DB
    loop = asyncio.get_event_loop()
    client = await loop.run_in_executor(None, get_client, conn, client_id)

    if client is None:
        await send({"type": "ERROR", "code": "CLIENT_NOT_FOUND", "detail": "Unknown client ID"})
        return

    allow_to = datetime.fromisoformat(client["allow_to"]).replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > allow_to:
        await send({"type": "ERROR", "code": "CLIENT_EXPIRED",
                    "detail": "Enrollment window has expired"})
        return

    existing = await loop.run_in_executor(None, get_cert_by_client_id, conn, client_id)
    if existing:
        await send({"type": "ERROR", "code": "CERT_ALREADY_ISSUED",
                    "detail": "Certificate already issued for this client"})
        return

    # Step 3: request CSR
    await send({"type": "CERT_REQUEST"})

    # Step 4: receive CSR
    msg = await recv_json()
    if not msg or msg.get("type") != "CSR" or not msg.get("data"):
        await send({"type": "ERROR", "code": "INVALID_CSR", "detail": "Expected CSR message"})
        return

    try:
        csr_der = base64.b64decode(msg["data"])
    except Exception:
        await send({"type": "ERROR", "code": "INVALID_CSR", "detail": "Invalid base64 data"})
        return

    # Step 5: validate and sign CSR
    try:
        csr = _validate_csr(csr_der, client_id)
        ca_cert, ca_key = await loop.run_in_executor(None, _load_ca, ca_cert_path, ca_key_path)
        cert = _sign_csr(csr, ca_cert, ca_key)
    except ValueError as exc:
        await send({"type": "ERROR", "code": "INVALID_CSR", "detail": str(exc)})
        return
    except Exception:
        logger.exception("Error signing CSR for client %s", client_id)
        await send({"type": "ERROR", "code": "INTERNAL_ERROR", "detail": "Certificate signing failed"})
        return

    # Step 6: store in DB
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    fingerprint = _fingerprint(cert)

    async with lock:
        await loop.run_in_executor(
            None, store_certificate, conn, client_id, fingerprint, cert_pem
        )

    # Step 7: send certificate to client
    with open(ca_cert_path, "rb") as f:
        ca_pem = f.read()

    await send({
        "type": "CERT_ISSUED",
        "certificate": base64.b64encode(cert_pem.encode()).decode(),
        "ca_certificate": base64.b64encode(ca_pem).decode(),
    })
    logger.info("Certificate issued for client %s (fingerprint: %s)", client_id, fingerprint)


def _load_ca(ca_cert_path: str, ca_key_path: str):
    with open(ca_cert_path, "rb") as f:
        ca_cert = x509.load_pem_x509_certificate(f.read(), default_backend())
    with open(ca_key_path, "rb") as f:
        ca_key = serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())
    return ca_cert, ca_key


def _validate_csr(csr_der: bytes, expected_cn: str) -> x509.CertificateSigningRequest:
    try:
        csr = x509.load_der_x509_csr(csr_der, default_backend())
    except Exception as exc:
        raise ValueError(f"Cannot parse CSR: {exc}") from exc

    if not csr.is_signature_valid:
        raise ValueError("CSR signature is invalid")

    cn_attrs = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if not cn_attrs or cn_attrs[0].value != expected_cn:
        raise ValueError(f"CSR CN must equal client_id '{expected_cn}'")

    return csr


def _sign_csr(
    csr: x509.CertificateSigningRequest,
    ca_cert: x509.Certificate,
    ca_key,
    validity_days: int = 365,
) -> x509.Certificate:
    import uuid as _uuid
    from datetime import timedelta

    now = datetime.utcnow()
    return (
        x509.CertificateBuilder()
        .subject_name(csr.subject)
        .issuer_name(ca_cert.subject)
        .public_key(csr.public_key())
        .serial_number(int(_uuid.uuid4()))
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=validity_days))
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True
        )
        .sign(ca_key, hashes.SHA256(), default_backend())
    )


def _fingerprint(cert: x509.Certificate) -> str:
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
