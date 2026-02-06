#!/bin/bash
set -e

# Deploy bot service to Cloud Run
# Usage: ./scripts/deploy-bot.sh

# Configuration
REGION="${GCP_REGION:-us-central1}"
SERVICE="paty-bot"
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
for var in DAILY_API_KEY OPENAI_API_KEY CARTESIA_API_KEY ASSEMBLYAI_API_KEY; do
  if [ -z "${!var}" ]; then
    echo "Error: $var is not set"
    exit 1
  fi
done

echo "Deploying $SERVICE to $PROJECT_ID in $REGION..."

# Build and push image (uses project root context with Dockerfile.bot)
TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD)}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/paty/${SERVICE}:${TAG}"

echo "Building image: $IMAGE"
docker build --platform linux/amd64 -t "$IMAGE" -f Dockerfile.bot .

echo "Configuring Docker for Artifact Registry..."
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

echo "Pushing image..."
docker push "$IMAGE"

echo "Deploying to Cloud Run..."
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --platform managed \
  --no-allow-unauthenticated \
  --no-cpu-throttling \
  --min-instances 0 \
  --max-instances 10 \
  --memory 2Gi \
  --cpu 2 \
  --timeout 3600 \
  --concurrency 1 \
  --set-env-vars "DAILY_API_KEY=${DAILY_API_KEY}" \
  --set-env-vars "OPENAI_API_KEY=${OPENAI_API_KEY}" \
  --set-env-vars "CARTESIA_API_KEY=${CARTESIA_API_KEY}" \
  --set-env-vars "ASSEMBLYAI_API_KEY=${ASSEMBLYAI_API_KEY}"

echo ""
echo "Deployment complete!"
URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format 'value(status.url)')
echo "Bot Service URL: $URL"
