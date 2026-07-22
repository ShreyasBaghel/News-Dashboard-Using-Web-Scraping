# Cache Architecture Decision:
# cache.json (seen_articles) is the canonical source of truth for all article metadata, including keywords.
# MySQL article_keywords table acts as a backing store and quick lookup cache for individual article url tags.
# When building the in-memory index or counting global keywords, if cache.json lacks keywords for a URL,
# they are fetched from MySQL, merged into the in-memory cache, and written back to cache.json on next save.

import os
import hashlib
import json
from app.database import SessionLocal, CachedPipelineResult, LLMCache, ArticleKeyword, NewsdataUsage, SeenArticleHash
import logging
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, Generic, TypeVar, List
from app.config import settings

logger = logging.getLogger(__name__)

K = TypeVar('K')
V = TypeVar('V')

class TTLLRUCache(Generic[K, V]):
    """
    A thread-safe-ish (for single-threaded async event loop) bounded LRU cache 
    with expiration time (TTL).
    """
    def __init__(self, maxsize: int = 500, ttl_seconds: float = 1800):
        self.maxsize = maxsize
        self.ttl_seconds = ttl_seconds
        self.cache: OrderedDict[K, Tuple[V, float]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: K) -> Optional[V]:
        if key not in self.cache:
            self.misses += 1
            return None
        val, ts = self.cache[key]
        if time.time() - ts > self.ttl_seconds:
            del self.cache[key]
            self.misses += 1
            return None
        # Move to end to mark as recently used
        self.cache.move_to_end(key)
        self.hits += 1
        return val

    def set(self, key: K, value: V):
        now = time.time()
        if key in self.cache:
            del self.cache[key]
        elif len(self.cache) >= self.maxsize:
            # Evict LRU
            self.cache.popitem(last=False)
        self.cache[key] = (value, now)

    def clear(self):
        self.cache.clear()
        self.hits = 0
        self.misses = 0

# Seen URLs memory cache variables
_seen_urls_cache: Optional[Dict[str, Any]] = None
_seen_urls_dirty: bool = False
seen_url_hits: int = 0
seen_url_misses: int = 0

# In-memory index structures
_in_memory_keyword_index: Dict[str, List[Dict[str, Any]]] = {}
_all_cached_articles: List[Dict[str, Any]] = []


def get_newsdata_usage(date_str: str) -> int:
    with SessionLocal() as db:
        entry = db.query(NewsdataUsage).filter(NewsdataUsage.date == date_str).first()
        if entry:
            return entry.request_count
        return 0


def increment_newsdata_usage(date_str: str):
    with SessionLocal() as db:
        entry = db.query(NewsdataUsage).filter(NewsdataUsage.date == date_str).first()
        if entry:
            entry.request_count += 1
        else:
            db.add(NewsdataUsage(date=date_str, request_count=1))
        db.commit()


