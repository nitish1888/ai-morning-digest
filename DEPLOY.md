# Deploying AI/ML Morning Digest (100% Free)

## Architecture

```
Push to GitHub
  │
  ├── GitHub Actions ─── auto-deploy to Render on every push
  ├── Render.com (free) ─── hosts the web app 24/7 with HTTPS
  ├── Groq API (free) ──── LLM scoring (Gemma 2 / Llama 3)
  └── GitHub Actions ──── morning cron at 6 AM IST wakes app + refreshes
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

## Step 2: Deploy on Render.com (5 minutes)

1. Go to **https://render.com** → Sign up free (use GitHub)
2. Click **New** → **Web Service**
3. Connect your `ai-morning-digest` GitHub repo
4. Render auto-detects `render.yaml` — accept defaults
5. Add environment variable:
   - `GROQ_API_KEY` = your key from Step 1
6. Click **Deploy**

Your app will be live at `https://ai-morning-digest.onrender.com`

---

## Step 3: Set Up Auto-Deploy + Morning Cron (3 minutes)

### A) Auto-deploy on every git push

1. In Render dashboard → your service → **Settings** → scroll to **Deploy Hook**
2. Copy the Deploy Hook URL (looks like `https://api.render.com/deploy/srv-xxx...`)
3. In GitHub repo: **Settings → Secrets and variables → Actions → New repository secret**
4. Add: `RENDER_DEPLOY_HOOK` = the URL from step 2
5. Add: `APP_URL` = `https://ai-morning-digest.onrender.com` (your Render URL)

Now every push to `main` triggers:
- GitHub Actions builds & validates
- Sends deploy hook to Render
- Render pulls latest code and redeploys
- Health check confirms it's live

### B) Morning cron (already configured)

The workflow `morning-digest.yml` runs at **6:00 AM IST** daily:
1. Wakes the Render app (free tier sleeps after 15 min idle)
2. Triggers `/api/refresh`
3. Waits for Groq to score articles
4. Verifies digest is ready

To change the time, edit the cron in `.github/workflows/morning-digest.yml`:
```yaml
- cron: "30 0 * * *"    # 6:00 AM IST
- cron: "0 6 * * *"     # 6:00 AM UTC
- cron: "0 11 * * *"    # 6:00 AM EST
- cron: "0 11 * * 1-5"  # 6:00 AM EST, weekdays only
```

You can also trigger manually: **Actions → Run workflow**

---

## How It Works Daily

| Time     | What Happens                                          |
|----------|-------------------------------------------------------|
| 6:00 AM  | GitHub Actions cron wakes Render app (30s cold start) |
| 6:01 AM  | App scans ~400 articles from TDS, Medium, ArXiv, HN   |
| 6:01 AM  | Groq (Gemma 2) scores & classifies top 30 in ~30s     |
| 6:02 AM  | Dashboard ready: top 10 + LLM news sidebar             |
| Anytime  | Search bar fetches live from Google News, Medium, etc. |
| On push  | GitHub Actions auto-deploys to Render                  |

---

## GitHub Secrets Summary

| Secret | Value | Purpose |
|--------|-------|---------|
| `RENDER_DEPLOY_HOOK` | `https://api.render.com/deploy/srv-...` | Auto-deploy on push |
| `APP_URL` | `https://ai-morning-digest.onrender.com` | Morning cron target |

---

## Local Development

```bash
cp .env.example .env
# Edit .env with your GROQ_API_KEY

pip install -r requirements.txt

# Run with Groq (cloud, fast)
LLM_BACKEND=groq python main.py --serve

# Run with Ollama (local Gemma 4)
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

Change model: `GROQ_MODEL=llama-3.3-70b-versatile`

---

## Security

- API keys in Render env vars (encrypted at rest) + GitHub Secrets (never in logs)
- HTTPS enforced by Render
- No user data collected or stored
- `.env` in `.gitignore` — never committed
