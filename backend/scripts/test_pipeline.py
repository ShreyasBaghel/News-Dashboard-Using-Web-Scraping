import sys
import os
import argparse
import asyncio
import logging

# Ensure project root is in the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Reconfigure stdout to support UTF-8 printing in Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.database import init_db
from app.pipeline import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("test_pipeline")

async def main():
    parser = argparse.ArgumentParser(description="Test end-to-end news pipeline offline.")
    parser.add_argument(
        "--keyword", 
        type=str, 
        default=None, 
        help="Keyword to query. If omitted, runs default dashboard pipeline."
    )
    parser.add_argument(
        "--force", 
        action="store_true", 
        help="Force run pipeline, bypassing database cache."
    )
    args = parser.parse_args()

    logger.info("Initializing database...")
    init_db()

    logger.info(f"Running pipeline for keyword: '{args.keyword}' (force={args.force})...")
    try:
        payload = await run_pipeline(keyword=args.keyword, force_refresh=args.force)
        
        print("\n" + "="*80)
        print(f"PIPELINE RUN RESULTS FOR: {payload['keyword']}")
        print(f"Last Updated: {payload['last_updated']}")
        print(f"Next Update:  {payload['next_update']}")
        print("="*80)
        
        print("\n--- GENERAL ARTICLES ---")
        for i, art in enumerate(payload["articles"], 1):
            print(f"\n[{i}] {art['title']}")
            print(f"    Source: {art['source']} | Date: {art['published_at']}")
            print(f"    URL: {art['url']}")
            print(f"    Summary: {art['summary']}")
            
        print("\n--- PINNED TECHNOLOGY ARTICLES ---")
        for i, art in enumerate(payload["pinned_articles"], 1):
            print(f"\n[{i}] [{art['company']}] {art['title']}")
            print(f"    Source: {art['source']} | Date: {art['published_at']}")
            print(f"    URL: {art['url']}")
            print(f"    Summary: {art['summary']}")
            
        print("="*80 + "\n")
        logger.info("Pipeline test completed successfully.")
        
    except Exception as e:
        logger.exception("Pipeline test execution failed!")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
