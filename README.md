# AI/ML Morning Digest

A personalized AI/ML news agent that curates your top 10 articles every morning from Towards Data Science, ArXiv, Hacker News, and 15+ other premium sources — ranked by relevance to your expert profile.

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the web dashboard

```bash
python main.py --serve
```

Open **http://localhost:8888** in your browser.

### 3. Or get a quick CLI digest

```bash
python main.py
```

## Deploy with Docker

```bash
docker compose up -d
```

The dashboard will be available at **http://localhost:8888**.

## Configuration

Edit `config.yaml` to customize:

- **Profile** — your interests, expertise areas, and negative keywords
- **Sources** — add/remove RSS feeds, toggle Hacker News
- **Digest** — number of articles, freshness window, category weights
- **Server** — host, port, refresh interval

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐
│  RSS Feeds   │────▶│              │     │               │
│  (TDS, ArXiv │     │   Fetcher    │────▶│    Scorer     │──▶ Top 10
│   Medium...) │     │  (async)     │     │  (profile-    │   Articles
├─────────────┤     │              │     │   based)      │
│ Hacker News  │────▶│              │     │               │
└─────────────┘     └──────────────┘     └───────────────┘
                            │
                    ┌───────▼───────┐
                    │   FastAPI     │
                    │  + Beautiful  │
                    │   Dashboard   │
                    └───────────────┘
```

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Web dashboard |
| `/api/articles` | GET | Current top articles (JSON) |
| `/api/refresh` | POST | Trigger manual refresh |
| `/api/health` | GET | Health check |
