#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 -i <server-ip> -k <path-to-key.pem>"
  echo ""
  echo "  -i  Public IP or hostname of the EC2 instance"
  echo "  -k  Path to the SSH private key (.pem) file"
  exit 1
}

SERVER_IP=""
KEY_FILE=""

while getopts "i:k:" opt; do
  case $opt in
    i) SERVER_IP="$OPTARG" ;;
    k) KEY_FILE="$OPTARG" ;;
    *) usage ;;
  esac
done

[[ -z "$SERVER_IP" || -z "$KEY_FILE" ]] && usage

if [[ ! -f "$KEY_FILE" ]]; then
  echo "Error: key file '$KEY_FILE' not found."
  exit 1
fi

chmod 400 "$KEY_FILE"

SSH="ssh -i $KEY_FILE -o StrictHostKeyChecking=no -o ConnectTimeout=15 ec2-user@$SERVER_IP"

echo "==> Connecting to $SERVER_IP ..."
$SSH "echo 'SSH connection OK'"

echo "==> Installing Docker ..."
$SSH "sudo dnf update -y && sudo dnf install -y docker"

echo "==> Starting and enabling Docker service ..."
$SSH "sudo systemctl enable --now docker && sudo usermod -aG docker ec2-user"

echo "==> Installing Docker Compose (latest) ..."
$SSH '
  COMPOSE_VERSION=$(curl -fsSL https://api.github.com/repos/docker/compose/releases/latest \
    | grep -oP "(?<=\"tag_name\": \")v[^\"]+")
  sudo curl -fsSL \
    "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-x86_64" \
    -o /usr/local/bin/docker-compose
  sudo chmod +x /usr/local/bin/docker-compose
'

echo "==> Verifying installation ..."
$SSH "docker --version && docker-compose --version"

echo ""
echo "Done. Docker and Docker Compose are installed on $SERVER_IP."
echo "Note: log out and back in (or run 'newgrp docker') to use Docker without sudo."
