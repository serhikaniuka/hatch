# Architecture

## Overview

A single AWS EC2 instance (Amazon Linux 2023) runs multiple AI coding agent tools inside Docker containers managed by Docker Compose. Each agent runs as the `serhiy` user and shares a common projects directory with the host filesystem, so files written inside any container are immediately visible on the host and between containers.

## Components

### EC2 Host

- **AMI:** Amazon Linux 2023 (latest)
- **OS user:** `ec2-user` (admin), `serhiy` inside containers
- **Shared projects path on host:** `/home/ec2-user/projects` (bind-mounted into each container at `/home/serhiy/projects`)
- Docker and Docker Compose installed via `scripts/setup-server.sh`

### Docker Layer

Each agent lives in its own subdirectory under `docker/` with a `Dockerfile` and `docker-compose.yml`. Containers share the host projects directory via a bind mount; persistent config/auth state is stored in named Docker volumes.

```
docker/
├── claude-code/   — Claude Code CLI (Anthropic)
└── opencode/      — OpenCode TUI
```

All containers are configured with `stdin_open: true` and `tty: true` for interactive TUI use.

### Agent Services

| Service | Image | User | Projects mount | Config volume |
|---|---|---|---|---|
| `claude-code` | built from `node:lts-slim` + `@anthropic-ai/claude-code` | serhiy | `/home/serhiy/projects` | `claude-config` → `/home/serhiy/.claude` |
| `opencode` | built from `ghcr.io/opencode-ai/opencode:latest` | serhiy | `/home/serhiy/projects` | `opencode-config` → `/home/serhiy/.config/opencode` |

## WSS — Secure Client Access

The `wss/` subsystem provides certificate-based mutual-TLS access for remote clients (e.g. home servers, other EC2 instances). It consists of four components:

### Server (`wss/server/`)

Async WebSocket server (Python `websockets`) listening on port 8765 with TLS. Supports two connection modes:

- **Enrollment** — client without a certificate; server validates a UUID enrollment window, signs a CSR, and issues a certificate.
- **Persistent** — client authenticates with its signed certificate (mTLS); heartbeat ping/pong every 30 s; server can push `MESSAGE` frames.

Storage: SQLite (`wss/docker/data/wss.db` on the host, bind-mounted into the container at `/data/wss.db`) for the client registry and certificates; Memcached (running inside the server container, bound to `127.0.0.1:11211`) for ephemeral connection state (TTL 1 h).

### Client (`wss/client/`)

Python process that runs on the remote machine. Two phases:

1. **Enrollment** — generates RSA key + CSR, exchanges with server, stores `client.key`, `client.crt`, `ca.crt`, `client_id`.
2. **Persistent** — long-lived mTLS connection with auto-reconnect (exponential backoff, max 60 s).

The client also exposes an **NNG management socket** (`tcp://127.0.0.1:8767` by default, `WSS_CLIENT_MGMT_SOCKET`) that allows `wss-client-mgr` to inspect live state without interrupting the WebSocket connection.

### Server manager (`wss/manager/`) — `wss-mgr`

Interactive REPL shell for administering the server: registering clients, listing connections, revoking certificates, and querying the server via its NNG management socket (`tcp://127.0.0.1:8766`, `WSS_MGMT_SOCKET`).

```
python -m manager.main
```

### Client manager (`wss/client_manager/`) — `wss-client-mgr`

Interactive REPL shell for inspecting the **client** process from the same machine. Connects to the client's NNG management socket.

```
python -m client_manager.main
```

| Command | Description |
|---|---|
| `/client ping` | Check NNG management socket reachability |
| `/client status` | Connection state, server URI, last ping/pong timestamps, uptime |
| `/client cert` | Certificate subject, validity window, SHA-256 fingerprint |

## NNG Management Protocol

Both the server and the client expose an NNG Rep0 socket. The protocol is JSON, request-reply.

**Request shape:**
```json
{"cmd": "<name>"}
```

**Response shape:**
```json
{"ok": true, "result": ...}
{"ok": false, "error": "descriptive message"}
```

### Server commands (port 8766)

| `cmd` | `result` |
|---|---|
| `ping` | `"pong"` |
| `status` | `{uptime_seconds, mgmt_socket}` |

### Client commands (port 8767)

| `cmd` | `result` |
|---|---|
| `ping` | `"pong"` |
| `status` | `{uptime_seconds, connection, client_id, server_uri, connected_at, last_ping_sent, last_pong_received, reconnect_attempts, mgmt_socket}` |
| `cert` | `{client_id, subject, not_before, not_after, fingerprint}` |

