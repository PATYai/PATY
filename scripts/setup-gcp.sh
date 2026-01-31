#!/bin/bash
# Setup script for Google Cloud Run deployment
# Run this once to configure your GCP project for CI/CD

set -e

# Configuration - update these values
PROJECT_ID="${GCP_PROJECT_ID:-}"
REGION="${GCP_REGION:-us-central1}"
GITHUB_REPO="${GITHUB_REPO:-}"  # Format: owner/repo

if [ -z "$PROJECT_ID" ]; then
    echo "Error: Set GCP_PROJECT_ID environment variable"
    echo "  export GCP_PROJECT_ID=your-project-id"
    exit 1
fi

if [ -z "$GITHUB_REPO" ]; then
    echo "Error: Set GITHUB_REPO environment variable"
    echo "  export GITHUB_REPO=owner/repo"
    exit 1
fi

echo "Setting up GCP project: $PROJECT_ID"
echo "GitHub repo: $GITHUB_REPO"
echo "Region: $REGION"
echo ""

# Set the project
gcloud config set project $PROJECT_ID

# Enable required APIs
echo "Enabling required APIs..."
gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    iamcredentials.googleapis.com \
    cloudresourcemanager.googleapis.com

# Create Artifact Registry repository
echo "Creating Artifact Registry repository..."
gcloud artifacts repositories create paty \
    --repository-format=docker \
    --location=$REGION \
    --description="PATY Docker images" \
    2>/dev/null || echo "Repository already exists"

# Create service account for GitHub Actions
SA_NAME="github-actions-deploy"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "Creating service account..."
gcloud iam service-accounts create $SA_NAME \
    --display-name="GitHub Actions Deploy" \
    2>/dev/null || echo "Service account already exists"

# Grant permissions to service account
echo "Granting permissions..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/run.admin" \
    --condition=None

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/artifactregistry.writer" \
    --condition=None

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/iam.serviceAccountUser" \
    --condition=None

# Setup Workload Identity Federation
echo "Setting up Workload Identity Federation..."
POOL_NAME="github-actions-pool"
PROVIDER_NAME="github-provider"

# Create workload identity pool
gcloud iam workload-identity-pools create $POOL_NAME \
    --location="global" \
    --display-name="GitHub Actions Pool" \
    2>/dev/null || echo "Pool already exists"

# Create workload identity provider
gcloud iam workload-identity-pools providers create-oidc $PROVIDER_NAME \
    --location="global" \
    --workload-identity-pool=$POOL_NAME \
    --display-name="GitHub Provider" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
    --attribute-condition="assertion.repository=='${GITHUB_REPO}'" \
    2>/dev/null || echo "Provider already exists"

# Get the workload identity provider resource name
WIF_PROVIDER=$(gcloud iam workload-identity-pools providers describe $PROVIDER_NAME \
    --location="global" \
    --workload-identity-pool=$POOL_NAME \
    --format="value(name)")

# Allow GitHub Actions to impersonate the service account
gcloud iam service-accounts add-iam-policy-binding $SA_EMAIL \
    --role="roles/iam.workloadIdentityUser" \
    --member="principalSet://iam.googleapis.com/${WIF_PROVIDER}/attribute.repository/${GITHUB_REPO}"

echo ""
echo "============================================"
echo "Setup complete! Add these secrets to GitHub:"
echo "============================================"
echo ""
echo "GCP_PROJECT_ID: $PROJECT_ID"
echo "WIF_PROVIDER: $WIF_PROVIDER"
echo "WIF_SERVICE_ACCOUNT: $SA_EMAIL"
echo ""
echo "Optional variables:"
echo "GCP_REGION: $REGION (or set as repository variable)"
echo ""
echo "Also add your LiveKit secrets:"
echo "- LIVEKIT_URL"
echo "- LIVEKIT_API_KEY"
echo "- LIVEKIT_API_SECRET"
echo "- SIP_OUTBOUND_TRUNK_ID"
