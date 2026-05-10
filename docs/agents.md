# Agents

## Overview

Two AI coding agent tools are currently configured, each running as an independent Docker Compose service. Both run as the `serhiy` user and share the host projects directory.

## claude-code

An interactive TUI for coding with Claude (Anthropic).

- **Docker path:** `docker/claude-code/`
- **Base image:** `node:lts-slim` with `@anthropic-ai/claude-code` installed via npm
- **Entry point:** `claude` CLI
- **Required env var:** `ANTHROPIC_API_KEY`
- **Config persistence:** named volume `claude-config` → `/home/serhiy/.claude`

```bash
docker attach claude-code     # open the TUI
```

## opencode

A terminal AI coding assistant supporting multiple providers.

- **Docker path:** `docker/opencode/`
- **Base image:** `ghcr.io/opencode-ai/opencode:latest`
- **Required env var:** at least one provider API key
- **Config persistence:** named volume `opencode-config` → `/home/serhiy/.config/opencode`

```bash
docker attach opencode        # open the TUI
```

## Shared Projects Directory

Both containers bind-mount the same host path:

| Host path | Container path |
|---|---|
| `$HOST_PROJECTS_DIR` (default: `/home/ec2-user/projects`) | `/home/serhiy/projects` |

Files created inside either container are immediately visible on the host and to the other container.

## Adding a New Agent

1. Create `docker/<agent-name>/Dockerfile` — extend the upstream image, add `serhiy` user, set `WORKDIR /home/serhiy/projects`
2. Create `docker/<agent-name>/docker-compose.yml` — bind-mount `${HOST_PROJECTS_DIR:-/home/ec2-user/projects}:/home/serhiy/projects`, add a named volume for config
3. Create `.env.example` with required vars and `.gitignore` excluding `.env`
4. Copy to server, configure `.env`, run `docker compose up -d --build`

## Logging

```bash
docker logs <container-name>           # last logs
docker logs -f <container-name>        # follow
```
