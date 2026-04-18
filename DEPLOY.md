# Deploying AI/ML Morning Digest (100% Free)

## Architecture

```
GitHub repo
  |
  ├── Render.com (free)     → hosts the web app 24/7
  ├── Groq API (free)       → LLM scoring (Gemma 2 / Llama 3)
  └── GitHub Actions (free) → morning cron trigger at 6 AM
```

Everything is open source. No paid services required.

---

## Step 1: Get a Free Groq API Key (2 minutes)

1. Go to **https://console.groq.com**
2. Sign up with your GitHub account (free)
3. Go to **API Keys** → Create new key
4. Copy the key (starts with `gsk_...`)

Groq free tier: **14,400 requests/day**, 30 req/min.
Supports: `gemma2-9b-it`, `llama-3.3-70b-versatile`, `mixtral-8x7b-32768`

---

## Step 2: Push to GitHub

```bash
cd ai_news_agent
git init
git add .
git commit -m "AI/ML Morning Digest"
gh repo create ai-morning-digest --private --source=. --push
```

---

## Step 3: Deploy on Render.com (5 minutes)

1. Go to **https://render.com** → Sign up free (use GitHub)
2. Click **New** → **Web Service**
3. Connect your GitHub repo
4. Render auto-detects `render.yaml` — accept defaults
5. Add environment variable:
   - `GROQ_API_KEY` = your key from Step 1
6. Click **Deploy**

Your app will be live at `https://ai-morning-digest.onrender.com`

> Render free tier: auto-sleeps after 15 min idle, wakes on request (~30s cold start).
> The GitHub Actions cron wakes it every morning.

---

## Step 4: Set Up Morning Cron (2 minutes)

1. In your GitHub repo, go to **Settings → Secrets → Actions**
2. Add secret: `APP_URL` = `https://ai-morning-digest.onrender.com` (your Render URL)
3. The workflow in `.github/workflows/morning-digest.yml` runs at **6:00 AM IST** daily
4. To change the time, edit the cron expression:
   ```yaml
   # Examples (all UTC):
   - cron: "30 0 * * *"    # 6:00 AM IST
   - cron: "0 6 * * *"     # 6:00 AM UTC
   - cron: "0 11 * * *"    # 6:00 AM EST
   ```
5. You can also trigger manually: **Actions → Morning Digest Refresh → Run workflow**

---

## How It Works

| Time     | What Happens                                          |
|----------|-------------------------------------------------------|
| 6:00 AM  | GitHub Actions cron fires, wakes Render app           |
| 6:00 AM  | App scans ~400 articles from TDS, Medium, ArXiv, HN   |
| 6:01 AM  | Groq (Gemma 2) scores, classifies, summarizes top 30  |
| 6:02 AM  | Dashboard ready with your top 10 curated articles      |
| Anytime  | Search bar fetches live from Google News, Medium, etc. |

---

## Local Development

```bash
# Clone and set up
cd ai_news_agent
cp .env.example .env
# Edit .env with your GROQ_API_KEY

# Install dependencies
pip install -r requirements.txt

# Run with Groq (cloud)
LLM_BACKEND=groq python main.py --serve

# Run with Ollama (local, needs Gemma 4 model)
LLM_BACKEND=ollama python main.py --serve
```

---

## Switch LLM Models

| Backend | Model                      | Speed    | Quality |
|---------|----------------------------|----------|---------|
| Groq    | `gemma2-9b-it`             | ~2s      | Good    |
| Groq    | `llama-3.3-70b-versatile`  | ~4s      | Best    |
| Groq    | `mixtral-8x7b-32768`       | ~3s      | Good    |
| Ollama  | `gemma4:e4b`               | ~30s     | Best    |

Change model via env var:
```bash
GROQ_MODEL=llama-3.3-70b-versatile
```

---

## Security Notes

- API key stored in Render env vars (encrypted at rest)
- GitHub secret used for Actions (never exposed in logs)
- No user data collected or stored
- HTTPS enforced by Render by default
- `.env` file in `.gitignore` — never committed
