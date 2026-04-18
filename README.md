# AI/ML Morning Digest

A personalized AI/ML news agent that curates your top 10 articles every morning from Towards Data Science, ArXiv, Hacker News, Medium, and 15+ other sources — scored and classified by LLM (Gemma via Groq or Ollama).

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/nitish1888/ai-morning-digest)

## Deploy (100% Free)

See [DEPLOY.md](DEPLOY.md) for full instructions. Quick version:

1. Get free **Groq API key** at [console.groq.com](https://console.groq.com)
2. Click the **Deploy to Render** button above
3. Add your `GROQ_API_KEY` environment variable
4. Done — your dashboard is live at `https://your-app.onrender.com`

## Local Development

```bash
cp .env.example .env
# Edit .env with your GROQ_API_KEY

pip install -r requirements.txt
python main.py --serve
```

Open **http://localhost:8888** in your browser.

## Features

- **400+ articles scanned** from TDS, Medium, ArXiv, HN, Google AI, Anthropic, and more
- **LLM-powered scoring** — Gemma classifies, summarizes problems, and generates personalized insights
- **Live search** — type any topic to fetch fresh articles from Google News, Medium, HN, ArXiv in real-time
- **Filter by category** — LLM-generated tags like "RAG & Retrieval", "AI Agents", "Claude & Anthropic"
- **Morning cron** — GitHub Actions refreshes your digest every morning at 6 AM
- **Dual LLM backend** — Groq (free cloud) for deployment, Ollama (local) for dev

## Architecture

```
GitHub Actions (6 AM cron)
  │
  ▼
┌──────────────────────────────────────────┐
│  Render.com (free tier)                  │
│                                          │
│  ┌─────────┐  ┌────────┐  ┌──────────┐  │
│  │ Sources  │─▶│ Scorer │─▶│ FastAPI  │  │
│  │ RSS/HN   │  │ + LLM  │  │ Dashboard│  │
│  └─────────┘  └────────┘  └──────────┘  │
│                    │                     │
│              ┌─────▼─────┐               │
│              │ Groq API  │               │
│              │ (free)    │               │
│              └───────────┘               │
└──────────────────────────────────────────┘
```

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Web dashboard |
| `/api/articles` | GET | Current top articles (JSON) |
| `/api/search` | POST | Live search with LLM re-ranking |
| `/api/refresh` | POST | Trigger manual refresh |
| `/api/health` | GET | Health check |

## Configuration

Edit `config.yaml` to customize your profile, sources, scoring weights, and server settings.
