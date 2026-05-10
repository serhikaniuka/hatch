# Deployment

## Structure

Each agent is an independent Docker Compose project under `docker/<agent-name>/`. They are deployed and managed separately.

## Deploying a New Version

```bash
# On the EC2 host, inside the agent directory (e.g. ~/claude-code)
docker compose pull          # if using a remote image
docker compose up -d --build # rebuild from Dockerfile if image is local
```

## Updating an Agent Image

For `claude-code` (built locally):
```bash
docker compose up -d --build --force-recreate
```

For `opencode` (upstream image):
```bash
docker compose pull && docker compose up -d --force-recreate
```

## Rolling Back

Docker does not keep previous image layers by default. To roll back:
1. Pin the previous image tag in `docker-compose.yml` (e.g. `ghcr.io/opencode-ai/opencode:v1.2.3`)
2. `docker compose up -d --force-recreate`

## Environment Variables & Secrets

Secrets are stored in a `.env` file alongside `docker-compose.yml` on the host (never committed — covered by `.gitignore`).

| Agent | Required vars | Optional vars |
|---|---|---|
| `claude-code` | `ANTHROPIC_API_KEY` | — |
| `opencode` | at least one of the provider keys below | `GITHUB_TOKEN` |

OpenCode provider keys: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `XAI_API_KEY`, `GROQ_API_KEY`, `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_REGION`.

The host projects path defaults to `/home/ec2-user/projects` and can be overridden per-agent via `HOST_PROJECTS_DIR` in `.env`.

## Health Checks

```bash
docker ps                          # confirm containers are Up
docker logs claude-code            # inspect startup output
docker logs opencode
```
