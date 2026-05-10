# Getting Started

## Prerequisites

- AWS account with EC2 access
- SSH key pair (`.pem`) downloaded locally
- `ssh` and `curl` available on your machine (standard on macOS)

## 1. Launch an EC2 Instance

- AMI: Amazon Linux 2023 (latest)
- Open port 22 (TCP) to your IP in the security group
- Download the key pair as a `.pem` file

The running instance is at `63.178.15.76`, key: `~/.ssh/SerhioKaniuka2025.pem`.

## 2. Provision the Server

Installs Docker 25 and Docker Compose v5 on the instance:

```bash
./scripts/setup-server.sh -i <EC2_PUBLIC_IP> -k <path-to-key.pem>
```

## 3. Create the shared projects directory on the host

```bash
ssh -i ~/.ssh/SerhioKaniuka2025.pem ec2-user@63.178.15.76 \
  "mkdir -p /home/ec2-user/projects"
```

## 4. Deploy an agent

Copy the agent folder to the server, configure `.env`, build, and start:

```bash
# Example: claude-code
scp -i ~/.ssh/SerhioKaniuka2025.pem -r docker/claude-code ec2-user@63.178.15.76:~/

ssh -i ~/.ssh/SerhioKaniuka2025.pem ec2-user@63.178.15.76
cd claude-code
cp .env.example .env
nano .env                          # set ANTHROPIC_API_KEY
docker compose up -d --build
```

Repeat with `docker/opencode` for the OpenCode agent.

## 5. Attach to an agent TUI

```bash
docker attach claude-code   # or: docker attach opencode
# Detach without stopping: Ctrl+P, Ctrl+Q
```

## 6. Verify

```bash
docker ps                          # both containers should be Up
ls /home/ec2-user/projects         # files created inside containers appear here
```
