#!/usr/bin/env bash
set -euo pipefail

# Deploy both PATY services to Fly.io
# Usage: ./scripts/deploy-fly.sh [bot|mcp|all]

COMPONENT="${1:-all}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

deploy_bot() {
    echo "==> Deploying paty-stage-bot..."
    fly deploy --config "$ROOT_DIR/fly.toml" --remote-only
    echo "==> paty-stage-bot deployed: https://paty-stage-bot.fly.dev"
}

deploy_mcp() {
    echo "==> Deploying paty-stage-mcp..."
    (cd "$ROOT_DIR/mcp" && fly deploy --remote-only)
    echo "==> paty-stage-mcp deployed: https://paty-stage-mcp.fly.dev"
}

case "$COMPONENT" in
    bot)
        deploy_bot
        ;;
    mcp)
        deploy_mcp
        ;;
    all)
        deploy_bot
        deploy_mcp
        ;;
    *)
        echo "Usage: $0 [bot|mcp|all]"
        exit 1
        ;;
esac

echo "==> Done!"
