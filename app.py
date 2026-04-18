"""
FastAPI web application for the AI/ML News Agent.
Serves the dashboard UI and provides API endpoints for article data.
"""

import asyncio
import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from scorer import RelevanceScorer
from sources import fetch_all_articles, live_search_articles, fetch_news_feed
from llm import search_with_gemma

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.yaml"

_state: dict = {
    "articles": [],
    "all_articles": [],
    "news_feed": [],
    "last_refresh": None,
    "config": {},
    "is_loading": False,
    "is_searching": False,
}


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


async def refresh_articles():
    if _state["is_loading"]:
        return
    _state["is_loading"] = True
    logger.info("Refreshing articles...")

    try:
        config = _state["config"]
        raw_articles = await fetch_all_articles(config)

        scorer = RelevanceScorer(
            profile=config.get("profile", {}),
            digest_config=config.get("digest", {}),
        )
        top_n = config.get("digest", {}).get("top_n", 10)
        ranked = await scorer.rank_articles(raw_articles, top_n=top_n)

        _state["articles"] = [a.to_dict() for a in ranked]

        # Store ALL articles for user search (keyword-scored, full pool)
        all_dicts = [a.to_dict() for a in raw_articles if a.title.strip()]
        _state["all_articles"] = all_dicts
        _state["last_refresh"] = datetime.now(timezone.utc).isoformat()
        _state["total_scanned"] = len(raw_articles)
        logger.info(f"Refresh complete. {len(raw_articles)} scanned, top {len(ranked)} selected. {len(all_dicts)} stored for search.")

        try:
            _state["news_feed"] = await fetch_news_feed()
            logger.info(f"News feed: {len(_state['news_feed'])} items loaded")
        except Exception as e:
            logger.warning(f"News feed fetch failed: {e}")
    except Exception as e:
        logger.error(f"Refresh failed: {e}", exc_info=True)
    finally:
        _state["is_loading"] = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    _state["config"] = load_config()
    asyncio.create_task(refresh_articles())
    yield


app = FastAPI(
    title="AI/ML Morning Digest",
    description="Your personalized AI/ML news agent",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    config = _state["config"]
    profile = config.get("profile", {})
    return templates.TemplateResponse(
        request,
        "index.html",
        context={
            "profile_name": profile.get("name", "User"),
            "profile_role": profile.get("role", ""),
        },
    )


@app.get("/api/articles")
async def get_articles():
    return JSONResponse({
        "articles": _state["articles"],
        "last_refresh": _state["last_refresh"],
        "total_scanned": _state.get("total_scanned", 0),
        "is_loading": _state["is_loading"],
    })


class SearchRequest(BaseModel):
    query: str


@app.post("/api/search")
async def search_articles(body: SearchRequest):
    """Search cached articles + fetch LIVE from sources, ranked by Gemma 4."""
    query = body.query.strip()
    if not query:
        return JSONResponse({"articles": _state["articles"], "query": "", "mode": "default"})

    logger.info(f"User search: '{query}'")

    # --- Step 1: keyword match from cached pool (fast) ---
    query_words = [w.lower() for w in re.findall(r'\w+', query) if len(w) > 2]
    cached_candidates = []
    for art in _state.get("all_articles", []):
        searchable = f"{art['title']} {art['summary']} {' '.join(art.get('tags', []))}".lower()
        hits = sum(1 for w in query_words if w in searchable)
        if hits > 0:
            cached_candidates.append((hits, art))
    cached_candidates.sort(key=lambda x: x[0], reverse=True)
    cached_top = [art for _, art in cached_candidates[:15]]

    # --- Step 2: live fetch from Google News, Medium, HN, ArXiv ---
    live_articles_raw = await live_search_articles(query)
    live_dicts = [a.to_dict() for a in live_articles_raw if a.title.strip()]
    logger.info(f"Live fetch: {len(live_dicts)} fresh articles for '{query}'")

    # --- Step 3: merge, dedupe ---
    seen = set()
    merged = []
    for art in cached_top + live_dicts:
        key = re.sub(r"\W+", "", art["title"].lower())
        if key not in seen:
            seen.add(key)
            merged.append(art)

    if not merged:
        return JSONResponse({"articles": [], "query": query, "mode": "search"})

    logger.info(f"Search pool: {len(cached_top)} cached + {len(live_dicts)} live = {len(merged)} merged")

    # --- Step 4: Gemma 4 re-ranks the merged pool ---
    profile = _state["config"].get("profile", {})
    results = await search_with_gemma(profile, query, merged[:30])

    return JSONResponse({
        "articles": results[:10],
        "query": query,
        "mode": "search",
        "cached_hits": len(cached_top),
        "live_fetched": len(live_dicts),
        "total_pool": len(merged),
    })


@app.get("/api/news-feed")
async def get_news_feed():
    return JSONResponse({"items": _state.get("news_feed", [])})


@app.post("/api/refresh")
async def trigger_refresh():
    if _state["is_loading"]:
        return JSONResponse({"status": "already_loading"})
    asyncio.create_task(refresh_articles())
    return JSONResponse({"status": "refresh_started"})


@app.get("/api/health")
async def health():
    return {"status": "ok", "last_refresh": _state["last_refresh"]}
