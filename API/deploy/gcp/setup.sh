#!/bin/bash
# ============================================================
# GCP Free Tier Setup Script
# ============================================================
# Run this ONCE to set up your GCP project.
# Estimated monthly cost: $0 (within free tier limits)
#
# Free tier includes:
#   Cloud Run:     2M requests/month, 360K GB-seconds compute
#   Cloud Build:   120 build-minutes/day
#   Secret Manager: 6 active secret versions
#   Cloud Scheduler: 3 jobs (exactly what we need!)
#
# Prerequisites:
#   - Install gcloud CLI: https://cloud.google.com/sdk/docs/install
#   - Login: gcloud auth login
#   - Set project: gcloud config set project YOUR_PROJECT_ID
# ============================================================

set -e  # Exit immediately if any command fails

PROJECT_ID=$(gcloud config get-value project)
REGION="us-central1"
SERVICE_NAME="ai-news-bot"

echo "Setting up AI News Bot on GCP..."
echo "Project: $PROJECT_ID"
echo "Region:  $REGION"
echo ""

# ── Enable Required APIs ──────────────────────────────────────
echo "Enabling APIs..."
gcloud services enable \
    cloudbuild.googleapis.com \
    run.googleapis.com \
    secretmanager.googleapis.com \
    cloudscheduler.googleapis.com \
    containerregistry.googleapis.com

echo "APIs enabled!"

# ── Store Secrets ─────────────────────────────────────────────
# You'll be prompted to enter values
echo ""
echo "Setting up secrets (you'll be asked to enter values)..."

read -p "Enter your GOOGLE_API_KEY: " GOOGLE_API_KEY
echo -n "$GOOGLE_API_KEY" | gcloud secrets create GOOGLE_API_KEY --data-file=- 2>/dev/null || \
echo -n "$GOOGLE_API_KEY" | gcloud secrets versions add GOOGLE_API_KEY --data-file=-

read -p "Enter your TELEGRAM_TOKEN: " TELEGRAM_TOKEN
echo -n "$TELEGRAM_TOKEN" | gcloud secrets create TELEGRAM_TOKEN --data-file=- 2>/dev/null || \
echo -n "$TELEGRAM_TOKEN" | gcloud secrets versions add TELEGRAM_TOKEN --data-file=-

read -p "Enter your TELEGRAM_CHAT_ID: " TELEGRAM_CHAT_ID
echo -n "$TELEGRAM_CHAT_ID" | gcloud secrets create TELEGRAM_CHAT_ID --data-file=- 2>/dev/null || \
echo -n "$TELEGRAM_CHAT_ID" | gcloud secrets versions add TELEGRAM_CHAT_ID --data-file=-

echo "Secrets stored in Secret Manager!"

# ── Initial Deploy ────────────────────────────────────────────
echo ""
echo "Building and deploying (first deploy — takes ~5 min)..."

cd "$(dirname "$0")/../.."  # Go to API directory

# Build and push Docker image
IMAGE="gcr.io/$PROJECT_ID/$SERVICE_NAME:latest"
docker build -t "$IMAGE" .
docker push "$IMAGE"

# Deploy to Cloud Run
gcloud run deploy "$SERVICE_NAME" \
    --image="$IMAGE" \
    --region="$REGION" \
    --platform=managed \
    --allow-unauthenticated \
    --port=8080 \
    --memory=512Mi \
    --cpu=1 \
    --min-instances=0 \
    --max-instances=3 \
    --timeout=300 \
    --set-secrets="GOOGLE_API_KEY=GOOGLE_API_KEY:latest,TELEGRAM_TOKEN=TELEGRAM_TOKEN:latest,TELEGRAM_CHAT_ID=TELEGRAM_CHAT_ID:latest"

# ── Get the Service URL ───────────────────────────────────────
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
    --region="$REGION" \
    --format="value(status.url)")

echo "Service URL: $SERVICE_URL"

# ── Update WEBHOOK_URL secret ──────────────────────────────────
echo -n "$SERVICE_URL" | gcloud secrets create WEBHOOK_URL --data-file=- 2>/dev/null || \
echo -n "$SERVICE_URL" | gcloud secrets versions add WEBHOOK_URL --data-file=-

# Redeploy with WEBHOOK_URL
gcloud run services update "$SERVICE_NAME" \
    --region="$REGION" \
    --set-secrets="GOOGLE_API_KEY=GOOGLE_API_KEY:latest,TELEGRAM_TOKEN=TELEGRAM_TOKEN:latest,TELEGRAM_CHAT_ID=TELEGRAM_CHAT_ID:latest,WEBHOOK_URL=WEBHOOK_URL:latest"

# ── Set Up Cloud Scheduler ────────────────────────────────────
echo ""
echo "Setting up Cloud Scheduler (daily news at 9 AM UTC)..."

gcloud scheduler jobs create http daily-ai-news \
    --location="$REGION" \
    --schedule="0 9 * * *" \
    --uri="$SERVICE_URL/trigger" \
    --http-method=POST \
    --time-zone="UTC" \
    --description="Trigger daily AI news delivery to Telegram" \
    2>/dev/null || echo "Scheduler job already exists, skipping..."

echo ""
echo "============================================"
echo "Setup Complete!"
echo "============================================"
echo "Service URL: $SERVICE_URL"
echo "API Docs:    $SERVICE_URL/docs"
echo "MCP SSE:     $SERVICE_URL/mcp/sse"
echo "Health:      $SERVICE_URL/health"
echo ""
echo "Daily news will be sent at 9:00 AM UTC"
echo "To trigger manually: curl -X POST $SERVICE_URL/trigger"
echo ""
echo "Connect Claude Desktop to MCP server:"
echo "  URL: $SERVICE_URL/mcp/sse"
echo "============================================"
