FROM node:22.23.1-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 git ca-certificates && rm -rf /var/lib/apt/lists/*
ARG CLAUDE_VERSION=2.1.322
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_VERSION}
WORKDIR /opt/deps
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
ENV NODE_PATH=/opt/deps/node_modules
USER node
WORKDIR /workspace
