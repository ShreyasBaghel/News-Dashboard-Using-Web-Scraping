import logging
from datetime import datetime, timezone, timedelta
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
from app.services.pinned_sources import fetch_pinned_articles, _generate_mock_pinned
from app.services.diversity import getNormalizedDomain, selectDiverseArticles
from app.models import Article, DashboardPayload
from pool.article_pool_fetcher import load_pool_from_disk
from app.services.language_detector import is_english
from app.services.validator import (
    is_valid_url,
    is_valid_source_type,
    validate_content_quality,
    validate_relevance,
    validate_summary_quality
)
import random

logger = logging.getLogger(__name__)

async def process_and_validate_candidate(art: Dict[str, Any], keyword: str, is_pinned: bool = False) -> Optional[Dict[str, Any]]:
    """
    Scrapes, validates, and summarizes a candidate article.
    Returns the fully validated and summarized article dictionary, or None if validation fails.
    """
    url = art.get("url")
    title = art.get("title", "")
    desc = art.get("description", "") or ""
    
    if not url:
        return None
        
    # 1. Pre-scrape checks (URL and title/description metadata)
    url_ok, url_reason = is_valid_url(url)
    if not url_ok:
        logger.info(f"Skipping candidate '{title}' because of URL check: {url_reason}")
        return None
        
    # Pre-scrape language check on metadata
    if not is_english(title, description=desc):
        logger.info(f"Skipping candidate '{title}' because metadata is detected as non-English.")
        return None
        
    # 2. Scrape article
    try:
        scraped_text = await scrape_article(url, title)
    except Exception as e:
        logger.info(f"Skipping candidate '{title}' because scraping failed: {str(e)}")
        return None
        
    # 3. Post-scrape quality and source checks
    source_ok, source_reason = is_valid_source_type(url, title, scraped_text)
    if not source_ok:
        logger.info(f"Skipping candidate '{title}' because of source type check: {source_reason}")
        return None
        
    quality_ok, quality_reason = validate_content_quality(scraped_text)
    if not quality_ok:
        logger.info(f"Skipping candidate '{title}' because of content quality check: {quality_reason}")
        return None
        
    # Post-scrape language check on actual body text
    if not is_english(title, content=scraped_text):
        logger.info(f"Skipping candidate '{title}' after scraping because content is detected as non-English.")
        return None
        
    # 4. Relevance check
    # Skip relevance check for pinned articles, or use company name as relevance topic
    relevance_kw = art.get("company", "technology") if is_pinned else keyword
    relevance_ok, score, reason = await validate_relevance(title, desc, url, scraped_text, relevance_kw)
    if not relevance_ok:
        logger.info(f"Skipping candidate '{title}' because of relevance check ({relevance_kw}): {reason}")
        return None
        
    # 5. Summarize content
    try:
        summary = await summarize_content(title, scraped_text)
    except Exception as e:
        logger.info(f"Skipping candidate '{title}' because summarization failed: {str(e)}")
        return None
        
    # 6. Validate summary quality
    if not validate_summary_quality(summary, title):
        logger.info(f"Skipping candidate '{title}' because summary is of poor quality or placeholder: '{summary}'")
        return None
        
    # All checks passed! Return the record
    return {
        "title": title,
        "url": url,
        "source": art.get("source", getNormalizedDomain(url) or "Unknown"),
        "published_at": art.get("published_at", ""),
        "summary": summary,
        "scraped_content": scraped_text,
        "keyword": keyword if not is_pinned else art.get("company"),
        "is_pinned": is_pinned,
        "company": art.get("company") if is_pinned else None
    }

