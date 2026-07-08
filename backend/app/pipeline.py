import logging
import asyncio
import time
import functools
import httpx
import random
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

from app.config import settings
from app.services.cache import (
    is_url_seen, add_seen_url, get_cached_results, save_cached_results,
    save_seen_articles_to_disk, get_seen_url_cache_stats, deduplicate_articles
)
from app.services.phrase_builder import expand_keyword
from app.services.news_fetcher import fetch_news_for_phrases
from app.services.scraper import scrape_article, _scrape_cache, get_canonical_url
from pool.keyword_extractor import get_cached_keywords
from app.services.summarizer import summarize_content, _summary_cache
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
    validate_summary_quality,
    BLACKLIST_TOPICS,
    _relevance_cache
)

logger = logging.getLogger(__name__)

TARGET_ARTICLE_COUNT = 50

@functools.lru_cache(maxsize=128)
def preprocess_keyword_string(keyword: str) -> List[str]:
    """Helper to split and normalize keyword comma-separated terms with caching."""
    return [k.strip().lower() for k in keyword.split(",") if k.strip()]

def calculate_article_score(article: Dict[str, Any], keyword: str, seen_domains: set) -> float:
    """
    Computes a composite relevance/quality score for an article.
    - Recency decay score based on published date (newer is higher).
    - Keyword match strength (adds 2.0 for title matches, 0.5 for description/content/summary matches).
    - Source diversity bonus (adds 0.3 if domain has not appeared in seen_domains).
    """
    # 1. Recency
    published_at = article.get("published_at", "")
    recency_score = 0.0
    if published_at:
        try:
            # Clean string for ISO parsing
            date_str = published_at
            if date_str.endswith("Z"):
                date_str = date_str[:-1] + "+00:00"
            pub_dt = datetime.fromisoformat(date_str)
            now = datetime.now(timezone.utc)
            age_days = (now - pub_dt).total_seconds() / 86400.0
            age_days = max(0.0, age_days)
            recency_score = 1.0 / (1.0 + age_days)
        except Exception:
            recency_score = 0.5
    else:
        recency_score = 0.5
        
    # 2. Keyword Match Strength
    match_score = 0.0
    title = article.get("title", "").lower()
    desc = (article.get("description", "") or "").lower()
    summary = (article.get("summary", "") or "").lower()
    scraped = (article.get("scraped_content", "") or "").lower()
    
    # Split keyword if it contains comma-separated terms (search keyword tags)
    keywords = preprocess_keyword_string(keyword)
    for kw in keywords:
        if kw in title:
            match_score += 2.0
        if kw in desc or kw in summary or kw in scraped:
            match_score += 0.5
            
    # 3. Source Diversity Bonus
    url = article.get("url", "")
    domain = getNormalizedDomain(url)
    diversity_bonus = 0.0
    if domain and domain not in seen_domains:
        diversity_bonus = 0.3
        seen_domains.add(domain)
        
    return round(recency_score + match_score + diversity_bonus, 3)