def migrate_caches():
    """
    Ensure every article record in cache.json and seen_articles.json consistently stores:
    title, url, published_at, and cache timestamp(s) where applicable.
    """
    logger.info("Starting cache schema migration check...")
    
    # We will migrate both files if they exist and are distinct
    files_to_migrate = set()
    if settings.cache_path_resolved:
        files_to_migrate.add(os.path.abspath(settings.cache_path_resolved))
    if settings.SEEN_ARTICLES_JSON_PATH:
        files_to_migrate.add(os.path.abspath(settings.SEEN_ARTICLES_JSON_PATH))
    
    # Pre-load all known URL metadata from all files to find matching titles/published_at
    url_metadata = {}
    
    # Phase 1: Scan and collect metadata from all files
    for file_path in files_to_migrate:
        if not os.path.exists(file_path):
            continue
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for key, entry in data.items():
                    if isinstance(entry, dict) and entry.get("url"):
                        url = entry["url"].strip()
                        title = entry.get("title")
                        pub = entry.get("published_at")
                        if title or pub:
                            if url not in url_metadata:
                                url_metadata[url] = {}
                            if title:
                                url_metadata[url]["title"] = title
                            if pub:
                                url_metadata[url]["published_at"] = pub
        except Exception as e:
            logger.error(f"Error scanning file {file_path} for migration: {e}")
            
    # Phase 2: Perform migration on each file
    for file_path in files_to_migrate:
        if not os.path.exists(file_path):
            continue
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if not isinstance(data, dict):
                continue
                
            migrated = False
            for key, entry in data.items():
                if not isinstance(entry, dict) or not entry.get("url"):
                    continue
                url = entry["url"].strip()
                
                # Check for missing keys
                if "title" not in entry or not entry.get("title") or "published_at" not in entry or not entry.get("published_at"):
                    # Try to populate from collected metadata
                    title = entry.get("title") or url_metadata.get(url, {}).get("title")
                    published_at = entry.get("published_at") or url_metadata.get(url, {}).get("published_at")
                    
                    # Heuristics if still missing
                    if not title:
                        parts = [p for p in url.split("/") if p]
                        if parts:
                            last_part = parts[-1].split("?")[0]
                            for ext in [".html", ".htm", ".shtml", ".php", ".aspx"]:
                                if last_part.endswith(ext):
                                    last_part = last_part[:-len(ext)]
                            title = last_part.replace("-", " ").replace("_", " ").strip().title()
                        if not title:
                            title = "URL Article"
                            
                    if not published_at:
                        added_at = entry.get("added_at")
                        if added_at:
                            published_at = added_at
                        else:
                            published_at = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                            
                    entry["title"] = title
                    entry["published_at"] = published_at
                    migrated = True
            
            if migrated:
                tmp_path = file_path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)
                if os.path.exists(file_path):
                    os.remove(file_path)
                os.rename(tmp_path, file_path)
                logger.info(f"Successfully migrated cache schema for {file_path}")
        except Exception as e:
            logger.error(f"Failed to migrate cache file {file_path}: {e}")
            
    logger.info("Cache schema migration check finished.")

def get_cached_llm_insights(cache_key: str) -> Optional[Dict[str, Any]]:
    if not settings.LLM_CACHE_ENABLED:
        return None
    with SessionLocal() as db:
        entry = db.query(LLMCache).filter(LLMCache.cache_key == cache_key).first()
        if entry:
            return json.loads(entry.payload)
        return None


def save_cached_llm_insights(cache_key: str, payload: Dict[str, Any]):
    if not settings.LLM_CACHE_ENABLED:
        return
    with SessionLocal() as db:
        existing = db.query(LLMCache).filter(LLMCache.cache_key == cache_key).first()
        payload_str = json.dumps(payload)
        if existing:
            existing.payload = payload_str
        else:
            db.add(LLMCache(cache_key=cache_key, payload=payload_str))
        db.commit()


def is_stale_fallback_keywords(url: str, keywords: List[str]) -> bool:
    """
    Checks if a list of keywords is a stale placeholder or title-split fallback.
    """
    if not keywords:
        return True
        
    keywords_lower = [k.lower().strip() for k in keywords if k.strip()]
    if not keywords_lower:
        return True

    # 1. Check placeholders
    placeholders = {
        "manufacturing", "industrial technology", "general", "automation", 
        "industry insights", "general topic"
    }
    
    # Check if they match exact placeholder lists
    placeholder_lists = [
        ["manufacturing", "industrial technology", "general"],
        ["manufacturing", "automation", "industry insights"],
        ["manufacturing", "industrial technology", "automation", "ai", "cement industry"]
    ]
    
    # If the set of keywords is a subset of standard fallbacks or contains placeholder terms
    if any(all(k in pl for k in keywords_lower) for pl in placeholder_lists):
        return True
        
    if all(k in placeholders for k in keywords_lower):
        return True

    # 2. Check title-word fallback (if title is available in seen articles cache)
    url_hash = _get_url_hash(url)
    entry = _load_seen_articles().get(url_hash)
    title = entry.get("title") if entry else None
    
    if title:
        title_clean = title.lower()
        title_words = [w.strip(".,;:!?()[]{}'\"-").lower() for w in title_clean.split() if w.strip(".,;:!?()[]{}'\"-")]
        
        # Stopwords + forbidden terms
        forbidden = {
            "news", "article", "update", "latest", "report", "today", "technology", "business", "company", "information",
            "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "as", "at", "be",
            "because", "been", "before", "being", "below", "between", "both", "but", "by", "for", "from", "in", "into",
            "is", "it", "its", "of", "on", "or", "that", "the", "this", "to", "with"
        }
        title_words_no_stop = [w for w in title_words if w not in forbidden]
        
        # If all keywords are single words and appear in the title
        if all(len(k.split()) == 1 for k in keywords_lower):
            # If they are exactly the first few non-stopwords of the title
            first_cands = title_words_no_stop[:len(keywords_lower)]
            if keywords_lower == first_cands:
                return True
                
            # If they are a subset of the first 5 words of the title
            if all(k in title_words[:5] for k in keywords_lower):
                return True
                
    return False

