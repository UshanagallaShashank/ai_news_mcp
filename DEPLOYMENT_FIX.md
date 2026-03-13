# Cloud Run Deployment Fix

## Problem
The deployed container has the old code with AI/scheduler dependencies that we removed. The container fails to start because it's trying to import modules that no longer exist.

## Solution
Rebuild and redeploy the container with the updated code.

## Steps to Fix

### Option 1: Using Cloud Build (Recommended)

```bash
# Navigate to API directory
cd API

# Build and deploy using Cloud Build
gcloud builds submit --config deploy/gcp/cloudbuild.yaml

# This will:
# 1. Build a new Docker image with the updated code
# 2. Push it to Google Container Registry
# 3. Deploy it to Cloud Run automatically
```

### Option 2: Manual Docker Build & Deploy

```bash
# Navigate to API directory
cd API

# Set your project ID
export PROJECT_ID=ai-news-bot-490007
export REGION=us-central1

# Build the Docker image
docker build -t ${REGION}-docker.pkg.dev/${PROJECT_ID}/ai-news-bot/app:latest .

# Push to Google Container Registry
docker push ${REGION}-docker.pkg.dev/${PROJECT_ID}/ai-news-bot/app:latest

# Deploy to Cloud Run
gcloud run deploy ai-news-bot \
  --image=${REGION}-docker.pkg.dev/${PROJECT_ID}/ai-news-bot/app:latest \
  --region=${REGION} \
  --platform=managed \
  --allow-unauthenticated
```

### Option 3: Quick Fix - Deploy from Source

```bash
# Navigate to API directory
cd API

# Deploy directly from source (Cloud Build will build automatically)
gcloud run deploy ai-news-bot \
  --source . \
  --region=us-central1 \
  --platform=managed \
  --allow-unauthenticated
```

## Environment Variables to Set

Make sure these are set in Cloud Run:

```bash
gcloud run services update ai-news-bot \
  --region=us-central1 \
  --set-env-vars="TELEGRAM_TOKEN=your_token_here" \
  --set-env-vars="TELEGRAM_CHAT_ID=your_chat_id" \
  --set-env-vars="WEBHOOK_URL=https://your-service-url.run.app" \
  --set-env-vars="NEWS_LIMIT=6" \
  --set-env-vars="NEWS_CACHE_TTL=1800"
```

Or set them in the Cloud Console:
1. Go to Cloud Run console
2. Select your service
3. Click "Edit & Deploy New Revision"
4. Go to "Variables & Secrets" tab
5. Remove: GOOGLE_API_KEY, GOOGLE_GENAI_USE_VERTEXAI, SCHEDULE_HOUR, SCHEDULE_MINUTE
6. Keep: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, WEBHOOK_URL, NEWS_LIMIT, NEWS_CACHE_TTL

## Verify Deployment

After deployment:

```bash
# Check service status
gcloud run services describe ai-news-bot --region=us-central1

# Test health endpoint
curl https://your-service-url.run.app/health

# Test news endpoint
curl https://your-service-url.run.app/news

# Check logs
gcloud logs read --service=ai-news-bot --limit=50
```

## Common Issues

### Issue: "Module not found: scheduler"
**Solution**: Rebuild the container - the old code is still deployed

### Issue: "Module not found: agent"
**Solution**: Rebuild the container - the old code is still deployed

### Issue: "GOOGLE_API_KEY not set"
**Solution**: Remove this environment variable from Cloud Run settings

### Issue: Container still fails
**Solution**: Check logs with `gcloud logs read --service=ai-news-bot --limit=100`
