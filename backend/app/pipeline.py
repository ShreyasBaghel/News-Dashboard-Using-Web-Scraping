import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import asyncio

from app.config import settings
from app.services.cache import (
    is_url_seen, add_seen_url, get_cached_results, save_cached_results
)
from app.services.phrase_builder import expand_keyword
from app.services.news_fetcher import fetch_news_for_phrases
from app.services.scraper import scrape_article
from app.services.summarizer import summarize_content
from app.services.pinned_sources import fetch_pinned_articles
from app.services.diversity import getNormalizedDomain, selectDiverseArticles
from app.models import Article, DashboardPayload
from pool.article_pool_fetcher import load_pool_from_disk
import random

logger = logging.getLogger(__name__)

async def run_pipeline(keyword: Optional[str] = None, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Run the end-to-end news pipeline:
    1. Check cache (unless force_refresh is True)
    2. Extract keywords (comma-separated if multiple)
    3. Query local pool first
    4. Reshuffle (randomize) if force_refresh is True, otherwise sort by date
    5. Filter out already seen/cached general articles (7-day cache check)
    6. Apply source diversity selection
    7. Fallback to live news API for any shortfall (scoped to shortfall)
    8. Scrape & Summarize selected general articles
    9. Fetch, Scrape & Summarize pinned articles
    10. Cache and return the results
    """
    db_keyword = keyword.lower().strip() if keyword else "default_dashboard"
    
    # 1. Check SQLite Cache
    if not force_refresh:
        cached = get_cached_results(db_keyword)
        if cached:
            logger.info(f"Returning cached pipeline results for: '{db_keyword}'")
            return cached

    logger.info(f"Running pipeline for keyword: '{db_keyword}' (force_refresh={force_refresh})")
    
    # Parse keyword into a list of single keywords (comma-separated from frontend)
    if keyword:
        selected_keywords = [k.strip().lower() for k in keyword.split(",") if k.strip()]
    else:
        selected_keywords = [k.strip().lower() for k in settings.DEFAULT_KEYWORDS if k.strip()]
        
    # 5. Fetch pinned technology articles first so we can extract their domains
    raw_pinned = await fetch_pinned_articles()
    pinned_domains = [getNormalizedDomain(art["url"]) for art in raw_pinned if art.get("url")]
    
    # 2. Query local pool
    pool_articles = load_pool_from_disk()
    
    # Filter pool for articles whose title/description contains any of the selected keywords (OR matching)
    pool_candidates = []
    for art in pool_articles:
        title = art.get("title", "").lower()
        desc = art.get("description", "").lower()
        if any(kw in title or kw in desc for kw in selected_keywords):
            pool_candidates.append(art)
            
    # Filter out already seen general articles (7-day check)
    unseen_pool_candidates = []
    seen_urls = set()
    for art in pool_candidates:
        url = art.get("url")
        if url and url not in seen_urls:
            if not is_url_seen(url):
                unseen_pool_candidates.append(art)
                seen_urls.add(url)
            else:
                logger.info(f"Filtering out already seen pool article: {art['title']}")
                
    # 6. Reshuffle (randomize) or Sort by date
    if force_refresh:
        candidates_to_select = list(unseen_pool_candidates)
        random.shuffle(candidates_to_select)
        logger.info(f"Reshuffling pool candidates for force refresh (found {len(candidates_to_select)} matched articles).")
    else:
        candidates_to_select = sorted(
            unseen_pool_candidates,
            key=lambda x: x.get("published_at", ""),
            reverse=True
        )
        logger.info(f"Sorting pool candidates by date for search (found {len(candidates_to_select)} matched articles).")
        
    # Apply source diversity selection to get up to 5 dynamic articles from the pool
    selected_articles = selectDiverseArticles(candidates_to_select, count=5, excludeDomains=pinned_domains)
    
    # 3. Fallback to live news API for shortfall
    pool_match_count = len(selected_articles)
    live_match_count = 0
    if pool_match_count < 5:
        shortfall = 5 - pool_match_count
        logger.info(f"Pool only provided {pool_match_count} diverse articles. Attempting to fetch {shortfall} from live fallback...")
        
        # Build query phrases for live fallback
        phrases = []
        for kw in selected_keywords:
            phrases.extend(await expand_keyword(kw))
        if not phrases:
            phrases = selected_keywords
            
        # Fetch page 1 of live news for these phrases
        live_raw = await fetch_news_for_phrases(phrases, page=1)
        
        # Filter live articles
        filtered_live = []
        selected_urls = {art["url"] for art in selected_articles if art.get("url")}
        for art in live_raw:
            url = art.get("url")
            if url and url not in selected_urls and url not in seen_urls:
                if not is_url_seen(url):
                    filtered_live.append(art)
                    seen_urls.add(url)
                    
        # Exclude domains from already selected articles
        selected_domains = [getNormalizedDomain(art["url"]) for art in selected_articles if art.get("url")]
        exclude_domains = list(set(pinned_domains + selected_domains))
        
        # Select diverse from the live fallback
        live_selected = selectDiverseArticles(filtered_live, count=shortfall, excludeDomains=exclude_domains)
        live_match_count = len(live_selected)
        selected_articles.extend(live_selected)
        logger.info(f"Shortfall fallback: added {live_match_count} articles from live API. Total now: {len(selected_articles)}")
        
    logger.info(f"Dynamic slots selection results -> Pool: {pool_match_count}, Live Fallback: {live_match_count}")
    
    # 4. Scrape & Summarize general articles
    summarized_articles = []
    for art in selected_articles:
        url = art["url"]
        title = art["title"]
        source = art.get("source", getNormalizedDomain(url) or "Unknown")
        pub_at = art["published_at"]
        
        logger.info(f"Processing general article: {title}")
        scraped_text = await scrape_article(url, title)
        summary = await summarize_content(title, scraped_text)
        
        # Mark url as seen to enforce the 7-day de-duplication window
        add_seen_url(url)
        
        summarized_articles.append({
            "title": title,
            "url": url,
            "source": source,
            "published_at": pub_at,
            "summary": summary,
            "scraped_content": scraped_text,
            "keyword": keyword or "Default",
            "is_pinned": False
        })
        
    # 5. Scrape & Summarize pinned articles (already fetched above)
    summarized_pinned = []
    
    for art in raw_pinned:
        url = art["url"]
        title = art["title"]
        source = art["source"]
        pub_at = art["published_at"]
        company = art["company"]
        
        logger.info(f"Processing pinned article ({company}): {title}")
        scraped_text = await scrape_article(url, title)
        summary = await summarize_content(title, scraped_text)
        
        # Pinned articles are not locked out by the 7-day de-dup window,
        # but we add them to seen so they don't show up in general feeds.
        add_seen_url(url)
        
        summarized_pinned.append({
            "title": title,
            "url": url,
            "source": source,
            "published_at": pub_at,
            "summary": summary,
            "scraped_content": scraped_text,
            "keyword": company,
            "is_pinned": True,
            "company": company
        })

    # Calculate updates
    last_updated_dt = datetime.utcnow()
    next_update_dt = last_updated_dt + timedelta(hours=12)
    
    payload = {
        "keyword": keyword or "Default Dashboard",
        "articles": summarized_articles,
        "pinned_articles": summarized_pinned,
        "last_updated": last_updated_dt.isoformat() + "Z",
        "next_update": next_update_dt.isoformat() + "Z"
    }
    
    # 6. Save in SQLite cache
    save_cached_results(db_keyword, payload)
    
    return payload
