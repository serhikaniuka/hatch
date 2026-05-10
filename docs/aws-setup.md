# AWS Setup

## EC2

- **AMI:** Amazon Linux 2023 (latest)
- **Public IP:** 63.178.15.76
- **SSH user:** `ec2-user`
- **Key pair:** `SerhioKaniuka2025.pem` (stored at `~/.ssh/` locally)
- **Packages installed:** Docker 25.0.14, Docker Compose v5.1.3

Security group inbound rules:

| Port | Protocol | Source  | Purpose    |
|------|----------|---------|------------|
| 22   | TCP      | your IP | SSH access |

## IAM

No instance profile is attached yet. If agents need to call AWS services (e.g. Bedrock, S3), attach a role with the minimum required policy and pass credentials via the container's `AWS_*` environment variables or instance metadata.

## Networking

- Default VPC, public subnet
- Elastic IP not yet assigned — the public IP may change on instance stop/start

## SSH Keys

The project-local key pair (`ai-aws-agent`) is at `.ssh/ai-aws-agent` (private) and `.ssh/ai-aws-agent.pub`. Install the public key on the server when access via this key is needed:

```bash
# ec2-user
ssh -i ~/.ssh/SerhioKaniuka2025.pem ec2-user@63.178.15.76 \
  "cat >> ~/.ssh/authorized_keys" < .ssh/ai-aws-agent.pub

# root
ssh -i ~/.ssh/SerhioKaniuka2025.pem ec2-user@63.178.15.76 \
  "sudo tee -a /root/.ssh/authorized_keys" < .ssh/ai-aws-agent.pub
```
