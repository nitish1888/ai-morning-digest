#!/usr/bin/env python3
"""
AI/ML Morning Digest - Entry Point
Run the web dashboard or generate a CLI digest.
"""

import argparse
import asyncio
import sys
from pathlib import Path

import yaml

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass


def load_config():
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def run_server(host: str = "0.0.0.0", port: int = 8888):
    import uvicorn
    print(f"\n  🧠 AI/ML Morning Digest")
    print(f"  ───────────────────────────────────")
    print(f"  Dashboard: http://localhost:{port}")
    print(f"  API:       http://localhost:{port}/api/articles")
    print(f"  Health:    http://localhost:{port}/api/health")
    print(f"  ───────────────────────────────────\n")
    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
        app_dir=str(Path(__file__).parent),
    )


async def run_cli_digest():
    """Print a quick CLI digest to terminal."""
    from sources import fetch_all_articles
    from scorer import RelevanceScorer

    config = load_config()
    profile = config.get("profile", {})
    digest_cfg = config.get("digest", {})

    print(f"\n  {'='*56}")
    print(f"  AI/ML MORNING DIGEST")
    print(f"  Curated for {profile.get('name', 'You')} - {profile.get('role', '')}")
    print(f"  {'='*56}\n")
    print("  Scanning sources + scoring with Gemma 4...\n")

    articles = await fetch_all_articles(config)
    scorer = RelevanceScorer(profile, digest_cfg)
    top = await scorer.rank_articles(articles, top_n=digest_cfg.get("top_n", 10))

    if not top:
        print("  No relevant articles found. Try again later.\n")
        return

    print(f"  Scanned {len(articles)} articles, picked top {len(top)}:\n")
    print(f"  {'─'*56}\n")

    for i, article in enumerate(top, 1):
        score_bar = "█" * int(article.score * 20) + "░" * (20 - int(article.score * 20))
        print(f"  #{i:2d}  [{score_bar}] {article.score:.0%}")
        print(f"       {article.title}")
        print(f"       {article.source} · {article.category}")
        print(f"       {article.url}")
        if getattr(article, "insight", ""):
            print(f"       💡 {article.insight}")
        elif article.summary:
            summary = article.summary[:120] + "..." if len(article.summary) > 120 else article.summary
            print(f"       {summary}")
        print()

    print(f"  {'─'*56}")
    print(f"  Run with --serve to launch the web dashboard\n")


def main():
    parser = argparse.ArgumentParser(
        description="AI/ML Morning Digest - Your personalized news agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                  # Quick CLI digest
  python main.py --serve          # Launch web dashboard
  python main.py --serve --port 3000
        """,
    )
    parser.add_argument("--serve", action="store_true", help="Launch the web dashboard")
    parser.add_argument("--host", default=None, help="Server host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=None, help="Server port (default: 8888)")
    args = parser.parse_args()

    config = load_config()
    server_cfg = config.get("server", {})

    if args.serve:
        run_server(
            host=args.host or server_cfg.get("host", "0.0.0.0"),
            port=args.port or server_cfg.get("port", 8888),
        )
    else:
        asyncio.run(run_cli_digest())


if __name__ == "__main__":
    main()
