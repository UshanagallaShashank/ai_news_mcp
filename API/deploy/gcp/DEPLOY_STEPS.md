# GCP Cloud Run — Step-by-Step Deployment

**Estimated time:** 20–30 minutes (first time), 5 min after that
**Estimated cost:** $0/month (within GCP free tier)
**Prereqs:** A Google account, your 3 API keys ready

---

## Free Tier Limits (you'll stay under these)

| Service | Free Tier | What We Use |
|---------|-----------|-------------|
| Cloud Run | 2M requests/month, 360K GB-sec | ~30 requests/day |
| Cloud Build | 120 min/day | ~5 min per deploy |
| Secret Manager | 6 secret versions | 4 secrets |
| Cloud Scheduler | 3 jobs | 1 job |
| Container Registry | 0.5 GB storage | ~200 MB |

---

## STEP 1 — Install gcloud CLI

Download and install: https://cloud.google.com/sdk/docs/install

Then open a terminal and run:
```bash
gcloud init
# → Follow prompts: sign in with Google, select/create a project
```

Verify it works:
```bash
gcloud --version
# Should show: Google Cloud SDK 450+
```

---

## STEP 2 — Create a GCP Project

Go to https://console.cloud.google.com and create a new project.
Note your **Project ID** (e.g. `ai-news-bot-123456`) — you'll use it below.

```bash
# Set your project in gcloud
gcloud config set project YOUR_PROJECT_ID

# Verify
gcloud config get-value project
```

---

## STEP 3 — Enable Required APIs (one-time)

```bash
gcloud services enable \
    cloudbuild.googleapis.com \
    run.googleapis.com \
    secretmanager.googleapis.com \
    cloudscheduler.googleapis.com \
    artifactregistry.googleapis.com
```

This takes about 1 minute. You only do this once per project.

---

## STEP 4 — Store Secrets in Secret Manager

Never put secrets in environment variables in your code or Dockerfile.
Secret Manager stores them securely and Cloud Run reads them at runtime.

Run each command and paste your value when prompted:

```bash
# Google API Key (from https://aistudio.google.com/apikey)
echo -n "YOUR_GOOGLE_API_KEY" | \
    gcloud secrets create GOOGLE_API_KEY --data-file=-

# Telegram Bot Token (from @BotFather)
echo -n "YOUR_TELEGRAM_TOKEN" | \
    gcloud secrets create TELEGRAM_TOKEN --data-file=-

# Telegram Chat ID (from @userinfobot)
echo -n "YOUR_TELEGRAM_CHAT_ID" | \
    gcloud secrets create TELEGRAM_CHAT_ID --data-file=-
```

Verify secrets were created:
```bash
gcloud secrets list
# Should show: GOOGLE_API_KEY, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
```

> **To update a secret later:**
> ```bash
> echo -n "NEW_VALUE" | gcloud secrets versions add SECRET_NAME --data-file=-
> ```

---

## STEP 5 — Create Artifact Registry (Docker image storage)

```bash
gcloud artifacts repositories create ai-news-bot \
    --repository-format=docker \
    --location=us-central1 \
    --description="AI News Bot Docker images"
```

---

## STEP 6 — Build and Push Docker Image

Run this from the `API/` folder (where the Dockerfile is):

```bash
cd /path/to/MCP-news/API

# Configure Docker to use gcloud credentials
gcloud auth configure-docker us-central1-docker.pkg.dev

# Build and push (replace YOUR_PROJECT_ID)
gcloud builds submit \
    --tag us-central1-docker.pkg.dev/YOUR_PROJECT_ID/ai-news-bot/app:latest \
    --timeout=600s
```

This uses Cloud Build to build remotely (no local Docker needed!).
You'll see build logs stream in your terminal. Takes ~5 minutes first time.

---

## STEP 7 — Deploy to Cloud Run

```bash
gcloud run deploy ai-news-bot \
    --image=us-central1-docker.pkg.dev/YOUR_PROJECT_ID/ai-news-bot/app:latest \
    --region=us-central1 \
    --platform=managed \
    --allow-unauthenticated \
    --port=8080 \
    --memory=512Mi \
    --cpu=1 \
    --min-instances=0 \
    --max-instances=3 \
    --timeout=300 \
    --set-secrets="GOOGLE_API_KEY=GOOGLE_API_KEY:latest,TELEGRAM_TOKEN=TELEGRAM_TOKEN:latest,TELEGRAM_CHAT_ID=TELEGRAM_CHAT_ID:latest"
```

After deploy, you'll see:
```
✓ Deploying... Done.
  ✓ Creating Revision...
  ✓ Routing traffic...
Done.
Service URL: https://ai-news-bot-xxxxxxxxxxxx-uc.a.run.app
```

**Save that URL** — you need it for the next steps.

Test it:
```bash
curl https://YOUR-APP.run.app/health
# → {"status": "healthy", "service": "ai-news-mcp-server"}

curl "https://YOUR-APP.run.app/news?limit=3"
# → JSON with articles
```

---

## STEP 8 — Set WEBHOOK_URL Secret and Redeploy

