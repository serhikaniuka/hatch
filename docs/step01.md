# Plan: Python WSS TLS Server & Client with Certificate-Based Auth

## Context

Add a new `wss/` module to the project implementing a WebSocket Secure (WSS) server and client in Python. Authentication uses mutual TLS (mTLS) with self-signed certificates. The server maintains a SQLite registry of allowed clients and Memcached state for active connections. A certificate enrollment handshake lets pre-registered clients obtain a signed client certificate before starting a persistent connection.

---

## Directory Structure

```
wss/
├── .gitignore                  # certs/, *.key, *.crt, *.pem, *.db, client/data/
├── requirements.txt
├── certs/                      # RUNTIME ONLY — never committed
│   ├── ca.key  (chmod 600)
│   ├── ca.crt
│   ├── server.key  (chmod 600)
│   └── server.crt
├── scripts/
│   ├── setup_certs.sh          # generates CA + server cert via openssl
│   └── register_client.py      # admin: INSERT client row, prints UUID
├── server/
│   ├── __init__.py
│   ├── main.py                 # asyncio.run(serve())
│   ├── config.py               # all settings from env vars
│   ├── db.py                   # SQLite DAL
│   ├── cache.py                # pymemcache async wrapper
│   ├── ssl_context.py          # server SSLContext (CERT_OPTIONAL)
│   ├── handler.py              # routes connection → enrollment or persistent
│   ├── enrollment.py           # signs CSR, stores cert, issues response
│   └── persistent.py           # manages live mTLS connection + Memcached state
└── client/
    ├── __init__.py
    ├── main.py                 # detects mode, runs enrollment or persistent
    ├── config.py               # settings + data dir paths
    ├── ssl_context.py          # enrollment vs persistent SSLContexts
    ├── enrollment.py           # generates key+CSR, runs handshake, saves to disk
    └── persistent.py           # mTLS persistent connection with ping/retry
```

---

## SQLite Schema

```sql
CREATE TABLE IF NOT EXISTS clients (
    id         TEXT PRIMARY KEY,          -- UUID4
    allow_to   TEXT NOT NULL,             -- ISO-8601; enrollment deadline
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS client_certificates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id   TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    fingerprint TEXT NOT NULL UNIQUE,     -- SHA-256 hex of DER cert
    certificate TEXT NOT NULL,            -- PEM
    approved_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_certs_client ON client_certificates(client_id);
```

---

## JSON Message Protocol

**Enrollment flow (no client cert)**

| Direction | Message |
|---|---|
| C → S | `{"type": "HELLO", "client_id": "<uuid>"}` |
| S → C | `{"type": "CERT_REQUEST"}` |
| S → C | `{"type": "ERROR", "code": "<code>", "detail": "<str>"}` |
| C → S | `{"type": "CSR", "data": "<base64-PEM>"}` |
| S → C | `{"type": "CERT_ISSUED", "certificate": "<base64-PEM>", "ca_certificate": "<base64-PEM>"}` |

Error codes: `CLIENT_NOT_FOUND`, `CLIENT_EXPIRED`, `CERT_ALREADY_ISSUED`, `INVALID_CSR`, `INTERNAL_ERROR`

**Persistent flow (mTLS)**

| Direction | Message |
|---|---|
| S → C | `{"type": "CONNECTED", "client_id": "<uuid>"}` |
| C → S | `{"type": "PING"}` |
| S → C | `{"type": "PONG"}` |
| Either | `{"type": "MESSAGE", "payload": <any>}` |

---

## Memcached Key Schema

| Key | Value | TTL |
|---|---|---|
| `client:state:<uuid>` | `{"status": "connected"/"disconnected", "last_seen": "<iso8601>", "ip": "<str>"}` | 3600 s |
| `connections:recent` | JSON array of `{client_id, event, ts}`, max 100 entries (prepend + trim) | none |

---

## SSL Context Design

**Server** — single port, single context:
```
ssl.PROTOCOL_TLS_SERVER
load_cert_chain(server.crt, server.key)
load_verify_locations(ca.crt)
verify_mode = ssl.CERT_OPTIONAL     # allows enrollment connections without cert
minimum_version = TLSv1_2
```
Client cert presence detected in app layer via `ssl_object.getpeercert(binary_form=True)`.

**Client enrollment** — no client cert, verifies server:
```
ssl.PROTOCOL_TLS_CLIENT
load_verify_locations(ca.crt)
verify_mode = CERT_REQUIRED, check_hostname = True
```

**Client persistent** — mTLS:
```
ssl.PROTOCOL_TLS_CLIENT
load_verify_locations(ca.crt)
load_cert_chain(client.crt, client.key)
verify_mode = CERT_REQUIRED, check_hostname = True
```

---

## Key Function Signatures

