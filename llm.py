"""
LLM integration supporting two backends:
  1. Groq API  (free tier, cloud — recommended for deployment)
  2. Ollama    (local, for development with Gemma 4)

Set LLM_BACKEND=groq and GROQ_API_KEY=... for cloud deployment.
Set LLM_BACKEND=ollama (default) for local dev with Gemma 4.
"""

import asyncio
import json
import logging
import os
import re
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────

LLM_BACKEND = os.environ.get("LLM_BACKEND", "ollama").lower()  # "groq" or "ollama"

# Groq (free tier: 30 req/min, 14400 req/day)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_BASE = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.environ.get("GROQ_MODEL", "gemma2-9b-it")

# Ollama (local)
OLLAMA_BASE = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("GEMMA_MODEL", "gemma4:e4b")

SYSTEM_PROMPT = "You are a JSON API. Respond with ONLY valid JSON, no markdown, no explanation."

CLASSIFICATION_TAGS = [
    "LLM & Foundation Models",
    "AI Agents & Autonomy",
    "RAG & Retrieval",
    "ML Architecture & Systems",
    "GenAI Applications",
    "Computer Vision",
    "NLP & Language",
    "MLOps & Deployment",
    "AI Safety & Ethics",
    "Data Science & Analytics",
    "Research & Papers",
    "Tutorials & How-To",
    "Industry News",
    "Claude & Anthropic",
]


# ── Backend availability checks ───────────────────────────────────────

async def _check_groq() -> bool:
    if not GROQ_API_KEY:
        logger.warning("GROQ_API_KEY not set")
        return False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status == 200:
                    logger.info(f"Groq API available (model: {GROQ_MODEL})")
                    return True
                logger.warning(f"Groq API returned {resp.status}")
    except Exception as e:
        logger.warning(f"Groq API unreachable: {e}")
    return False


async def _check_ollama() -> bool:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{OLLAMA_BASE}/api/tags",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = [m.get("name", "") for m in data.get("models", [])]
                    available = any(OLLAMA_MODEL.split(":")[0] in m for m in models)
                    if available:
                        logger.info(f"Ollama available (model: {OLLAMA_MODEL})")
                    else:
                        logger.warning(f"Model not found. Available: {models}")
                    return available
    except Exception as e:
        logger.warning(f"Ollama not reachable: {e}")
    return False


async def _check_llm() -> bool:
    if LLM_BACKEND == "groq":
        return await _check_groq()
    return await _check_ollama()


# ── Unified chat function ─────────────────────────────────────────────

async def _chat_groq(user_msg: str, system_msg: str = SYSTEM_PROMPT,
                     max_tokens: int = 1024, temperature: float = 0.2) -> Optional[str]:
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                GROQ_BASE, json=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    content = data["choices"][0]["message"]["content"].strip()
                    return content
                elif resp.status == 429:
                    logger.warning("Groq rate limit hit, waiting 5s...")
                    await asyncio.sleep(5)
                    return None
                else:
                    body = await resp.text()
                    logger.warning(f"Groq HTTP {resp.status}: {body[:200]}")
    except asyncio.TimeoutError:
        logger.warning("Groq chat timed out")
    except Exception as e:
        logger.warning(f"Groq error: {type(e).__name__}: {e}")
    return None


async def _chat_ollama(user_msg: str, system_msg: str = SYSTEM_PROMPT,
                       max_tokens: int = 1500, temperature: float = 0.2) -> Optional[str]:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        "stream": False,
        "format": "json",
        "options": {"num_predict": max_tokens, "temperature": temperature},
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{OLLAMA_BASE}/api/chat", json=payload,
                timeout=aiohttp.ClientTimeout(total=90),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    content = data.get("message", {}).get("content", "").strip()
                    if not content:
                        logger.warning(
                            f"Ollama empty: done_reason={data.get('done_reason')} "
                            f"eval_count={data.get('eval_count')}"
                        )
                    return content
                else:
                    body = await resp.text()
                    logger.warning(f"Ollama HTTP {resp.status}: {body[:200]}")
    except asyncio.TimeoutError:
        logger.warning("Ollama chat timed out")
    except Exception as e:
        logger.warning(f"Ollama error: {type(e).__name__}: {e}")
    return None


async def _chat(user_msg: str, system_msg: str = SYSTEM_PROMPT,
                max_tokens: int = 1024, temperature: float = 0.2) -> Optional[str]:
    if LLM_BACKEND == "groq":
        return await _chat_groq(user_msg, system_msg, max_tokens, temperature)
    return await _chat_ollama(user_msg, system_msg, max_tokens, temperature)


# ── Helpers ────────────────────────────────────────────────────────────

def _sanitize(text: str) -> str:
    text = re.sub(r'[^\x20-\x7E]', ' ', text)
    text = text.replace('"', "'").replace('\\', ' ')
    return re.sub(r'\s+', ' ', text).strip()


def _build_scoring_prompt(profile: dict, articles_batch: list[dict]) -> str:
    tags_str = ", ".join(CLASSIFICATION_TAGS)
    profile_desc = (
        f"{profile.get('role', 'AI/ML Professional')}, "
        f"{profile.get('years_experience', 10)}yr exp. "
        f"Focus: {', '.join(profile.get('primary_interests', [])[:5])}. "
        f"Arch: {', '.join(profile.get('architecture_interests', [])[:4])}. "
        f"Edge: {', '.join(profile.get('cutting_edge_interests', [])[:5])}."
    )

    articles_text = ""
    for i, art in enumerate(articles_batch):
        title = _sanitize(art.get('title', ''))[:100]
        source = _sanitize(art.get('source', ''))
        summary = _sanitize(art.get('summary', ''))[:100]
        articles_text += f"\n[{i}] {title}\n    {source} | {summary}"

    return (
        f"Profile: {profile_desc}\n"
        f"Tags: [{tags_str}]\n"
        f"\nArticles:{articles_text}\n\n"
        f"For each article return JSON array. Each element:\n"
        f'{{"index":N, "score":0.0-1.0, "tag":"one tag from Tags list", '
        f'"problem_summary":"1 sentence: what problem does this article solve or address", '
        f'"insight":"1 sentence: why this matters to this architect"}}\n'
        f"Be strict: beginner/generic = low score. Advanced ML, architecture, GenAI = high."
    )


