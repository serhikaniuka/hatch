#!/usr/bin/env bash
# Client entrypoint: pre-seed the CA cert from the mounted certs volume so
# the enrollment SSL handshake can verify the server certificate.
set -euo pipefail

DATA_DIR="${WSS_CLIENT_DATA_DIR:-/data}"
mkdir -p "$DATA_DIR"

if [[ -f /certs/ca.crt && ! -f "$DATA_DIR/ca.crt" ]]; then
    cp /certs/ca.crt "$DATA_DIR/ca.crt"
fi

exec python -m client.main
