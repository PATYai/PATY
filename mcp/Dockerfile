# syntax=docker/dockerfile:1
# TODO: Use hardened images
# Use the official UV Python base image with Python 3.13 on Debian Bookworm
ARG PYTHON_VERSION=3.13
FROM ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-bookworm-slim AS base

# Keeps Python from buffering stdout and stderr
ENV PYTHONUNBUFFERED=1

# Create a non-privileged user
ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/app" \
    --shell "/sbin/nologin" \
    --uid "${UID}" \
    appuser

# Create working directory
WORKDIR /app

# Copy just the dependency files first for caching
COPY pyproject.toml uv.lock* ./
RUN mkdir -p src

# Install dependencies
RUN uv sync --locked || uv sync

# Copy application files
COPY . .

# Change ownership to non-privileged user
RUN chown -R appuser:appuser /app

# Switch to non-privileged user
USER appuser

# Cloud Run sets PORT environment variable
ENV PORT=8080

# Run the MCP server
# FastMCP uses streamable-http transport by default which works with Cloud Run
CMD ["uv", "run", "python", "src/server.py"]
