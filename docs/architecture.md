# Architecture

## Overview

A single AWS EC2 instance (Amazon Linux 2023) runs multiple AI coding agent tools inside Docker containers managed by Docker Compose. Each agent runs as the `serhiy` user and shares a common projects directory with the host filesystem, so files written inside any container are immediately visible on the host and between containers.

## Components

### EC2 Host

- **AMI:** Amazon Linux 2023 (latest)
- **IP:** 63.178.15.76
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

## Data Flow

```
Developer (local machine)
        │  SSH
        ▼
  EC2 host (63.178.15.76)
  /home/ec2-user/projects  ◄──── bind mount ────►  /home/serhiy/projects
                                                    (inside each container)
        │
        ├── claude-code container  →  Anthropic API
        └── opencode container     →  configured AI provider API
```

## Infrastructure Diagram

```
┌──────────────────────────────────────────────┐
│  EC2 (Amazon Linux 2023)                     │
│                                              │
│  /home/ec2-user/projects  (host filesystem)  │
│          │                                   │
│  ┌───────┴──────────────────────────────┐    │
│  │  Docker                              │    │
│  │  ┌─────────────┐  ┌──────────────┐  │    │
│  │  │ claude-code │  │   opencode   │  │    │
│  │  │  serhiy     │  │   serhiy     │  │    │
│  │  │ /home/serhiy│  │ /home/serhiy │  │    │
│  │  │  /projects  │  │  /projects   │  │    │
│  │  └─────────────┘  └──────────────┘  │    │
│  └──────────────────────────────────────┘    │
└──────────────────────────────────────────────┘
```