# ── Scoring ────────────────────────────────────────────────────────────

async def score_articles_with_gemma(profile: dict, articles: list[dict],
                                     batch_size: int = 0) -> list[dict]:
    if not await _check_llm():
        logger.info("LLM unavailable, skipping scoring")
        return articles

    if batch_size == 0:
        batch_size = 5 if LLM_BACKEND == "groq" else 3

    backend_name = "Groq" if LLM_BACKEND == "groq" else "Ollama"
    model_name = GROQ_MODEL if LLM_BACKEND == "groq" else OLLAMA_MODEL
    logger.info(f"Scoring {len(articles)} articles via {backend_name} ({model_name})...")

    for i in range(0, len(articles), batch_size):
        batch = articles[i:i + batch_size]
        user_msg = _build_scoring_prompt(profile, batch)
        response = await _chat(user_msg, max_tokens=1500, temperature=0.2)

        if not response:
            logger.warning(f"Batch {i//batch_size + 1}: empty response")
            continue

        try:
            parsed = json.loads(response)
            scores = parsed if isinstance(parsed, list) else next(
                (v for v in parsed.values() if isinstance(v, list)), []
            )

            for item in scores:
                if not isinstance(item, dict):
                    continue
                idx = item.get("index", -1)
                if 0 <= idx < len(batch):
                    batch[idx]["llm_score"] = max(0.0, min(1.0, float(item.get("score", 0.5))))
                    if item.get("tag"):
                        batch[idx]["classification"] = item["tag"]
                    if item.get("problem_summary"):
                        batch[idx]["problem_summary"] = item["problem_summary"]
                    if item.get("insight"):
                        batch[idx]["insight"] = item["insight"]

            logger.info(f"Batch {i//batch_size + 1}: scored {len(scores)} articles")
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(f"Parse error batch {i//batch_size + 1}: {e}")

        if LLM_BACKEND == "groq":
            await asyncio.sleep(2.5)

    scored_count = sum(1 for a in articles if "llm_score" in a)
    logger.info(f"LLM scoring complete: {scored_count}/{len(articles)} articles scored")
    return articles


# ── Search ─────────────────────────────────────────────────────────────

async def search_with_gemma(profile: dict, query: str,
                             candidates: list[dict]) -> list[dict]:
    if not await _check_llm():
        logger.info("LLM unavailable for search, returning keyword matches")
        return candidates[:10]

    logger.info(f"LLM search: '{query}' over {len(candidates)} candidates")
    tags_str = ", ".join(CLASSIFICATION_TAGS)

    all_scored: list[dict] = []
    batch_size = 5
    for i in range(0, min(len(candidates), 20), batch_size):
        batch = candidates[i:i + batch_size]
        articles_text = ""
        for j, art in enumerate(batch):
            title = _sanitize(art.get('title', ''))[:100]
            source = _sanitize(art.get('source', ''))
            summary = _sanitize(art.get('summary', ''))[:120]
            articles_text += f"\n[{j}] {title}\n    {source} | {summary}"

        user_msg = (
            f"USER QUERY: \"{_sanitize(query)}\"\n"
            f"Profile: {profile.get('role', 'AI/ML Professional')}, "
            f"{profile.get('years_experience', 10)}yr exp.\n"
            f"Tags: [{tags_str}]\n"
            f"\nArticles:{articles_text}\n\n"
            f"Rank these articles by how well they answer the user's query. "
            f"Return JSON array. Each element:\n"
            f'{{"index":N, "score":0.0-1.0, "tag":"one from Tags", '
            f'"problem_summary":"1 sentence: what problem this solves", '
            f'"insight":"1 sentence: how this relates to the user query"}}\n'
            f"Score 0 for irrelevant. Score high only if directly relevant to the query."
        )

        response = await _chat(user_msg, max_tokens=1500, temperature=0.2)
        if not response:
            for art in batch:
                all_scored.append(art)
            continue

        try:
            parsed = json.loads(response)
            scores = parsed if isinstance(parsed, list) else next(
                (v for v in parsed.values() if isinstance(v, list)), []
            )
            for item in scores:
                if not isinstance(item, dict):
                    continue
                idx = item.get("index", -1)
                if 0 <= idx < len(batch):
                    art_copy = dict(batch[idx])
                    art_copy["score"] = max(0.0, min(1.0, float(item.get("score", 0.3))))
                    if item.get("tag"):
                        art_copy["classification"] = item["tag"]
                    if item.get("problem_summary"):
                        art_copy["problem_summary"] = item["problem_summary"]
                    if item.get("insight"):
                        art_copy["insight"] = item["insight"]
                    all_scored.append(art_copy)
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(f"Search parse error: {e}")
            for art in batch:
                all_scored.append(art)

        if LLM_BACKEND == "groq":
            await asyncio.sleep(2.5)

    all_scored.sort(key=lambda a: a.get("score", 0), reverse=True)
    results = [a for a in all_scored if a.get("score", 0) > 0.1][:10]
    logger.info(f"Search complete: {len(results)} results for '{query}'")
    return results
