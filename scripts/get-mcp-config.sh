#!/bin/bash
# Generate .mcp.json config for the paty-mcp server.
# 1. Prints ChatGPT staging connection info
# 2. Checks if local server is running
# 3. If local is up, adds it as paty-control-local
# 4. If local is down, adds staging as paty-control

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
MCP_CONFIG_FILE="$PROJECT_ROOT/.mcp.json"

LOCAL_URL="http://localhost:8080/mcp"
STAGE_URL="https://paty-stage-mcp.fly.dev/mcp"

# Streamable-http requires this Accept header
ACCEPT_HEADER="application/json, text/event-stream"

# 1. Print ChatGPT staging connection info
echo "=== ChatGPT MCP Configuration (Staging) ==="
echo ""
echo "  Server URL:  $STAGE_URL"
if [ -n "$MCP_API_KEY" ]; then
    echo "  Auth Header: Authorization: Bearer $MCP_API_KEY"
else
    echo "  Auth Header: (none — set MCP_API_KEY to enable)"
fi
echo ""
echo "To add in ChatGPT: Settings > MCP > Add Server"
echo "  URL: $STAGE_URL"
echo "==========================================="
echo ""

# 2. Check if local server is running (any HTTP response means it's up)
LOCAL_RUNNING=false
if curl -s -o /dev/null -w "%{http_code}" "$LOCAL_URL" 2>/dev/null | grep -q "^[1-5]"; then
    LOCAL_RUNNING=true
    echo "Local MCP server detected at $LOCAL_URL"
else
    echo "Local server not running."
fi
echo ""

# 3/4. Build .mcp.json
if [ "$LOCAL_RUNNING" = true ]; then
    # Local server found — use paty-control-local
    cat > "$MCP_CONFIG_FILE" <<EOF
{
  "mcpServers": {
    "paty-control-local": {
      "type": "http",
      "url": "$LOCAL_URL",
      "headers": {
        "Accept": "$ACCEPT_HEADER"
      }
    },
    "livekit-docs": {
      "type": "http",
      "url": "https://docs.livekit.io/mcp"
    }
  }
}
EOF
    echo "Created $MCP_CONFIG_FILE with:"
    echo "  - paty-control-local: $LOCAL_URL"
else
    # No local server — use staging
    AUTH_BLOCK=""
    if [ -n "$MCP_API_KEY" ]; then
        AUTH_BLOCK="\"Authorization\": \"Bearer $MCP_API_KEY\","
    fi
    cat > "$MCP_CONFIG_FILE" <<EOF
{
  "mcpServers": {
    "paty-control": {
      "type": "http",
      "url": "$STAGE_URL",
      "headers": {
        ${AUTH_BLOCK}
        "Accept": "$ACCEPT_HEADER"
      }
    },
    "livekit-docs": {
      "type": "http",
      "url": "https://docs.livekit.io/mcp"
    }
  }
}
EOF
    echo "Created $MCP_CONFIG_FILE with:"
    echo "  - paty-control: $STAGE_URL"
fi

echo "  - livekit-docs: https://docs.livekit.io/mcp"
echo ""
echo "Restart your coding agent to pick up the new MCP configuration."