def get_cached_keywords_for_article(url: str) -> Optional[List[str]]:
    with SessionLocal() as db:
        entry = db.query(ArticleKeyword).filter(ArticleKeyword.url == url.strip()).first()
        if entry:
            return json.loads(entry.keywords)
        return None


def save_cached_keywords_for_article(url: str, keywords: List[str]):
    save_keywords_for_article(url, keywords)


def get_smart_cached_tags(url: str, current_title: str, current_summary: str) -> Optional[List[str]]:
    with SessionLocal() as db:
        entry = db.query(ArticleKeyword).filter(ArticleKeyword.url == url.strip()).first()
        if not entry:
            return None
        
        cached_title = entry.title or ""
        cached_summary = entry.summary or ""
        
        if not are_titles_similar(current_title, cached_title):
            logger.info(f"Smart cache miss (title mismatch) for {url}")
            return None
            
        current_summary_hash = get_content_hash(current_summary)
        cached_summary_hash = get_content_hash(cached_summary)
        
        if current_summary_hash != cached_summary_hash:
            logger.info(f"Smart cache miss (summary mismatch) for {url}")
            return None
            
        return json.loads(entry.keywords)


def save_smart_cached_tags(url: str, keywords: List[str], title: str = "", summary: str = ""):
    save_keywords_for_article(url, keywords, title, summary)


def cleanup_stale_keywords_in_cache():
    try:
        articles_data = _load_seen_articles()
        cleaned_urls = []
        for url_hash, entry in articles_data.items():
            if isinstance(entry, dict) and "keywords" in entry:
                url = entry.get("url", "")
                if is_stale_fallback_keywords(url, entry["keywords"]):
                    entry["keywords"] = []
                    cleaned_urls.append(url)
        save_seen_articles_to_disk()
        logger.info(f"Cleaned stale keywords for {len(cleaned_urls)} articles in cache.json.")
    except Exception as e:
        logger.error(f"Error during cache.json stale keywords cleanup: {e}")
    try:
        with SessionLocal() as db:
            rows = db.query(ArticleKeyword).all()
            urls_to_delete = []
            for r in rows:
                try:
                    kws = json.loads(r.keywords)
                    if is_stale_fallback_keywords(r.url, kws):
                        urls_to_delete.append(r.url)
                except Exception:
                    urls_to_delete.append(r.url)
            
            if urls_to_delete:
                db.query(ArticleKeyword).filter(ArticleKeyword.url.in_(urls_to_delete)).delete(synchronize_session=False)
                db.commit()
                logger.info(f"Successfully pruned {len(urls_to_delete)} stale/placeholder entries from database.")
            else:
                logger.info("No stale fallback/placeholder keywords found in database.")
    except Exception as e:
        logger.error(f"Error during database keywords cache pruning: {e}")


def get_all_aggregated_keywords() -> List[str]:
    with SessionLocal() as db:
        rows = db.query(ArticleKeyword).all()
        all_kws = set()
        for r in rows:
            try:
                kws = json.loads(r.keywords)
                for k in kws:
                    if k.strip():
                        all_kws.add(k.strip())
            except Exception:
                pass
        return sorted(list(all_kws))


def _get_url_hash(url: str) -> str:
    """Generate a SHA-256 hash for a given URL to use as index."""
    return hashlib.sha256(url.strip().encode('utf-8')).hexdigest()

def _load_seen_articles() -> Dict[str, Any]:
    """Load the seen articles dictionary from the JSON file or memory cache."""
    global _seen_urls_cache
    if _seen_urls_cache is not None:
        return _seen_urls_cache
        
    if not os.path.exists(settings.cache_path_resolved):
        _seen_urls_cache = {}
        return _seen_urls_cache
    try:
        with open(settings.cache_path_resolved, "r", encoding="utf-8") as f:
            _seen_urls_cache = json.load(f)
    except Exception:
        _seen_urls_cache = {}
    return _seen_urls_cache

