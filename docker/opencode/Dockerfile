FROM ghcr.io/opencode-ai/opencode:latest

RUN useradd -m -s /bin/bash serhiy && \
    mkdir -p /home/serhiy/projects && \
    chown -R serhiy:serhiy /home/serhiy

USER serhiy
WORKDIR /home/serhiy/projects
