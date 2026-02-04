#!/bin/bash
set -e

# Deploy MCP server to Cloud Run
# Usage: ./scripts/deploy-mcp.sh

# Configuration
REGION="${GCP_REGION:-us-central1}"
SERVICE="paty-mcp"
PROJECT_ID="${GCP_PROJECT_ID:-$(gcloud config get-value project)}"

if [ -z "$PROJECT_ID" ]; then
  echo "Error: GCP_PROJECT_ID not set and no default project configured"
  exit 1
fi

# Load environment variables from .env.local if it exists
if [ -f ".env.local" ]; then
  echo "Loading environment from .env.local..."
  export $(grep -v '^#' .env.local | xargs)
fi

# Check required env vars
for var in LIVEKIT_URL LIVEKIT_API_KEY LIVEKIT_API_SECRET; do
  if [ -z "${!var}" ]; then
    echo "Error: $var is not set"
    exit 1
  fi
done

echo "Deploying $SERVICE to $PROJECT_ID in $REGION..."

# Build and push image
TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD)}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/paty/${SERVICE}:${TAG}"

echo "Building image: $IMAGE"
docker build -t "$IMAGE" mcp/

echo "Configuring Docker for Artifact Registry..."
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

echo "Pushing image..."
docker push "$IMAGE"

echo "Deploying to Cloud Run..."
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --no-invoker-iam-check \
  --min-instances 0 \
  --max-instances 5 \
  --memory 512Mi \
  --cpu 1 \
  --timeout 300 \
  --set-env-vars "LIVEKIT_URL=${LIVEKIT_URL}" \
  --set-env-vars "LIVEKIT_API_KEY=${LIVEKIT_API_KEY}" \
  --set-env-vars "LIVEKIT_API_SECRET=${LIVEKIT_API_SECRET}" \
  --set-env-vars "SIP_OUTBOUND_TRUNK_ID=${SIP_OUTBOUND_TRUNK_ID:-}" \
  --set-env-vars "MCP_AUTH_DISABLED=true"

echo ""
echo "Deployment complete!"
URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format 'value(status.url)')
echo "MCP Server URL: $URL"
echo ""
echo "To use with Claude Code:"
echo "  claude mcp add --transport http paty-control $URL/mcp"
