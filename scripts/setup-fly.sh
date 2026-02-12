#!/usr/bin/env bash
set -euo pipefail

# Create and configure PATY Fly.io apps from scratch.
# Usage: ./scripts/setup-fly.sh
#
# Prerequisites:
#   - fly CLI installed and authenticated (fly auth login)
#   - .env.local in project root with required API keys

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env.local"

BOT_APP="paty-stage-bot"
MCP_APP="paty-stage-mcp"
WEB_APP="paty-web"
REGION="ord"

# --- Helpers ---

require_env() {
    local var="$1"
    local val
    val=$(grep "^${var}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)
    # Strip surrounding quotes
    val="${val%\"}"
    val="${val#\"}"
    if [ -z "$val" ]; then
        echo "Error: $var is not set in $ENV_FILE"
        exit 1
    fi
    echo "$val"
}

create_app() {
    local app="$1"
    if fly apps list --json | grep -q "\"$app\""; then
        echo "  App $app already exists, skipping creation"
    else
        fly apps create "$app" --org personal
        echo "  Created app $app"
    fi
}

# --- Validate .env.local ---

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: $ENV_FILE not found. Copy .env.example to .env.local and fill in values."
    exit 1
fi

echo "==> Reading secrets from $ENV_FILE"
DAILY_API_KEY=$(require_env DAILY_API_KEY)
OPENAI_API_KEY=$(require_env OPENAI_API_KEY)
CARTESIA_API_KEY=$(require_env CARTESIA_API_KEY)
ASSEMBLYAI_API_KEY=$(require_env ASSEMBLYAI_API_KEY)
BOT_API_KEY=$(require_env BOT_API_KEY)

# Optional
OTEL_EXPORTER_OTLP_ENDPOINT=$(grep "^OTEL_EXPORTER_OTLP_ENDPOINT=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
OTEL_EXPORTER_OTLP_HEADERS=$(grep "^OTEL_EXPORTER_OTLP_HEADERS=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)

# --- Create apps ---

echo "==> Creating Fly apps in $REGION region"
create_app "$BOT_APP"
create_app "$MCP_APP"
create_app "$WEB_APP"

# --- Set bot secrets ---

echo "==> Setting secrets for $BOT_APP"
bot_secrets=(
    "DAILY_API_KEY=$DAILY_API_KEY"
    "OPENAI_API_KEY=$OPENAI_API_KEY"
    "CARTESIA_API_KEY=$CARTESIA_API_KEY"
    "ASSEMBLYAI_API_KEY=$ASSEMBLYAI_API_KEY"
    "BOT_API_KEY=$BOT_API_KEY"
)
if [ -n "$OTEL_EXPORTER_OTLP_ENDPOINT" ]; then
    bot_secrets+=("OTEL_EXPORTER_OTLP_ENDPOINT=$OTEL_EXPORTER_OTLP_ENDPOINT")
fi
if [ -n "$OTEL_EXPORTER_OTLP_HEADERS" ]; then
    bot_secrets+=("OTEL_EXPORTER_OTLP_HEADERS=$OTEL_EXPORTER_OTLP_HEADERS")
fi
fly secrets set "${bot_secrets[@]}" -a "$BOT_APP"

# --- Set MCP secrets ---

echo "==> Setting secrets for $MCP_APP"
fly secrets set \
    "DAILY_API_KEY=$DAILY_API_KEY" \
    "BOT_API_KEY=$BOT_API_KEY" \
    "BOT_SERVICE_URL=https://${BOT_APP}.fly.dev" \
    -a "$MCP_APP"

# --- Deploy ---

echo "==> Deploying $BOT_APP"
fly deploy --config "$ROOT_DIR/fly.toml" --remote-only -a "$BOT_APP"

echo "==> Deploying $MCP_APP"
(cd "$ROOT_DIR/mcp" && fly deploy --remote-only -a "$MCP_APP")

echo "==> Deploying $WEB_APP"
(cd "$ROOT_DIR/web" && fly deploy --remote-only -a "$WEB_APP")

echo ""
echo "==> Setup complete!"
echo "  Bot: https://${BOT_APP}.fly.dev"
echo "  MCP: https://${MCP_APP}.fly.dev/mcp"
echo "  Web: https://${WEB_APP}.fly.dev"
echo ""
echo "==> Custom domain setup:"
echo "  To connect paty.ai, run:"
echo "    fly certs add paty.ai -a $WEB_APP"
echo "  Then add DNS records per the output."
if [ -n "$OTEL_EXPORTER_OTLP_ENDPOINT" ]; then
    echo "  Tracing: enabled ($OTEL_EXPORTER_OTLP_ENDPOINT)"
else
    echo "  Tracing: not configured (set OTEL_EXPORTER_OTLP_ENDPOINT in .env.local to enable)"
fi
