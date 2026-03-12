# AWS Lambda — Step-by-Step Deployment

**Estimated time:** 30–45 minutes (first time), 5 min after that
**Estimated cost:** $0/month (within AWS free tier)
**Prereqs:** An AWS account, your 3 API keys ready

---

## Free Tier Limits (you'll stay under these)

| Service | Free Tier | What We Use |
|---------|-----------|-------------|
| Lambda | 1M requests/month, 400K GB-sec | ~30 requests/day |
| API Gateway | 1M REST API calls/month | ~30 calls/day |
| EventBridge | 14M events/month | 1 event/day |
| SSM Parameter Store | Free (standard tier) | 3 parameters |

---

## How it works

```
Telegram  →  API Gateway  →  Lambda (FastAPI via Mangum)
EventBridge cron  →  Lambda (scheduled news job)
Secrets stored in  →  SSM Parameter Store
```

---

## STEP 1 — Install AWS CLI and Serverless Framework

**Install AWS CLI:**
Download from https://aws.amazon.com/cli/ and install.

Verify:
```bash
aws --version
# Should show: aws-cli/2.x.x
```

**Install Node.js** (needed for Serverless Framework):
Download from https://nodejs.org/ (LTS version)

**Install Serverless Framework:**
```bash
npm install -g serverless
serverless --version
# Should show: Framework Core: 3.x
```

---

## STEP 2 — Configure AWS Credentials

Create an IAM user with programmatic access:

1. Go to https://console.aws.amazon.com/iam/
2. Click **Users** → **Create user**
3. Username: `ai-news-bot-deploy`
4. Click **Next** → **Attach policies directly**
5. Attach: `AdministratorAccess` (simplest for first deploy)
6. Click **Create user** → go into the user → **Security credentials**
7. Click **Create access key** → select **CLI** → copy the keys

Then configure the CLI:
```bash
aws configure
# AWS Access Key ID:     [paste your key]
# AWS Secret Access Key: [paste your secret]
# Default region name:   us-east-1
# Default output format: json
```

Verify:
```bash
aws sts get-caller-identity
# Should show your account ID and user ARN
```

---

## STEP 3 — Store Secrets in SSM Parameter Store

Never hardcode secrets. SSM Parameter Store stores them securely.

Run each command and replace the placeholder with your actual value:

```bash
# Google API Key (from https://aistudio.google.com/apikey)
aws ssm put-parameter \
    --name "/ai-news-bot/GOOGLE_API_KEY" \
    --value "YOUR_GOOGLE_API_KEY" \
    --type "SecureString"

# Telegram Bot Token (from @BotFather on Telegram)
aws ssm put-parameter \
    --name "/ai-news-bot/TELEGRAM_TOKEN" \
    --value "YOUR_TELEGRAM_BOT_TOKEN" \
    --type "SecureString"

# Telegram Chat ID (from @userinfobot on Telegram)
aws ssm put-parameter \
    --name "/ai-news-bot/TELEGRAM_CHAT_ID" \
    --value "YOUR_TELEGRAM_CHAT_ID" \
    --type "SecureString"
```

Verify they were saved:
```bash
aws ssm get-parameters-by-path --path "/ai-news-bot/" --with-decryption
# Should show 3 parameters
```

> **To update a secret later:**
> ```bash
> aws ssm put-parameter \
>     --name "/ai-news-bot/TELEGRAM_TOKEN" \
>     --value "NEW_VALUE" \
>     --type "SecureString" \
>     --overwrite
> ```

---

## STEP 4 — Add mangum to requirements.txt

`mangum` is the adapter that lets Lambda understand FastAPI.

Add this line to `API/requirements.txt`:
```
mangum>=0.17.0
```

Or run from the `API/` folder:
```bash
echo "mangum>=0.17.0" >> requirements.txt
```

---

## STEP 5 — Install the Serverless Python Plugin

From the `API/` folder:
```bash
cd path/to/MCP-news/API

# Install the plugin that handles pip dependencies for Lambda
npm install --save-dev serverless-python-requirements
```

This creates a `node_modules/` folder and `package.json`. That's normal.

> **Requires Docker:** The plugin uses Docker to package native dependencies.
> Install Docker Desktop from https://www.docker.com/products/docker-desktop/
> Make sure Docker is running before deploying.

---

## STEP 6 — Deploy

From the `API/` folder, run:
```bash
serverless deploy --config deploy/aws/serverless.yml
```

This will:
1. Package your Python code and dependencies into a zip
2. Upload to S3
3. Create the Lambda function
4. Set up API Gateway
5. Set up EventBridge scheduler

