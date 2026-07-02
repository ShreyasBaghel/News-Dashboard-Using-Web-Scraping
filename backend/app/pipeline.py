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

logger = logging.getLogger(__name__)

async def run_pipeline(keyword: Optional[str] = None, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Run the end-to-end news pipeline:
    1. Check cache (unless force_refresh is True)
    2. Expand keyword(s)
    3. Fetch and deduplicate articles
    4. Scrape & Summarize articles (capped at top 8 to control processing time)
    5. Fetch, Scrape & Summarize pinned articles (capped at 5)
    6. Cache and return the results
    """
    db_keyword = keyword.lower().strip() if keyword else "default_dashboard"
    
    # 1. Check SQLite Cache
    if not force_refresh:
        cached = get_cached_results(db_keyword)
        if cached:
            logger.info(f"Returning cached pipeline results for: '{db_keyword}'")
            return cached

    logger.info(f"Running pipeline for keyword: '{db_keyword}' (force_refresh={force_refresh})")
    
    # Determine phrases/queries
    if not keyword:
        # For default dashboard, we query each of the default keywords
        phrases = settings.DEFAULT_KEYWORDS
    else:
        phrases = await expand_keyword(keyword)
        
    # 5. Fetch pinned technology articles first so we can extract their domains
    raw_pinned = await fetch_pinned_articles()
    pinned_domains = [getNormalizedDomain(art["url"]) for art in raw_pinned if art.get("url")]
    
    # 2 & 3. Fetch general news articles (start with page 1)
    page = 1
    raw_articles = await fetch_news_for_phrases(phrases, page=page)
    
    # Filter out already seen/cached general articles (7-day cache check first)
    filtered_articles = []
    seen_urls = set()
    for art in raw_articles:
        url = art.get("url")
        if url and url not in seen_urls:
            if not is_url_seen(url):
                filtered_articles.append(art)
                seen_urls.add(url)
            else:
                logger.info(f"Filtering out already seen article: {art['title']}")
                
    unique_domains = {getNormalizedDomain(art["url"]) for art in filtered_articles if art.get("url")}
    
    # Backfill logic: fetch additional pages if fewer than 5 unique-domain candidates found
    max_pages = 3
    while len(unique_domains) < 5 and page < max_pages:
        page += 1
        logger.info(f"Fewer than 5 unique-domain candidates found ({len(unique_domains)}). Attempting backfill by fetching page {page}...")
        
        additional_raw = await fetch_news_for_phrases(phrases, page=page)
        if not additional_raw:
            logger.info(f"No additional articles returned on page {page}. Stopping backfill.")
            break
            
        new_candidates_added = 0
        for art in additional_raw:
            url = art.get("url")
            if url and url not in seen_urls:
                if not is_url_seen(url):
                    filtered_articles.append(art)
                    seen_urls.add(url)
                    domain = getNormalizedDomain(url)
                    if domain:
                        unique_domains.add(domain)
                    new_candidates_added += 1
                else:
                    logger.info(f"Filtering out already seen article from page {page}: {art['title']}")
                    
        logger.info(f"Page {page} fetch added {new_candidates_added} new unique candidates. Total unique domains now: {len(unique_domains)}.")
        if new_candidates_added == 0:
            logger.info("No new unique candidates added on this page. Stopping backfill.")
            break
            
    # Apply source diversity selection to get exactly 5 dynamic articles
    raw_articles = selectDiverseArticles(filtered_articles, count=5, excludeDomains=pinned_domains)
    
    # 4. Scrape & Summarize general articles
    summarized_articles = []
    for art in raw_articles:
        url = art["url"]
        title = art["title"]
        source = art["source"]
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
