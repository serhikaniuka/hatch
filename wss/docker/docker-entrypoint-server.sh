#!/usr/bin/env bash
# Runs as root: copies bind-mounted certs (owned by the host user) into a
# container-local directory with correct ownership, then drops to the 'wss'
# user via gosu so the server process never runs as root.
set -euo pipefail

chown -R wss:wss /data

CERTS_WORK=/run/certs
mkdir -p "$CERTS_WORK"
cp /certs/ca.crt /certs/ca.key /certs/server.crt /certs/server.key "$CERTS_WORK/"
chown wss:wss "$CERTS_WORK"/*.crt "$CERTS_WORK"/*.key
chmod 644 "$CERTS_WORK"/*.crt
chmod 600 "$CERTS_WORK"/*.key

export WSS_CA_CERT="$CERTS_WORK/ca.crt"
export WSS_CA_KEY="$CERTS_WORK/ca.key"
export WSS_SERVER_CERT="$CERTS_WORK/server.crt"
export WSS_SERVER_KEY="$CERTS_WORK/server.key"

# Start memcached bound to localhost only; runs alongside the server process
gosu wss memcached -l 127.0.0.1 -p 11211 -m 64 &

exec gosu wss python -m server.main
