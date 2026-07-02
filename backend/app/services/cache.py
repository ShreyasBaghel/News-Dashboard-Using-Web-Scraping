import os
import sqlite3
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from app.config import settings

logger = logging.getLogger(__name__)

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
    """Load the seen articles dictionary from the JSON file."""
    if not os.path.exists(settings.cache_path_resolved):
        return {}
    try:
        with open(settings.cache_path_resolved, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_seen_articles(data: Dict[str, Any]):
    """Save the seen articles dictionary to the JSON file."""
    try:
        # Atomic write: write to tmp file first then rename
        tmp_path = settings.cache_path_resolved + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        if os.path.exists(settings.cache_path_resolved):
            os.remove(settings.cache_path_resolved)
        os.rename(tmp_path, settings.cache_path_resolved)
    except Exception as e:
        logger.error(f"Error saving seen articles to cache: {str(e)}")
        pass

def is_url_seen(url: str) -> bool:
    """
    Check if a URL was seen in the last TTL_DAYS.
    Prunes expired entries first.
    """
    prune_old_urls()
    
    url_hash = _get_url_hash(url)
    data = _load_seen_articles()
    return url_hash in data

def add_seen_url(url: str):
    """Mark a URL as seen in the JSON file."""
    url_hash = _get_url_hash(url)
    data = _load_seen_articles()
    if url_hash not in data:
        data[url_hash] = {
            "url": url.strip(),
            "added_at": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        }
        _save_seen_articles(data)

def prune_old_urls():
    """Delete entries older than settings.ttl_days_resolved."""
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

