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

# ── SSH setup ──────────────────────────────────────────────────────────────────
SSH_DIR=/data/ssh
mkdir -p "$SSH_DIR"
chmod 755 "$SSH_DIR"

# Generate SSH host keys once (persisted in the bind-mounted /data volume)
[ -f "$SSH_DIR/ssh_host_rsa_key" ]     || ssh-keygen -q -t rsa     -b 4096 -f "$SSH_DIR/ssh_host_rsa_key"     -N ""
[ -f "$SSH_DIR/ssh_host_ed25519_key" ] || ssh-keygen -q -t ed25519        -f "$SSH_DIR/ssh_host_ed25519_key"  -N ""

# Dynamic authorized_keys managed by the server process at runtime.
# Clear on startup; clients re-register their keys when they reconnect.
: > "$SSH_DIR/authorized_keys"
chown wss:wss "$SSH_DIR/authorized_keys"
chmod 644 "$SSH_DIR/authorized_keys"

# Write sshd_config
cat > "$SSH_DIR/sshd_config" <<SSHD_EOF
Port 2022
ListenAddress 0.0.0.0

HostKey $SSH_DIR/ssh_host_rsa_key
HostKey $SSH_DIR/ssh_host_ed25519_key

PermitRootLogin no
PasswordAuthentication no
ChallengeResponseAuthentication no
UsePAM no
PubkeyAuthentication yes
AuthorizedKeysFile $SSH_DIR/authorized_keys

StrictModes no
AllowTcpForwarding yes
GatewayPorts yes
X11Forwarding no
PermitTunnel no
AllowStreamLocalForwarding no
AllowAgentForwarding no

AllowUsers tunnel
PrintMotd no
PrintLastLog no
SSHD_EOF

# Start sshd (stays as root; privilege separation handled by sshd itself)
/usr/sbin/sshd -f "$SSH_DIR/sshd_config"

# ── Start memcached as wss user ────────────────────────────────────────────────
gosu wss memcached -l 127.0.0.1 -p 11211 -m 64 &

exec gosu wss python -m server.main
