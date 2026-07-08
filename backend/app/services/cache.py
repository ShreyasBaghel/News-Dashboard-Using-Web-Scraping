import os
import sqlite3
import hashlib
import json
import logging
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, Generic, TypeVar
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

def get_db_connection():
    conn = sqlite3.connect(settings.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database tables for article de-duplication and pipeline caching."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Table for storing compiled JSON payloads per search query/keyword
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cached_pipeline_results (
            keyword TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()

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

def add_seen_url(url: str):
    """Mark a URL as seen in the memory cache."""
    url_hash = _get_url_hash(url)
    data = _load_seen_articles()
    if url_hash not in data:
        data[url_hash] = {
            "url": url.strip(),
            "added_at": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
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
    """Retrieve the cached JSON dashboard payload for a specific keyword."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT payload FROM cached_pipeline_results WHERE keyword = ?",
        (keyword.lower().strip(),)
    )
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return json.loads(row['payload'])
    return None

def save_cached_results(keyword: str, payload: Dict[str, Any]):
    """Save/update the JSON dashboard payload for a specific keyword."""
    conn = get_db_connection()
    cursor = conn.cursor()
    payload_str = json.dumps(payload)
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute(
        """
        INSERT OR REPLACE INTO cached_pipeline_results (keyword, payload, updated_at)
        VALUES (?, ?, ?)
        """,
        (keyword.lower().strip(), payload_str, now_str)
    )
    conn.commit()
    conn.close()

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
import hashlib
from difflib import SequenceMatcher
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from typing import List, Dict, Any

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

