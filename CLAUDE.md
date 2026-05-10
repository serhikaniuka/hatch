# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project purpose

Tooling for provisioning and configuring AWS EC2 instances (Amazon Linux 2023) to run AI agents inside Docker containers.

## Scripts

All operational scripts live in `scripts/`. They are plain Bash and should remain self-contained — no external dependencies beyond what macOS ships with (`ssh`, `curl`).

### Provisioning a server

```bash
./scripts/setup-server.sh -i <EC2_PUBLIC_IP> -k <path-to-key.pem>
```

- Targets `ec2-user` on Amazon Linux 2023 (uses `dnf`, not `yum` or `apt`).
- Installs Docker via `dnf`, then fetches the latest Docker Compose binary from GitHub releases.
- Idempotent: safe to re-run if a step was interrupted.

## Open source

This project is published publicly on GitHub. Every file is visible to anyone. Apply these rules without exception:

- **No secrets in any file** — no API keys, tokens, passwords, IPs, or private key material. Use `.env` files (covered by `.gitignore`) or environment variables. `.env.example` files must contain only empty placeholders.
- **No hardcoded infrastructure details** in committed code — IPs, account IDs, region names, and usernames belong in `.env` or docs, not in scripts or Dockerfiles.
- **`.gitignore` must be verified** before any new sensitive file type is introduced.
- **Licensing** — all contributions must be compatible with the project's chosen open source licence.

## Security

Security is a first-class requirement. Apply at every step:

### Secrets & credentials
- Never commit `.env` files, `.pem` keys, or any credential. The `.ssh/` directory is in `.gitignore`.
- Rotate any secret that is accidentally committed immediately — assume it is compromised.

### Docker
- Containers run as a non-root user (`serhiy`) — never revert to running as root.
- Do not use `privileged: true` or mount the Docker socket (`/var/run/docker.sock`) unless strictly necessary and explicitly reviewed.
- Pin image tags to specific versions for production use; `latest` is acceptable only in development.
- Keep base images up to date to pull in OS-level security patches.

### Bash scripts
- Always use `set -euo pipefail`.
- Quote all variables (`"$VAR"`) to prevent word splitting and injection.
- Validate all user-supplied arguments before use.
- Avoid `eval` and dynamic command construction from external input.

### SSH
- `StrictHostKeyChecking=no` is used only during initial provisioning — flag it if it appears in long-running or production paths.
- Private keys must have permissions `600` or stricter.

### Vulnerability checks
- Before adding any new package, image, or dependency, verify it is actively maintained and has no known critical CVEs.
- When updating Dockerfiles or scripts, re-check that no new attack surface is introduced (exposed ports, world-writable mounts, capability additions).

## Conventions

- Scripts use `set -euo pipefail` — any unhandled error aborts immediately.
- SSH options `StrictHostKeyChecking=no` and `ConnectTimeout=15` are set for non-interactive provisioning runs.
- Remote commands are sent as single SSH invocations; multi-line remote blocks use single-quoted heredoc-style strings to avoid local variable expansion.
- Architecture assumed: `x86_64`. If ARM instances (e.g. Graviton) are added, the Docker Compose download URL must be updated to `docker-compose-linux-aarch64`.