Now that you have the Cloud Run URL, tell the bot where it lives:

```bash
# Replace with YOUR actual Cloud Run URL
echo -n "https://ai-news-bot-xxxxxxxxxxxx-uc.a.run.app" | \
    gcloud secrets create WEBHOOK_URL --data-file=-

# Redeploy with all 4 secrets
gcloud run services update ai-news-bot \
    --region=us-central1 \
    --set-secrets="GOOGLE_API_KEY=GOOGLE_API_KEY:latest,TELEGRAM_TOKEN=TELEGRAM_TOKEN:latest,TELEGRAM_CHAT_ID=TELEGRAM_CHAT_ID:latest,WEBHOOK_URL=WEBHOOK_URL:latest"
```

Verify the webhook was registered with Telegram:
```bash
curl "https://api.telegram.org/bot YOUR_TELEGRAM_TOKEN/getWebhookInfo"
# Should show your Cloud Run URL as the webhook
```

---

## STEP 9 — Set Up Cloud Scheduler (Daily News)

This replaces APScheduler — it sends an HTTP request to your `/trigger`
endpoint every morning. Cloud Run wakes up, fetches news, sends to Telegram, sleeps.

```bash
# Daily at 9:00 AM UTC
gcloud scheduler jobs create http daily-ai-news \
    --location=us-central1 \
    --schedule="0 9 * * *" \
    --uri="https://YOUR-APP.run.app/trigger" \
    --http-method=POST \
    --time-zone="UTC" \
    --description="Daily AI news delivery to Telegram"
```

**Test it runs correctly (run manually now):**
```bash
gcloud scheduler jobs run daily-ai-news --location=us-central1
```

Check your Telegram — news should arrive within 30 seconds.

**Adjust the time** (edit the cron schedule):
```bash
# Example: 8:30 AM IST = 3:00 AM UTC
gcloud scheduler jobs update http daily-ai-news \
    --location=us-central1 \
    --schedule="0 3 * * *"
```

---

## STEP 10 — Test Your Telegram Bot

1. Open Telegram → find your bot (the one you created with @BotFather)
2. Send `/start` — should show welcome message
3. Send `/ainews` — should fetch and return AI news (10-30 sec)
4. Send `/quick` — should return news in 2-5 sec
5. Send `/sources` — should show 3 sources

---

## Set Up CI/CD (Auto-Deploy on Git Push)

Connect your GitHub repo so every push to `main` auto-deploys:

1. Go to https://console.cloud.google.com/cloud-build/triggers
2. Click **Connect Repository** → connect your GitHub
3. Click **Create Trigger**:
   - Event: Push to branch `main`
   - Config: Cloud Build config file
   - Location: `API/deploy/gcp/cloudbuild.yaml`
4. Click **Save**

Now every `git push origin main` triggers a rebuild and redeploy automatically.

---

## Useful Commands After Deploy

```bash
# View live logs
gcloud run services logs read ai-news-bot --region=us-central1 --tail=50

# Trigger news manually
curl -X POST https://YOUR-APP.run.app/trigger

# View Cloud Run service info
gcloud run services describe ai-news-bot --region=us-central1

# List all scheduled jobs
gcloud scheduler jobs list --location=us-central1

# Update a secret
echo -n "NEW_VALUE" | gcloud secrets versions add TELEGRAM_TOKEN --data-file=-
# Then redeploy to pick up the new value:
gcloud run services update ai-news-bot --region=us-central1 \
    --set-secrets="GOOGLE_API_KEY=GOOGLE_API_KEY:latest,TELEGRAM_TOKEN=TELEGRAM_TOKEN:latest,TELEGRAM_CHAT_ID=TELEGRAM_CHAT_ID:latest,WEBHOOK_URL=WEBHOOK_URL:latest"

# Delete everything (if you want to start over)
gcloud run services delete ai-news-bot --region=us-central1
gcloud scheduler jobs delete daily-ai-news --location=us-central1
```

---

## Architecture After Deploy

```
GitHub (code)
    ↓ git push → Cloud Build builds Docker image
    ↓
Artifact Registry (stores Docker image)
    ↓
Cloud Run (runs the FastAPI app)
    ↑               ↑
    |               |
Telegram         Cloud Scheduler
(users send     (hits /trigger at
/ainews)         9:00 AM UTC daily)
    |               |
    └───────────────┘
        ↓
    ADK Agent (Gemini)
        ↓
    Scraper (Marktechpost RSS + HackerNews + DEV.to)
        ↓
    Telegram Channel (formatted news)
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `403` on health check | Remove `--no-allow-unauthenticated` or add IAM binding |
| Bot not responding | Check webhook: `curl https://api.telegram.org/bot TOKEN/getWebhookInfo` |
| News not sending | Run scheduler manually: `gcloud scheduler jobs run daily-ai-news --location=us-central1` |
| Build fails | Check Dockerfile + requirements.txt, view logs in Cloud Build console |
| `Secret not found` | Verify with `gcloud secrets list`, re-add if missing |
| Memory limit | Increase `--memory=1Gi` in the deploy command |
