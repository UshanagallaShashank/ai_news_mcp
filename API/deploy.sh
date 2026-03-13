#!/bin/bash
# Quick deployment script for Cloud Run

set -e  # Exit on error

echo "=================================="
echo "  Deploying News Bot to Cloud Run"
echo "=================================="

# Configuration
PROJECT_ID="ai-news-bot-490007"
REGION="us-central1"
SERVICE_NAME="ai-news-bot"

echo ""
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Service: $SERVICE_NAME"
echo ""

# Check if we're in the API directory
if [ ! -f "main.py" ]; then
    echo "Error: Please run this script from the API/ directory"
    exit 1
fi

# Set the project
echo "Setting GCP project..."
gcloud config set project $PROJECT_ID

# Deploy from source (Cloud Build will build the container)
echo ""
echo "Deploying from source..."
echo "This will:"
echo "  1. Build a new Docker image"
echo "  2. Push it to Container Registry"
echo "  3. Deploy to Cloud Run"
echo ""

gcloud run deploy $SERVICE_NAME \
  --source . \
  --region=$REGION \
  --platform=managed \
  --allow-unauthenticated \
  --port=8080 \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=3 \
  --timeout=300

echo ""
echo "=================================="
echo "  Deployment Complete!"
echo "=================================="
echo ""

# Get the service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)')

echo "Service URL: $SERVICE_URL"
echo ""
echo "Test endpoints:"
echo "  Health: curl $SERVICE_URL/health"
echo "  News:   curl $SERVICE_URL/news"
echo "  Docs:   $SERVICE_URL/docs"
echo ""
echo "Don't forget to update WEBHOOK_URL environment variable:"
echo "  gcloud run services update $SERVICE_NAME --region=$REGION --set-env-vars=WEBHOOK_URL=$SERVICE_URL"
echo ""
