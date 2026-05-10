#!/usr/bin/env bash
# Generate CA and server certificates for the WSS Docker test stack.
# The CA is preserved across runs; the server cert is always regenerated.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CERTS_DIR="$SCRIPT_DIR/certs"
mkdir -p "$CERTS_DIR"

SERVER_CN="access-manager.kanyuka.info"
CA_KEY="$CERTS_DIR/ca.key"
CA_CRT="$CERTS_DIR/ca.crt"
SERVER_KEY="$CERTS_DIR/server.key"
SERVER_CSR="$CERTS_DIR/server.csr"
SERVER_CRT="$CERTS_DIR/server.crt"
DAYS_CA=3650
DAYS_SERVER=365

echo "==> CA key and certificate ..."
if [[ ! -f "$CA_KEY" ]]; then
    openssl genrsa -out "$CA_KEY" 4096
    chmod 600 "$CA_KEY"
else
    echo "    CA key already exists, skipping."
fi

if [[ ! -f "$CA_CRT" ]]; then
    openssl req -new -x509 -days "$DAYS_CA" \
        -key "$CA_KEY" -out "$CA_CRT" \
        -subj "/CN=wss-ca/O=ai-aws-agent"
else
    echo "    CA cert already exists, skipping."
fi

echo "==> Server key and certificate (CN=${SERVER_CN}) — regenerating ..."
rm -f "$SERVER_KEY" "$SERVER_CRT" "$SERVER_CSR" "$CERTS_DIR/ca.srl"

openssl genrsa -out "$SERVER_KEY" 2048
chmod 600 "$SERVER_KEY"

openssl req -new \
    -key "$SERVER_KEY" \
    -out "$SERVER_CSR" \
    -subj "/CN=${SERVER_CN}/O=ai-aws-agent"

openssl x509 -req -days "$DAYS_SERVER" \
    -in "$SERVER_CSR" \
    -CA "$CA_CRT" -CAkey "$CA_KEY" -CAcreateserial \
    -extfile <(printf "subjectAltName=DNS:%s,DNS:localhost,IP:127.0.0.1" "$SERVER_CN") \
    -out "$SERVER_CRT"

rm -f "$SERVER_CSR" "$CERTS_DIR/ca.srl"

echo "==> Done."
echo "    CA cert:     $CA_CRT"
echo "    Server cert: $SERVER_CRT"