def _generate_fallback_article(keyword: str, used_urls: set) -> Dict[str, Any]:
    """Generates a high-quality mock article for last resort fallbacks."""
    url = f"https://www.industrynews-mock.com/fallback-{hash(keyword)}-{len(used_urls)}"
    kw_title = keyword.title().strip()
    if kw_title.endswith(" Industry"):
        kw_title = kw_title[:-9].strip()
    title = f"How Smart Automation and Edge Technologies are Optimizing the {kw_title} Industry"
    desc = f"An in-depth look at how {kw_title} facilities are adopting digital twins, robotics, and advanced automation."
    content = (
        f"This comprehensive report explores the ongoing transformation in the {kw_title} sector. "
        f"Industrial plants and factories are increasingly deploying edge sensors and machine learning "
        f"algorithms to monitor production lines in real time, preventing unexpected downtime and boosting safety.\n\n"
        f"Furthermore, companies are leveraging green technologies and energy-efficient kilns to reduce carbon footprints. "
        f"These strategic initiatives are driving significant cost reductions while ensuring compliance with new regulatory standards."
    )
    summary = (
        f"The {kw_title} industry is undergoing a major digital transformation driven by smart automation, digital twins, and edge computing. "
        f"These advanced technologies are helping facilities optimize their production workflows, prevent downtime, and implement eco-friendly operations."
    )
    return {
        "title": title,
        "url": url,
        "source": "Industry Insights Mock",
        "published_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "summary": summary,
        "scraped_content": content,
        "keyword": keyword,
        "is_pinned": False,
        "company": None
    }

