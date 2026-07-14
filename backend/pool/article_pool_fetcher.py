import logging
import os
import json
from datetime import datetime, timezone
from app.services.news_fetcher import fetch_articles
from app.services.cache import is_url_seen
from app.services.diversity import getNormalizedDomain
from app.services.language_detector import is_english

logger = logging.getLogger(__name__)

def resolve_path(relative_path: str) -> str:
    """Resolve path relative to the backend base directory."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, relative_path)

async def fetch_article_pool(topics: list[str], target_total: int = 150) -> list[dict]:
    """
    Fetches articles from the configured APIs for each topic in buckets.
    Applies the 7-day de-duplication cache logic.
    """
    pool = []
    seen_pool_urls = set()
    num_topics = len(topics)
    target_per_topic = (target_total + num_topics - 1) // num_topics  # Ceil division
    
    logger.info(f"Starting article pool fetch for {num_topics} topics. Target total: {target_total}, Target per topic: {target_per_topic}")
    
    for topic in topics:
        topic_articles = []
        page = 1
        max_pages = 3
        
        logger.info(f"Fetching articles for topic bucket: '{topic}'")
        
        while len(topic_articles) < target_per_topic and page <= max_pages:
            raw_articles = await fetch_articles([topic], page=page, is_pool_generation=True)
            if not raw_articles:
                logger.info(f"No more articles found for topic '{topic}' at page {page}.")
                break
                
            new_added = 0
            for art in raw_articles:
                url = art.get("url")
                if not url or url in seen_pool_urls:
                    continue
                # Apply 7-day de-duplication cache
                if is_url_seen(url):
                    logger.debug(f"Filtering out article in 7-day cache: {art.get('title')}")
                    continue
                    
                # Filter out non-English articles
                if not is_english(art.get("title", ""), art.get("description", "") or ""):
                    logger.info(f"Skipping article from fetch_article_pool '{art.get('title')}' because it is detected as non-English.")
                    continue
                    
                # Build pooled article record
                domain = getNormalizedDomain(url)
                record = {
                    "title": art.get("title", ""),
                    "url": url,
                    "source": art.get("source", "Unknown"),
                    "source_domain": domain,
                    "description": art.get("description", "") or "",
                    "published_at": art.get("published_at", ""),
                    "topic_bucket": topic,
                    "fetched_at": datetime.now(timezone.utc).isoformat() + "Z"
                }
                topic_articles.append(record)
                seen_pool_urls.add(url)
                new_added += 1
                if len(topic_articles) >= target_per_topic:
                    break
                    
            logger.info(f"Page {page} fetched. Added {new_added} articles for topic '{topic}'. Total for topic: {len(topic_articles)}")
            page += 1
            
        pool.extend(topic_articles)
        
    logger.info(f"Article pool fetching complete. Total articles fetched: {len(pool)}")
    return pool

def save_pool_to_disk(pool: list[dict], path: str = "data/article_pool.json") -> None:
    """Saves the article pool to disk with a pool_generated_at timestamp."""
    full_path = resolve_path(path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    data = {
        "pool_generated_at": datetime.now(timezone.utc).isoformat(),
        "articles": pool
    }
    try:
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        logger.info(f"Successfully saved {len(pool)} articles to {full_path}")
    except Exception as e:
        logger.error(f"Error saving pool to {full_path}: {e}")

def load_pool_from_disk(path: str = "data/article_pool.json") -> list[dict]:
    """Loads the article pool from disk. Returns [] and logs a warning on error or missing file."""
    full_path = resolve_path(path)
    if not os.path.exists(full_path):
        logger.warning(f"Pool file not found at {full_path}. Returning empty pool.")
        return []
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("articles", [])
    except Exception as e:
        logger.warning(f"Error reading pool from {full_path}: {e}. Returning empty pool.")
        return []

def get_pool_age_hours(path: str = "data/article_pool.json") -> float | None:
    """Returns the age of the article pool in hours. Returns None if pool doesn't exist or is invalid."""
    full_path = resolve_path(path)
    if not os.path.exists(full_path):
        return None
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        gen_at_str = data.get("pool_generated_at")
        if not gen_at_str:
            return None
        if gen_at_str.endswith("Z"):
            gen_at_str = gen_at_str[:-1] + "+00:00"
        gen_at = datetime.fromisoformat(gen_at_str)
        now = datetime.now(timezone.utc)
        age = (now - gen_at).total_seconds() / 3600.0
        return age
    except Exception as e:
        logger.warning(f"Error reading pool age from {full_path}: {e}")
        return None

async def ensure_fresh_pool_on_startup(topics: list[str], target_total: int = 150, max_age_hours: int = 24) -> list[dict]:
    """Ensures a fresh pool of articles exists on server startup."""
    from pool.keyword_extractor import extract_keywords_from_pool, save_keywords_to_disk
    from datetime import timedelta
    from app.config import settings
    
    age = get_pool_age_hours()
    if age is None:
        logger.info("Pool file is missing or unreadable. Refreshing pool now...")
    elif age >= max_age_hours:
        logger.info(f"Pool is {age:.2f} hours old (stale, >= {max_age_hours}h). Refreshing pool now...")
    else:
        logger.info(f"Pool is {age:.2f} hours old (fresh, < {max_age_hours}h). Skipping refresh, loading from disk.")
        pool = load_pool_from_disk()
        return pool
        
    # Load existing articles to avoid losing them
    existing_articles = load_pool_from_disk()
    
    # Refresh pool (fetch new articles)
    new_articles = await fetch_article_pool(topics, target_total)
    
    # Merge and deduplicate by URL
    seen_urls = set()
    merged_pool = []
    
    # Prioritize new articles
    for art in new_articles:
        url = art.get("url")
        if url and url not in seen_urls:
            seen_urls.add(url)
            merged_pool.append(art)
            
    # Add existing articles if they are not expired
    ttl_days = settings.ttl_days_resolved or 7
    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
    
    skipped_count = 0
    expired_count = 0
    for art in existing_articles:
        url = art.get("url")
        if not url:
            continue
        if url in seen_urls:
            skipped_count += 1
            continue
            
        # Parse published_at or fetched_at to check expiration
        keep = True
        date_str = art.get("published_at") or art.get("fetched_at")
        if date_str:
            try:
                clean_date = date_str.replace("Z", "+00:00")
                pub_date = datetime.fromisoformat(clean_date)
                if pub_date.tzinfo is None:
                    pub_date = pub_date.replace(tzinfo=timezone.utc)
                if pub_date < cutoff:
                    keep = False
                    expired_count += 1
            except Exception:
                pass # Keep if parsing fails to be safe
                
        if keep:
            seen_urls.add(url)
            merged_pool.append(art)
            
    logger.info(f"Merged pool: new_fetched={len(new_articles)}, existing_kept={len(merged_pool)-len(new_articles)}, duplicates_skipped={skipped_count}, expired_skipped={expired_count}")
    
    save_pool_to_disk(merged_pool)
    
    # Trigger keyword extraction
    logger.info("Triggering keyword extraction on the merged pool...")
    keywords = extract_keywords_from_pool(merged_pool)
    save_keywords_to_disk(keywords)
    
    return merged_pool
