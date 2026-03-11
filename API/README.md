# AI News MCP Server

> A production-ready AI news bot: Telegram frontend, Python MCP server backend, powered by Google ADK + Gemini.

---

## What This Does

Every morning (or on demand), this bot:
1. **Scrapes** AI/ML news from Marktechpost + HackerNews
2. **Curates** it with Gemini AI via Google ADK
3. **Delivers** a formatted digest to your Telegram

It also exposes a full **MCP Server** — meaning Claude Desktop, Cursor IDE, and any MCP client can connect and use the same news tools.

---

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                      FastAPI Server                        │
│                                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│  │  REST API    │  │  MCP Server  │  │  Telegram Bot    │ │
│  │  /news       │  │  /mcp/sse    │  │  /telegram/      │ │
│  │  /trigger    │  │  (SSE)       │  │  webhook         │ │
│  │  /health     │  │              │  │                  │ │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘ │
│         └─────────────────┴───────────────────┘            │
│                           │                                │
│                  ┌────────▼────────┐                       │
│                  │  Google ADK     │                       │
│                  │  Agent (Gemini) │                       │
│                  └────────┬────────┘                       │
│                           │                                │
│                  ┌────────▼────────┐                       │
│                  │   Scraper       │                       │
│                  │  Marktechpost   │                       │
│                  │  HackerNews     │                       │
│                  └─────────────────┘                       │
│                                                            │
│  ┌──────────────────────────────────────┐                  │
│  │  APScheduler (daily auto-send)       │                  │
│  └──────────────────────────────────────┘                  │
└────────────────────────────────────────────────────────────┘
```

---

## Folder Structure

```
API/
├── main.py                 # FastAPI entry point (production + webhook)
├── dev.py                  # Dev runner (polling mode, no public URL needed)
├── requirements.txt
├── .env.example            # Copy to .env and fill in your values
├── Dockerfile
├── .gitignore
│
├── config/
│   └── settings.py         # All settings loaded from env vars
│
├── scraper/
│   └── news.py             # Async scraper: Marktechpost + HackerNews
│                           # 30-min in-memory cache included
│
├── mcp_server/
│   └── server.py           # MCP server (FastMCP) with 3 tools
│                           # Any AI client can connect at /mcp/sse
│
├── agent/
│   └── agent.py            # Google ADK agent (Gemini-powered)
│                           # Orchestrates scraping + AI summarization
│
├── bot/
│   └── telegram_bot.py     # Telegram bot (/ainews /quick /sources /help)
│
├── scheduler/
│   └── jobs.py             # APScheduler — daily auto-send at 9 AM UTC
│
└── deploy/
    ├── gcp/
    │   ├── cloudbuild.yaml  # CI/CD: GitHub push -> Cloud Build -> Cloud Run
    │   └── setup.sh         # One-time GCP setup script
    └── aws/
        ├── serverless.yml   # Lambda + API Gateway + EventBridge
        └── lambda_handler.py
```

---

## Quick Start (Local Development)

### 1. Get API Keys

| Key | Where to get it | Free? |
|-----|----------------|-------|
| `GOOGLE_API_KEY` | [AI Studio](https://aistudio.google.com/apikey) | Yes (15 req/min) |
| `TELEGRAM_TOKEN` | @BotFather on Telegram → `/newbot` | Yes |
| `TELEGRAM_CHAT_ID` | @userinfobot on Telegram | — |

### 2. Setup

```bash
cd API

# Create virtual environment
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and fill in environment variables
cp .env.example .env
# Edit .env — at minimum fill in GOOGLE_API_KEY, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
```

### 3. Run

```bash
# Development mode (polling — no public URL needed)
python dev.py
```

You'll see:
```
==================================================
  AI News Bot — Development Mode
==================================================
  API:      http://localhost:8080
  API docs: http://localhost:8080/docs
  MCP SSE:  http://localhost:8080/mcp/sse
