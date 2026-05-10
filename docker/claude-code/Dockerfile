FROM node:lts-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    bash \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code

RUN useradd -m -s /bin/bash serhiy && \
    mkdir -p /home/serhiy/projects && \
    chown -R serhiy:serhiy /home/serhiy

RUN git config --system --add safe.directory /home/serhiy/projects

USER serhiy
WORKDIR /home/serhiy/projects

ENTRYPOINT ["claude"]