def _save_seen_articles(data: Dict[str, Any]):
    """Update the seen articles memory cache and mark dirty."""
    global _seen_urls_cache, _seen_urls_dirty
    _seen_urls_cache = data
    _seen_urls_dirty = True

def save_seen_articles_to_disk():
    """Atomically save the dirty seen articles to the JSON file on disk."""
    global _seen_urls_cache, _seen_urls_dirty
    if not _seen_urls_dirty or _seen_urls_cache is None:
        return
    try:
        tmp_path = settings.cache_path_resolved + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(_seen_urls_cache, f, indent=4)
        if os.path.exists(settings.cache_path_resolved):
            os.remove(settings.cache_path_resolved)
        os.rename(tmp_path, settings.cache_path_resolved)
        _seen_urls_dirty = False
        logger.info("Successfully flushed seen articles cache to disk.")
    except Exception as e:
        logger.error(f"Error saving seen articles to cache: {str(e)}")
        
    # Phase 4 Deduplication cleanup
    cleanup_expired_hashes()

def is_url_seen(url: str) -> bool:
    """
    Check if a URL was seen in the last TTL_DAYS.
    Prunes expired entries first.
    """
    global seen_url_hits, seen_url_misses
    prune_old_urls()
    
    url_hash = _get_url_hash(url)
    data = _load_seen_articles()
    if url_hash in data:
        seen_url_hits += 1
        return True
    else:
        seen_url_misses += 1
        return False

def add_seen_url(url: str, title: Optional[str] = None, published_at: Optional[str] = None):
    """Mark a URL as seen in the memory cache, storing title and published_at for schema completeness."""
    url_hash = _get_url_hash(url)
    data = _load_seen_articles()
    if url_hash not in data:
        data[url_hash] = {
            "url": url.strip(),
            "added_at": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            "title": title or "",
            "published_at": published_at or ""
        }
        _save_seen_articles(data)
    else:
        # Backward compatibility: populate missing fields in existing entries
        entry = data[url_hash]
        updated = False
        if title and not entry.get("title"):
            entry["title"] = title
            updated = True
        if published_at and not entry.get("published_at"):
            entry["published_at"] = published_at
            updated = True
        if updated:
            _save_seen_articles(data)

def cache_article(article: Dict[str, Any]):
    """Save/update the full article metadata in the cache.json store."""
    url = article.get("url")
    if not url:
        return
    url_hash = _get_url_hash(url)
    data = _load_seen_articles()
    
    # Preserve original added_at timestamp if present
    added_at = data.get(url_hash, {}).get("added_at") or datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    keywords = article.get("keywords") or []
    if not keywords:
        logger.warning(f"Caching article {url} with empty keywords.")
    
    data[url_hash] = {
        "url": url.strip(),
        "added_at": added_at,
        "title": article.get("title") or "",
        "summary": article.get("summary") or "",
        "keywords": keywords,
        # Store metadata for full object reconstruction
        "source": article.get("source") or "Unknown",
        "published_at": article.get("published_at") or "",
        "is_pinned": article.get("is_pinned", False),
        "relevance_score": article.get("relevance_score") or 0.0,
        "company": article.get("company"),
        "scraped_content": article.get("scraped_content") or "",
        "validation_relevance_score": article.get("validation_relevance_score") or 0.0,
        "llm_insights": article.get("llm_insights")
    }
    _save_seen_articles(data)

def get_seen_url_cache_stats() -> Tuple[int, int]:
    """Return seen URL cache hits and misses."""
    global seen_url_hits, seen_url_misses
    return seen_url_hits, seen_url_misses

def prune_old_urls():
    """Delete entries older than settings.ttl_days_resolved in memory cache."""
    cutoff = datetime.utcnow() - timedelta(days=settings.ttl_days_resolved)
    data = _load_seen_articles()
    
    updated_data = {}
    changed = False
    for url_hash, entry in data.items():
        try:
            added_at_dt = datetime.strptime(entry["added_at"], '%Y-%m-%d %H:%M:%S')
            if added_at_dt >= cutoff:
                updated_data[url_hash] = entry
            else:
                changed = True
        except Exception:
            changed = True
            
    if changed:
        _save_seen_articles(updated_data)

def get_cached_results(keyword: str) -> Optional[Dict[str, Any]]:
    with SessionLocal() as db:
        entry = db.query(CachedPipelineResult).filter(CachedPipelineResult.keyword == keyword).first()
        if entry:
            return json.loads(entry.payload)
        return None


