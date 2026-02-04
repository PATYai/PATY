#!/bin/bash
set -e

# Deploy voice agent to Cloud Run
# Usage: ./scripts/deploy-voice.sh

# Configuration
REGION="${GCP_REGION:-us-central1}"
SERVICE="paty-voice"
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
docker build -t "$IMAGE" voice/

echo "Configuring Docker for Artifact Registry..."
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

echo "Pushing image..."
docker push "$IMAGE"

echo "Deploying to Cloud Run..."
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --platform managed \
  --port 8081 \
  --no-allow-unauthenticated \
  --min-instances 1 \
  --max-instances 10 \
  --memory 3Gi \
  --cpu 2 \
  --cpu-boost \
  --timeout 3600 \
  --startup-probe=tcpSocket.port=8081,initialDelaySeconds=0,timeoutSeconds=240,periodSeconds=10,failureThreshold=30 \
  --set-env-vars "LIVEKIT_URL=${LIVEKIT_URL}" \
  --set-env-vars "LIVEKIT_API_KEY=${LIVEKIT_API_KEY}" \
  --set-env-vars "LIVEKIT_API_SECRET=${LIVEKIT_API_SECRET}" \
  --set-env-vars "SIP_OUTBOUND_TRUNK_ID=${SIP_OUTBOUND_TRUNK_ID:-}"

echo ""
echo "Deployment complete!"
gcloud run services describe "$SERVICE" --region "$REGION" --format 'value(status.url)'