==================================================
```

Send `/ainews` to your Telegram bot and watch the magic happen.

### 4. Test

```bash
# Get news articles directly
curl http://localhost:8080/news

# Trigger news job (sends to Telegram)
curl -X POST http://localhost:8080/trigger

# Health check
curl http://localhost:8080/health
```

---

## Connect Claude Desktop to MCP Server

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ai-news": {
      "url": "http://localhost:8080/mcp/sse"
    }
  }
}
```

Now in Claude Desktop you can say:
> *"Use scrape_ai_news to get 5 AI articles, then format them for Telegram"*

---

## MCP Tools

| Tool | Description | Key Args |
|------|-------------|----------|
| `scrape_ai_news` | Fetch latest AI articles as JSON | `limit: int` |
| `format_for_telegram` | Format articles as Telegram Markdown | `articles_json, title` |
| `get_news_summary` | Quick stats on available articles | `limit: int` |

---

## Telegram Commands

| Command | Description | Speed |
|---------|-------------|-------|
| `/ainews` | AI-curated digest via Gemini | 10-30s |
| `/quick` | Direct scraping, no AI | 2-5s |
| `/sources` | Show news sources | Instant |
| `/help` | Show all commands | Instant |

---

## Deploy to GCP Cloud Run (Free Tier ~$0/month)

```bash
# One-time setup
bash deploy/gcp/setup.sh
```

Sets up: Cloud Run (scales to zero) + Cloud Scheduler (daily 9 AM UTC) + Secret Manager.

**After setup, redeploy with:**
```bash
gcloud builds submit --config deploy/gcp/cloudbuild.yaml
```

---

## Deploy to AWS Lambda (Free Tier ~$0/month)

```bash
npm install -g serverless

# Store secrets
aws ssm put-parameter --name /ai-news-bot/GOOGLE_API_KEY --value "..." --type SecureString
aws ssm put-parameter --name /ai-news-bot/TELEGRAM_TOKEN --value "..." --type SecureString
aws ssm put-parameter --name /ai-news-bot/TELEGRAM_CHAT_ID --value "..." --type SecureString

cd deploy/aws && serverless deploy
```

---

## Triggering Without APScheduler (Serverless / Scales-to-zero)

When using Cloud Run or Lambda that scales to zero, disable APScheduler and use
an external cron trigger instead — it's cheaper and simpler.

**GCP Cloud Scheduler:**
```bash
gcloud scheduler jobs create http daily-news \
  --schedule="0 9 * * *" \
  --uri="https://YOUR-APP.run.app/trigger" \
  --http-method=POST --time-zone=UTC
```

**GitHub Actions (free, no extra infra):**
```yaml
# .github/workflows/daily-news.yml
on:
  schedule:
    - cron: "0 9 * * *"
jobs:
  trigger:
    runs-on: ubuntu-latest
    steps:
      - run: curl -X POST ${{ secrets.APP_URL }}/trigger
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_API_KEY` | Yes | — | Gemini API key from AI Studio |
| `TELEGRAM_TOKEN` | Yes | — | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Yes | — | Chat/channel to send news to |
| `WEBHOOK_URL` | No | — | Public HTTPS URL (empty = dev polling mode) |
| `NEWS_LIMIT` | No | `5` | Articles per update |
| `SCHEDULE_HOUR` | No | `9` | Auto-send hour (UTC) |
| `SCHEDULE_MINUTE` | No | `0` | Auto-send minute (UTC) |

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Web Framework | FastAPI + Uvicorn |
| MCP Server | FastMCP (official Python MCP SDK) |
| AI Agent | Google ADK + Gemini 2.0 Flash |
| Telegram | python-telegram-bot v21 |
| Scraper | httpx + BeautifulSoup4 |
| Scheduler | APScheduler |
| Config | pydantic-settings |
| GCP Deploy | Cloud Run + Cloud Scheduler |
| AWS Deploy | Lambda + API Gateway + EventBridge |