def save_cached_results(keyword: str, payload: Dict[str, Any], session=None):
    payload_str = json.dumps(payload)
    if session:
        existing = session.query(CachedPipelineResult).filter(CachedPipelineResult.keyword == keyword).first()
        if existing:
            existing.payload = payload_str
        else:
            session.add(CachedPipelineResult(keyword=keyword, payload=payload_str))
    else:
        with SessionLocal() as db:
            existing = db.query(CachedPipelineResult).filter(CachedPipelineResult.keyword == keyword).first()
            if existing:
                existing.payload = payload_str
            else:
                db.add(CachedPipelineResult(keyword=keyword, payload=payload_str))
            db.commit()


def load_cache() -> Dict[str, Any]:
    """Load the seen articles dictionary from the JSON file."""
    return _load_seen_articles()

def save_cache(data: Dict[str, Any]):
    """Save the seen articles dictionary to the JSON file."""
    _save_seen_articles(data)

def is_cached(url: str) -> bool:
    """Check if a URL was seen in the last TTL_DAYS."""
    return is_url_seen(url)

def mark_seen(url: str):
    """Mark a URL as seen in the JSON file."""
    add_seen_url(url)

def purge_older_than(days: int = None):
    """Delete entries older than specified days (default settings.ttl_days_resolved)."""
    cutoff_days = days if days is not None else settings.ttl_days_resolved
    cutoff = datetime.utcnow() - timedelta(days=cutoff_days)
    data = _load_seen_articles()
    
    updated_data = {}
    changed = False
    for url_hash, entry in data.items():
        try:
            added_at_dt = datetime.strptime(entry["added_at"], '%Y-%m-%d %H:%M:%S')
            if added_at_dt >= cutoff:
                updated_data[url_hash] = entry
            else:
                changed = True
        except Exception:
            changed = True
            
    if changed:
        _save_seen_articles(updated_data)

# Layered Deduplication Helper Functions
import re
from difflib import SequenceMatcher
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

def normalize_url(url: str) -> str:
    if not url:
        return ""
    url = url.strip().lower()
    if url.startswith("http://"):
        url = "https://" + url[7:]
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme
        netloc = parsed.netloc
        path = parsed.path
        if path.endswith("/"):
            path = path.rstrip("/")
            
        ignored_params = {
            'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
            'fbclid', 'gclid', 'yclid', 'mc_cid', 'mc_eid', 'sessionid', 'sid',
            'jsessionid', 'phpsessid', 'aspsessionid'
        }
        query_params = parse_qsl(parsed.query)
        filtered_query = [(k, v) for k, v in query_params if k not in ignored_params]
        filtered_query.sort()
        
        new_query = urlencode(filtered_query)
        normalized = urlunparse((scheme, netloc, path, parsed.params, new_query, ""))
        return normalized
    except Exception:
        return url

def normalize_title(title: str) -> str:
    """Normalize title: lowercase, strip punctuation and extra whitespace."""
    if not title:
        return ""
    # Lowercase
    t = title.lower()
    # Remove punctuation
    t = re.sub(r'[^\w\s]', '', t)
    # Remove extra whitespace
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def get_hash(content: str) -> str:
    if not content:
        return ""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def is_hash_seen(url_hash: str) -> bool:
    with SessionLocal() as db:
        return db.query(SeenArticleHash).filter(SeenArticleHash.url_hash == url_hash).first() is not None


def mark_hash_seen(url_hash: str):
    with SessionLocal() as db:
        existing = db.query(SeenArticleHash).filter(SeenArticleHash.url_hash == url_hash).first()
        if not existing:
            db.add(SeenArticleHash(url_hash=url_hash))
            try:
                db.commit()
            except Exception as e:
                logger.warning(f"Failed to mark hash seen (maybe a race condition): {e}")
                db.rollback()


def cleanup_expired_hashes():
    from datetime import datetime, timedelta
    try:
        with SessionLocal() as db:
            cutoff = datetime.utcnow() - timedelta(days=3)
            db.query(SeenArticleHash).filter(SeenArticleHash.created_at < cutoff).delete(synchronize_session=False)
            db.commit()
    except Exception as e:
        logger.error(f"Error cleaning up expired hashes: {e}")