Adding a new command: implement it in `server/mgmt.py` or `client/mgmt.py` (`_dispatch`), add the method to the corresponding `nng_client.py`, and add the CLI command to `manager/` or `client_manager/`.

## WebSocket Message Protocol

### Enrollment phase

```
Client → Server  {"type": "HELLO", "client_id": "<uuid>"}
Server → Client  {"type": "CERT_REQUEST"}
Client → Server  {"type": "CSR", "data": "<base64-DER>"}
Server → Client  {"type": "CERT_ISSUED", "certificate": "...", "ca_certificate": "..."}
Server → Client  {"type": "ERROR", "code": "...", "detail": "..."}
```

### Persistent phase

```
Server → Client  {"type": "CONNECTED", "client_id": "<uuid>"}
Client → Server  {"type": "PING"}
Server → Client  {"type": "PONG"}
Server → Client  {"type": "MESSAGE", "payload": "..."}
```

## Environment Variables

### Server

| Variable | Default | Description |
|---|---|---|
| `WSS_SERVER_HOST` | `0.0.0.0` | Bind address |
| `WSS_SERVER_PORT` | `8765` | WebSocket port |
| `WSS_DB_PATH` | `wss/server/wss.db` | SQLite database |
| `WSS_CA_CERT` | `wss/certs/ca.crt` | CA certificate |
| `WSS_SERVER_CERT` | `wss/certs/server.crt` | Server certificate |
| `WSS_SERVER_KEY` | `wss/certs/server.key` | Server private key |
| `WSS_CA_KEY` | `wss/certs/ca.key` | CA private key |
| `WSS_MEMCACHED_HOST` | `127.0.0.1` | Memcached host |
| `WSS_MEMCACHED_PORT` | `11211` | Memcached port |
| `WSS_CLIENT_STATE_TTL` | `3600` | Connection state TTL (s) |
| `WSS_MGMT_SOCKET` | `tcp://127.0.0.1:8766` | Server NNG socket |

### Client

| Variable | Default | Description |
|---|---|---|
| `WSS_SERVER_HOST` | `localhost` | Server hostname |
| `WSS_SERVER_PORT` | `8765` | Server port |
| `WSS_CLIENT_DATA_DIR` | `wss/client/data` | Key/cert storage directory |
| `WSS_CLIENT_ID` | *(none)* | UUID for enrollment (one-time) |
| `WSS_CLIENT_MGMT_SOCKET` | `tcp://127.0.0.1:8767` | Client NNG socket |

## Data Flow

```
Developer / home server
        │  wss-client-mgr (NNG :8767)
        │         │
        │  wss/client ──── mTLS wss:// ──────► wss/server ── NNG :8766 ── wss-mgr
        │                                              │
        │                                         SQLite (host bind mount)
        │                                         Memcached (in-container)
        │
        │  SSH
        ▼
  EC2 host
  /home/ec2-user/projects  ◄── bind mount ──►  /home/serhiy/projects
                                               (inside each container)
        │
        ├── claude-code container  →  Anthropic API
        └── opencode container     →  configured AI provider API
```

## Infrastructure Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│  EC2 (Amazon Linux 2023)                                         │
│                                                                  │
│  /home/ec2-user/projects  (host filesystem)                      │
│          │                                                       │
│  ┌───────┴──────────────────────────────┐                        │
│  │  Docker                              │                        │
│  │  ┌─────────────┐  ┌──────────────┐  │                        │
│  │  │ claude-code │  │   opencode   │  │                        │
│  │  │  serhiy     │  │   serhiy     │  │                        │
│  │  │ /home/serhiy│  │ /home/serhiy │  │                        │
│  │  │  /projects  │  │  /projects   │  │                        │
│  │  └─────────────┘  └──────────────┘  │                        │
│  └──────────────────────────────────────┘                        │
│                                                                  │
│  wss/server  (port 8765 mTLS)                                    │
│    ├── memcached  (127.0.0.1:11211, in-container)                │
│    └── wss.db     (bind mount ← wss/docker/data/wss.db)          │
│  wss-mgr     (NNG tcp://127.0.0.1:8766)                          │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  Remote machine (home server / other EC2)                        │
│                                                                  │
│  wss/client  ──── mTLS wss:// ────────────────────► EC2:8765    │
│  wss-client-mgr  (NNG tcp://127.0.0.1:8767)                      │
└──────────────────────────────────────────────────────────────────┘
```
