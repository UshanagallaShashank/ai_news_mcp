# AI News Bot

An intelligent AI news aggregator that scrapes, curates, and delivers daily AI/ML news via Telegram, powered by Google Gemini and exposed as an MCP server for AI clients.

**Repository**: [github.com/UshanagallaShashank/ai_news_mcp](https://github.com/UshanagallaShashank/ai_news_mcp)

## Features

- **Multi-Source Aggregation** — Marktechpost, HackerNews, and DEV.to
- **AI-Powered Curation** — Google Gemini 2.0 Flash for summarization
- **Telegram Bot** — Interactive commands for instant news access
- **MCP Server** — Exposes tools for AI clients (Claude Desktop, Cursor IDE)
- **Automated Delivery** — Daily scheduled news at configurable times
- **Free Tier Compatible** — GCP Cloud Run, AWS Lambda, or any VPS

## Architecture

```
Telegram Bot  ──┐
REST API      ──┼──►  Google ADK Agent (Gemini)  ──►  News Scraper
MCP Server    ──┘                                        ├── Marktechpost (RSS)
                                                         ├── HackerNews (API)
APScheduler  ──────►  Google ADK Agent (Gemini)  ──►    └── DEV.to (API)
(daily 9 AM)
```

### Data Flow

**Telegram** (`/ainews`): User → Bot → ADK Agent → Scraper → Gemini AI → Formatted Message → User

**MCP Client** (Claude Desktop): Claude → MCP Server → Scraper → JSON Response → Claude

**Scheduled**: APScheduler (9 AM UTC) → ADK Agent → Scraper → Gemini AI → Telegram Channel

## Quick Start

### Prerequisites

- Python 3.9+
- Google AI Studio API key (free)
- Telegram bot token + chat ID

### Installation

```bash
git clone https://github.com/UshanagallaShashank/ai_news_mcp.git
cd ai_news_mcp/API

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
```

### Get API Keys

| Service | URL | Cost |
|---------|-----|------|
| Google AI Studio | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | Free (15 req/min) |
| Telegram Bot | Message @BotFather → `/newbot` | Free |
| Telegram Chat ID | Message @userinfobot | Free |

### Run

```bash
# Development (polling, no public URL needed)
python dev.py

# Production (webhook)
uvicorn main:app --host 0.0.0.0 --port 8080
```

- API docs: `http://localhost:8080/docs`
- MCP endpoint: `http://localhost:8080/mcp/sse`

## Usage

### Telegram Commands

| Command | Description | Speed |
|---------|-------------|-------|
| `/ainews` | AI-curated digest (uses Gemini) | 10–30s |
| `/quick` | Fast news without AI | 2–5s |
| `/sources` | View news sources | instant |
| `/help` | Show commands | instant |

### REST API

```bash
curl http://localhost:8080/news          # Get news
curl -X POST http://localhost:8080/trigger  # Trigger news job
curl http://localhost:8080/health        # Health check
```

### MCP Integration (Claude Desktop)

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

Available tools: `scrape_ai_news`, `format_for_telegram`, `get_news_summary`

## Deployment

### Google Cloud Run (Recommended)

```bash
cd API/deploy/gcp
bash setup.sh
```

Free tier: 2M requests/month, scales to zero. See [API/deploy/gcp/DEPLOY_STEPS.md](API/deploy/gcp/DEPLOY_STEPS.md)

### AWS Lambda

```bash
cd API/deploy/aws
npm install -g serverless
serverless deploy
```

Free tier: 1M requests/month. See [API/deploy/aws/DEPLOY_STEPS.md](API/deploy/aws/DEPLOY_STEPS.md)

### Docker

```bash
cd API
docker build -t ai-news-bot .
docker run -p 8080:8080 --env-file .env ai-news-bot
```

## Configuration

Key environment variables (see [API/.env.example](API/.env.example)):

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_API_KEY` | Yes | Gemini API key |
| `TELEGRAM_TOKEN` | Yes | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Yes | Target chat/channel ID |
| `WEBHOOK_URL` | No | Public URL (empty = dev mode) |
| `NEWS_LIMIT` | No | Articles per update (default: 6) |
| `SCHEDULE_HOUR` | No | Auto-send hour UTC (default: 9) |

## Project Structure

```
.
├── README.md
└── API/
    ├── main.py                  # Production entry (webhook)
    ├── dev.py                   # Development entry (polling)
    ├── requirements.txt
    ├── .env.example
    ├── Dockerfile
    ├── config/settings.py       # Configuration
    ├── scraper/news.py          # Multi-source scraper
    ├── mcp_server/server.py     # MCP server
    ├── agent/agent.py           # Google ADK agent
    ├── bot/telegram_bot.py      # Telegram handlers
    ├── scheduler/jobs.py        # Background jobs
    └── deploy/
        ├── gcp/                 # Cloud Run deployment
        └── aws/                 # Lambda deployment
```

## Tech Stack

- **Framework**: FastAPI + Uvicorn
- **AI**: Google ADK + Gemini 2.0 Flash
- **MCP**: FastMCP (Model Context Protocol)
- **Bot**: python-telegram-bot v21
- **Scraping**: httpx + stdlib
- **Scheduling**: APScheduler
- **Config**: pydantic-settings

## License

MIT — see LICENSE file for details. Contributions welcome via [issues or PRs](https://github.com/UshanagallaShashank/ai_news_mcp).