async def run_pipeline(keyword: Optional[str] = None, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Run the end-to-end news pipeline:
    1. Check cache (unless force_refresh is True)
    2. Extract keywords
    3. Query local pool
    4. Sort or Shuffle candidates
    5. Iterate, Scrape, Validate, and Summarize until 5 dynamic articles are successfully generated.
    6. Fallback to live News APIs if pool candidates are exhausted or fail validation.
    7. Fetch, Scrape, and Validate pinned articles using round-robin representation.
    8. Cache and return the results.
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
        
    # Fetch pinned technology articles first so we can extract their domains
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
            # Check language of candidate article metadata
            if is_english(art.get("title", ""), art.get("description", "") or ""):
                pool_candidates.append(art)
            else:
                logger.info(f"Skipping pool candidate '{art.get('title')}' because metadata is detected as non-English.")
            
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
                
    # 3. Reshuffle (randomize) or Sort by date
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
        
    # Apply source diversity selection to order the candidates
    ordered_pool_candidates = selectDiverseArticles(candidates_to_select, count=len(candidates_to_select), excludeDomains=pinned_domains)
    
    # Now let's loop through candidates, scraping and validating until we have exactly 5 general articles
    summarized_articles = []
    used_domains = set()
    used_urls = set()
    
    # Pass 1: Unique domains (prefer domains not used yet)
    for art in ordered_pool_candidates:
        if len(summarized_articles) >= 5:
            break
        url = art["url"]
        domain = getNormalizedDomain(url)
        if url in used_urls or domain in used_domains:
            continue
            
        val_art = await process_and_validate_candidate(art, keyword or "Default", is_pinned=False)
        if val_art:
            summarized_articles.append(val_art)
            used_domains.add(domain)
            used_urls.add(url)
            add_seen_url(url)
            
    # Pass 2: Repeating domains (if we have less than 5)
    if len(summarized_articles) < 5:
        logger.info(f"Pool unique domains exhausted. Still need {5 - len(summarized_articles)} articles. Trying repeating domains...")
        for art in ordered_pool_candidates:
            if len(summarized_articles) >= 5:
                break
            url = art["url"]
            if url in used_urls:
                continue
                
            val_art = await process_and_validate_candidate(art, keyword or "Default", is_pinned=False)
            if val_art:
                summarized_articles.append(val_art)
                used_urls.add(url)
                add_seen_url(url)

    # 4. Fallback to live news API for shortfall
    if len(summarized_articles) < 5:
        shortfall = 5 - len(summarized_articles)
        logger.info(f"Pool only provided {len(summarized_articles)} valid articles. Attempting to fetch from live fallback...")
        
        phrases = []
        for kw in selected_keywords:
            phrases.extend(await expand_keyword(kw))
        if not phrases:
            phrases = selected_keywords
            
        # We will loop over multiple pages if needed (up to 3 pages)
        page = 1
        max_pages = 3
        while len(summarized_articles) < 5 and page <= max_pages:
            logger.info(f"Fetching page {page} of live news fallback...")
            live_raw = await fetch_news_for_phrases(phrases, page=page)
            if not live_raw:
                logger.info("No more live news articles found.")
                break
                
            # Filter live articles (must not be seen, and must be English metadata)
            filtered_live = []
            for art in live_raw:
                url = art.get("url")
                if url and url not in used_urls and not is_url_seen(url):
                    if is_english(art.get("title", ""), art.get("description", "") or ""):
                        filtered_live.append(art)
                        
            # Apply diversity sorting
            exclude_domains = list(set(pinned_domains + list(used_domains)))
            ordered_live_candidates = selectDiverseArticles(filtered_live, count=len(filtered_live), excludeDomains=exclude_domains)
            
            # Pass 1: Unique domains for live articles
            for art in ordered_live_candidates:
                if len(summarized_articles) >= 5:
                    break
                url = art["url"]
                domain = getNormalizedDomain(url)
                if url in used_urls or domain in used_domains:
                    continue
                    
                val_art = await process_and_validate_candidate(art, keyword or "Default", is_pinned=False)
                if val_art:
                    summarized_articles.append(val_art)
                    used_domains.add(domain)
                    used_urls.add(url)
                    add_seen_url(url)
                    
            # Pass 2: Repeating domains for live articles
            if len(summarized_articles) < 5:
                for art in ordered_live_candidates:
                    if len(summarized_articles) >= 5:
                        break
                    url = art["url"]
                    if url in used_urls:
                        continue
                        
                    val_art = await process_and_validate_candidate(art, keyword or "Default", is_pinned=False)
                    if val_art:
                        summarized_articles.append(val_art)
                        used_urls.add(url)
                        add_seen_url(url)
                        
            page += 1

    # 5. Last Resort Fallback (if we still have less than 5, backfill with mock articles)
    while len(summarized_articles) < 5:
        shortfall = 5 - len(summarized_articles)
        logger.info(f"Shortfall persistent after live fallback. Backfilling {shortfall} articles with high-quality generated mocks.")
        mock_art = _generate_fallback_article(keyword or "Manufacturing", used_urls)
        summarized_articles.append(mock_art)
        used_urls.add(mock_art["url"])
        add_seen_url(mock_art["url"])

    # 6. Scrape & Summarize pinned articles with round-robin selection and validation
    summarized_pinned = []
    seen_pinned_urls = set()
    companies = settings.PINNED_COMPANIES
    
    # Try to find real pinned articles first (round-robin)
    # Loop multiple times if needed to find enough candidates
    for attempt in range(5):
        if len(summarized_pinned) >= 5:
            break
        for company in companies:
            if len(summarized_pinned) >= 5:
                break
            # Find candidates for this company
            matching = [a for a in raw_pinned if a.get("company") == company and a["url"] not in seen_pinned_urls]
            if matching:
                cand = matching[0]
                seen_pinned_urls.add(cand["url"])
                val_art = await process_and_validate_candidate(cand, keyword="", is_pinned=True)
                if val_art:
                    summarized_pinned.append(val_art)
                    add_seen_url(cand["url"])
                    
    # If pinned shortfall exists, backfill with mock pinned articles
    if len(summarized_pinned) < 5:
        logger.info(f"Pinned articles shortfall ({len(summarized_pinned)}/5). Backfilling with mock pinned articles.")
        mock_candidates = _generate_mock_pinned()
        for attempt in range(5):
            if len(summarized_pinned) >= 5:
                break
            for company in companies:
                if len(summarized_pinned) >= 5:
                    break
                matching = [a for a in mock_candidates if a.get("company") == company and a["url"] not in seen_pinned_urls]
                if matching:
                    cand = matching[0]
                    seen_pinned_urls.add(cand["url"])
                    val_art = await process_and_validate_candidate(cand, keyword="", is_pinned=True)
                    if val_art:
                        summarized_pinned.append(val_art)
                        add_seen_url(cand["url"])

    # Calculate updates
    last_updated_dt = datetime.now(timezone.utc)
    next_update_dt = last_updated_dt + timedelta(hours=12)
    
    payload = {
        "keyword": keyword or "Default Dashboard",
        "articles": summarized_articles,
        "pinned_articles": summarized_pinned,
        "last_updated": last_updated_dt.isoformat().replace("+00:00", "Z"),
        "next_update": next_update_dt.isoformat().replace("+00:00", "Z")
    }
    
    # 7. Save in SQLite cache
    save_cached_results(db_keyword, payload)
    
    return payload
