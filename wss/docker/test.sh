#!/usr/bin/env bash
# End-to-end test: generate certs, start stack, enroll a client, run persistent.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Prefer 'docker compose' (plugin) if available, fall back to 'docker-compose' (standalone)
if docker compose version &>/dev/null 2>&1; then
    COMPOSE="docker compose -f $SCRIPT_DIR/docker-compose.yml"
else
    COMPOSE="docker-compose -f $SCRIPT_DIR/docker-compose.yml"
fi

step() { echo ""; echo "==> $*"; }

# 1. Certificates
step "Generating certificates ..."
bash "$SCRIPT_DIR/gen_certs.sh"

# 2. Build images and start infrastructure
# docker-compose build requires buildx >=0.17; use docker build directly.
step "Building images ..."
docker build -f "$SCRIPT_DIR/Dockerfile.server" -t wss-server:dev "$SCRIPT_DIR/.."
docker build -f "$SCRIPT_DIR/Dockerfile.client" -t wss-client:dev "$SCRIPT_DIR/.."

step "Starting server ..."
$COMPOSE up -d server

# 3. Wait for server health check
step "Waiting for server to become healthy ..."
for i in $(seq 1 30); do
    STATUS=$(docker inspect --format='{{.State.Health.Status}}' \
        "$(docker ps -qf "name=docker-server" 2>/dev/null)" 2>/dev/null || echo "")
    if [[ "$STATUS" == "healthy" ]]; then
        echo "    Server is healthy."
        break
    fi
    echo "    ($i/30) waiting ..."
    sleep 2
    if [[ "$i" -eq 30 ]]; then
        echo "ERROR: server did not become healthy in time." >&2
        $COMPOSE logs server
        exit 1
    fi
done

# 4. Register a test client
step "Registering test client in server DB ..."
CLIENT_ID=$(
    $COMPOSE exec -T server \
        python /app/scripts/register_client.py --db /data/wss.db --days 1
)
echo "    Client ID: $CLIENT_ID"

# 5. Enrollment run (client presents WSS_CLIENT_ID, gets a certificate)
step "Running enrollment ..."
$COMPOSE --profile client run --rm \
    -e WSS_CLIENT_ID="$CLIENT_ID" \
    client

# 6. Persistent run — detached so the script can verify and then clean up
step "Starting persistent connection ..."
$COMPOSE --profile client up -d client
sleep 5
echo ""
echo "    Client logs:"
docker logs docker-client-1 2>&1 | sed 's/^/    /'

# 7. Verify client state via NNG management socket
step "Querying client management socket ..."
docker exec docker-client-1 python3 -c "
import json, pynng
for cmd in ['ping', 'status', 'cert']:
    with pynng.Req0(dial='tcp://127.0.0.1:8767', recv_timeout=3000, send_timeout=3000) as s:
        s.send(json.dumps({'cmd': cmd}).encode())
        resp = json.loads(s.recv())
    print(f'  [{cmd}] ok={resp[\"ok\"]}', end='')
    if cmd == 'status' and resp.get('ok'):
        print(f'  connection={resp[\"result\"][\"connection\"]}', end='')
    print()
"

# 8. Verify server sees the client (via wss-mgr NNG)
step "Querying server management socket ..."
docker exec docker-server-1 python3 -c "
import json, pynng
with pynng.Req0(dial='tcp://127.0.0.1:8766', recv_timeout=3000, send_timeout=3000) as s:
    s.send(json.dumps({'cmd': 'status'}).encode())
    resp = json.loads(s.recv())
print(f'  server uptime: {resp[\"result\"][\"uptime_seconds\"]}s')
"

$COMPOSE --profile client stop client 2>/dev/null || true

step "Test complete."
