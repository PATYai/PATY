#!/bin/bash
# Generate MCP config for the deployed paty-mcp server

set -e

REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="paty-mcp"

URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format 'value(status.url)' 2>/dev/null)

if [ -z "$URL" ]; then
    echo "Error: Could not get URL for $SERVICE_NAME in region $REGION"
    echo "Make sure the service is deployed and you have access."
    exit 1
fi

MCP_URL="${URL}/mcp"

echo "MCP Server URL: $MCP_URL"
echo ""
echo "To add to Claude Code, run:"
echo "  claude mcp add --transport http paty-control \"$MCP_URL\""
echo ""
echo "Or add this to ~/.claude/settings.json:"
echo ""
cat <<EOF
{
  "mcpServers": {
    "paty-control": {
      "type": "http",
      "url": "$MCP_URL"
    }
  }
}
EOF