Takes about 5–10 minutes the first time. You'll see:
```
✔ Service deployed to stack ai-news-bot-dev

endpoints:
  ANY - https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/dev/{proxy+}
  ANY - https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/dev/

functions:
  api: ai-news-bot-dev-api
  scheduler: ai-news-bot-dev-scheduler
```

**Save that URL** — you need it in the next step.

Test it:
```bash
curl https://YOUR-API-URL.execute-api.us-east-1.amazonaws.com/dev/health
# → {"status": "healthy", "service": "ai-news-mcp-server"}
```

---

## STEP 7 — Set WEBHOOK_URL and Register Telegram Webhook

Now that you have the API Gateway URL, store it and register it with Telegram:

```bash
# Store the webhook URL (replace with your actual API Gateway URL)
aws ssm put-parameter \
    --name "/ai-news-bot/WEBHOOK_URL" \
    --value "https://YOUR-API-URL.execute-api.us-east-1.amazonaws.com/dev" \
    --type "String"

# Register the webhook with Telegram (replace TOKEN and URL)
curl -X POST "https://api.telegram.org/botYOUR_TELEGRAM_TOKEN/setWebhook" \
    -d "url=https://YOUR-API-URL.execute-api.us-east-1.amazonaws.com/dev/webhook"
```

Verify the webhook was registered:
```bash
curl "https://api.telegram.org/botYOUR_TELEGRAM_TOKEN/getWebhookInfo"
# Should show your API Gateway URL as the webhook
```

Then redeploy so Lambda picks up the new WEBHOOK_URL parameter:
```bash
serverless deploy --config deploy/aws/serverless.yml
```

---

## STEP 8 — Test Your Telegram Bot

1. Open Telegram → find your bot (the one you created with @BotFather)
2. Send `/start` — should show welcome message
3. Send `/ainews` — should fetch and return AI news (10–30 sec)
4. Send `/quick` — should return news in 2–5 sec
5. Send `/sources` — should show 3 sources

---

## STEP 9 — Test the Scheduler (Optional)

Trigger the news job manually to confirm it works:
```bash
# Invoke the scheduler Lambda directly
aws lambda invoke \
    --function-name ai-news-bot-dev-scheduler \
    --payload '{}' \
    response.json

cat response.json
# → {"statusCode": 200, "body": "News job completed"}
```

Check your Telegram — news should arrive within 30 seconds.

**Adjust the daily schedule** — edit `deploy/aws/serverless.yml` line:
```yaml
rate: cron(0 9 * * ? *)   # Change 9 to your preferred hour (UTC)
```
Then redeploy: `serverless deploy --config deploy/aws/serverless.yml`

---

## Useful Commands After Deploy

```bash
# View Lambda logs (last 50 lines)
serverless logs -f api --config deploy/aws/serverless.yml --tail

# Trigger news job manually
aws lambda invoke \
    --function-name ai-news-bot-dev-scheduler \
    --payload '{}' /dev/stdout

# Redeploy after code changes
serverless deploy --config deploy/aws/serverless.yml

# Deploy only one function (faster, skips CloudFormation)
serverless deploy function -f api --config deploy/aws/serverless.yml

# View deployed service info
serverless info --config deploy/aws/serverless.yml

# Remove everything (deletes Lambda, API Gateway, EventBridge)
serverless remove --config deploy/aws/serverless.yml
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `docker: command not found` | Install Docker Desktop and make sure it's running |
| `No module named 'mangum'` | Add `mangum>=0.17.0` to requirements.txt |
| `AccessDenied` on SSM | Check IAM user has `ssm:GetParameter` permission |
| Bot not responding | Check webhook: `curl https://api.telegram.org/botTOKEN/getWebhookInfo` |
| Lambda timeout | Increase `timeout: 300` in serverless.yml (max is 900) |
| `Task timed out` on news job | AI + scraping is slow — increase memory to 1024 in serverless.yml |
| Build fails on Windows | Serverless uses Docker to build — ensure Docker Desktop is running |

---

## Architecture After Deploy

```
GitHub (code)
    ↓ serverless deploy
    ↓
AWS Lambda (runs FastAPI via Mangum)
    ↑                    ↑
    |                    |
API Gateway          EventBridge
(Telegram webhook    (hits scheduler Lambda
 + /news + /trigger)  at 9:00 AM UTC daily)
    |                    |
    └────────────────────┘
            ↓
        ADK Agent (Gemini)
            ↓
        Scraper (Marktechpost RSS + HackerNews + DEV.to)
            ↓
        Telegram Channel (formatted news)
```
