#!/usr/bin/env bash
set -euo pipefail

# Deploy PATY services to Fly.io
# Usage: ./scripts/deploy-fly.sh [bot|mcp|web|all]

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

deploy_web() {
    echo "==> Deploying paty-web..."
    (cd "$ROOT_DIR/web" && fly deploy --remote-only)
    echo "==> paty-web deployed: https://paty-web.fly.dev"
}

case "$COMPONENT" in
    bot)
        deploy_bot
        ;;
    mcp)
        deploy_mcp
        ;;
    web)
        deploy_web
        ;;
    all)
        deploy_bot
        deploy_mcp
        deploy_web
        ;;
    *)
        echo "Usage: $0 [bot|mcp|web|all]"
        exit 1
        ;;
esac

echo "==> Done!"