def are_titles_similar(t1: str, t2: str) -> bool:
    s1 = re.sub(r'\W+', '', t1.lower())
    s2 = re.sub(r'\W+', '', t2.lower())
    if not s1 or not s2:
        return False
    if s1 == s2:
        return True
    return SequenceMatcher(None, s1, s2).ratio() >= 0.95

def get_content_hash(content: str) -> str:
    if not content:
        return ""
    clean = re.sub(r'\W+', '', content.lower())
    prefix = clean[:400]
    return hashlib.sha256(prefix.encode('utf-8')).hexdigest()

def get_article_quality_score(art: dict) -> float:
    is_pinned = art.get("is_pinned", False)
    is_mock = "-mock.com" in art.get("url", "")
    content_len = len(art.get("scraped_content", "") or "")
    summary_len = len(art.get("summary", "") or "")
    relevance_score = art.get("relevance_score", 0.0) or 0.0
    
    score = 0.0
    if is_pinned:
        score += 1000000.0
    if not is_mock:
        score += 10000.0
    score += content_len * 0.1
    score += summary_len * 0.5
    score += relevance_score * 10.0
    return score

def deduplicate_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # De-duplicate a list of article dicts based on the layered strategy
    sorted_arts = sorted(articles, key=get_article_quality_score, reverse=True)
    
    unique_articles = []
    seen_canonicals = set()
    seen_normalized_urls = set()
    seen_titles = []
    seen_content_hashes = set()
    
    for art in sorted_arts:
        url = art.get("url", "")
        canonical = art.get("canonical_url", "")
        title = art.get("title", "")
        content = art.get("scraped_content", "") or ""
        
        # Priority 1: Canonical URL
        if canonical:
            norm_canonical = normalize_url(canonical)
            if norm_canonical in seen_canonicals:
                logger.info(f"Deduplicated by Canonical URL: '{title}' ({url})")
                continue
                
        # Priority 2: Normalized URL
        norm_url = normalize_url(url)
        if norm_url in seen_normalized_urls:
            logger.info(f"Deduplicated by Normalized URL: '{title}' ({url})")
            continue
            
        # Priority 3: Title similarity (>=95%)
        is_dup_title = False
        for seen_t in seen_titles:
            if are_titles_similar(title, seen_t):
                is_dup_title = True
                break
        if is_dup_title:
            logger.info(f"Deduplicated by Title Similarity: '{title}' ({url})")
            continue
            
        # Priority 4: Normalized content hash
        c_hash = get_content_hash(content)
        if c_hash and c_hash in seen_content_hashes:
            logger.info(f"Deduplicated by Content Hash: '{title}' ({url})")
            continue
            
        # If we passed all, we keep the article!
        unique_articles.append(art)
        if canonical:
            seen_canonicals.add(normalize_url(canonical))
        seen_normalized_urls.add(norm_url)
        seen_titles.append(title)
        if c_hash:
            seen_content_hashes.add(c_hash)
            
    # Restore original order
    url_to_index = {art["url"]: idx for idx, art in enumerate(articles)}
    unique_articles.sort(key=lambda x: url_to_index.get(x["url"], 999999))
    return unique_articles

def is_duplicate_of_any(art: Dict[str, Any], list_of_arts: List[Dict[str, Any]]) -> bool:
    url = art.get("url", "")
    canonical = art.get("canonical_url", "")
    title = art.get("title", "")
    content = art.get("scraped_content", "") or ""
    
    norm_url = normalize_url(url)
    norm_canonical = normalize_url(canonical) if canonical else ""
    
    for other in list_of_arts:
        other_url = other.get("url", "")
        other_canonical = other.get("canonical_url", "")
        other_title = other.get("title", "")
        other_content = other.get("scraped_content", "") or ""
        
        # Priority 1: Canonical URL
        if norm_canonical and other_canonical:
            if norm_canonical == normalize_url(other_canonical):
                return True
                
        # Priority 2: Normalized URL
        if norm_url == normalize_url(other_url):
            return True
            
        # Priority 3: Title similarity
        if are_titles_similar(title, other_title):
            return True
            
        # Priority 4: Content hash
        h1 = get_content_hash(content)
        h2 = get_content_hash(other_content)
        if h1 and h2 and h1 == h2:
            return True
            
    return False

