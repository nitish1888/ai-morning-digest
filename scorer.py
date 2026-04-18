"""
Hybrid relevance scoring: keyword-based + Gemma 4 LLM intelligence.
Uses fast keyword matching as a first pass, then Gemma 4 for deep scoring & insights.
"""

import asyncio
import math
import re
from datetime import datetime, timezone

from sources import Article
from llm import score_articles_with_gemma


def _match_keywords(text: str, keywords: list[str]) -> tuple[int, list[str]]:
    text_lower = text.lower()
    matched = [kw for kw in keywords if kw.lower() in text_lower]
    return len(matched), matched


class RelevanceScorer:
    def __init__(self, profile: dict, digest_config: dict):
        self.profile = profile
        self.category_boost = digest_config.get("category_boost", {})
        self.interest_weights = {
            "primary": (profile.get("primary_interests", []), 1.0),
            "cutting_edge": (profile.get("cutting_edge_interests", []), 0.92),
            "architecture": (profile.get("architecture_interests", []), 0.85),
            "data_science": (profile.get("data_science_interests", []), 0.65),
        }
        self.negative_keywords = profile.get("negative_keywords", [])

    def _keyword_score(self, article: Article) -> float:
        """Fast keyword-based relevance score (0 to 1)."""
        searchable = f"{article.title} {article.summary} {' '.join(article.tags)}"

        keyword_score = 0.0
        total_matched = 0
        for _, (keywords, weight) in self.interest_weights.items():
            count, _ = _match_keywords(searchable, keywords)
            keyword_score += count * weight
            total_matched += count

        if total_matched == 0:
            return 0.0

        keyword_score = min(keyword_score, 8.0)
        normalized = keyword_score / 8.0

        neg_count, _ = _match_keywords(searchable, self.negative_keywords)
        if neg_count > 0:
            normalized *= max(0.1, 1.0 - (neg_count * 0.4))

        freshness = 0.75
        if article.published:
            hours_old = (datetime.now(timezone.utc) - article.published).total_seconds() / 3600
            freshness = max(0.5, 1.0 - (hours_old / 72.0))

        cat_boost = self.category_boost.get(article.category, 1.0)
        priority_boost = 1.15 if article.priority_source else 1.0

        hn_boost = 1.0
        if article.hn_points > 0:
            hn_boost = 1.0 + min(0.3, math.log10(max(1, article.hn_points)) / 10)

        substance = min(1.0, len(article.summary) / 300) * 0.1 + 0.9

        return round(min(1.0, (
            normalized * 0.55 + freshness * 0.25 + substance * 0.20
        ) * cat_boost * priority_boost * hn_boost), 4)

    async def rank_articles(self, articles: list[Article], top_n: int = 10) -> list[Article]:
        """
        Two-pass ranking:
        1. Fast keyword scoring to shortlist candidates
        2. Gemma 4 deep scoring for top candidates + insight generation
        """
        # Pass 1: keyword scoring
        for article in articles:
            article.score = self._keyword_score(article)

        candidates = [a for a in articles if a.score > 0.05]
        candidates.sort(key=lambda a: a.score, reverse=True)

        # Take top ~30 candidates for LLM scoring
        shortlist = candidates[:max(top_n * 3, 30)]

        # Pass 2: Gemma 4 deep scoring
        article_dicts = [a.to_dict() for a in shortlist]
        enriched = await score_articles_with_gemma(self.profile, article_dicts)

        for i, article in enumerate(shortlist):
            if i < len(enriched) and "llm_score" in enriched[i]:
                llm_score = enriched[i]["llm_score"]
                article.score = round(article.score * 0.4 + llm_score * 0.6, 4)
                if enriched[i].get("insight"):
                    article.insight = enriched[i]["insight"]
                if enriched[i].get("classification"):
                    article.classification = enriched[i]["classification"]
                if enriched[i].get("problem_summary"):
                    article.problem_summary = enriched[i]["problem_summary"]

        shortlist.sort(key=lambda a: a.score, reverse=True)

        # Ensure source diversity: max 3 from same source
        final = []
        source_counts: dict[str, int] = {}
        for article in shortlist:
            src = article.source
            if source_counts.get(src, 0) >= 3:
                continue
            final.append(article)
            source_counts[src] = source_counts.get(src, 0) + 1
            if len(final) >= top_n:
                break

        return final