async def process_and_validate_candidate(
    art: Dict[str, Any], 
    keyword: str, 
    is_pinned: bool = False,
    client: Optional[httpx.AsyncClient] = None,
    semaphore: Optional[asyncio.Semaphore] = None,
    stats: Optional[Dict[str, Any]] = None,
    scrape_times: Optional[List[float]] = None,
    relevance_times: Optional[List[float]] = None,
    summary_times: Optional[List[float]] = None
) -> Optional[Dict[str, Any]]:
    """
    Scrapes, validates, and summarizes a candidate article with progressive filtering.
    Returns the fully validated and summarized article dictionary, or None if validation fails.
    """
    if semaphore is None:
        semaphore = asyncio.Semaphore(12)
    if stats is None:
        stats = {
            "candidates_examined": 0, "candidates_scraped": 0, "candidates_validated": 0,
            "candidates_summarized": 0, "accepted_articles": 0, "duplicate_urls": 0,
            "non_english_metadata": 0, "non_english_content": 0, "scrape_failures": 0,
            "invalid_url": 0, "invalid_source_type": 0, "low_quality_content": 0,
            "failed_relevance_validation": 0, "failed_summary_validation": 0
        }
    if scrape_times is None:
        scrape_times = []
    if relevance_times is None:
        relevance_times = []
    if summary_times is None:
        summary_times = []

    url = art.get("url")
    title = art.get("title", "")
    desc = art.get("description", "") or ""
    
    if not url:
        return None
        
    # --- PROGRESSIVE METADATA FILTERING ---
    stats["candidates_examined"] += 1
    
    # A. Check URL
    url_ok, url_reason = is_valid_url(url)
    if not url_ok:
        logger.info(f"Skipping candidate '{title}' because of URL check: {url_reason}")
        stats["invalid_url"] += 1
        return None

    # Check seen URL deduplication
    if is_url_seen(url):
        logger.info(f"Skipping candidate '{title}' because URL has already been seen.")
        stats["duplicate_urls"] += 1
        return None
        
    # B. Pre-scrape language check on metadata
    if not is_english(title, description=desc):
        logger.info(f"Skipping candidate '{title}' because metadata is detected as non-English.")
        stats["non_english_metadata"] += 1
        return None

    # C. Pre-scrape metadata source type check (check document/changelog signatures in title)
    title_lower = title.lower()
    doc_title_keywords = [
        "api reference", "documentation", "changelog", "release notes",
        "tutorial", "how to", "getting started", "installation", "404",
        "not found", "login", "sign in", "sign up", "forgot password",
        "terms of service", "privacy policy", "pricing", "features"
    ]
    for kw in doc_title_keywords:
        if kw in title_lower:
            logger.info(f"Skipping candidate '{title}' because metadata suggests non-article content type ({kw})")
            stats["invalid_source_type"] += 1
            return None

    # D. Pre-scrape obvious blacklist topic check on metadata
    text_to_check = f"{title} {desc} {url}".lower()
    import re
    for blacklist_kw in BLACKLIST_TOPICS:
        if re.search(r'\b' + re.escape(blacklist_kw) + r'\b', text_to_check):
            logger.info(f"Skipping candidate '{title}' due to blacklisted topic in metadata: '{blacklist_kw}'")
            stats["failed_relevance_validation"] += 1
            return None
    # --- END PROGRESSIVE METADATA FILTERING ---

    # Protect concurrency with Semaphore
    async with semaphore:
        # 2. Scrape article
        stats["candidates_scraped"] += 1
        is_scrape_cached = url in _scrape_cache.cache
        
        t0 = time.perf_counter()
        try:
            scraped_text = await scrape_article(url, title, client=client)
            if not is_scrape_cached:
                scrape_times.append(time.perf_counter() - t0)
        except Exception as e:
            logger.info(f"Skipping candidate '{title}' because scraping failed: {str(e)}")
            stats["scrape_failures"] += 1
            return None
            
        # 3. Post-scrape quality and source checks
        source_ok, source_reason = is_valid_source_type(url, title, scraped_text)
        if not source_ok:
            logger.info(f"Skipping candidate '{title}' because of source type check: {source_reason}")
            stats["invalid_source_type"] += 1
            return None
            
        quality_ok, quality_reason = validate_content_quality(scraped_text)
        if not quality_ok:
            logger.info(f"Skipping candidate '{title}' because of content quality check: {quality_reason}")
            stats["low_quality_content"] += 1
            return None
            
        # Post-scrape language check on actual body text
        if not is_english(title, content=scraped_text):
            logger.info(f"Skipping candidate '{title}' after scraping because content is detected as non-English.")
            stats["non_english_content"] += 1
            return None
            
        # 4. Relevance check
        stats["candidates_validated"] += 1
        relevance_kw = art.get("company", "technology") if is_pinned else keyword
        is_relevance_cached = (url, title, relevance_kw) in _relevance_cache.cache
        
        t0 = time.perf_counter()
        relevance_ok, score, reason = await validate_relevance(title, desc, url, scraped_text, relevance_kw, client=client)
        if not is_relevance_cached:
            relevance_times.append(time.perf_counter() - t0)
            
        if not relevance_ok:
            logger.info(f"Skipping candidate '{title}' because of relevance check ({relevance_kw}): {reason}")
            stats["failed_relevance_validation"] += 1
            return None
            
        # 5. Summarize content
        stats["candidates_summarized"] += 1
        is_summary_cached = url in _summary_cache.cache
        
        t0 = time.perf_counter()
        try:
            summary = await summarize_content(title, scraped_text, client=client, url=url)
            if not is_summary_cached:
                summary_times.append(time.perf_counter() - t0)
        except Exception as e:
            logger.info(f"Skipping candidate '{title}' because summarization failed: {str(e)}")
            stats["failed_summary_validation"] += 1
            return None
            
        # 6. Validate summary quality
        if not validate_summary_quality(summary, title):
            logger.info(f"Skipping candidate '{title}' because summary is of poor quality or placeholder: '{summary}'")
            stats["failed_summary_validation"] += 1
            return None
            
        # All checks passed! Return the record
        stats["accepted_articles"] += 1
        return {
            "title": title,
            "url": url,
            "canonical_url": get_canonical_url(url),
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
    5. Iterate, Scrape, Validate, and Summarize until 50 dynamic articles are successfully generated.
    6. Fallback to live News APIs if pool candidates are exhausted or fail validation.
    7. Fetch, Scrape, and Validate pinned articles using round-robin representation.
    8. Cache and return the results.
    """
    pipeline_start_time = time.perf_counter()
    db_keyword = keyword.lower().strip() if keyword else "default_dashboard"
    
    # 1. Check SQLite Cache
    if not force_refresh:
        cached = get_cached_results(db_keyword)
        if cached:
            logger.info(f"Returning cached pipeline results for: '{db_keyword}'")
            return cached

    logger.info(f"Running pipeline for keyword: '{db_keyword}' (force_refresh={force_refresh})")
    
    # Initialize Rejection Stats and Timings
    stats = {
        "candidates_examined": 0, "candidates_scraped": 0, "candidates_validated": 0,
        "candidates_summarized": 0, "accepted_articles": 0, "duplicate_urls": 0,
        "non_english_metadata": 0, "non_english_content": 0, "scrape_failures": 0,
        "invalid_url": 0, "invalid_source_type": 0, "low_quality_content": 0,
        "failed_relevance_validation": 0, "failed_summary_validation": 0
    }
    
    scrape_times = []
    relevance_times = []
    summary_times = []
    
    # Parse keyword into a list of single keywords (comma-separated from frontend)
    if keyword:
        selected_keywords = preprocess_keyword_string(keyword)
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
                stats["non_english_metadata"] += 1
            
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
                stats["duplicate_urls"] += 1
                
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
    
    summarized_articles = []
    used_domains = set()
    used_urls = set()
    
    max_concurrency = 12
    semaphore = asyncio.Semaphore(max_concurrency)
    client_timeout = httpx.Timeout(connect=3.0, read=10.0, write=3.0, pool=5.0)
    
    try:
        async with httpx.AsyncClient(timeout=client_timeout, follow_redirects=True) as client:
            
            async def process_batch_flow(candidates_list: List[Dict[str, Any]], check_unique_domains: bool):
                """
                Helper to run validation tasks concurrently in batches, awaiting in candidate order
                and cleanly cancelling remaining tasks when the TARGET_ARTICLE_COUNT is hit.
                """
                nonlocal summarized_articles, used_domains, used_urls
                
                i = 0
                while len(summarized_articles) < TARGET_ARTICLE_COUNT and i < len(candidates_list):
                    shortfall = TARGET_ARTICLE_COUNT - len(summarized_articles)
                    SAFETY_MARGIN = 3
                    batch_size = min(max_concurrency, shortfall + SAFETY_MARGIN)
                    
                    # Slice next batch
                    batch_candidates = []
                    while len(batch_candidates) < batch_size and i < len(candidates_list):
                        cand = candidates_list[i]
                        i += 1
                        url = cand.get("url")
                        if not url or url in used_urls:
                            continue
                        domain = getNormalizedDomain(url)
                        if check_unique_domains and domain in used_domains:
                            continue
                        batch_candidates.append(cand)
                        
                    if not batch_candidates:
                        break
                        
                    # Spawn tasks concurrently
                    tasks = []
                    for cand in batch_candidates:
                        task = asyncio.create_task(
                            process_and_validate_candidate(
                                cand, 
                                keyword=keyword or "Default", 
                                is_pinned=False, 
                                client=client, 
                                semaphore=semaphore,
                                stats=stats,
                                scrape_times=scrape_times,
                                relevance_times=relevance_times,
                                summary_times=summary_times
                            )
                        )
                        tasks.append(task)
                        
                    target_reached = False
                    for idx, task in enumerate(tasks):
                        try:
                            val_art = await task
                            if val_art:
                                url = val_art["url"]
                                domain = getNormalizedDomain(url)
                                
                                # Re-verify conditions (since domain/url could be taken while tasks ran in background)
                                if url in used_urls:
                                    continue
                                if check_unique_domains and domain in used_domains:
                                    continue
                                    
                                if len(summarized_articles) < TARGET_ARTICLE_COUNT:
                                    summarized_articles.append(val_art)
                                    used_domains.add(domain)
                                    used_urls.add(url)
                                    add_seen_url(url)
                                    
                                    if len(summarized_articles) >= TARGET_ARTICLE_COUNT:
                                        target_reached = True
                                        # Cancel all remaining tasks starting from idx + 1
                                        for rem_idx in range(idx + 1, len(tasks)):
                                            tasks[rem_idx].cancel()
                                        # Await cancelled tasks to clean up resources cleanly
                                        if idx + 1 < len(tasks):
                                            await asyncio.gather(*tasks[idx+1:], return_exceptions=True)
                                        break
                        except Exception as ex:
                            logger.error(f"Task processing error: {ex}")
                            
                    if target_reached:
                        break

            # Pass 1: Unique domains (prefer domains not used yet)
            await process_batch_flow(ordered_pool_candidates, check_unique_domains=True)
            
            # Pass 2: Repeating domains (if we have less than TARGET_ARTICLE_COUNT)
            if len(summarized_articles) < TARGET_ARTICLE_COUNT:
                logger.info(f"Pool unique domains exhausted. Still need {TARGET_ARTICLE_COUNT - len(summarized_articles)} articles. Trying repeating domains...")
                await process_batch_flow(ordered_pool_candidates, check_unique_domains=False)
                
            # 4. Fallback to live news API for shortfall
            if len(summarized_articles) < TARGET_ARTICLE_COUNT:
                shortfall = TARGET_ARTICLE_COUNT - len(summarized_articles)
                logger.info(f"Pool only provided {len(summarized_articles)} valid articles. Attempting to fetch from live fallback...")
                
                phrases = []
                for kw in selected_keywords:
                    phrases.extend(await expand_keyword(kw))
                if not phrases:
                    phrases = selected_keywords
                    
                # We will loop over multiple pages if needed (up to 5 pages since target is 50)
                page = 1
                max_pages = 5
                while len(summarized_articles) < TARGET_ARTICLE_COUNT and page <= max_pages:
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
                            else:
                                stats["non_english_metadata"] += 1
                        elif url:
                            stats["duplicate_urls"] += 1
                                
                    # Apply diversity sorting
                    exclude_domains = list(set(pinned_domains + list(used_domains)))
                    ordered_live_candidates = selectDiverseArticles(filtered_live, count=len(filtered_live), excludeDomains=exclude_domains)
                    
                    # Pass 1: Unique domains for live articles
                    await process_batch_flow(ordered_live_candidates, check_unique_domains=True)
                    
                    # Pass 2: Repeating domains for live articles
                    if len(summarized_articles) < TARGET_ARTICLE_COUNT:
                        await process_batch_flow(ordered_live_candidates, check_unique_domains=False)
                                
                    page += 1
        
            # 5. Last Resort Fallback (if we still have less than TARGET_ARTICLE_COUNT, backfill with mock articles)
            while len(summarized_articles) < TARGET_ARTICLE_COUNT:
                shortfall = TARGET_ARTICLE_COUNT - len(summarized_articles)
                logger.info(f"Shortfall persistent after live fallback. Backfilling {shortfall} articles with high-quality generated mocks.")
                mock_art = _generate_fallback_article(keyword or "Manufacturing", used_urls)
                summarized_articles.append(mock_art)
                used_urls.add(mock_art["url"])
                add_seen_url(mock_art["url"])
                stats["accepted_articles"] += 1
        
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
                        val_art = await process_and_validate_candidate(
                            cand, keyword="", is_pinned=True, client=client, semaphore=semaphore,
                            stats=stats, scrape_times=scrape_times, relevance_times=relevance_times,
                            summary_times=summary_times
                        )
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
                            val_art = await process_and_validate_candidate(
                                cand, keyword="", is_pinned=True, client=client, semaphore=semaphore,
                                stats=stats, scrape_times=scrape_times, relevance_times=relevance_times,
                                summary_times=summary_times
                            )
                            if val_art:
                                summarized_pinned.append(val_art)
                                add_seen_url(cand["url"])
                                
    finally:
        # Flush the dirty seen articles to disk atomically
        save_seen_articles_to_disk()

    # Calculate relevance_score for all general articles, and sort them descending
    seen_domains_scoring = set()
    for art in summarized_articles:
        score = calculate_article_score(art, keyword or "Default", seen_domains_scoring)
        art["relevance_score"] = score
        
    # Order by relevance_score descending
    summarized_articles = sorted(
        summarized_articles,
        key=lambda x: x.get("relevance_score", 0.0),
        reverse=True
    )
    
    # Calculate relevance_score for pinned articles
    seen_domains_scoring_pinned = set()
    for art in summarized_pinned:
        score = calculate_article_score(art, art.get("company", "technology") or "technology", seen_domains_scoring_pinned)
        art["relevance_score"] = score

    # Calculate updates
    last_updated_dt = datetime.now(timezone.utc)
    next_update_dt = last_updated_dt + timedelta(hours=12)
    
    # 7. Print Performance & Statistics Summaries
    pipeline_duration = time.perf_counter() - pipeline_start_time
    avg_scrape = sum(scrape_times) / len(scrape_times) if scrape_times else 0.0
    avg_relevance = sum(relevance_times) / len(relevance_times) if relevance_times else 0.0
    avg_summary = sum(summary_times) / len(summary_times) if summary_times else 0.0
    
    seen_hits, seen_misses = get_seen_url_cache_stats()
    
    logger.info("=" * 60)
    logger.info("PIPELINE PERFORMANCE SUMMARY METRICS")
    logger.info("=" * 60)
    logger.info(f"Total Pipeline Runtime:          {pipeline_duration:.3f} seconds")
    logger.info(f"Candidates Examined:             {stats.get('candidates_examined', 0)}")
    logger.info(f"Candidates Scraped:              {stats.get('candidates_scraped', 0)}")
    logger.info(f"Candidates AI Validated:         {stats.get('candidates_validated', 0)}")
    logger.info(f"Candidates Summarized:           {stats.get('candidates_summarized', 0)}")
    logger.info(f"Accepted Articles:               {stats.get('accepted_articles', 0)}")
    logger.info("-" * 60)
    logger.info(f"Average Scrape Time:             {avg_scrape:.3f} seconds (network only)")
    logger.info(f"Average Relevance Check Time:    {avg_relevance:.3f} seconds")
    logger.info(f"Average Summarization Time:      {avg_summary:.3f} seconds")
    logger.info("=" * 60)
    logger.info("PIPELINE REJECTION REASON STATISTICS")
    logger.info("-" * 60)
    logger.info(f"Duplicate URLs:                  {stats.get('duplicate_urls', 0)}")
    logger.info(f"Non-English Metadata:            {stats.get('non_english_metadata', 0)}")
    logger.info(f"Non-English Content:             {stats.get('non_english_content', 0)}")
    logger.info(f"Invalid URLs:                    {stats.get('invalid_url', 0)}")
    logger.info(f"Scrape Failures:                 {stats.get('scrape_failures', 0)}")
    logger.info(f"Invalid Source Types:            {stats.get('invalid_source_type', 0)}")
    logger.info(f"Low Quality Content:             {stats.get('low_quality_content', 0)}")
    logger.info(f"Failed Relevance Validation:     {stats.get('failed_relevance_validation', 0)}")
    logger.info(f"Failed Summary Validation:       {stats.get('failed_summary_validation', 0)}")
    logger.info("=" * 60)
    logger.info("CACHE EFFECTIVENESS STATISTICS")
    logger.info("-" * 60)
    logger.info(f"Seen URL Cache:                  Hits={seen_hits}, Misses={seen_misses}")
    logger.info(f"Scrape Cache:                    Hits={_scrape_cache.hits}, Misses={_scrape_cache.misses}")
    logger.info(f"Relevance Cache:                 Hits={_relevance_cache.hits}, Misses={_relevance_cache.misses}")
    logger.info(f"Summary Cache:                   Hits={_summary_cache.hits}, Misses={_summary_cache.misses}")
    logger.info("=" * 60)

    # Deduplicate summarized feed
    summarized_articles = deduplicate_articles(summarized_articles)
    summarized_pinned = deduplicate_articles(summarized_pinned)
    
    # Calculate keyword counts for all cached keywords
    cached_keywords = get_cached_keywords()
    keyword_counts = {}
    if cached_keywords:
        pool_articles_full = load_pool_from_disk()
        all_source_arts = pool_articles_full + raw_pinned
        for kw in cached_keywords:
            kw_lower = kw.lower().strip()
            cnt = 0
            for art in all_source_arts:
                title_lower = art.get("title", "").lower()
                desc_lower = (art.get("description", "") or "").lower()
                if kw_lower in title_lower or kw_lower in desc_lower:
                    cnt += 1
            keyword_counts[kw] = cnt

    payload = {
        "keyword": keyword or "Default Dashboard",
        "articles": summarized_articles,
        "pinned_articles": summarized_pinned,
        "last_updated": last_updated_dt.isoformat().replace("+00:00", "Z"),
        "next_update": next_update_dt.isoformat().replace("+00:00", "Z"),
        "keyword_counts": keyword_counts
    }
    
    # 8. Save in SQLite cache
    save_cached_results(db_keyword, payload)
    
    return payload