# In-Memory Keyword Search Index Implementations
def build_in_memory_index():
    global _in_memory_keyword_index, _all_cached_articles, _seen_urls_dirty
    logger.info("Building in-memory keyword index from cache.json...")
    try:
        articles_data = _load_seen_articles()
        
        articles = []
        for entry in articles_data.values():
            if isinstance(entry, dict) and "title" in entry:
                articles.append(entry)
                
        # Sort by date (newest first)
        articles.sort(key=lambda x: x.get("published_at") or x.get("added_at") or "", reverse=True)
        _all_cached_articles = articles
        
        # Second pass: query all (url, keywords) rows from article_keywords in database
        with SessionLocal() as db:
            rows = db.query(ArticleKeyword).all()
            db_lookup = {}
            for r in rows:
                try:
                    db_lookup[r.url] = json.loads(r.keywords)
                except Exception:
                    pass
        
        merged_any = False
        for art in _all_cached_articles:
            url = art.get("url")
            if url:
                keywords = art.get("keywords")
                if not keywords: # empty or missing
                    db_kws = db_lookup.get(url)
                    if db_kws:
                        art["keywords"] = db_kws
                        url_hash = _get_url_hash(url)
                        if url_hash in articles_data:
                            articles_data[url_hash]["keywords"] = db_kws
                        _seen_urls_dirty = True
                        merged_any = True
                        
        new_index = {}
        for art in _all_cached_articles:
            keywords = art.get("keywords") or []
            for kw in keywords:
                kw_clean = kw.strip().lower()
                if kw_clean:
                    if kw_clean not in new_index:
                        new_index[kw_clean] = []
                    if art not in new_index[kw_clean]:
                        new_index[kw_clean].append(art)
                        
        _in_memory_keyword_index = new_index
        logger.info(f"In-memory index successfully built: {len(_all_cached_articles)} articles, {len(_in_memory_keyword_index)} unique keywords.")
        
        # Save seen articles if merged any to ensure persistence
        if merged_any:
            save_seen_articles_to_disk()
            
    except Exception as e:
        logger.error(f"Failed to build in-memory keyword index: {e}")

def get_global_keyword_counts() -> Dict[str, int]:
    """Aggregate keywords from all articles in cache.json and merge with MySQL."""
    counts = {}
    try:
        articles_data = _load_seen_articles()
        
        # Fetch keywords from database as a lookup
        with SessionLocal() as db:
            rows = db.query(ArticleKeyword).all()
            db_lookup = {}
            for r in rows:
                try:
                    db_lookup[r.url] = json.loads(r.keywords)
                except Exception:
                    pass
        
        for entry in articles_data.values():
            if isinstance(entry, dict) and "title" in entry:
                kws = entry.get("keywords") or []
                url = entry.get("url")
                if not kws and url in db_lookup:
                    kws = db_lookup[url]
                for kw in kws:
                    kw_clean = kw.strip()
                    if kw_clean:
                        display_kw = kw_clean
                        if display_kw.islower():
                            if display_kw == "ai":
                                display_kw = "AI"
                            else:
                                display_kw = display_kw.title()
                        counts[display_kw] = counts.get(display_kw, 0) + 1
    except Exception as e:
        logger.error(f"Error gathering global keyword counts: {e}")
        
    # Sort them by frequency descending, then alphabetically
    sorted_kws = sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))
    return {kw: cnt for kw, cnt in sorted_kws}

def search_cache_by_keyword(keyword: str) -> List[Dict[str, Any]]:
    """Instant search using in-memory index or fallback string matching."""
    if not keyword:
        return _all_cached_articles
        
    kw_lower = keyword.lower().strip()
    
    # 1. Try exact keyword match
    if kw_lower in _in_memory_keyword_index:
        return _in_memory_keyword_index[kw_lower]
        
    # 2. Try partial match on keywords
    matched_articles = []
    seen_urls = set()
    for indexed_kw, arts in _in_memory_keyword_index.items():
        if kw_lower in indexed_kw or indexed_kw in kw_lower:
            for art in arts:
                if art["url"] not in seen_urls:
                    matched_articles.append(art)
                    seen_urls.add(art["url"])
                    
    # 3. Fallback to title/summary substring matching
    if len(matched_articles) < 5:
        for art in _all_cached_articles:
            if art["url"] not in seen_urls:
                title = art.get("title", "").lower()
                summary = art.get("summary", "").lower()
                if kw_lower in title or kw_lower in summary:
                    matched_articles.append(art)
                    seen_urls.add(art["url"])
                    
    return matched_articles
