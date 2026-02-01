#!/bin/bash
# Setup script for Google Cloud Run deployment
# Run this once to configure your GCP project for CI/CD

set -e

# TODO: Migrate to terraform
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
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")

# Enable required APIs
echo "Enabling required APIs..."
gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    iamcredentials.googleapis.com \
    cloudresourcemanager.googleapis.com

SA_ID="github-deployer-sa"
SA_EMAIL="${SA_ID}@${PROJECT_ID}.iam.gserviceaccount.com"

# Check if SA exists first to avoid "Conflict" errors
if gcloud iam service-accounts describe "${SA_EMAIL}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
    echo "Service Account ${SA_ID} already exists. Skipping..."
else
    echo "Creating Service Account ${SA_ID}..."
    gcloud iam service-accounts create "${SA_ID}" \
        --display-name="GitHub Deployer" \
        --description="Service Account for GitHub Actions deployments"

    # Only sleep if we just created it (to allow for propagation)
    echo "Waiting 20 seconds for Service Account propagation..."
    sleep 20
fi

# Be cautious about changes to these roles, PoLP
for ROLE in cloudfunctions.developer run.developer artifactregistry.writer; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/$ROLE"
done

POOL_ID="github-actions-pool"

# Check if the Workload Identity Pool exists
if gcloud iam workload-identity-pools describe "${POOL_ID}" \
  --project="${PROJECT_ID}" \
  --location="global" > /dev/null 2>&1; then

  echo "Workload Identity Pool '${POOL_ID}' exists. Updating..."

  # Update existing pool
  gcloud iam workload-identity-pools update "${POOL_ID}" \
    --project="${PROJECT_ID}" \
    --location="global" \
    --display-name="GitHub Actions Pool"

else

  echo "Workload Identity Pool '${POOL_ID}' does not exist. Creating..."

  # Create new pool
  gcloud iam workload-identity-pools create "${POOL_ID}" \
    --project="${PROJECT_ID}" \
    --location="global" \
    --display-name="GitHub Actions Pool"

fi

PROVIDER_ID="github-provider"

# Check if the provider exists
if gcloud iam workload-identity-pools providers describe "${PROVIDER_ID}" \
  --project="${PROJECT_ID}" \
  --location="global" \
  --workload-identity-pool="${POOL_ID}" > /dev/null 2>&1; then

  echo "Provider '${PROVIDER_ID}' exists. Updating..."
  
  # Update existing provider
  gcloud iam workload-identity-pools providers update-oidc "${PROVIDER_ID}" \
    --project="${PROJECT_ID}" \
    --location="global" \
    --workload-identity-pool="${POOL_ID}" \
    --display-name="GitHub Actions Provider" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
    --attribute-condition="assertion.repository=='${GITHUB_REPO}' && assertion.ref=='refs/heads/main'" \
    --issuer-uri="https://token.actions.githubusercontent.com"
else
  echo "Provider '${PROVIDER_ID}' does not exist. Creating..."

  # Create new provider
  gcloud iam workload-identity-pools providers create-oidc "${PROVIDER_ID}" \
    --project="${PROJECT_ID}" \
    --location="global" \
    --workload-identity-pool="${POOL_ID}" \
    --display-name="GitHub Actions Provider" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
    --attribute-condition="assertion.repository=='${GITHUB_REPO}' && assertion.ref=='refs/heads/main'" \
    --issuer-uri="https://token.actions.githubusercontent.com"
fi

gcloud iam service-accounts add-iam-policy-binding "${SA_EMAIL}" \
    --project="${PROJECT_ID}" \
    --role="roles/iam.workloadIdentityUser" \
    --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/attribute.repository/${GITHUB_REPO}"

# Create Artifact Registry repository
echo "Creating Artifact Registry repository..."
gcloud artifacts repositories create paty \
    --repository-format=docker \
    --location=$REGION \
    --description="PATY Docker images" \
    2>/dev/null || echo "Repository already exists"

echo ""
echo "============================================"
echo "Setup complete! Add these secrets to GitHub:"
echo "============================================"
echo ""
echo "GCP_PROJECT_ID: $PROJECT_ID"
echo "WIF_PROVIDER: $PROVIDER_ID"
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