### `server/db.py`
```python
get_connection(db_path: str) -> sqlite3.Connection          # WAL mode + FK on
initialize_schema(conn) -> None
get_client(conn, client_id: str) -> dict | None
create_client(conn, client_id: str, allow_to: datetime) -> None
get_cert_by_fingerprint(conn, fingerprint: str) -> dict | None
get_cert_by_client_id(conn, client_id: str) -> dict | None
store_certificate(conn, client_id: str, fingerprint: str, cert_pem: str) -> None
```
All called via `loop.run_in_executor(None, fn)` — no blocking the event loop.

### `server/handler.py`
```python
async def connection_handler(websocket, conn, db_lock, cache, config) -> None
def _get_peer_cert_der(websocket) -> bytes | None    # None = no cert presented
def _compute_fingerprint(der: bytes) -> str          # SHA-256 hex
```
Logic: no cert → `handle_enrollment`; cert found in `client_certificates` → `handle_persistent`; cert not in DB → close with error.

### `server/enrollment.py`
```python
async def handle_enrollment(websocket, conn, lock, ca_cert_path, ca_key_path) -> None
def _validate_csr(csr_der: bytes, expected_cn: str) -> x509.CertificateSigningRequest
def _sign_csr(csr, ca_cert, ca_key, validity_days=365) -> x509.Certificate
def _fingerprint(cert: x509.Certificate) -> str
```

### `server/persistent.py`
```python
async def handle_persistent(websocket, client_id, client_ip, cache, config) -> None
# try/finally: always writes "disconnected" state to Memcached on exit
```

### `client/enrollment.py`
```python
async def run_enrollment(client_id: str) -> None
def _generate_key_and_csr(client_id: str) -> tuple[RSAPrivateKey, CSR]
def _save_artifacts(client_id, private_key, cert_pem, ca_pem, data_dir) -> None
# client.key saved with Path.chmod(0o600)
```

### `client/persistent.py`
```python
async def run_persistent(client_id: str) -> None
# exponential backoff on disconnect: min(2**attempt, 60) seconds
```

---

## `scripts/register_client.py`

```
Usage: python register_client.py [--db <path>] [--days <N>]
Stdout: <uuid>          ← only output; assign to a shell variable
```
Inserts `clients` row with `allow_to = now + N days`. Default N=1.

---

## `scripts/setup_certs.sh`

```bash
set -euo pipefail
# Generates certs/ca.key (chmod 600), certs/ca.crt (10yr)
# Generates certs/server.key (chmod 600), certs/server.crt (1yr)
# SAN includes $WSS_SERVER_HOST, localhost, 127.0.0.1
# Idempotent: skips if files already exist
```

---

## Dependencies (`requirements.txt`)

```
websockets>=12.0
cryptography>=42.0
pymemcache>=4.0
```

Python 3.12+. No framework — pure asyncio.

---

## How to Run

```bash
# 1. Generate certs
cd wss
WSS_SERVER_HOST=63.178.15.76 bash scripts/setup_certs.sh

# 2. Start server (Memcached must be running, e.g. via Docker)
WSS_SERVER_HOST=0.0.0.0 python -m server.main

# 3. Register a client (server DB initialised on first start)
CLIENT_UUID=$(python scripts/register_client.py --days 1)

# 4. Enroll client (run on client machine; copy ca.crt from server first)
WSS_CLIENT_ID=$CLIENT_UUID WSS_SERVER_HOST=63.178.15.76 python -m client.main

# 5. Persistent connection (re-run after enrollment completes)
WSS_SERVER_HOST=63.178.15.76 python -m client.main
```

---

## Verification Steps

```bash
# Cert chain valid
openssl verify -CAfile wss/certs/ca.crt wss/certs/server.crt

# DB has cert record after enrollment
sqlite3 wss/server/wss.db \
  "SELECT c.id, cc.fingerprint, cc.approved_at FROM clients c JOIN client_certificates cc ON cc.client_id=c.id;"

# Memcached shows connected state
echo "get client:state:<uuid>" | nc 127.0.0.1 11211

# mTLS handshake succeeds
openssl s_client -connect 63.178.15.76:8765 \
  -CAfile wss/certs/ca.crt \
  -cert wss/client/data/client.crt \
  -key wss/client/data/client.key

# Negative: expired window → CLIENT_EXPIRED error
sqlite3 wss/server/wss.db "UPDATE clients SET allow_to=datetime('now','-1 hour') WHERE id='<uuid>';"
WSS_CLIENT_ID=<uuid> python -m client.main   # should print ERROR CLIENT_EXPIRED
```

---

## Security Checklist

| Requirement | Implementation |
|---|---|
| No certs/keys committed | `wss/.gitignore` covers `certs/`, `client/data/`, `*.key`, `*.crt` |
| CA key 600 permissions | `chmod 600` in `setup_certs.sh`; client key in `_save_artifacts` |
| No hardcoded values | All config via env vars in `config.py` |
| Bash `set -euo pipefail` + quoted vars | Applied in `setup_certs.sh` |
| Non-root container user | `USER serhiy` in Dockerfile (to be added in `docker/wss-server/`) |
| `CERT_OPTIONAL` intent documented | Inline comment in `ssl_context.py` explaining single-port design |
