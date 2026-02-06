#!/bin/bash
# Generate .mcp.json config for the deployed paty-mcp server on Fly.io

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
MCP_CONFIG_FILE="$PROJECT_ROOT/.mcp.json"

MCP_URL="https://paty-mcp.fly.dev/mcp"

# Check for API key
if [ -z "$MCP_API_KEY" ]; then
    echo "Warning: MCP_API_KEY not set. The config will not include authentication."
    echo "Set MCP_API_KEY environment variable before running this script."
    echo ""

    # Write config without auth
    cat > "$MCP_CONFIG_FILE" <<EOF
{
  "mcpServers": {
    "paty-control": {
      "type": "http",
      "url": "$MCP_URL"
    },
    "livekit-docs": {
      "type": "http",
      "url": "https://docs.livekit.io/mcp"
    }
  }
}
EOF
else
    # Write config with auth header
    cat > "$MCP_CONFIG_FILE" <<EOF
{
  "mcpServers": {
    "paty-control": {
      "type": "http",
      "url": "$MCP_URL",
      "headers": {
        "Authorization": "Bearer $MCP_API_KEY"
      }
    },
    "livekit-docs": {
      "type": "http",
      "url": "https://docs.livekit.io/mcp"
    }
  }
}
EOF
fi

echo "Created $MCP_CONFIG_FILE with:"
echo "  - paty-control: $MCP_URL"
echo "  - livekit-docs: https://docs.livekit.io/mcp"
echo ""
if [ -n "$MCP_API_KEY" ]; then
    echo "Authentication: Bearer token configured"
else
    echo "Authentication: None (set MCP_API_KEY to enable)"
fi
echo ""
echo "Restart your coding agent to pick up the new MCP configuration."
