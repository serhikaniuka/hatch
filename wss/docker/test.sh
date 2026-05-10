#!/usr/bin/env bash
# End-to-end test: generate certs, start stack, enroll a client, run persistent.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE="docker compose -f $SCRIPT_DIR/docker-compose.yml"

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

# 6. Persistent run (client uses the issued certificate)
step "Starting persistent connection (runs until you press Ctrl-C) ..."
$COMPOSE --profile client run --rm client

step "Test complete."
